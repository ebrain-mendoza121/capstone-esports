# Stress Test Documentation

## Overview

This stress test suite validates the Esports Analytics Platform API under concurrent load using [Locust](https://locust.io), a Python-based load testing framework.

---

## Files

| File | Purpose |
|---|---|
| `tests/stress/locustfile.py` | User behaviour model and task weights |
| `tests/stress/run_stress_test.sh` | Headless test runner with summary output |
| `tests/stress/stress_results.html` | Generated HTML report (post-run) |
| `tests/stress/stress_results_stats.csv` | Per-endpoint CSV data (post-run) |

---

## Prerequisites

```bash
# From backend/
pip install locust
# or add to requirements.txt:
# locust>=2.28
```

---

## Running the Test

```bash
# From backend/
cd backend
bash tests/stress/run_stress_test.sh

# Override defaults:
bash tests/stress/run_stress_test.sh http://localhost:8000 50 5 60s
# Arguments: HOST  USERS  SPAWN_RATE  RUN_TIME
```

The backend must be running before the script starts:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Test Methodology

### User Simulation

Each virtual user (`EsportsApiUser`) models a realistic frontend session:

- **Wait time**: 1–3 seconds between requests (simulates human reading/interaction time).
- **Task weights**: higher weight = more frequent. Player-specific endpoints receive the highest weight because they are the core product surface.

| Endpoint | Weight | Rationale |
|---|---|---|
| `GET /` | 1 | Baseline liveness |
| `GET /health` | 1 | Monitoring probe |
| `GET /players/` | 3 | Browse/search flow |
| `GET /champions` | 3 | Reference data, cached in browser |
| `GET /analytics/bans/most-banned` | 2 | Meta overview page |
| `GET /analytics/player/{puuid}/metrics` | 5 | Player dashboard — primary use case |
| `GET /analytics/player/{puuid}/role-performance` | 4 | Player dashboard card |
| `GET /analytics/player/{puuid}/champion-stats` | 3 | Champion pool page |
| `GET /analytics/player/{puuid}/objective-control` | 3 | Objective control card |
| `GET /analytics/champion/{id}/ban-rate` | 2 | Per-champion ban rate lookup |

Player PUUIDs are fetched from `GET /players/?limit=20` before the ramp-up begins, so player-specific tasks always use real data from the database.

### Load Profile

| Parameter | Default |
|---|---|
| Concurrent users | 50 |
| Spawn rate | 5 users/second |
| Ramp-up time | 10 seconds (50 / 5) |
| Sustained load duration | 60 seconds |
| Total test duration | ~70 seconds |

---

## Target Metrics

| Metric | Target | Notes |
|---|---|---|
| p50 (median) response time | < 500 ms | Perceived as instant |
| p95 response time | **< 2 000 ms** | Hard SLA for all endpoints |
| p99 response time | < 5 000 ms | Acceptable tail latency |
| Failure rate | **< 1%** | HTTP 4xx/5xx counted as failures |
| Requests/second | ≥ 20 RPS | Aggregate throughput under 50 users |

The script flags any endpoint that breaches the p95 target with a `⚠` in the summary output.

---

## Interpreting Results

### HTML Report (`stress_results.html`)

Open in any browser. Key charts:

- **Response time over time** — shows if the system degrades as users ramp up or if it stabilises.
- **Number of users** — confirms the ramp profile was applied correctly.
- **Requests per second** — throughput trend; a plateau indicates the system is saturated.

### CSV Files

- `stress_results_stats.csv` — aggregate per-endpoint statistics.
- `stress_results_failures.csv` — individual failure records with error messages.
- `stress_results_stats_history.csv` — time-series data for charting outside Locust.

### Common Failure Patterns

| Symptom | Likely Cause |
|---|---|
| p95 > 2 000 ms on analytics endpoints | Missing DB index; N+1 query |
| Failure rate spike at ramp-up | Connection pool exhausted (`pool_size` in SQLAlchemy settings) |
| Flat RPS despite increasing users | CPU-bound Python; consider `--workers` with `gunicorn` |
| 503 errors | Uvicorn worker timeout; increase `--timeout-keep-alive` |

---

## Tuning Tips

- **Database indexes**: ensure `participant_stats(player_id)`, `matches(game_creation)`, and `derived_metrics(puuid, match_id)` are indexed.
- **Connection pool**: default SQLAlchemy pool is 5; increase `pool_size=20, max_overflow=10` for 50 concurrent users.
- **Caching**: static endpoints (`/champions`, `/analytics/bans/most-banned`) are good candidates for a short TTL cache (e.g., 60 s).
- **Async endpoints**: `/ingest/player` is async and backed by Riot API calls; it is intentionally excluded from this read-path stress test.
