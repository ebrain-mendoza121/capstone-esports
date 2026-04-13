"""
Integration tests for matches routes — additional coverage beyond the
not-found smoke test already present in test_health.py.

Covers:
  GET /matches/player/{puuid}          → 404 for unknown player (already in health)
  GET /matches/{match_id}              → 404 for unknown match_id
  GET /matches/{match_id}/draft        → 404 for unknown match_id
  GET /matches/player/{puuid}?limit=5  → 404 unknown player regardless of limit

All tests are SQLite-compatible — ORM lookups only.
"""

import pytest
from unittest.mock import AsyncMock, patch

_MOCK_CHAMPION_MAP = {1: "Annie", 64: "Lee Sin", 222: "Jinx"}


@pytest.mark.integration
def test_match_detail_unknown_id_returns_404(client):
    """GET /matches/{match_id} returns 404 for a match that does not exist."""
    with patch(
        "app.api.routes.matches.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/matches/NONEXISTENT_MATCH_ID")
    assert resp.status_code == 404


@pytest.mark.integration
def test_match_draft_unknown_id_returns_404(client):
    """GET /matches/{match_id}/draft returns 404 for an unknown match."""
    resp = client.get("/matches/NONEXISTENT_MATCH_ID/draft")
    assert resp.status_code == 404


@pytest.mark.integration
def test_player_match_history_with_limit_param(client):
    """GET /matches/player/{puuid}?limit=5 returns 404 for unknown player."""
    with patch(
        "app.api.routes.matches.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/matches/player/ghost-puuid?limit=5")
    assert resp.status_code == 404


@pytest.mark.integration
def test_player_match_history_large_limit_accepted(client):
    """GET /matches/player/{puuid}?limit=100 does not cause a 500 (unknown player → 404)."""
    with patch(
        "app.api.routes.matches.get_champion_map",
        AsyncMock(return_value=_MOCK_CHAMPION_MAP),
    ):
        resp = client.get("/matches/player/ghost-puuid?limit=100")
    assert resp.status_code == 404
