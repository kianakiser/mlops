"""Tests for the Limitless client.

These do not touch the network. What matters here is that the politeness guarantees hold —
the rate budget, the self-identifying User-Agent, and the immutable cache — because those are
the things that, if wrong, get the project blocked mid-semester rather than merely failing a test.
"""

from __future__ import annotations

import json

from optcg_forecast.features.client import (
    BASE_URL,
    CONTACT_URL,
    RATE_LIMIT,
    RATE_WINDOW_S,
    USER_AGENT,
    LimitlessClient,
    TokenBucket,
)


def test_user_agent_identifies_the_project_and_a_contact():
    """The existing Node scraper spoofs desktop Chrome. This must not."""
    assert "Mozilla" not in USER_AGENT
    assert "Chrome" not in USER_AGENT
    assert "optcg-match-forecast" in USER_AGENT
    assert CONTACT_URL in USER_AGENT


def test_base_url_is_the_api_not_the_website():
    assert BASE_URL == "https://play.limitlesstcg.com/api"


def test_bucket_stays_inside_the_published_budget(monkeypatch):
    """50-in-5min is the advertised limit; the bucket must sit under it, not on it."""
    bucket = TokenBucket()
    assert bucket.limit < RATE_LIMIT, "no headroom under the published limit"
    assert bucket.window_s == RATE_WINDOW_S

    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        # Simulate the clock advancing past the window so the loop can make progress.
        bucket._hits.clear()

    monkeypatch.setattr("optcg_forecast.features.client.time.sleep", fake_sleep)

    for _ in range(bucket.limit):
        bucket.take()
    assert slept == [], "should not sleep before the budget is spent"

    bucket.take()
    assert slept, "must sleep once the budget is spent rather than overrun it"
    assert slept[0] > 0


def test_finished_events_are_cached_and_never_refetched(tmp_path):
    """Events are immutable once finished, so a second read must not hit the network."""
    payload = {"standings": [{"player": "a"}], "pairings": [{"round": 1}]}
    (tmp_path / "evt1.json").write_text(json.dumps(payload))

    client = LimitlessClient(cache_dir=tmp_path)
    got = client.event_payload("evt1")

    assert got == payload
    assert client.requests_made == 0, "a cached event must not cost a request"
    assert client.cache_hits == 1


def test_cache_miss_writes_through(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_get(self, path, params=None):
        calls.append(path)
        return [{"player": "a"}] if "standings" in path else [{"round": 1}]

    monkeypatch.setattr(LimitlessClient, "_get", fake_get)
    client = LimitlessClient(cache_dir=tmp_path)

    first = client.event_payload("evt2")
    assert len(calls) == 2  # standings + pairings
    assert (tmp_path / "evt2.json").is_file()

    second = client.event_payload("evt2")
    assert second == first
    assert len(calls) == 2, "second read must come from cache"
