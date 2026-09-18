"""A polite client for the Limitless tournament API.

Design notes, because "polite" here is a requirement rather than a courtesy:

The API is keyless and community-run, and it advertises its budget in-band as a ``ratelimit``
response header of the form ``50-in-5min``, partitioned per source IP. This client holds to that
with a token bucket rather than discovering the limit by being throttled, honours ``Retry-After``
on 429, and identifies itself with a real User-Agent and a contact URL. The existing Node scraper
sends a spoofed desktop Chrome string; that is not something to carry forward into a project whose
write-up argues about being a good guest on someone else's free service.

Finished tournaments are immutable, so a fetched event is cached on disk and never re-fetched.
That is what makes a full backfill affordable inside the rate budget and makes the pipeline
idempotent: a skipped scheduled run costs nothing, because the next one refetches only what is new.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://play.limitlesstcg.com/api"

# Published budget, advertised in the `ratelimit` response header as "50-in-5min".
RATE_LIMIT = 50
RATE_WINDOW_S = 5 * 60
# Deliberate headroom: the budget is per source IP and a CI runner may be shared.
RATE_SAFETY = 5

CONTACT_URL = "https://github.com/kianakiser/optcg-match-forecast"
USER_AGENT = f"optcg-match-forecast/0.1 (HSLU MLOps student project; +{CONTACT_URL})"


class ApiError(RuntimeError):
    """The API could not be reached, or answered with an error."""


@dataclass
class TokenBucket:
    """Holds to `limit` requests per `window_s`, sleeping rather than overrunning."""

    limit: int = RATE_LIMIT - RATE_SAFETY
    window_s: float = RATE_WINDOW_S
    _hits: deque[float] = field(default_factory=deque)

    def take(self) -> None:
        """Block until a request may be made, then record it.

        A loop rather than recursion: if the clock does not advance as expected, recursing
        would grow the stack until it broke, which is a poor failure mode for a throttle.
        """
        while True:
            now = time.monotonic()
            while self._hits and now - self._hits[0] > self.window_s:
                self._hits.popleft()
            if len(self._hits) < self.limit:
                self._hits.append(now)
                return
            sleep_for = self.window_s - (now - self._hits[0]) + 0.25
            time.sleep(max(0.05, sleep_for))


@dataclass
class LimitlessClient:
    """Fetches tournaments, standings and pairings, with an on-disk immutable cache."""

    cache_dir: Path | None = None
    api_key: str | None = None
    timeout_s: float = 30.0
    bucket: TokenBucket = field(default_factory=TokenBucket)
    requests_made: int = 0
    cache_hits: int = 0

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{BASE_URL}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            # Optional: the docs issue keys for higher limits. The client works without one.
            headers["X-Access-Key"] = self.api_key

        for attempt in range(3):
            self.bucket.take()
            self.requests_made += 1
            try:
                with urlopen(Request(url, headers=headers), timeout=self.timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429:
                    # Respect the server's own instruction rather than guessing a backoff.
                    retry_after = float(exc.headers.get("Retry-After", 30))
                    time.sleep(retry_after + 1)
                    continue
                if exc.code >= 500 and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise ApiError(f"{url} -> HTTP {exc.code}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise ApiError(f"{url} unreachable: {exc}") from exc
        raise ApiError(f"{url}: giving up after retries")

    # ---------------------------------------------------------------- endpoints

    def tournaments(self, *, game: str = "OP", limit: int = 50, page: int = 1) -> list[dict]:
        """The tournament index. This is the ONLY place an event's date comes from."""
        data = self._get("/tournaments", {"game": game, "limit": limit, "page": page})
        if not isinstance(data, list):
            raise ApiError("/tournaments did not return a list")
        return data

    def event_payload(self, event_id: str) -> dict[str, Any]:
        """Standings + pairings for one event, cached on disk because events are immutable."""
        if self.cache_dir:
            cached = self.cache_dir / f"{event_id}.json"
            if cached.is_file():
                self.cache_hits += 1
                return json.loads(cached.read_text())

        payload = {
            "standings": self._get(f"/tournaments/{event_id}/standings"),
            "pairings": self._get(f"/tournaments/{event_id}/pairings"),
        }

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{event_id}.json").write_text(json.dumps(payload))
        return payload
