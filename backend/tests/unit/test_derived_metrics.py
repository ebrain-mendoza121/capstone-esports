"""
Unit tests for derived_metrics_calculator.py

Tests the six performance metric computations:
  KDA, CS/min, Gold/min, Kill Participation, Damage Share, Vision/min

All tests are pure — no database, no HTTP, no Riot API.
Validation target: error margin < 2% vs manual verification (capstone requirement).
"""

import pytest
from app.services.derived_metrics_calculator import (
    compute_derived_metrics,
    extract_team_participants,
    normalize_game_duration,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_participant(**overrides) -> dict:
    """Return a minimal valid participant dict with sensible defaults."""
    base = {
        "kills": 5,
        "deaths": 3,
        "assists": 7,
        "goldEarned": 12000,
        "totalDamageDealtToChampions": 20000,
        "visionScore": 30,
        "totalMinionsKilled": 150,
        "neutralMinionsKilled": 20,
        "teamId": 100,
    }
    base.update(overrides)
    return base


def _make_team(participants: list[dict] | None = None) -> list[dict]:
    """Return a 5-player team list."""
    if participants is not None:
        return participants
    return [_make_participant(kills=5) for _ in range(5)]


# ---------------------------------------------------------------------------
# Test 1 — Basic metric computation (30-minute game)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_basic_metrics_30min_game():
    """Verify all six metrics compute correctly for a normal 30-minute game."""
    p = _make_participant(
        kills=5, deaths=3, assists=7,
        goldEarned=12000,
        totalDamageDealtToChampions=20000,
        visionScore=30,
        totalMinionsKilled=150,
        neutralMinionsKilled=20,
    )
    team = _make_team([_make_participant(kills=5) for _ in range(5)])
    duration = 1800  # 30 minutes in seconds

    result = compute_derived_metrics(p, team, duration)

    # KDA = (5 + 7) / 3 = 4.0
    assert result["kda"] == pytest.approx(4.0, rel=0.02), "KDA incorrect"

    # CS/min = 170 / 30 = 5.67
    assert result["cs_per_min"] == pytest.approx(5.67, rel=0.02), "CS/min incorrect"

    # Gold/min = 12000 / 30 = 400.0
    assert result["gold_per_min"] == pytest.approx(400.0, rel=0.02), "Gold/min incorrect"

    # Kill participation = (5 + 7) / 25 = 0.48
    assert result["kill_participation"] == pytest.approx(0.48, rel=0.02), "Kill participation incorrect"

    # Vision/min = 30 / 30 = 1.0
    assert result["vision_per_min"] == pytest.approx(1.0, rel=0.02), "Vision/min incorrect"

    # Damage share = 20000 / (20000 * 5) = 0.20
    assert result["damage_share"] == pytest.approx(0.20, rel=0.02), "Damage share incorrect"


# ---------------------------------------------------------------------------
# Test 2 — Zero deaths (perfect KDA)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zero_deaths_kda():
    """KDA denominator is clamped to 1 when deaths = 0 (no division by zero)."""
    p = _make_participant(kills=10, deaths=0, assists=5)
    team = _make_team()
    result = compute_derived_metrics(p, team, 1800)

    # KDA = (10 + 5) / max(0, 1) = 15.0
    assert result["kda"] == pytest.approx(15.0, rel=0.02)
    assert result["kda"] > 0, "KDA must be positive when deaths=0"


# ---------------------------------------------------------------------------
# Test 3 — Zero game duration
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zero_game_duration():
    """All per-minute metrics return 0.0 when game duration is 0 (no division by zero)."""
    p = _make_participant()
    team = _make_team()
    result = compute_derived_metrics(p, team, game_duration_seconds=0)

    assert result["cs_per_min"] == 0.0
    assert result["gold_per_min"] == 0.0
    assert result["vision_per_min"] == 0.0


# ---------------------------------------------------------------------------
# Test 4 — Zero team kills
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zero_team_kills():
    """Kill participation returns 0.0 when no team kills (no division by zero)."""
    p = _make_participant(kills=0, assists=0)
    team = [_make_participant(kills=0) for _ in range(5)]
    result = compute_derived_metrics(p, team, 1800)

    assert result["kill_participation"] == 0.0


# ---------------------------------------------------------------------------
# Test 5 — Zero team damage
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_zero_team_damage():
    """Damage share returns 0.0 when total team damage is 0 (no division by zero)."""
    p = _make_participant(totalDamageDealtToChampions=0)
    team = [_make_participant(totalDamageDealtToChampions=0) for _ in range(5)]
    result = compute_derived_metrics(p, team, 1800)

    assert result["damage_share"] == 0.0


# ---------------------------------------------------------------------------
# Test 6 — Support profile (high assists, low CS)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_support_profile():
    """Support player: low CS, high assists, high vision score."""
    p = _make_participant(
        kills=1, deaths=2, assists=20,
        totalMinionsKilled=20, neutralMinionsKilled=0,
        visionScore=80,
        goldEarned=8000,
    )
    team = _make_team()
    result = compute_derived_metrics(p, team, 1800)

    # KDA = (1 + 20) / 2 = 10.5
    assert result["kda"] == pytest.approx(10.5, rel=0.02)

    # CS/min should be very low: 20/30 ≈ 0.67
    assert result["cs_per_min"] < 1.0

    # Vision/min should be high: 80/30 ≈ 2.67
    assert result["vision_per_min"] > 2.0


# ---------------------------------------------------------------------------
# Test 7 — extract_team_participants
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_extract_team_participants():
    """Only participants matching teamId are returned."""
    all_participants = [
        {"teamId": 100, "kills": 5},
        {"teamId": 100, "kills": 3},
        {"teamId": 200, "kills": 4},
        {"teamId": 200, "kills": 6},
        {"teamId": 100, "kills": 2},
    ]
    team100 = extract_team_participants(all_participants, team_id=100)
    team200 = extract_team_participants(all_participants, team_id=200)

    assert len(team100) == 3
    assert len(team200) == 2
    assert all(p["teamId"] == 100 for p in team100)
    assert all(p["teamId"] == 200 for p in team200)


# ---------------------------------------------------------------------------
# Test 8 — normalize_game_duration (Riot API patch 11.20 handling)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_normalize_game_duration_post_patch():
    """Post-patch 11.20: gameDuration already in seconds when gameEndTimestamp present."""
    match_info = {"gameDuration": 1800, "gameEndTimestamp": 1700000000000}
    assert normalize_game_duration(match_info) == 1800


@pytest.mark.unit
def test_normalize_game_duration_pre_patch():
    """Pre-patch 11.20: gameDuration in milliseconds, must divide by 1000."""
    match_info = {"gameDuration": 1800000}  # no gameEndTimestamp
    assert normalize_game_duration(match_info) == 1800


# ---------------------------------------------------------------------------
# Test 9 — Metric rounding (2 decimal places)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_metric_output_rounded():
    """All returned metric values are rounded to at most 4 decimal places."""
    p = _make_participant(kills=7, deaths=3, assists=4)
    team = _make_team()
    result = compute_derived_metrics(p, team, 1743)  # odd duration

    for key, value in result.items():
        if value is not None:
            str_val = str(value)
            if "." in str_val:
                decimal_places = len(str_val.split(".")[1])
                assert decimal_places <= 4, f"{key} has too many decimal places: {value}"
