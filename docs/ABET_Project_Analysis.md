# Capstone Esports Analytics Platform — Comprehensive Project Analysis
## CIIC/INSO 4151 Capstone — ABET Assessment Documentation
**Author (Primary Developer):** Ebrain Mendoza (ebmendoza / ebrain-mendoza121)
**Course:** CIIC/INSO 4151 — Senior Capstone Design
**Date:** May 2026

---

## 1. Project Overview

The **Esports Analytics Platform** is a full-stack League of Legends analytics system developed as part of the CIIC/INSO 4151 Capstone course at the University of Puerto Rico. The system is designed to serve esports coaching staff and competitive players by providing data-driven insights derived from the Riot Games API. It bridges raw match data with ML-backed predictions and an interactive web dashboard.

### 1.1 Target Users

- Esports coaches and analysts at the collegiate or amateur level
- Competitive players seeking objective performance benchmarks
- Team managers evaluating draft and matchup decisions

### 1.2 Core Value Proposition

Traditional esports review involves manually watching VODs and interpreting aggregate stats on third-party platforms. This platform centralizes player ingestion, computes normalized performance KPIs, and layers machine-learning predictions on top to provide:

- Objective player performance scoring (KDA, CS/min, gold/min, kill participation, damage share, vision/min)
- Pre-match win probability and player projection
- Matchup intelligence and draft analysis
- Playstyle archetype classification (carry, skirmisher, support/utility, farm-efficiency)

---

## 2. Problem Statement

### 2.1 Background and Context

Esports has grown into a highly competitive discipline at the collegiate and semi-professional levels, yet accessible tooling for objective player and team analysis remains fragmented. Existing tools either require paid subscriptions, expose only limited historical data, or lack ML-driven recommendations tailored to a team's specific roster.

### 2.2 Problem Statement

> **Coaches and players in collegiate esports lack a unified, data-driven analytics platform that can ingest their team's match history, compute normalized performance KPIs, and deliver ML-backed predictions and champion recommendations — all integrated into a single web application.**

The specific pain points addressed are:

1. **No single source of truth** for a team's historical match data and derived statistics.
2. **No predictive layer** — existing platforms display raw stats but do not predict future performance or win probability.
3. **No team-level composition analysis** — matchup and draft tools are separate from player performance tools.
4. **Manual data collection** — coaches had to manually track stats in spreadsheets with no automation.

### 2.3 SMART Goals Defined at Project Inception

| # | Goal | Target |
|---|------|--------|
| G1 | Derived metric coverage across all ingested participant-match rows | ≥ 95% |
| G2 | API response time for analytics endpoints | < 2,000 ms |
| G3 | Minimum distinct players ingested and queryable | ≥ 5 |
| G4 | Match data capacity verified at scale | ≥ 10,000 participant-match rows |
| G5 | Concurrent-user stress test | 50 concurrent users, p95 < 2,000 ms, < 1% failure rate |

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                    Riot Games API                        │
└─────────────────────────┬────────────────────────────────┘
                          │ HTTP (httpx, async)
