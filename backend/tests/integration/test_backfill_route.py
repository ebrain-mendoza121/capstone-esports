"""
Integration tests for the backfill route.

Covers:
  POST /backfill/derived  → 200 with "No missing derived metrics" on empty DB
  POST /backfill/derived?puuid=x → 200 targeting a specific PUUID (empty DB)

No PostgreSQL-specific SQL is executed in these code paths — the route uses
ORM joins so SQLite is compatible.
"""

import pytest


@pytest.mark.integration
def test_backfill_derived_empty_db_returns_success(client):
    """POST /backfill/derived on empty DB returns 200 with processed=0."""
    resp = client.post("/backfill/derived")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["processed"] == 0
    assert data["failed"] == 0


@pytest.mark.integration
def test_backfill_derived_response_has_expected_keys(client):
    """POST /backfill/derived always returns the full response schema."""
    resp = client.post("/backfill/derived")
    assert resp.status_code == 200
    data = resp.json()
    expected_keys = {"status", "processed", "failed", "failed_matches"}
    assert expected_keys.issubset(data.keys()), (
        f"Missing keys: {expected_keys - data.keys()}"
    )


@pytest.mark.integration
def test_backfill_derived_with_unknown_puuid_returns_success(client):
    """POST /backfill/derived?puuid=unknown returns success (no rows matched, 0 processed)."""
    resp = client.post("/backfill/derived?puuid=ghost-puuid-xyz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["processed"] == 0


@pytest.mark.integration
def test_backfill_derived_limit_param_accepted(client):
    """POST /backfill/derived?limit=10 does not error with a custom limit."""
    resp = client.post("/backfill/derived?limit=10")
    assert resp.status_code == 200
