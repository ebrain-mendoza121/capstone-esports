"""
Unit tests for metrics_service.py aggregation logic.

Tests two paths in get_player_metrics():
  1. Primary path  — derived_metrics table has rows → SQL aggregate query used.
  2. Fallback path — no derived_metrics rows → raw participant_stats aggregation.

All tests mock the database session to avoid any DB dependency.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.services.metrics_service import get_player_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_derived_row(matches, win_rate, kda, cs_per_min, gold_per_min,
                      vision_per_min, kill_participation, damage_share):
    """Build a mapping-like mock for the SQL aggregate row (primary path)."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "matches":            matches,
        "win_rate":           win_rate,
        "kda":                kda,
        "cs_per_min":         cs_per_min,
        "gold_per_min":       gold_per_min,
        "vision_per_min":     vision_per_min,
        "kill_participation": kill_participation,
        "damage_share":       damage_share,
    }[key]
    row.__bool__ = lambda self: True
    return row


def _make_raw_stats(kills, deaths, assists, cs, gold, vision, duration_s, win):
    """Build a (ParticipantStats, Match) mock tuple (fallback path)."""
    ps = MagicMock()
    ps.kills = kills
    ps.deaths = deaths
    ps.assists = assists
    ps.cs = cs
    ps.gold_earned = gold
    ps.vision_score = vision
    ps.win = win
    match = MagicMock()
    match.game_duration = duration_s
    return (ps, match)


def _session_with_derived(row):
    """Return a session mock whose .execute().mappings().first() returns row."""
    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = row
    return session


def _session_no_derived_with_raw(raw_rows):
    """Return a session mock for the fallback path:
    - .execute() returns a row with matches=0 (triggers fallback)
    - .query()...all() returns raw_rows
    """
    empty_row = MagicMock()
    empty_row.__getitem__ = lambda self, key: 0 if key == "matches" else None
    empty_row.__bool__ = lambda self: False  # falsy → fallback

    session = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = empty_row
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = raw_rows
    return session


# ---------------------------------------------------------------------------
# Primary path: derived_metrics
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_primary_path_returns_all_fields():
    """Primary path returns all 8 KPI fields including kill_participation and damage_share."""
    row = _make_derived_row(
        matches=10, win_rate=0.6, kda=3.5,
        cs_per_min=7.2, gold_per_min=420.0,
        vision_per_min=1.8, kill_participation=0.72, damage_share=0.25,
    )
    result = get_player_metrics(_session_with_derived(row), "test-puuid")

    assert result is not None
    assert result["matches"]            == 10
    assert result["win_rate"]           == pytest.approx(0.6,  rel=0.01)
    assert result["kda"]                == pytest.approx(3.5,  rel=0.01)
    assert result["cs_per_min"]         == pytest.approx(7.2,  rel=0.01)
    assert result["gold_per_min"]       == pytest.approx(420.0, rel=0.01)
    assert result["vision_per_min"]     == pytest.approx(1.8,  rel=0.01)
    assert result["kill_participation"] == pytest.approx(0.72, rel=0.01)
    assert result["damage_share"]       == pytest.approx(0.25, rel=0.01)


@pytest.mark.unit
def test_primary_path_none_fields_default_to_zero():
    """NULL SQL aggregates (e.g. no data) should default to 0.0, not raise."""
    row = _make_derived_row(
        matches=5, win_rate=None, kda=None,
        cs_per_min=None, gold_per_min=None,
        vision_per_min=None, kill_participation=None, damage_share=None,
    )
    result = get_player_metrics(_session_with_derived(row), "test-puuid")
    assert result is not None
    assert result["kda"] == 0.0
    assert result["win_rate"] == 0.0


# ---------------------------------------------------------------------------
# Fallback path: raw participant_stats
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_fallback_no_matches_returns_none():
    """Fallback path with no raw rows should return None (not crash)."""
    session = _session_no_derived_with_raw([])
    result = get_player_metrics(session, "fake-puuid")
    assert result is None


@pytest.mark.unit
def test_fallback_single_match_metrics():
    """Fallback path: 30-minute game, 5/3/7, verify per-minute stats."""
    row = _make_raw_stats(
        kills=5, deaths=3, assists=7,
        cs=170, gold=12000, vision=30,
        duration_s=1800, win=True,
    )
    session = _session_no_derived_with_raw([row])
    result = get_player_metrics(session, "fake-puuid")

    assert result is not None
    assert result["matches"]    == 1
    assert result["win_rate"]   == pytest.approx(1.0)
    assert result["kda"]        == pytest.approx(4.0,   rel=0.02)   # (5+7)/3
    assert result["cs_per_min"] == pytest.approx(5.67,  rel=0.02)   # 170/30
    assert result["gold_per_min"] == pytest.approx(400.0, rel=0.02)  # 12000/30
    assert result["vision_per_min"] == pytest.approx(1.0, rel=0.02)  # 30/30
    # kill_participation and damage_share are unavailable from raw stats
    assert result["kill_participation"] == 0.0
    assert result["damage_share"]       == 0.0


@pytest.mark.unit
def test_fallback_win_rate_calculation():
    """Fallback path: win rate = wins / total matches."""
    rows = [
        _make_raw_stats(5, 2, 3, 150, 11000, 25, 1800, True),
        _make_raw_stats(3, 5, 8, 140, 9000,  20, 1800, False),
        _make_raw_stats(7, 1, 4, 180, 13000, 35, 1800, True),
        _make_raw_stats(2, 6, 10, 130, 8500,  40, 1800, False),
    ]
    session = _session_no_derived_with_raw(rows)
    result = get_player_metrics(session, "fake-puuid")

    assert result["matches"]  == 4
    assert result["win_rate"] == pytest.approx(0.5, rel=0.01)


@pytest.mark.unit
def test_fallback_zero_deaths_no_zerodivision():
    """Fallback path: total deaths = 0 should not raise ZeroDivisionError."""
    row = _make_raw_stats(
        kills=10, deaths=0, assists=5,
        cs=200, gold=15000, vision=40,
        duration_s=1800, win=True,
    )
    result = get_player_metrics(_session_no_derived_with_raw([row]), "fake-puuid")
    assert result is not None
    assert result["kda"] > 0


@pytest.mark.unit
def test_fallback_zero_duration_game():
    """Fallback path: duration=0 should not crash; per-minute stats default to 0."""
    row = _make_raw_stats(
        kills=5, deaths=3, assists=7,
        cs=170, gold=12000, vision=30,
        duration_s=0, win=True,
    )
    result = get_player_metrics(_session_no_derived_with_raw([row]), "fake-puuid")
    assert result is not None
    assert result["cs_per_min"]    == 0.0
    assert result["gold_per_min"]  == 0.0
    assert result["vision_per_min"] == 0.0
