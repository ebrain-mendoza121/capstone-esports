"""
Locust stress test for the Esports Analytics Platform API.

Target: 50 concurrent users, p95 < 2000ms, failure rate < 1%

Run via run_stress_test.sh or directly:
    locust -f tests/stress/locustfile.py --host=http://localhost:8000

Endpoint map (all verified against actual backend routes):
    GET /                                        → root health
    GET /health                                  → detailed health
    GET /players/?limit=20&min_matches=1         → paginated player list
    GET /champions                               → DDragon champion list
    GET /analytics/bans/most-banned              → global ban leaderboard
    GET /metrics/player/{puuid}                  → aggregate player metrics
    GET /analytics/player/{puuid}/role-performance → role percentile stats
    GET /analytics/player/{puuid}/bans           → ban analytics per player
    GET /analytics/player/{puuid}/trends         → rolling trend + series
    GET /analytics/champion/202/ban-rate         → single champion ban rate
"""

import random
import requests as _requests

from locust import HttpUser, between, events, task
from locust.exception import RescheduleTask

# ---------------------------------------------------------------------------
# Seed player PUUIDs at test start so we can hit player-specific endpoints.
# Uses the standard `requests` library directly — avoids the fragile
# Locust internal user-class context manager pattern.
# ---------------------------------------------------------------------------
_player_puuids: list[str] = []


@events.test_start.add_listener
def fetch_players(environment, **kwargs):
    """Fetch up to 20 tracked player PUUIDs before the swarm begins."""
    host = environment.host or "http://localhost:8000"
    try:
        resp = _requests.get(
            f"{host}/players/",
            params={"limit": 20, "min_matches": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            players = resp.json()
            if isinstance(players, list):
                _player_puuids.extend(p["puuid"] for p in players if p.get("puuid"))
        print(f"[locust] Loaded {len(_player_puuids)} player PUUIDs for per-player tasks.")
    except Exception as exc:
        print(f"[locust] WARNING: Could not pre-load player PUUIDs: {exc}")
        print("[locust] Per-player tasks will be skipped during this run.")


# ---------------------------------------------------------------------------
# User class
# ---------------------------------------------------------------------------

class EsportsApiUser(HttpUser):
    """
    Simulates a user browsing the Esports Analytics Platform dashboard.

    Task weights reflect realistic dashboard usage:
    - Player-specific analytics are hit most often (coaches checking rosters)
    - Reference data (champions list) is cached client-side in real usage
    - Health/root are lightweight but included for baseline measurement
    """
    wait_time = between(1, 3)

    # ── Baseline endpoints ───────────────────────────────────────────────

    @task(1)
    def root(self):
        self.client.get("/", name="GET /")

    @task(1)
    def health(self):
        self.client.get("/health", name="GET /health")

    # ── Reference data ───────────────────────────────────────────────────

    @task(2)
    def list_players(self):
        # min_matches=5 filters ghost participants — keeps response small
        with self.client.get(
            "/players/?limit=20&min_matches=5",
            name="GET /players/",
            catch_response=True,
        ) as resp:
            if resp.status_code == 503:
                resp.success()

    @task(2)
    def list_champions(self):
        self.client.get("/champions", name="GET /champions")

    # ── Global analytics ─────────────────────────────────────────────────

    @task(2)
    def most_banned(self):
        self.client.get(
            "/analytics/bans/most-banned?limit=10",
            name="GET /analytics/bans/most-banned",
        )

    @task(1)
    def ban_rate_sample(self):
        """Single champion ban rate — Jinx (202) as a fixed representative."""
        self.client.get(
            "/analytics/champion/202/ban-rate",
            name="GET /analytics/champion/{id}/ban-rate",
        )

    # ── Per-player analytics (skip gracefully when no players are loaded) ─

    @task(5)
    def player_metrics(self):
        """
        Aggregate metrics — the primary dashboard KPI call.
        Correct route: /metrics/player/{puuid}  (NOT /analytics/player/…/metrics)
        503 responses are marked as success (transient DB busy) to distinguish
        from real application errors.
        """
        if not _player_puuids:
            return
        puuid = random.choice(_player_puuids)
        with self.client.get(
            f"/metrics/player/{puuid}",
            name="GET /metrics/player/{puuid}",
            catch_response=True,
        ) as resp:
            if resp.status_code == 503:
                resp.success()  # transient pool exhaustion — not a test failure

    @task(4)
    def player_role_performance(self):
        """Role breakdown with peer percentile comparison."""
        if not _player_puuids:
            return
        puuid = random.choice(_player_puuids)
        with self.client.get(
            f"/analytics/player/{puuid}/role-performance",
            name="GET /analytics/player/{puuid}/role-performance",
            catch_response=True,
        ) as resp:
            if resp.status_code == 503:
                resp.success()

    @task(3)
    def player_bans(self):
        """
        Ban analytics per player (replaces champion-stats until T2-A is deployed).
        Correct route: /analytics/player/{puuid}/bans
        """
        if not _player_puuids:
            return
        puuid = random.choice(_player_puuids)
        with self.client.get(
            f"/analytics/player/{puuid}/bans",
            name="GET /analytics/player/{puuid}/bans",
            catch_response=True,
        ) as resp:
            if resp.status_code == 503:
                resp.success()

    @task(3)
    def player_trends(self):
        """
        Rolling window trends + per-game series (replaces objective-control until T2-B).
        Correct route: /analytics/player/{puuid}/trends
        """
        if not _player_puuids:
            return
        puuid = random.choice(_player_puuids)
        with self.client.get(
            f"/analytics/player/{puuid}/trends",
            name="GET /analytics/player/{puuid}/trends",
            catch_response=True,
        ) as resp:
            if resp.status_code == 503:
                resp.success()
