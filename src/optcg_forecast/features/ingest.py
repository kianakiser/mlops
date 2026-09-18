"""The ingest boundary: raw Limitless payloads in, leakage-free rows out.

This module exists to make one class of mistake impossible rather than merely discouraged.

The tournament API returns each event as ``{"standings": [...], "pairings": [...]}``. A standings
row carries the submitted decklist (known *before* play, so a legitimate feature) sitting right
next to ``placing``, ``record`` and ``drop`` — all of which are outcomes *of the very event being
predicted*. Nothing stops a join from carrying them into a feature row, and a model trained that
way scores beautifully and is worthless.

So the outcome fields are dropped **here**, at the boundary, before anything downstream ever sees
them. Filtering them out at training time would leave the loaded footgun in place for every future
caller.

There is a second, subtler trap. ``placing`` is null for players who dropped out mid-event, and
dropping out is itself an outcome — droppers win far fewer matches than finishers. The obvious
``WHERE placing IS NOT NULL`` therefore conditions the population on *finishing*, silently deleting
most of the true negatives. :func:`entrant_rows` keeps dropped players and records the fact in
``did_drop``, so the population stays the one you actually predict over.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# Outcomes of the event being predicted. Never features.
LEAKY_STANDING_FIELDS = frozenset({"placing", "record", "drop"})

# Phase 1 is swiss; later phases are top cut, where pairing is by standing rather
# than by the swiss algorithm and the population is already outcome-selected.
SWISS_PHASE = 1


class IngestError(ValueError):
    """A payload did not have the shape this module requires."""


@dataclass(frozen=True)
class Entrant:
    """One player's entry in one event, with every post-hoc field removed.

    ``did_drop`` is derived from the outcome fields before they are discarded. It is retained
    deliberately: it must never be used as a *feature* (it is an outcome), but it is needed to
    reason about the population and to avoid conditioning on finishing.
    """

    event_id: str
    player: str
    leader_id: str | None
    country: str | None
    decklist: dict[str, Any] | None
    did_drop: bool

    @property
    def has_decklist(self) -> bool:
        return bool(self.decklist)


@dataclass(frozen=True)
class Match:
    """One decided swiss pairing. ``winner`` is the label."""

    event_id: str
    round: int
    table: int
    player1: str
    player2: str
    winner: str

    @property
    def player1_won(self) -> bool:
        return self.winner == self.player1


@dataclass
class IngestStats:
    """What was kept and what was discarded, and why."""

    entrants: int = 0
    entrants_with_decklist: int = 0
    entrants_dropped_out: int = 0
    pairings_seen: int = 0
    matches_kept: int = 0
    skipped_non_swiss: int = 0
    skipped_no_winner: int = 0
    skipped_bye: int = 0
    skipped_winner_not_in_pairing: int = 0
    leaky_fields_stripped: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        out = {k: v for k, v in vars(self).items() if k != "leaky_fields_stripped"}
        out["leaky_fields_stripped"] = sorted(self.leaky_fields_stripped)
        return out


def _leader_id(standing: dict[str, Any]) -> str | None:
    deck = standing.get("deck")
    if isinstance(deck, dict) and deck.get("id"):
        return str(deck["id"])
    # Fall back to the decklist's own leader block when `deck` is absent.
    decklist = standing.get("decklist")
    if isinstance(decklist, dict):
        leader = decklist.get("leader")
        if isinstance(leader, dict) and leader.get("set") and leader.get("number"):
            return f"{leader['set']}-{leader['number']}"
    return None


def entrant_rows(
    event_id: str, payload: dict[str, Any], stats: IngestStats | None = None
) -> Iterator[Entrant]:
    """Yield one :class:`Entrant` per standings row, with outcome fields stripped.

    Dropped players are **kept**. Excluding them would condition the population on finishing
    the event, which is an outcome.
    """
    stats = stats if stats is not None else IngestStats()
    standings = payload.get("standings")
    if not isinstance(standings, list):
        raise IngestError(f"event {event_id}: 'standings' missing or not a list")

    for standing in standings:
        if not isinstance(standing, dict):
            continue
        player = standing.get("player")
        if not player:
            # Without the username there is no join key to the pairings.
            continue

        stats.leaky_fields_stripped |= LEAKY_STANDING_FIELDS & standing.keys()
        did_drop = standing.get("drop") is not None

        stats.entrants += 1
        if did_drop:
            stats.entrants_dropped_out += 1
        decklist = standing.get("decklist")
        if decklist:
            stats.entrants_with_decklist += 1

        yield Entrant(
            event_id=event_id,
            player=str(player),
            leader_id=_leader_id(standing),
            country=standing.get("country"),
            decklist=decklist if isinstance(decklist, dict) else None,
            did_drop=did_drop,
        )


def match_rows(
    event_id: str, payload: dict[str, Any], stats: IngestStats | None = None
) -> Iterator[Match]:
    """Yield decided swiss matches. Byes, ties and top-cut pairings are excluded."""
    stats = stats if stats is not None else IngestStats()
    pairings = payload.get("pairings")
    if not isinstance(pairings, list):
        raise IngestError(f"event {event_id}: 'pairings' missing or not a list")

    for pairing in pairings:
        if not isinstance(pairing, dict):
            continue
        stats.pairings_seen += 1

        if pairing.get("phase") != SWISS_PHASE:
            stats.skipped_non_swiss += 1
            continue

        p1, p2, winner = pairing.get("player1"), pairing.get("player2"), pairing.get("winner")
        if not p1 or not p2:
            stats.skipped_bye += 1  # a bye has only one seat
            continue
        if not winner:
            stats.skipped_no_winner += 1  # unfinished, or a tie
            continue
        if winner not in (p1, p2):
            # Defensive: a winner naming neither seat means the row cannot be trusted.
            stats.skipped_winner_not_in_pairing += 1
            continue

        stats.matches_kept += 1
        yield Match(
            event_id=event_id,
            round=int(pairing.get("round", 0)),
            table=int(pairing.get("table", 0)),
            player1=str(p1),
            player2=str(p2),
            winner=str(winner),
        )


def assert_no_leakage(rows: list[dict[str, Any]]) -> None:
    """Fail loudly if any outcome field survived into feature rows.

    Call this at the end of the feature pipeline, before writing to the feature store. It is
    cheap, and it turns a silent modelling disaster into a failed pipeline run.
    """
    offenders: dict[str, int] = {}
    for row in rows:
        for key in LEAKY_STANDING_FIELDS & row.keys():
            offenders[key] = offenders.get(key, 0) + 1
    if offenders:
        raise IngestError(
            "post-hoc outcome fields reached the feature rows: "
            + ", ".join(f"{k} in {n} row(s)" for k, n in sorted(offenders.items()))
        )
