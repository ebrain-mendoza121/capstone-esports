# Stress Test Documentation — Esports Analytics Platform

**Date:** April 2026  
**Course:** CIIC4151-001 | Prof. Wilson Rivera Gallego

---

## 1. Overview

This document describes the stress testing methodology, configuration, and target metrics for the Esports Analytics Platform. Stress testing validates the SMART goal: **50 concurrent users with p95 response time < 2,000 ms and < 1% failure rate**.

The stress test is implemented using [Locust](https://locust.io/) — a Python-based open-source load testing framework that simulates concurrent HTTP users and generates structured HTML and CSV reports.

---

## 2. Test Files

| File | Purpose |
|------|---------|
| `backend/tests/stress/locustfile.py` | Locust user class with endpoint task definitions and weights |
| `backend/tests/stress/run_stress_test.sh` | Shell script to execute headless Locust run and print summary |
| `backend/tests/stress/stress_results.html` | HTML report generated after each run (auto-generated) |
| `backend/tests/stress/stress_results_stats.csv` | Per-endpoint CSV statistics (auto-generated) |
| `backend/tests/stress/stress_results_history.csv` | Per-second throughput history (auto-generated) |

---

## 3. Target Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Concurrent users | 50 | SMART goal from capstone proposal |
| Spawn rate | 5 users/second | Gradual ramp to avoid cold-start spikes |
| Run duration | 60 seconds | Sufficient steady-state measurement window |
| p95 response time | < 2,000 ms | Dashboard interaction must feel responsive |
| Failure rate | < 1% | High availability requirement |
| Requests/sec | > 10 | Minimum throughput for 50 users |

---

## 4. Endpoint Coverage and Task Weights

The Locust user simulates realistic dashboard behavior. Weights reflect how frequently each endpoint would be called by a coaching staff member reviewing player analytics.

| Endpoint | Weight | Category | Why Included |
|----------|--------|----------|--------------|
| `GET /` | 1 | Baseline | Root health check |
| `GET /health` | 1 | Baseline | Detailed health with DB status |
| `GET /players/?limit=20&min_matches=5` | 2 | Reference data | Player roster list |
| `GET /champions` | 2 | Reference data | DDragon champion catalog |
| `GET /analytics/bans/most-banned?limit=10` | 2 | Global analytics | Ban leaderboard — shared dashboard widget |
| `GET /analytics/champion/202/ban-rate` | 1 | Global analytics | Single champion ban rate |
| `GET /metrics/player/{puuid}` | 5 | Per-player (highest weight) | Primary KPI dashboard call |
| `GET /analytics/player/{puuid}/role-performance` | 4 | Per-player | Role percentile breakdown |
| `GET /analytics/player/{puuid}/bans` | 3 | Per-player | Ban tendencies per player |
| `GET /analytics/player/{puuid}/trends` | 3 | Per-player | Rolling trend sparkline data |

Per-player endpoints are skipped gracefully if no players exist in the database (pre-ingestion runs).

---

## 5. How to Run

### Prerequisites

```bash
pip install locust requests
```

The backend must be running on the target host (default: `http://localhost:8000`).

### Quick Run (from backend directory)

```bash
./tests/stress/run_stress_test.sh
```

### Custom Parameters

```bash
# Syntax: ./run_stress_test.sh [HOST] [USERS] [SPAWN_RATE] [RUN_TIME]
./tests/stress/run_stress_test.sh http://localhost:8000 50 5 60s
```

### Manual Locust Command

```bash
locust \
  -f tests/stress/locustfile.py \
  --host http://localhost:8000 \
  --headless \
  --users 50 \
  --spawn-rate 5 \
  --run-time 60s \
  --html tests/stress/stress_results.html \
  --csv tests/stress/stress_results
```

### Interactive Web UI (for live monitoring)

```bash
locust -f tests/stress/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 in browser
```

---

## 6. How to Interpret Results

### HTML Report (`stress_results.html`)

The HTML report contains three sections:

1. **Statistics Table** — per-endpoint request count, failure count, median, 95th percentile, 99th percentile, average, min, max response times, and requests/sec.
2. **Charts** — response time over time, requests per second over time, and number of active users over time. Look for the steady-state plateau (after the 10-second ramp) to evaluate true performance.
3. **Failures** — any HTTP errors or exceptions that occurred during the run.

### CSV Report (`stress_results_stats.csv`)

The `run_stress_test.sh` script parses this CSV and prints a summary table. Key columns:

| Column | Meaning |
|--------|---------|
| `Name` | Endpoint name |
| `50%` | Median response time (ms) |
| `95%` | 95th percentile response time (ms) — compare against 2,000 ms target |
| `Requests/s` | Throughput for this endpoint |
| `Failure Count` | Total HTTP errors or timeouts |

Endpoints marked with `⚠` in the script output exceed the 2,000 ms p95 target and require investigation.

### Pass/Fail Criteria

| Criterion | Pass Condition |
|-----------|---------------|
| p95 response time | All endpoints < 2,000 ms |
| Failure rate | < 1% across all requests |
| Throughput | System handles 50 users without queuing |

---

## 7. Pre-Ingestion Behavior

If no players are ingested, per-player tasks (`metrics`, `role-performance`, `bans`, `trends`) are automatically skipped by the locust user. The test still runs and validates the reference data and global analytics endpoints. To enable full coverage:

```bash
# From project root, ingest a player first:
curl -X POST http://localhost:8000/ingest/player \
  -H "Content-Type: application/json" \
  -d '{"gameName":"PlayerName","tagLine":"NA1","platform":"NA","count":20,"queue":420}'
```

---

## 8. Architecture Notes

### Database Connection Pool

`session.py` is configured with `pool_size=10, max_overflow=5` — allowing up to 15 simultaneous database connections. With 50 concurrent users and typical query durations under 100ms, this pool is sufficient: connection hold time ÷ total connections × users = ~0.1s / 15 × 50 ≈ 0.33 connections per user at peak, well within the pool capacity.

### Rate Limiting

The backend uses `slowapi` (FastAPI rate-limiting middleware) configured per the `app/main.py` setup. Rate limits are not expected to trigger during the 50-user, 60-second test window given the `between(1, 3)` second wait time per user. If rate limits are observed, the wait time can be increased in `locustfile.py`.

### SQLite vs PostgreSQL

Stress tests must be run against the **production Supabase database** (or a PostgreSQL instance). SQLite does not support the PostgreSQL window functions used by the analytics endpoints and will produce errors on per-player endpoints.

---

## 9. Mapping to SMART Goals

| SMART Goal | Stress Test Evidence Source |
|------------|-----------------------------|
| ≥95% API retrieval success rate | Failure rate % from `stress_results_stats.csv` |
| < 2,000 ms dashboard response | p95 column for all endpoints in stats CSV |
| Support 50 concurrent users | `--users 50` parameter in Locust run |
| < 2 min for 100 match ingestion | Not covered by stress test — see `benchmark.py` and `POST /ingest/player` timing |

---

*Esports Analytics Platform — CIIC4151-001 — April 2026*
