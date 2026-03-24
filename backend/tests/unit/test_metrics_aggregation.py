"""
Unit tests for metrics_service.py aggregation logic.

Tests the get_player_metrics() function which aggregates raw
participant_stats across multiple matches into summary KPIs.
These tests mock the database session to avoid any DB dependency.
"""

import pytest
from unittest.mock import MagicMock
from app.services.metrics_service import get_player_metrics


def _make_mock_stats(kills, deaths, assists, cs, gold, vision, duration_s, win):
    """Build a (ParticipantStats, Match) mock tuple."""
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


@pytest.mark.unit
def test_no_matches_returns_none():
    """No stored matches should return None (not crash)."""
    session = MagicMock()
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = []

    result = get_player_metrics(session, "fake-puuid")
    assert result is None


@pytest.mark.unit
def test_single_match_metrics():
    """Single match: verify each metric is computed correctly."""
    # 30 minute game, 5/3/7, 170 cs, 12000 gold, 30 vision, win
    row = _make_mock_stats(
        kills=5, deaths=3, assists=7,
        cs=170, gold=12000, vision=30,
        duration_s=1800, win=True
    )
    session = MagicMock()
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [row]

    result = get_player_metrics(session, "fake-puuid")

    assert result is not None
    assert result["matches"] == 1
    assert result["win_rate"] == pytest.approx(1.0)
    # KDA = (5+7)/3 = 4.0
    assert result["kda"] == pytest.approx(4.0, rel=0.02)
    # CS/min = 170/30 ≈ 5.67
    assert result["cs_per_min"] == pytest.approx(5.67, rel=0.02)
    # Gold/min = 12000/30 = 400.0
    assert result["gold_per_min"] == pytest.approx(400.0, rel=0.02)
    # Vision/min = 30/30 = 1.0
    assert result["vision_per_min"] == pytest.approx(1.0, rel=0.02)


@pytest.mark.unit
def test_win_rate_calculation():
    """Win rate = wins / total matches across multiple games."""
    rows = [
        _make_mock_stats(5, 2, 3, 150, 11000, 25, 1800, True),
        _make_mock_stats(3, 5, 8, 140, 9000,  20, 1800, False),
        _make_mock_stats(7, 1, 4, 180, 13000, 35, 1800, True),
        _make_mock_stats(2, 6, 10, 130, 8500,  40, 1800, False),
    ]
    session = MagicMock()
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = rows

    result = get_player_metrics(session, "fake-puuid")

    assert result["matches"] == 4
    assert result["win_rate"] == pytest.approx(0.5, rel=0.01)


@pytest.mark.unit
def test_zero_deaths_across_all_games():
    """If total deaths = 0, KDA should not raise ZeroDivisionError."""
    row = _make_mock_stats(
        kills=10, deaths=0, assists=5,
        cs=200, gold=15000, vision=40,
        duration_s=1800, win=True
    )
    session = MagicMock()
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [row]

    result = get_player_metrics(session, "fake-puuid")
    assert result is not None
    assert result["kda"] > 0


@pytest.mark.unit
def test_zero_duration_game():
    """Game with duration=0 should not crash; per-minute stats default to 0."""
    row = _make_mock_stats(
        kills=5, deaths=3, assists=7,
        cs=170, gold=12000, vision=30,
        duration_s=0, win=True
    )
    session = MagicMock()
    session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [row]

    result = get_player_metrics(session, "fake-puuid")
    assert result is not None
    assert result["cs_per_min"] == 0.0
    assert result["gold_per_min"] == 0.0
    assert result["vision_per_min"] == 0.0
