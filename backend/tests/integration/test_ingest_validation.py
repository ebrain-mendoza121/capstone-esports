"""
Integration tests for the ingestion endpoint input validation.

These tests verify that malformed or missing request bodies
return proper HTTP 422 errors, not 500s — ensuring the API
is robust against bad client input.

No actual Riot API calls are made — these test input validation only.
"""

import pytest


@pytest.mark.integration
def test_ingest_missing_body_returns_422(client):
    """POST /ingest/player with no body returns HTTP 422."""
    response = client.post("/ingest/player")
    assert response.status_code == 422


@pytest.mark.integration
def test_ingest_missing_game_name_returns_422(client):
    """POST /ingest/player without gameName returns HTTP 422."""
    response = client.post("/ingest/player", json={
        "tagLine": "NA1",
        "platform": "NA",
        "count": 10,
    })
    assert response.status_code == 422


@pytest.mark.integration
def test_ingest_missing_tag_line_returns_422(client):
    """POST /ingest/player without tagLine returns HTTP 422."""
    response = client.post("/ingest/player", json={
        "gameName": "TestPlayer",
        "platform": "NA",
        "count": 10,
    })
    assert response.status_code == 422


@pytest.mark.integration
def test_ingest_empty_strings_returns_422(client):
    """POST /ingest/player with empty gameName returns HTTP 422."""
    response = client.post("/ingest/player", json={
        "gameName": "",
        "tagLine": "NA1",
        "platform": "NA",
        "count": 10,
    })
    # Should be rejected — empty riot ID is invalid
    assert response.status_code in (422, 400)


@pytest.mark.integration
def test_ingest_invalid_count_type_returns_422(client):
    """POST /ingest/player with non-integer count returns HTTP 422."""
    response = client.post("/ingest/player", json={
        "gameName": "TestPlayer",
        "tagLine": "NA1",
        "platform": "NA",
        "count": "many",
    })
    assert response.status_code == 422
