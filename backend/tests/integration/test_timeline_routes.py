"""
Integration tests for timeline routes.

Covers:
  GET /timeline/{match_id}                        → 404 for unknown match_id
  GET /timeline/{match_id}/frames                 → 404 for unknown match_id
  GET /timeline/{match_id}/frames/by-puuid/{puuid}→ 404 for unknown match_id

All three endpoints guard with a MatchTimeline existence check before
touching frame/event tables, so an unknown match_id always returns 404.
These tests are safe on SQLite — no PostgreSQL-specific syntax is used.
"""

import pytest


@pytest.mark.integration
def test_timeline_summary_unknown_match_returns_404(client):
    """GET /timeline/{match_id} returns 404 when the match has no timeline data."""
    resp = client.get("/timeline/FAKE_MATCH_ID_999")
    assert resp.status_code == 404


@pytest.mark.integration
def test_timeline_frames_unknown_match_returns_404(client):
    """GET /timeline/{match_id}/frames returns 404 for a non-existent match."""
    resp = client.get("/timeline/FAKE_MATCH_ID_999/frames")
    assert resp.status_code == 404


@pytest.mark.integration
def test_timeline_frames_by_puuid_unknown_match_returns_404(client):
    """GET /timeline/{match_id}/frames/by-puuid/{puuid} returns 404 for unknown match."""
    resp = client.get("/timeline/FAKE_MATCH_ID_999/frames/by-puuid/some-puuid")
    assert resp.status_code == 404


@pytest.mark.integration
def test_timeline_summary_response_shape_when_found(client, db_session):
    """
    If a MatchTimeline row exists, summary returns the expected keys.
    Uses db_session to pre-insert a minimal timeline row.
    """
    from app.models.match_timeline import MatchTimeline

    row = MatchTimeline(
        match_id="TEST_MATCH_1",
        frame_interval=60000,
        end_of_game_result="GameComplete",
    )
    db_session.add(row)
    db_session.commit()

    resp = client.get("/timeline/TEST_MATCH_1")
    assert resp.status_code == 200
    data = resp.json()
    assert "match_id" in data
    assert "frame_interval_ms" in data
    assert "participant_frame_rows" in data
    assert "event_rows" in data
    assert data["match_id"] == "TEST_MATCH_1"


@pytest.mark.integration
def test_timeline_frames_returns_empty_list_when_no_frames(client, db_session):
    """
    When a MatchTimeline exists but has no frame rows the endpoint returns
    an empty list (HTTP 200) rather than 404/500.
    """
    from app.models.match_timeline import MatchTimeline

    row = MatchTimeline(
        match_id="TEST_MATCH_2",
        frame_interval=60000,
        end_of_game_result="GameComplete",
    )
    db_session.add(row)
    db_session.commit()

    resp = client.get("/timeline/TEST_MATCH_2/frames")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_timeline_frames_limit_param_accepted(client, db_session):
    """GET /timeline/{match_id}/frames?limit=10 does not error when match exists."""
    from app.models.match_timeline import MatchTimeline

    row = MatchTimeline(
        match_id="TEST_MATCH_3",
        frame_interval=60000,
        end_of_game_result="GameComplete",
    )
    db_session.add(row)
    db_session.commit()

    resp = client.get("/timeline/TEST_MATCH_3/frames?limit=10&offset=0")
    assert resp.status_code == 200
