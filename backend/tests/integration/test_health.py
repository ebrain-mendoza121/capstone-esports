"""
Integration tests for health check endpoints.

These tests verify the API surface is reachable and returns
correct status codes and response shapes. They use the in-memory
SQLite test database — no real PostgreSQL or Riot API needed.
"""

import pytest

_PG_ONLY = pytest.mark.xfail(
    strict=False,
    reason=(
        "Requires PostgreSQL: raw SQL uses ::numeric cast syntax "
        "unsupported by the SQLite test database. Passes against real DB."
    ),
)


@pytest.mark.integration
def test_root_endpoint_returns_ok(client):
    """GET / should return HTTP 200 with status=ok."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


@pytest.mark.integration
def test_health_endpoint_returns_200(client):
    """GET /health should return HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.integration
def test_players_empty_list(client):
    """GET /players/ on empty DB returns an empty list, not an error."""
    response = client.get("/players/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.integration
def test_player_not_found(client):
    """GET /players/{puuid} for unknown PUUID returns 404."""
    response = client.get("/players/nonexistent-puuid-xyz")
    assert response.status_code == 404


@pytest.mark.integration
def test_matches_empty_for_unknown_player(client):
    """GET /matches/player/{puuid} for unknown player returns 404.

    The route first verifies the player exists; an unknown PUUID returns 404
    rather than an empty list, which is the correct contract for this endpoint.
    """
    response = client.get("/matches/player/nonexistent-puuid")
    assert response.status_code == 404


@_PG_ONLY
@pytest.mark.integration
def test_metrics_not_found_for_unknown_player(client):
    """GET /metrics/player/{puuid} for unknown player returns 404."""
    response = client.get("/metrics/player/nonexistent-puuid")
    assert response.status_code == 404
