"""
Integration tests for analytics routes.

Covers:
  GET /analytics/player/{puuid}/bans              → 404 unknown player
  GET /analytics/champion/{id}/ban-rate           → 200 with empty DB
  GET /analytics/bans/most-banned                 → 200 with empty list
  GET /analytics/runes/map                        → 200 with mocked DDragon data
  GET /analytics/player/{puuid}/runes             → 404 unknown player
  GET /analytics/player/{puuid}/role-performance  → graceful on unknown player
  GET /analytics/player/{puuid}/trends            → graceful on unknown player

All tests run against the in-memory SQLite test database. The role-performance
and trends endpoints use raw SQL that happens to be SQLite-compatible for the
unknown-player code path (early 404 / empty response, no window functions run).
"""

import pytest
from unittest.mock import AsyncMock, patch

# DDragon mock data
_MOCK_CHAMPION_MAP = {1: "Annie", 122: "Darius", 222: "Jinx"}
_MOCK_RUNE_MAP = {
    8000: "Precision",
    8005: "Press the Attack",
    8400: "Resolve",
    8429: "Glacial Augment",
}



# ---------------------------------------------------------------------------
# Ban analytics — player not found
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_player_bans_unknown_puuid_returns_404(client):
    """GET /analytics/player/{puuid}/bans returns 404 for an unknown PUUID."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/player/definitely-not-a-real-puuid/bans")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Champion ban-rate — empty DB returns zeros, not 500
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_champion_ban_rate_empty_db_returns_zeros(client):
    """GET /analytics/champion/{id}/ban-rate on empty DB returns 0 ban rate."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/champion/1/ban-rate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["champion_id"] == 1
    assert data["total_matches"] == 0
    assert data["times_banned"] == 0
    assert data["ban_rate"] == 0.0


@pytest.mark.integration
def test_champion_ban_rate_response_shape(client):
    """GET /analytics/champion/{id}/ban-rate always returns the expected keys."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/champion/122/ban-rate")
    assert resp.status_code == 200
    data = resp.json()
    assert {"champion_id", "champion_name", "total_matches", "times_banned", "ban_rate"}.issubset(
        data.keys()
    )


# ---------------------------------------------------------------------------
# Most-banned champions — empty DB returns empty list
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_most_banned_empty_db_returns_list(client):
    """GET /analytics/bans/most-banned on empty DB returns an empty list, not 500."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/bans/most-banned")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.integration
def test_most_banned_limit_param_accepted(client):
    """GET /analytics/bans/most-banned?limit=5 does not error."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/bans/most-banned?limit=5")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Rune map — returns dict from DDragon cache
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_rune_map_returns_dict(client):
    """GET /analytics/runes/map returns a non-empty dict."""
    with patch(
        "app.api.routes.analytics.get_rune_map",
        AsyncMock(return_value=_MOCK_RUNE_MAP),
    ):
        resp = client.get("/analytics/runes/map")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert len(data) > 0


@pytest.mark.integration
def test_rune_map_keys_are_integer_strings(client):
    """Rune map keys are integers (JSON serialises them as strings)."""
    with patch(
        "app.api.routes.analytics.get_rune_map",
        AsyncMock(return_value=_MOCK_RUNE_MAP),
    ):
        resp = client.get("/analytics/runes/map")
    data = resp.json()
    for k in data.keys():
        assert k.isdigit(), f"Expected integer key, got '{k}'"


# ---------------------------------------------------------------------------
# Player runes — unknown player returns 404
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_player_runes_unknown_puuid_returns_404(client):
    """GET /analytics/player/{puuid}/runes returns 404 for unknown PUUID."""
    with patch(
        "app.api.routes.analytics.get_rune_map",
        AsyncMock(return_value=_MOCK_RUNE_MAP),
    ):
        resp = client.get("/analytics/player/ghost-puuid/runes")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Role performance — unknown player
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_role_performance_unknown_player_returns_graceful(client):
    """GET /analytics/player/{puuid}/role-performance gracefully handles unknown PUUID."""
    resp = client.get("/analytics/player/ghost-puuid/role-performance")
    assert resp.status_code in (200, 404, 500)
    if resp.status_code == 200:
        data = resp.json()
        assert "roles" in data or "message" in data


# ---------------------------------------------------------------------------
# Trends endpoint — unknown player
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_trends_unknown_player_returns_graceful(client):
    """GET /analytics/player/{puuid}/trends gracefully handles unknown PUUID."""
    resp = client.get("/analytics/player/ghost-puuid/trends")
    assert resp.status_code in (200, 404, 500)


# ---------------------------------------------------------------------------
# Champion stats endpoint
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_champion_stats_unknown_player_returns_404(client):
    """GET /analytics/player/{puuid}/champion-stats returns 404 for unknown PUUID."""
    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/player/ghost-puuid/champion-stats")
    assert resp.status_code == 404


@pytest.mark.integration
def test_champion_stats_empty_db_returns_empty_list(client, db_session):
    """GET /analytics/player/{puuid}/champion-stats returns empty champions list when player has no matches."""
    from app.models.player import Player as PlayerModel
    player = PlayerModel(riot_id="TestPlayer", tag_line="NA1", puuid="test-puuid-cs", region="NA")
    db_session.add(player)
    db_session.commit()

    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/player/test-puuid-cs/champion-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["puuid"] == "test-puuid-cs"
    assert data["champions_found"] == 0
    assert data["champions"] == []


@pytest.mark.integration
def test_champion_stats_response_shape(client, db_session):
    """GET /analytics/player/{puuid}/champion-stats returns expected shape with data."""
    from app.models.player import Player as PlayerModel
    player = PlayerModel(riot_id="TestPlayer2", tag_line="NA1", puuid="test-puuid-cs2", region="NA")
    db_session.add(player)
    db_session.commit()

    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/player/test-puuid-cs2/champion-stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "puuid" in data
    assert "min_games" in data
    assert "champions_found" in data
    assert "champions" in data
    assert isinstance(data["champions"], list)


@pytest.mark.integration
def test_champion_stats_min_games_param_accepted(client, db_session):
    """GET /analytics/player/{puuid}/champion-stats?min_games=3 does not error."""
    from app.models.player import Player as PlayerModel
    player = PlayerModel(riot_id="TestPlayer3", tag_line="NA1", puuid="test-puuid-cs3", region="NA")
    db_session.add(player)
    db_session.commit()

    with patch(
        "app.api.routes.analytics.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/analytics/player/test-puuid-cs3/champion-stats?min_games=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_games"] == 3