┌─────────────────────────▼────────────────────────────────┐
│              FastAPI Backend (Python 3.11)               │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
│  │  Ingestion    │  │   Analytics   │  │  ML / AI     │  │
│  │  Service      │  │   Routes      │  │  Pipeline    │  │
│  └──────┬────────┘  └───────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│  ┌──────▼──────────────────▼──────────────────▼───────┐  │
│  │         SQLAlchemy ORM + PostgreSQL (Supabase)     │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          TTL In-Process Cache (Thread-Safe)         │  │
│  └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                          │ REST / JSON
┌─────────────────────────▼────────────────────────────────┐
│              Next.js 14 Frontend (React / TypeScript)    │
│  Pages: Dashboard, Player, Champion, Matchup, Team       │
└──────────────────────────────────────────────────────────┘
```

### 3.1 Technology Stack

| Layer | Technology | Justification |
|-------|-----------|---------------|
| API Framework | FastAPI (Python 3.11) | Async support, auto-generated OpenAPI/Swagger docs, native Pydantic validation |
| ASGI Server | Uvicorn | Production-grade async server for FastAPI |
| Database | PostgreSQL (Supabase) | Relational model for match/player data, JSONB support, hosted managed service |
| ORM | SQLAlchemy 2.0 | Battle-tested Python ORM, supports async sessions |
| Schema/Migrations | Prisma (Node.js) | Declarative schema management, auto-generated migration files |
| HTTP Client | httpx | Async-native HTTP for Riot API calls |
| ML | scikit-learn + XGBoost | Industry-standard ML libraries; XGBoost for high-performance gradient boosting |
| Model Serialization | joblib | Efficient serialization of numpy-heavy model artifacts |
| Rate Limiting | slowapi | Protects Riot-facing ingestion endpoints from abuse |
| Config | pydantic-settings + .env | Type-safe environment variable loading with validation |
| Frontend | Next.js 14 (App Router) | Server-side rendering, React ecosystem, TypeScript safety |
| CI/CD | GitHub Actions | Automated pytest + flake8 pipeline on every push and pull request |
| Load Testing | Locust | Python-native load testing with structured CSV/HTML reports |
| Deployment | Railway (backend) + Vercel (frontend) | Platform-as-a-service; zero-ops deployment |

---

## 4. Developer Contributions (ebmendoza / ebrain-mendoza121 / Ebrain Mendoza)

Across the project's ~105 total commits, the primary developer (Ebrain Mendoza) authored approximately **89 commits** across three username variants (`ebmendoza`, `ebrain-mendoza121`, `Ebrain Mendoza`), representing roughly **85% of all repository activity**.

### 4.1 Contribution Timeline

#### Phase 1 — Project Bootstrap (March 5, 2026)
Commits under `ebmendoza`:
- `8dcfbcc` — Initial `.gitignore`
- `f7a1a78` — Docker Compose for local PostgreSQL
- `ad03df9` — FastAPI app dependencies and Alembic configuration
- `9a1ec81` — FastAPI app bootstrap, settings, and database session
- `1777f29` — SQLAlchemy ORM models
- `5bbc3e5`, `ff956dd`, `082a788`, `794c613` — Database migrations (players, matches, participant_stats, team_objectives, derived_metrics, team_bans)
- `abc3500` — Ingestion CRUD operations
- `c17c04b` — Pydantic schemas for ingestion and API responses
- `82a44d6` — Riot client, ingestion pipeline, and metrics services
- `072e7bd` — Helper utilities
- `32a8e1b` — Initial frontend scaffold
- `78d2b82`, `74ce436` — Dev scripts and documentation
- `c00695b` — Starting scripts and app summary

#### Phase 2 — Core Backend Development (March 7 – March 25, 2026)
- `f72918e` — Draft actions improvements
- `3b6efe0`, `ebb6d57`, `b433ab2` — Player and match ingestion routes
- `5bb676a` — Updated ingestion routes
- `48b1c1f` — Match timeline and champion mapping
- `b8303fd` — Finalized endpoints before AI layer
- `899cc8c` — Bulk ingestion file
- `d82ab6f` — Initial model training
- `ac931bb` — Complete test suites and GitHub CI/CD
- `f7c68f4` — CI fixes (flake8 config, coverage threshold)
- `c6b3b14` — Fixed CRUD ingestion for large data batches
- `b2372a6` — Code quality improvements

#### Phase 3 — ML Pipeline and Analytics (April 6, 2026)
- `b96a5aa` — Metrics: `derived_metrics` as primary query path with raw fallback
- `95063310` — Global exception handler and DDragon startup preload
- `b319dc56` — Ingest: draft_actions failure surfacing; timeline raw column removal
- `f0678451` — Champions: resolve IDs to names in draft and AI recommendation endpoints
- `aae93056` — flake8 whitespace/slice formatting fixes
- `385c5d39` — Meta/config files
- `37825c3e`, `71ad0b4e` — Test suite syntax fixes
- `286b0fe` — Rate limiters for Riot API
- `762faab7` — Metrics: fixed round function
- `3c0918cb` — App startup script

#### Phase 4 — Team Insights, Testing, and Advanced Features (April 8–13, 2026)
- `ed9a5a10` — Testing files, team insights and individual rolling trends endpoint connections
- `f7259a7c` — Main testing files and missing features additions
- `bf23e56e` — Matchup table
- `5744aba8` — Champion matchup page
- `d71d2ad5` — Normalized champion roles

#### Phase 5 — Deployment, Performance, and ML Retraining (April 14–16, 2026)
- `8eda1814` — Build fixes for Vercel
- `814cbf59` — Procfile for Railway deployment
- `0af5b931` — CORS headers on all exception handler responses
- `549ce8be` — Retrained models and testing files
- `009b77e`, `e89b199`, `168c43e`, etc. — CORS origins, hardcoded routes, API URL fixes
- `ba2dee54` — Removed unused files
- `1356a1e` — Procfile for backend
- `e5f0cab` — Debug card and navbar
- `287fd12` — Testing insights
- `db5c0ac` — Trailing slash mismatch fix
- `cbb5a58` — Removed debugging page

#### Phase 6 — Final Performance Optimization and Caching (April 16, 2026)
- `662ea78` — Committed trained ML model artifacts
- `9b810a1` — **Stress testing, composite DB indexes, statement timeout, TTL cache** (core performance fix for SMART goal G5)
- `09c5140` — Fixed team insights calls
- `8438c62` — Possible cache feature testing
- `150e38c` — Fixed caching problems and charts (final performance milestone)

### 4.2 Scope of Individual Contributions

The primary developer owned the following subsystems end-to-end:

1. **Entire backend architecture** — FastAPI app structure, routing, middleware, exception handling
2. **Database schema design** — 9 relational tables (players, matches, participant_stats, team_objectives, team_bans, derived_metrics, match_timelines, draft_actions, participant_perks)
3. **Riot API integration** — async client with retry logic, backoff, rate limiting
4. **Derived metrics computation pipeline** — 6 normalized KPIs (KDA, CS/min, gold/min, kill participation, damage share, vision/min)
5. **Rolling feature engineering** — 11+ pre-match rolling window features for ML training
6. **All 7 ML models** — playstyle clustering, win prediction, matchup prediction, KDA regressor, CS regressor, early-game predictor, champion archetypes
7. **Champion recommendation engine** — Bayesian-smoothed scoring with playstyle affinity
8. **Team composition analysis** — threat scores, team DNA, role matchup cards
9. **Backfill system** — asynchronous gap-filling for derived metrics, draft actions, perks, timelines
10. **TTL in-process cache** — thread-safe stampede-protected cache for high-concurrency scenarios
11. **Performance optimization** — composite database indexes, statement timeout guards
12. **CI/CD pipeline** — GitHub Actions workflows with pytest and flake8
13. **Stress test suite** — Locust configuration targeting 50 concurrent users
14. **Deployment configuration** — Railway (backend) and Vercel (frontend) Procfiles, environment management

---

## 5. System Design Deep Dive

### 5.1 Database Schema

The relational schema is managed by Prisma and executed against PostgreSQL. The nine core tables are:

| Table | Purpose |
|-------|---------|
| `players` | Riot account identity (PUUID, gameName, tagLine, region) |
| `matches` | Match-level metadata (duration, queue, patch, mode) |
| `participant_stats` | Per-player per-match raw stats (KDA, gold, CS, vision, items) |
| `team_objectives` | Tower, dragon, baron, herald objectives per team per match |
| `team_bans` | Draft ban picks with pick_turn ordering |
| `derived_metrics` | Computed normalized KPIs per player per match |
| `match_timelines` | Frame-by-frame game state (JSON blob) |
| `draft_actions` | Ordered pick/ban sequences from match data |
| `participant_perks` | Rune configurations per participant |

Performance indexes include composite indexes on `(match_id, puuid)` for the hottest query paths.

### 5.2 Ingestion Pipeline

The ingestion flow:
1. Frontend submits `POST /ingest/player` with `{gameName, tagLine, platform}`.
2. Backend calls Riot Account API to resolve PUUID.
3. Backend calls Riot Match API to fetch match IDs and match details.
4. Each match is atomically written: `matches`, `participant_stats`, `team_objectives`, `team_bans`.
5. Backfill endpoints fill in timeline, draft actions, perks, and derived metrics asynchronously.
6. Model training is triggered manually or scheduled via `/ai/train/*` endpoints.

### 5.3 ML Pipeline

Seven models are trained from ingested data:

| Model | Type | Algorithm | Goal |
|-------|------|-----------|------|
| `playstyle_kmeans` | Clustering | KMeans (k=4) | Player archetype classification |
| `win_predictor` | Classification | Logistic Regression / XGBoost | Per-player pre-match win probability |
| `matchup_predictor` | Classification | Logistic Regression / XGBoost | Team-level match win probability |
| `kda_regressor` | Regression | Ridge / XGBoost | Expected KDA prediction |
| `cs_regressor` | Regression | Ridge / XGBoost | Expected CS/min prediction |
| `earlygame_predictor` | Classification | Logistic Regression | Minute-10/15 win probability |
| `champion_clusters` | Clustering | KMeans | Champion archetype grouping |

**Key design choices:**
- **Temporal train/test split** (oldest 80% train, newest 20% test) — prevents data leakage from future matches
- **Candidate model comparison** (Logistic Regression vs. XGBoost) — selects by ROC-AUC or R²
- **Persisted training medians** — ensures inference-time imputation matches training distribution
- **Minimum data gates** — prevents training on insufficient samples

### 5.4 Caching and Performance

A custom in-process TTL cache (`TTLCache` and `TTLCacheDict`) was implemented with **stampede protection** using double-checked locking. Under 50 concurrent users, only one thread executes the expensive DB query while all others block and receive the cached result. Cache TTL is 300 seconds (5 minutes).

Database performance was further improved through:
- **Composite indexes** on hottest query paths
- **Statement timeout guards** to prevent runaway queries
- **DB-first data access pattern** — live Riot API only called during ingestion, never during analytics reads

### 5.5 Deployment Architecture

| Service | Platform | Configuration |
|---------|----------|---------------|
| Backend API | Railway | Procfile: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Frontend | Vercel | Next.js auto-detected, `NEXT_PUBLIC_API_URL` points to Railway backend |
| Database | Supabase | Managed PostgreSQL, connection pooling via `DATABASE_URL` |

CORS is configured to allow cross-origin requests from the Vercel frontend domain to the Railway backend.

---

## 6. Testing and Validation

### 6.1 Unit Tests

Located in `backend/tests/unit/`:
- `test_derived_metrics.py` — validates KPI computation formulas
- `test_feature_helpers.py` — validates rolling window feature engineering
- `test_metrics_aggregation.py` — validates aggregate player metric calculations

### 6.2 Integration Tests

Located in `backend/tests/integration/`:
- `test_health.py` — API health and DB connectivity probes
- `test_ingest_validation.py` — ingestion schema validation
- `test_analytics_routes.py` — analytics endpoint integration
- `test_ai_endpoints.py` — ML training and inference endpoints
- `test_backfill_route.py` — backfill job endpoints
- `test_champions_and_teams.py` — champion and team analysis endpoints
- `test_matches_routes.py` — match retrieval endpoints
- `test_timeline_routes.py` — timeline data endpoints

### 6.3 CI/CD

GitHub Actions pipeline runs on every push and pull request:
- `pytest` with coverage threshold enforcement
- `flake8` linting across the entire backend codebase

### 6.4 Stress Testing (Locust)

| Metric | Target | Result |
|--------|--------|--------|
| Concurrent users | 50 | ✅ Met |
| Spawn rate | 5 users/sec | ✅ Met |
| p95 response time | < 2,000 ms | ✅ Met |
| Failure rate | < 1% | ✅ Met |
| Minimum throughput | > 10 req/s | ✅ Met |

### 6.5 Performance Benchmarks (benchmark.sh)

| SMART Goal | Measured | Target | Pass |
|------------|----------|--------|------|
| Derived metric coverage | 100.0% (36,100 rows) | ≥ 95% | ✅ |
| API response time (analytics) | ≤ 922 ms | < 2,000 ms | ✅ |
| Players ingested | 14,205 | ≥ 5 | ✅ |
| Match data capacity | 36,100 rows | ≥ 10,000 | ✅ |

---

## 7. Constraints and Trade-offs

| Constraint | Impact | Resolution |
|------------|--------|------------|
| Riot API rate limit (100 req/20s) | Slows large-batch ingestion | Retry logic with exponential backoff; rate-limiting middleware (slowapi) |
| Supabase free-tier connection limit | Limits concurrent DB connections | Connection pooling; TTL cache to reduce repeated queries |
| ML model training requires sufficient data | Models unusable with few players | Data gates per model, `/ai/models/status` reports readiness |
| Riot API key daily limits | Caps total data volume | Targeted ingestion of tracked players only, not global scraping |
| SQLAlchemy array cast incompatibility (PostgreSQL) | Query failures on ARRAY literals | Explicit `cast(ARRAY[...], ARRAY[Integer()])` workaround documented in repo memory |

---

## 8. Professional Standards and Best Practices Applied

1. **OpenAPI / Swagger documentation** — auto-generated from FastAPI decorators, accessible at `/docs`
2. **Environment variable management** — Pydantic `BaseSettings` with `.env` file; no secrets in source code
3. **Conventional commits** — lowercase imperative commit messages (e.g., `feat:`, `fix:`, `chore:`, `refactor:`)
4. **Temporal ML validation** — avoids data leakage by splitting chronologically, not randomly
5. **CORS security** — explicit allow-list of trusted origins, no wildcard in production
6. **Rate limiting on public endpoints** — slowapi guards Riot-facing routes
7. **DB-first architecture** — analytics reads never touch the Riot API, protecting rate limits and improving response time
8. **Graceful error handling** — global FastAPI exception handler ensures CORS headers are present on all error responses
9. **Model governance** — artifact metadata sidecars (`.json` files alongside `.joblib`) record trained_at, sample count, metrics, and library versions
10. **Prisma schema versioning** — all DB changes tracked as named migrations

---

## 9. Summary

The Esports Analytics Platform represents a complete software engineering project lifecycle:
- **Requirements analysis** → SMART goals, user story identification
- **System design** → multi-tier architecture, relational schema, ML pipeline design
- **Implementation** → 89+ commits spanning backend, ML, frontend, deployment, and testing
- **Validation** → unit tests, integration tests, CI/CD, stress testing, benchmark scripts
- **Deployment** → production Railway + Vercel deployment with CORS and environment management
- **Documentation** → README, backend study guide, retraining checklist, performance evidence, stress test documentation

All four SMART goals and the stress-test target were met or exceeded as documented in `performance_evidence.md`.
