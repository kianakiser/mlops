"""Tests for the ingest boundary.

The point of these is narrow: prove that outcome fields cannot reach a feature row, and that
players who dropped out are not silently deleted from the population.
"""

from __future__ import annotations

import json
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
    entrants = list(entrant_rows("evt", PAYLOAD))
    for entrant in entrants:
        for leaky in LEAKY_STANDING_FIELDS:
            assert not hasattr(entrant, leaky), f"{leaky} survived onto Entrant"
    assert not (LEAKY_STANDING_FIELDS & set(vars(entrants[0])))


def test_stats_record_which_leaky_fields_were_stripped():
    stats = IngestStats()
    list(entrant_rows("evt", PAYLOAD, stats))
    assert stats.leaky_fields_stripped == {"placing", "record", "drop"}


def test_assert_no_leakage_catches_a_bad_row():
    with pytest.raises(IngestError, match="placing"):
        assert_no_leakage([{"player": "x", "placing": 3}])


def test_assert_no_leakage_passes_clean_rows():
    assert_no_leakage([{"player": "x", "leader_id": "OP05-098"}])


# --------------------------------------------------------------------------- population


def test_players_who_dropped_are_kept_not_deleted():
    """The whole point: filtering droppers out would condition on finishing the event."""
    entrants = {e.player: e for e in entrant_rows("evt", PAYLOAD)}
    assert "dropper2" in entrants, "dropped players must stay in the population"
    assert entrants["dropper2"].did_drop is True
    assert entrants["finisher1"].did_drop is False


def test_drop_is_derived_from_drop_field_not_from_null_placing():
    """nodeck3 has a placing and no drop; dropper2 has neither placing nor a finish."""
    entrants = {e.player: e for e in entrant_rows("evt", PAYLOAD)}
    assert entrants["nodeck3"].did_drop is False
    assert entrants["dropper2"].did_drop is True


def test_entrant_fields_that_are_known_before_play_survive():
    entrants = {e.player: e for e in entrant_rows("evt", PAYLOAD)}
    assert entrants["finisher1"].leader_id == "OP05-098"
    assert entrants["finisher1"].country == "CH"
    assert entrants["finisher1"].has_decklist
    assert not entrants["nodeck3"].has_decklist


def test_leader_id_falls_back_to_the_decklist_leader_block():
    payload = {
        "standings": [{"player": "p", "decklist": {"leader": {"set": "OP07", "number": "001"}}}],
        "pairings": [],
    }
    (entrant,) = entrant_rows("e", payload)
    assert entrant.leader_id == "OP07-001"


# --------------------------------------------------------------------------- matches


def test_only_decided_swiss_matches_are_kept():
    stats = IngestStats()
    matches = list(match_rows("evt", PAYLOAD, stats))
    assert len(matches) == 1
    assert matches[0].player1 == "finisher1"
    assert matches[0].player1_won is True
    assert stats.skipped_no_winner == 1
    assert stats.skipped_bye == 1
    assert stats.skipped_non_swiss == 1
    assert stats.skipped_winner_not_in_pairing == 1


def test_malformed_payloads_raise():
    with pytest.raises(IngestError):
        list(entrant_rows("e", {"pairings": []}))
    with pytest.raises(IngestError):
        list(match_rows("e", {"standings": []}))


# --------------------------------------------------------------------------- real data

REAL_CACHE = Path("/Users/kianakiser/Desktop/Kiana Jin/Apps/gumgum/.cache/pairings")


@pytest.mark.skipif(not REAL_CACHE.is_dir(), reason="local gumgum cache not present")
def test_against_real_cached_payloads():
    """Run the boundary over real events and assert the invariants hold on live-shaped data."""
    files = sorted(REAL_CACHE.glob("*.json"))[:25]
    assert files, "expected cached event payloads"

    stats = IngestStats()
    total_matches = 0
    for path in files:
        payload = json.loads(path.read_text())
        entrants = list(entrant_rows(path.stem, payload, stats))
        matches = list(match_rows(path.stem, payload, stats))
        total_matches += len(matches)

        players = {e.player for e in entrants}
        for match in matches:
            # Every seat must resolve to an entrant, or the join silently loses rows.
            assert match.player1 in players
            assert match.player2 in players
            assert match.winner in (match.player1, match.player2)

        assert_no_leakage([vars(e) for e in entrants])

    assert total_matches > 0
    assert stats.entrants_dropped_out > 0, "real data should contain players who dropped"
    # Regression guard on the trap: dropping them would delete a large share of the population.
    drop_share = stats.entrants_dropped_out / stats.entrants
    assert 0.1 < drop_share < 0.8, f"unexpected dropper share {drop_share:.2%}"
