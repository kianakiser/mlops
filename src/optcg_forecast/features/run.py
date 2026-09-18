"""Feature pipeline, ingest stage: fetch new tournaments and turn them into clean rows.

This is the entry point the scheduled GitHub Actions workflow calls. It is deliberately the
smallest thing that genuinely works end to end, because a scheduled job that fails is worse
than no scheduled job: it accumulates red runs on a public repository that reviewers clone.

What it does today: ask the tournament index what exists, work out which events are new,
fetch each one once, push it through the ingest boundary, and write the resulting rows to a
local landing directory. What it does not do yet: write to the feature store (MS2) or compute
model features. Those arrive in later milestones and plug in at the marked seam.

Two properties matter more than the feature set and are worth keeping:

*Idempotent.* Events are immutable once finished and are fetched by id, so running twice
changes nothing and a skipped run is repaired by the next one. This is why the schedule can be
best-effort without the pipeline needing to care.

*No credentials.* The endpoints used here are keyless, so a scheduled run needs no secrets at
all. Adding a required credential would make the job fail for no reason.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from optcg_forecast.common.config import load_settings, redacted
from optcg_forecast.features.client import ApiError, LimitlessClient
from optcg_forecast.features.ingest import (
    IngestStats,
    assert_no_leakage,
    entrant_rows,
    match_rows,
)

log = logging.getLogger("optcg_forecast.features.run")

# Events below this are a few friends in a shop rather than a read on the format.
# Lowering it is the cheapest way to reduce single-organiser concentration - see
# notes/domain_analysis.md - so it is a flag rather than a constant.
DEFAULT_MIN_PLAYERS = 32


def _event_date(event: dict[str, Any]) -> date | None:
    raw = event.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def discover(
    client: LimitlessClient, *, min_players: int, limit: int, already_have: set[str]
) -> list[dict[str, Any]]:
    """Return in-scope events from the index that have not been ingested yet."""
    index = client.tournaments(limit=limit)
    fresh = []
    for event in index:
        if not event.get("id") or event["id"] in already_have:
            continue
        if (event.get("players") or 0) < min_players:
            continue
        if _event_date(event) is None:
            # No date means no out-of-time split, so the row is unusable. Skip loudly
            # rather than silently ingesting something that can never be trained on.
            log.warning("skipping %s: no usable date", event.get("id"))
            continue
        fresh.append(event)
    return fresh


def ingest_event(
    client: LimitlessClient, event: dict[str, Any], stats: IngestStats
) -> dict[str, Any]:
    """Fetch one event and push it through the ingest boundary."""
    event_id = str(event["id"])
    event_date = _event_date(event)
    assert event_date is not None  # discover() guarantees this
    payload = client.event_payload(event_id)

    entrants = list(entrant_rows(event_id, event_date, payload, stats))
    matches = list(match_rows(event_id, event_date, payload, stats))

    # Cheap and worth it: prove no outcome field survived before anything downstream sees it.
    assert_no_leakage([vars(e) for e in entrants])

    return {
        "event_id": event_id,
        "event_date": event_date.isoformat(),
        "organizer_id": event.get("organizerId"),
        "name": event.get("name"),
        "entrants": [vars(e) for e in entrants],
        "matches": [vars(m) for m in matches],
    }


def write_landing(out_dir: Path, record: dict[str, Any]) -> Path:
    """Write one event's clean rows to the landing zone, partitioned by date.

    Local for now; this is the seam where GCS and then the feature store take over.
    """
    target = out_dir / record["event_date"][:7] / f"{record['event_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, default=str))
    return target


def already_ingested(out_dir: Path) -> set[str]:
    return {p.stem for p in out_dir.rglob("*.json")}


def run(*, min_players: int, limit: int, out_dir: Path, dry_run: bool) -> int:
    settings = load_settings()
    log.info("settings: %s", redacted(settings))

    client = LimitlessClient(
        cache_dir=out_dir.parent / "raw_cache",
        api_key=settings.source_api_key or None,
    )
    have = already_ingested(out_dir)
    log.info("%d event(s) already in the landing zone", len(have))

    try:
        fresh = discover(client, min_players=min_players, limit=limit, already_have=have)
    except ApiError as exc:
        log.error("could not reach the tournament index: %s", exc)
        return 1

    if not fresh:
        # The normal case on most days: the source is bursty and roughly 40% of days add
        # nothing. Nothing to do is a success, not a failure.
        log.info("no new in-scope events; nothing to do")
        return 0

    log.info("%d new in-scope event(s) to ingest", len(fresh))
    stats = IngestStats()
    written = 0
    for event in fresh:
        try:
            record = ingest_event(client, event, stats)
        except ApiError as exc:
            # One bad event must not lose the whole run; the next run retries it.
            log.error("skipping %s: %s", event.get("id"), exc)
            continue
        if dry_run:
            log.info("would write %s (%d matches)", record["event_id"], len(record["matches"]))
        else:
            path = write_landing(out_dir, record)
            log.info("wrote %s (%d matches)", path, len(record["matches"]))
        written += 1

    log.info("ingested %d event(s); %s", written, stats.as_dict())
    log.info("api requests: %d, cache hits: %d", client.requests_made, client.cache_hits)
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-players", type=int, default=DEFAULT_MIN_PLAYERS)
    parser.add_argument("--limit", type=int, default=100, help="index page size to scan")
    parser.add_argument("--out-dir", type=Path, default=Path("data/landing"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    return run(
        min_players=args.min_players,
        limit=args.limit,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
