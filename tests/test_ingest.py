"""Tests for the ingest boundary.

The point of these is narrow: prove that outcome fields cannot reach a feature row, and that
players who dropped out are not silently deleted from the population.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from optcg_forecast.features.ingest import (
    LEAKY_STANDING_FIELDS,
    IngestError,
    IngestStats,
    assert_no_leakage,
    entrant_rows,
    match_rows,
)

EVT_DATE = date(2026, 3, 14)

# A payload shaped exactly like the real API response.
PAYLOAD = {
    "standings": [
        {
            "name": "Finisher One",
            "country": "CH",
            "player": "finisher1",
            "decklist": {"leader": {"name": "Enel", "set": "OP05", "number": "098"}},
            "deck": {"id": "OP05-098", "name": "Enel"},
            "placing": 1,
            "record": {"wins": 5, "losses": 0, "ties": 0},
            "drop": None,
        },
        {
            "name": "Dropper Two",
            "country": "ES",
            "player": "dropper2",
            "decklist": {"leader": {"name": "Luffy", "set": "OP01", "number": "003"}},
            "deck": {"id": "OP01-003", "name": "Luffy"},
            "placing": None,  # null placing ...
            "record": {"wins": 1, "losses": 4, "ties": 0},
            "drop": 5,  # ... because they dropped
        },
        {
            "name": "No Deck Three",
            "country": "DE",
            "player": "nodeck3",
            "deck": {"id": "OP02-025", "name": "Kid"},
            "placing": 12,
            "record": {"wins": 2, "losses": 3, "ties": 0},
            "drop": None,
        },
    ],
    "pairings": [
        {
            "round": 1,
            "phase": 1,
            "table": 1,
            "winner": "finisher1",
            "player1": "finisher1",
            "player2": "dropper2",
        },
        {
            "round": 2,
            "phase": 1,
            "table": 1,
            "winner": None,
            "player1": "finisher1",
            "player2": "nodeck3",
        },  # unfinished / tie
        {
            "round": 1,
            "phase": 1,
            "table": 9,
            "winner": "nodeck3",
            "player1": "nodeck3",
            "player2": None,
        },  # bye
        {
            "round": 1,
            "phase": 2,
            "table": 1,
            "winner": "finisher1",
            "player1": "finisher1",
            "player2": "nodeck3",
        },  # top cut, not swiss
        {
            "round": 3,
            "phase": 1,
            "table": 2,
            "winner": "ghost",
            "player1": "finisher1",
            "player2": "dropper2",
        },  # winner names neither seat
    ],
}


# --------------------------------------------------------------------------- leakage


def test_outcome_fields_never_reach_an_entrant():
    entrants = list(entrant_rows("evt", EVT_DATE, PAYLOAD))
    for entrant in entrants:
        for leaky in LEAKY_STANDING_FIELDS:
            assert not hasattr(entrant, leaky), f"{leaky} survived onto Entrant"
    assert not (LEAKY_STANDING_FIELDS & set(vars(entrants[0])))


def test_stats_record_which_leaky_fields_were_stripped():
    stats = IngestStats()
    list(entrant_rows("evt", EVT_DATE, PAYLOAD, stats))
    assert stats.leaky_fields_stripped == {"placing", "record", "drop"}


def test_assert_no_leakage_catches_a_bad_row():
    with pytest.raises(IngestError, match="placing"):
        assert_no_leakage([{"player": "x", "placing": 3}])


def test_assert_no_leakage_passes_clean_rows():
    assert_no_leakage([{"player": "x", "leader_id": "OP05-098"}])


# --------------------------------------------------------------------------- population


def test_players_who_dropped_are_kept_not_deleted():
    """The whole point: filtering droppers out would condition on finishing the event."""
    entrants = {e.player: e for e in entrant_rows("evt", EVT_DATE, PAYLOAD)}
    assert "dropper2" in entrants, "dropped players must stay in the population"
    assert entrants["dropper2"].did_drop is True
    assert entrants["finisher1"].did_drop is False


def test_drop_is_derived_from_drop_field_not_from_null_placing():
    """nodeck3 has a placing and no drop; dropper2 has neither placing nor a finish."""
    entrants = {e.player: e for e in entrant_rows("evt", EVT_DATE, PAYLOAD)}
    assert entrants["nodeck3"].did_drop is False
    assert entrants["dropper2"].did_drop is True


def test_entrant_fields_that_are_known_before_play_survive():
    entrants = {e.player: e for e in entrant_rows("evt", EVT_DATE, PAYLOAD)}
    assert entrants["finisher1"].leader_id == "OP05-098"
    assert entrants["finisher1"].country == "CH"
    assert entrants["finisher1"].has_decklist
    assert not entrants["nodeck3"].has_decklist


# --------------------------------------------------------------------------- matches


def test_only_decided_swiss_matches_are_kept():
    stats = IngestStats()
    matches = list(match_rows("evt", EVT_DATE, PAYLOAD, stats))
    assert len(matches) == 1
    assert matches[0].player1 == "finisher1"
    assert matches[0].player1_won is True
    assert stats.skipped_no_winner == 1
    assert stats.skipped_bye == 1
    assert stats.skipped_non_swiss == 1
    assert stats.skipped_winner_not_in_pairing == 1


def test_malformed_payloads_raise():
    with pytest.raises(IngestError):
        list(entrant_rows("e", EVT_DATE, {"pairings": []}))
    with pytest.raises(IngestError):
        list(match_rows("e", EVT_DATE, {"standings": []}))


# --------------------------------------------------------------------------- real-shaped data

# A real event, anonymised: player names hashed, every structural quirk preserved. Committed
# so this runs in CI, which the Repository Guide requires ("unit tests, run in CI"). The
# previous version pointed at an absolute path inside a private repo and was therefore always
# skipped on a runner — a test that never runs is not a test.
FIXTURE = Path(__file__).parent / "fixtures" / "event_sample.json"


def test_boundary_holds_on_a_real_event():
    payload = json.loads(FIXTURE.read_text())
    stats = IngestStats()

    entrants = list(entrant_rows("fixture", EVT_DATE, payload, stats))
    matches = list(match_rows("fixture", EVT_DATE, payload, stats))

    assert entrants and matches
    assert_no_leakage([vars(e) for e in entrants])

    players = {e.player for e in entrants}
    for match in matches:
        # Every seat must resolve to an entrant, or the join silently loses rows.
        assert match.player1 in players
        assert match.player2 in players
        assert match.winner in (match.player1, match.player2)


def test_real_event_contains_droppers_and_they_survive():
    payload = json.loads(FIXTURE.read_text())
    stats = IngestStats()
    entrants = list(entrant_rows("fixture", EVT_DATE, payload, stats))

    assert stats.entrants_dropped_out > 0, "fixture should exercise the dropper path"
    dropped = [e for e in entrants if e.did_drop]
    assert dropped, "droppers must stay in the population, not be filtered out"


def test_real_event_strips_every_outcome_field():
    payload = json.loads(FIXTURE.read_text())
    raw_keys = {k for s in payload["standings"] for k in s}
    assert {"placing", "record", "drop"} <= raw_keys, "fixture must contain the traps"

    stats = IngestStats()
    list(entrant_rows("fixture", EVT_DATE, payload, stats))
    assert stats.leaky_fields_stripped == {"placing", "record", "drop"}


def test_bracket_rows_are_excluded_even_when_labelled_phase_one():
    """Two real events are single-elimination brackets with every row marked phase 1.

    The `match` field ("T32-16") is the reliable marker, so a row carrying one is top cut
    regardless of its phase.
    """
    payload = {
        "standings": [{"player": "a"}, {"player": "b"}],
        "pairings": [
            {"round": 1, "phase": 1, "winner": "a", "player1": "a", "player2": "b"},
            {
                "round": 1,
                "phase": 1,
                "winner": "a",
                "player1": "a",
                "player2": "b",
                "match": "T32-16",
            },
        ],
    }
    stats = IngestStats()
    matches = list(match_rows("e", EVT_DATE, payload, stats))
    assert len(matches) == 1, "the bracket row must be excluded"
    assert stats.skipped_non_swiss == 1


def test_integer_zero_winner_is_treated_as_no_winner():
    """The API uses 0 on 30 real rows to mean no winner recorded."""
    payload = {
        "standings": [{"player": "a"}, {"player": "b"}],
        "pairings": [{"round": 1, "phase": 1, "winner": 0, "player1": "a", "player2": "b"}],
    }
    stats = IngestStats()
    assert list(match_rows("e", EVT_DATE, payload, stats)) == []
    assert stats.skipped_no_winner == 1
