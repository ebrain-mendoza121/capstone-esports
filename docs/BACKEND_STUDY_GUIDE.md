# 🎓 Capstone Esports App — Backend Study Guide

> **Purpose:** This document is your one-stop reference for understanding every
> moving part of your backend. Read it top-to-bottom for the full picture, or
> jump to any section when you need to explain a specific piece.

---

## Table of Contents

1. [Big Picture — What Does This App Do?](#1-big-picture)
2. [Tech Stack at a Glance](#2-tech-stack)
3. [Project File Map — Where Everything Lives](#3-file-map)
4. [The Entry Point: `main.py`](#4-entry-point)
5. [Configuration & Environment](#5-configuration)
6. [Database Layer — How Data Is Stored](#6-database-layer)
7. [ORM Models — Your Data Shapes](#7-orm-models)
8. [The API Layer — Every Endpoint Explained](#8-api-layer)
9. [The Service Layer — Business Logic](#9-service-layer)
10. [The ML Pipeline — AI/Analytics](#10-ml-pipeline)
11. [Data Flow: End-to-End Walkthroughs](#11-data-flows)
12. [Key Concepts You Should Be Able to Explain](#12-key-concepts)
13. [Glossary](#13-glossary)

---

## 1. Big Picture — What Does This App Do? <a name="1-big-picture"></a>

Your app is a **League of Legends analytics platform**. It:

1. **Ingests** player match data from the Riot Games API
2. **Stores** it in a PostgreSQL database (hosted on Supabase)
3. **Computes** derived stats (KDA, CS/min, gold/min, etc.)
4. **Trains ML models** to predict wins, KDA, CS, playstyles, and early-game outcomes
5. **Serves** all of that through a REST API that a Next.js frontend consumes

Think of it as: **Riot API → Python Backend → PostgreSQL → ML Models → REST API → React Frontend**

---

## 2. Tech Stack at a Glance <a name="2-tech-stack"></a>

| Layer | Technology | Why It Matters |
|-------|-----------|----------------|
| **Web Framework** | FastAPI (Python) | Async, auto-generates OpenAPI docs, type-safe |
| **Server** | Uvicorn (ASGI) | Runs FastAPI; handles async I/O |
| **Database** | PostgreSQL on Supabase | Relational DB with JSONB support |
| **ORM** | SQLAlchemy 2.0 | Maps Python classes to database tables |
| **Migrations** | Prisma (via Node.js) | Manages schema changes/versioning |
| **HTTP Client** | httpx | Async HTTP calls to Riot API |
| **ML** | scikit-learn + XGBoost | Clustering, classification, regression |
| **Model Storage** | joblib | Serializes trained models to `.joblib` files |
| **Rate Limiting** | slowapi | Protects ingestion endpoints from abuse |
| **Config** | pydantic-settings + .env | Type-safe environment variable loading |
| **Testing** | pytest | Unit + integration test suite |
| **CI/CD** | GitHub Actions | Auto-runs tests + lint on push/PR |

### Key Libraries to Know:
- **FastAPI** — Defines routes with decorators (`@router.get("/path")`), auto-validates with Pydantic
- **SQLAlchemy** — Defines tables as Python classes; queries use ORM syntax or raw SQL
- **httpx** — Like `requests` but async; used for Riot API calls
- **pandas** — DataFrames for feature engineering before ML training
- **scikit-learn** — KMeans clustering, Logistic Regression, StandardScaler
- **XGBoost** — Gradient-boosted trees for win/KDA/CS prediction

---

## 3. Project File Map — Where Everything Lives <a name="3-file-map"></a>

```
backend/
├── app/                          # ← ALL application code
│   ├── main.py                   # App entry point, middleware, exception handlers
│   ├── api/
│   │   ├── router.py             # Registers all route modules
│   │   └── routes/               # ← One file per feature area
│   │       ├── ingest.py         #    Ingest players from Riot API
│   │       ├── players.py        #    List/get players
│   │       ├── matches.py        #    Match history & detail
│   │       ├── metrics.py        #    Aggregated player stats
│   │       ├── analytics.py      #    Bans, runes, role perf, trends
│   │       ├── ai.py             #    ML training & predictions
│   │       ├── teams.py          #    Team stats & composition
│   │       ├── champions.py      #    Champion data & matchups
│   │       ├── matchups.py       #    CSV import & counter queries
│   │       ├── timeline.py       #    Frame-by-frame match data
│   │       ├── backfill.py       #    Fill gaps in derived data
│   │       └── health.py         #    Liveness/readiness probes
│   ├── core/
│   │   ├── settings.py           # Pydantic config (loads .env)
│   │   └── limiter.py            # Shared rate-limiter instance
│   ├── db/
│   │   ├── session.py            # SQLAlchemy engine + session factory
│   │   └── crud_ingest.py        # Database write operations
│   ├── models/                   # ← SQLAlchemy ORM table definitions
│   │   ├── match.py              #    matches table (hub)
│   │   ├── player.py             #    players table
│   │   ├── participant_stats.py  #    Per-player match stats
│   │   ├── team_objectives.py    #    Towers/dragons/barons
│   │   ├── team_bans.py          #    Draft bans
│   │   ├── derived_metrics.py    #    Computed KPIs
│   │   ├── match_timeline.py     #    Timeline frames + events
│   │   ├── draft_actions.py      #    Full pick/ban order
│   │   ├── participant_perks.py  #    Rune selections
│   │   └── champion_matchups.py  #    Researched win rates
│   ├── schemas/
│   │   └── ingest.py             # Pydantic request/response models
│   └── services/                 # ← Business logic layer
│       ├── riot_client.py        #    Riot API wrapper (rate-limited)
│       ├── riot_live_service.py  #    Hybrid DB/API stat fetcher
│       ├── ddragon.py            #    Champion/rune metadata cache
│       ├── ingestion_service.py  #    Orchestrates full ingest flow
│       ├── derived_metrics_calculator.py  # Stateless metric math
│       ├── metrics_service.py    #    Career stat aggregation
│       ├── feature_extractor.py  #    ML feature engineering
│       └── ai_service.py         #    ML model train + predict
├── ml_models/                    # ← Serialized .joblib model files
├── prisma/
│   ├── schema.prisma             # Database schema definition
│   └── migrations/               # SQL migration files
├── tests/
│   ├── unit/                     # Fast, no-DB tests
│   ├── integration/              # Tests with SQLite DB
│   └── stress/                   # Load testing
├── scripts/
│   ├── startup_and_train.sh      # Boot server + train all models
│   └── enrich_opponents.sh       # Analyze opponent data coverage
├── requirements.txt              # Python dependencies
├── package.json                  # Node deps (Prisma only)
└── .env                          # Secrets (DB URL, Riot API key)
```

---

## 4. The Entry Point: `main.py` <a name="4-entry-point"></a>

This is the **first file that runs** when the server starts. Understand it and
you understand the app's skeleton.

### What it does (in order):

1. **Imports all ORM models** — SQLAlchemy needs every model imported so it
   knows what tables exist. Lines 21–30 are `import app.models.X` for this.

2. **Defines the lifespan** — The `_lifespan()` async context manager runs
   **once at startup**. It pre-loads champion + rune data from Riot's CDN
   (Data Dragon) so the first API request doesn't wait for a network call.

3. **Creates the FastAPI app** — `app = FastAPI(...)` with the lifespan attached.

4. **Attaches middleware:**
   - **CORS** — Allows the frontend (localhost:3000) to call the API
   - **Rate limiter** — slowapi for ingestion endpoints
   - **Timeout** — 60s for normal requests, 600s for backfill/import

5. **Registers routers** — `health_router` + `api_router` (which bundles all 11 route files)

6. **Exception handlers:**
   - `SATimeoutError` → 503 (DB pool exhausted)
   - `SAOperationalError` → 503 (transient DB error)
   - Generic `Exception` → 500 with structured JSON (never leaks tracebacks)

### 🔑 Study questions:
- *What is a "lifespan" in FastAPI and why is it used instead of `@app.on_event("startup")`?*
- *What does CORS do and why does the frontend need it?*
- *Why would you return 503 vs 500 for a database error?*

---

## 5. Configuration & Environment <a name="5-configuration"></a>

### `core/settings.py` — How Config Works

```python
class Settings(BaseSettings):
    database_url: str              # PostgreSQL connection string
    cors_origins: List[str]        # Allowed frontend origins
    riot_api_key: str = ""         # Riot API key
    http_timeout_seconds: float    # Timeout for outgoing HTTP calls
    riot_max_retries: int          # Retry count for rate-limited calls
    riot_backoff_base_seconds: float  # Exponential backoff base
```

- Uses **pydantic-settings** to load from `.env` file automatically
- `@lru_cache` on `get_settings()` means the `.env` file is only read **once**
  per process — all subsequent calls return the cached object

### `.env` file contains:
```
DATABASE_URL=postgresql+psycopg://...@supabase:6543/postgres
RIOT_API_KEY=RGAPI-xxxxxxxx
CORS_ORIGINS=http://localhost:3000
```

### 🔑 Study questions:
- *What is `@lru_cache` and why is it used on `get_settings()`?*
- *What's the difference between port 5432 (Session Mode) and 6543 (Transaction Mode) in Supabase?*
- *Why does `prepare_threshold=0` need to be set?*

---

## 6. Database Layer <a name="6-database-layer"></a>

### `db/session.py` — The Connection Engine

This file creates the SQLAlchemy **engine** (connection pool) and **session factory**.

**Key concepts:**

| Term | What It Is |
|------|-----------|
| **Engine** | A pool of database connections. You don't open/close connections manually. |
| **Session** | A unit-of-work that holds pending queries. Created per request, committed or rolled back, then closed. |
| **SessionLocal** | A factory — call `SessionLocal()` to get a new session. |
| **Base** | All ORM models inherit from this. It tracks metadata about all tables. |
| **get_db()** | A generator that yields a session and closes it after the request. Used as a FastAPI dependency. |

**Connection Pool Settings (for Supabase Transaction Mode):**
```python
pool_size=5          # 5 persistent connections
max_overflow=5       # 5 more on burst → 10 max
pool_timeout=30      # Wait 30s for a connection before error
pool_recycle=1800    # Recycle connections every 30 min
pool_pre_ping=True   # Check if connection is alive before using it
```

### FastAPI Dependency Injection Pattern:
```python
# In a route:
@router.get("/players")
def list_players(db: Session = Depends(get_db)):
    # db is automatically created, injected, and cleaned up
    return db.query(Player).all()
```

### 🔑 Study questions:
- *What is a connection pool and why not just open a new connection per request?*
- *What does `Depends(get_db)` do in FastAPI?*
- *What is PgBouncer Transaction Mode and why does it matter?*

---

## 7. ORM Models — Your Data Shapes <a name="7-orm-models"></a>

### Entity Relationship Diagram

```
                        ┌──────────────┐
                        │   PLAYERS    │
                        │──────────────│
                        │ puuid (PK)   │
                        │ riot_id      │
                        │ tag_line     │
                        │ region       │
                        └──────┬───────┘
                               │ 1:N
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ PARTICIPANT     │ │ DERIVED         │ │ PARTICIPANT     │
│ _STATS          │ │ _METRICS        │ │ _PERKS          │
│─────────────────│ │─────────────────│ │─────────────────│
│ kills, deaths   │ │ kda             │ │ keystone        │
│ assists, cs     │ │ cs_per_min      │ │ primary_style   │
│ gold, damage    │ │ gold_per_min    │ │ sub_style       │
│ vision, items   │ │ kill_part       │ │ stat shards     │
│ win, role       │ │ damage_share    │ └────────┬────────┘
└────────┬────────┘ │ vision_per_min  │          │
         │          └────────┬────────┘          │
         │                   │                   │
         │          ┌────────┴────────────────────┘
         │          │
         ▼          ▼
┌───────────────────────────────────────────────────────┐
│                     MATCHES (hub)                      │
│───────────────────────────────────────────────────────│
│ match_id (PK), game_duration, queue_id, patch_version │
│ game_creation, platform_id, game_mode                 │
└──────┬──────────┬──────────┬──────────┬───────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌───────────┐┌──────────┐┌──────────┐┌──────────────────┐
│ TEAM      ││ TEAM     ││ DRAFT    ││ MATCH_TIMELINE   │
│ OBJECTIVES││ BANS     ││ ACTIONS  ││──────────────────│
│───────────││──────────││──────────││ frame_interval   │
│ towers    ││ champ_id ││ type     ││                  │
│ dragons   ││ pick_turn││ phase    ││ ┌──────────────┐ │
│ barons    │└──────────┘│ champ_id ││ │ TIMELINE     │ │
│ inhibitors│            │ turn     ││ │ _FRAMES      │ │
│ rift_herd │            └──────────┘│ │ gold, xp, cs │ │
└───────────┘                        │ │ position     │ │
                                     │ └──────────────┘ │
┌────────────────────┐               │ ┌──────────────┐ │
│ CHAMPION_MATCHUPS  │               │ │ TIMELINE     │ │
│ (standalone)       │               │ │ _EVENTS      │ │
│────────────────────│               │ │ type, json   │ │
│ champ_a vs champ_b │               │ └──────────────┘ │
│ role, win_rate     │               └──────────────────┘
│ source, confidence │
└────────────────────┘
```

### Model Summaries (what to know about each):

| Model | Table | Key Columns | Why It Exists |
|-------|-------|-------------|---------------|
| **Match** | `matches` | match_id, game_duration, queue_id, patch | Hub table — everything links here |
| **Player** | `players` | puuid, riot_id, tag_line, region | Player registry |
| **ParticipantStats** | `participant_stats` | kills, deaths, assists, cs, gold, damage, vision, items, win | Raw per-player match data (10 rows per match) |
| **TeamObjectives** | `team_objectives` | towers, dragons, barons, inhibitors, first_X | Per-team objective control (2 rows per match) |
| **TeamBans** | `team_bans` | champion_id, pick_turn | What was banned (up to 10 per match) |
| **DerivedMetrics** | `derived_metrics` | kda, cs_per_min, gold_per_min, kill_part, damage_share, vision_per_min | Computed from raw stats — used by ML |
| **MatchTimeline** | `match_timelines` | frame_interval | Parent for frame-by-frame data |
| **TimelineParticipantFrame** | `timeline_participant_frames` | gold, xp, level, cs, position | Snapshot every ~1 minute |
| **TimelineEvent** | `timeline_events` | event_type, raw_event_json | Kills, objectives, items (stored as JSON) |
| **DraftActions** | `draft_actions` | action_type (PICK/BAN), phase, champion_id, turn | Full draft order |
| **ParticipantPerks** | `participant_perks` | keystone, primary_style, sub_style, stat shards | Rune selections |
| **ChampionMatchup** | `champion_matchups` | champ_a vs champ_b, role, win_rate, confidence | Researched counter-pick data |

### 🔑 Study questions:
- *Why is `matches` considered the "hub" table?*
- *What's the difference between `participant_stats` (raw) and `derived_metrics` (computed)?*
- *Why store timeline events as JSON instead of normalized columns?*
- *What does cascade delete mean and why is it on the Match relationships?*

---

## 8. The API Layer — Every Endpoint <a name="8-api-layer"></a>

### How Routing Works

```
main.py
  └─→ api/router.py           (bundles all sub-routers)
        ├─→ routes/ingest.py   (/ingest/...)
        ├─→ routes/players.py  (/players/...)
        ├─→ routes/matches.py  (/matches/...)
        ├─→ routes/metrics.py  (/metrics/...)
        ├─→ routes/backfill.py (/backfill/...)
        ├─→ routes/analytics.py(/analytics/...)
        ├─→ routes/timeline.py (/timeline/...)
        ├─→ routes/ai.py       (/ai/...)
        ├─→ routes/teams.py    (/teams/...)
        ├─→ routes/champions.py(/champions/...)
        └─→ routes/matchups.py (/matchups/...)
```

### Complete Endpoint Reference

#### 📥 INGESTION (`/ingest`)
| Method | Path | What It Does |
|--------|------|-------------|
| POST | `/ingest/player` | Fetch one player's match history from Riot API and store it. Rate: 10/min |
| POST | `/ingest/players/batch` | Ingest multiple players. Each in isolated DB session. Rate: 3/min |

#### 👤 PLAYERS (`/players`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/players` | List all tracked players sorted by match count |
| GET | `/players/{puuid}` | Get one player's profile |

#### ⚔️ MATCHES (`/matches`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/matches/player/{puuid}` | Player's match history (last 20) |
| GET | `/matches/{match_id}` | Full match detail (both teams, all 10 players) |
| GET | `/matches/{match_id}/draft` | Pick/ban order for a match |

#### 📊 METRICS (`/metrics`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/metrics/player/{puuid}` | Career averages (win rate, KDA, CS/min, etc.) |

#### 🔄 BACKFILL (`/backfill`)
| Method | Path | What It Does |
|--------|------|-------------|
| POST | `/backfill/derived` | Compute derived_metrics for matches missing them |
| GET | `/backfill/status` | Coverage % for derived metrics |
| POST | `/backfill/draft-actions` | Re-fetch draft data for matches missing it |
| POST | `/backfill/participant-perks` | Re-fetch rune data |
| POST | `/backfill/timeline` | Fetch timeline data for matches |
| GET | `/backfill/*/status` | Coverage reports for each data type |

#### 📈 ANALYTICS (`/analytics`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/analytics/player/{puuid}/bans` | Ban analytics (for/against player) |
| GET | `/analytics/champion/{id}/ban-rate` | Ban rate % for a champion |
| GET | `/analytics/bans/most-banned` | Top-20 most banned champions |
| GET | `/analytics/runes/map` | All rune name lookups |
| GET | `/analytics/player/{puuid}/runes` | Player's recent rune choices |
| GET | `/analytics/player/{puuid}/role-performance` | Per-role stats with percentile ranks |
| GET | `/analytics/player/{puuid}/trends` | Rolling window + time series for charts |
| GET | `/analytics/player/{puuid}/champion-stats` | Per-champion performance |
| GET | `/analytics/player/{puuid}/objective-control` | Team objectives when winning vs losing |

#### 🤖 AI / ML (`/ai`)
| Method | Path | What It Does |
|--------|------|-------------|
| POST | `/ai/train/playstyle` | Train KMeans player clustering |
| POST | `/ai/train/win-prediction` | Train win predictor (XGBoost) |
| POST | `/ai/train/matchup-prediction` | Train match-level win predictor |
| POST | `/ai/train/kda-regression` | Train KDA predictor |
| POST | `/ai/train/cs-regression` | Train CS/min predictor |
| POST | `/ai/train/early-game` | Train early-game win predictor |
| POST | `/ai/train/champion-clusters` | Cluster champions into archetypes |
| GET | `/ai/models/status` | Status of all trained models |
| GET | `/ai/playstyle/{puuid}` | Player's playstyle cluster |
| GET | `/ai/predict/{puuid}/{match_id}` | Win probability |
| GET | `/ai/predict/kda/{puuid}/{match_id}` | Expected KDA |
| GET | `/ai/predict/cs/{puuid}/{match_id}` | Expected CS/min |
| GET | `/ai/champions/{puuid}` | Champion recommendations |
| GET | `/ai/early-game/{match_id}` | Early-game prediction from timeline |
| GET | `/ai/threat-weights` | Feature importance weights |
| GET | `/ai/backtest/win-prediction` | Model calibration backtest |

#### 🏆 TEAMS (`/teams`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/teams` | List all team IDs (100=Blue, 200=Red) |
| GET | `/teams/{match_id}/{team_id}` | Full team detail for a match |
| GET | `/teams/{team_id}/matches` | Match history for a team side |
| GET | `/teams/{team_id}/stats` | Aggregate team stats |

#### 🛡️ CHAMPIONS (`/champions`)
| Method | Path | What It Does |
|--------|------|-------------|
| GET | `/champions` | All champions with role/tag/search filters |
| GET | `/champions/by-role/{role}` | Champions for a specific role |
| GET | `/champions/matchup/{a}/{b}` | Head-to-head win rates |
| GET | `/champions/{id}` | Champion detail + tracked performance |

#### ⚖️ MATCHUPS (`/matchups`)
| Method | Path | What It Does |
|--------|------|-------------|
| POST | `/matchups/import/csv` | Bulk import researched matchup data |
| GET | `/matchups` | Query stored matchups with filters |
| GET | `/matchups/{id}/counters` | Champions that beat this one |
| GET | `/matchups/{id}/favors` | Champions this one beats |

### 🔑 Study questions:
- *Why does `/ingest/players/batch` use isolated DB sessions per player?*
- *What's the difference between `backfill` endpoints and regular endpoints?*
- *Why is cursor-based pagination used for timeline events instead of offset?*
- *What happens when you call `/ai/predict` but the model isn't trained?*

---

## 9. The Service Layer — Business Logic <a name="9-service-layer"></a>

Services contain the **real logic**. Routes are thin wrappers that validate
input, call a service, and format the response.

### 9.1 `riot_client.py` — Riot API Wrapper

**What it does:** Manages all HTTP calls to Riot's API with retry logic.

**Key design decisions:**
- **Shared httpx.AsyncClient** — Reuses TCP connections (connection pooling)
- **Global semaphore (3)** — Never sends more than 3 concurrent requests (Riot rate limits)
- **Exponential backoff** — On 429 (rate limited) or 5xx errors, waits 1s, 2s, 4s, etc.
- **Context manager** — `async with RiotClient() as client:` ensures cleanup

**Functions:**
```
get_puuid(game_name, tag_line)       → Resolve "Player#NA1" to their PUUID
get_match_ids(puuid, count, queue)   → Get last N match IDs for a player
get_match(match_id)                  → Get full match data
get_match_timeline(match_id)         → Get minute-by-minute timeline
get_matches_concurrent(ids, ...)     → Batch fetch with rate limiting
```

### 9.2 `ingestion_service.py` — Ingest Orchestrator

**The full flow when you POST `/ingest/player`:**
```
1. Resolve Riot ID → PUUID via riot_client.get_puuid()
2. Fetch recent match IDs via riot_client.get_match_ids()
3. Filter out matches already in DB (crud_ingest.match_exists())
4. Batch-fetch remaining matches (5 concurrent via riot_client)
5. For each match, call crud_ingest.insert_match_bundle_for_player()
6. Return counts: inserted, skipped, failed
```

### 9.3 `ddragon.py` — Static Data Cache

**What is Data Dragon?** Riot publishes static game data (champion names, images,
rune names) at `ddragon.leagueoflegends.com`. This service fetches it **once at
startup** and caches it in memory.

**Three caches:**
- `get_champion_map()` → `{1: "Annie", 2: "Olaf", ...}` (simple name lookup)
- `get_champion_full_map()` → full metadata (image URLs, tags, role affinity, stats)
- `get_rune_map()` → `{8005: "Press the Attack", 8008: "Lethal Tempo", ...}`

### 9.4 `derived_metrics_calculator.py` — The Math

**Pure functions** (no DB access) that compute KPIs:

```python
KDA = (kills + assists) / max(deaths, 1)
CS/min = total_cs / (game_duration_seconds / 60)
Gold/min = gold_earned / (game_duration_seconds / 60)
Kill Participation = (kills + assists) / team_total_kills
Damage Share = player_damage / team_total_damage
Vision/min = vision_score / (game_duration_seconds / 60)
```

### 9.5 `metrics_service.py` — Career Aggregation

Computes career averages for a player:
1. **Primary path:** Uses pre-computed `derived_metrics` table (fast)
2. **Fallback path:** If no derived_metrics exist, computes from raw `participant_stats`

### 9.6 `feature_extractor.py` — ML Feature Engineering

This is where raw DB data becomes ML-ready features. **Most important service
for understanding the AI.**

**Feature types:**

| Feature Set | Count | Used By | Description |
|-------------|-------|---------|-------------|
| Clustering | 14 | Playstyle KMeans | KDA, CS/min, vision, damage %, first blood rate |
| Rolling (20-game) | ~10 | Win/KDA/CS prediction | Last-20-game averages per player |
| Timeline | ~12 | Early-game predictor | Gold/XP/CS diffs at T=10 and T=15 min |
| Champion | varies | Recommendations | Per-champion win rate, KDA, CS by role |

### 9.7 `ai_service.py` — ML Training & Inference

See [Section 10](#10-ml-pipeline) for full details.

### 9.8 `riot_live_service.py` — Hybrid DB/API Stats

**Clever design:** For tracked players, reads stats from DB (instant). For
untracked players, fetches from Riot API (slower but always available). This
means the app works for **any** player, not just ingested ones.

### 9.9 `crud_ingest.py` — Database Writes

**The insert_match_bundle_for_player() function** is the workhorse:
```
One Riot API match response → 6 database tables:
  1. matches         (1 row)
  2. participant_stats (10 rows — all players in the game)
  3. team_objectives  (2 rows — blue + red team)
  4. team_bans       (up to 10 rows)
  5. derived_metrics (1 row — the tracked player)
  6. draft_actions   (up to 20 rows, in a savepoint)
```

**Savepoint pattern:** Draft actions insert inside a `begin_nested()` savepoint.
If draft parsing fails, only the draft is rolled back — the rest of the match
data still commits.

### 🔑 Study questions:
- *Why use a semaphore in riot_client instead of just sending all requests at once?*
- *What is exponential backoff and why is it needed for the Riot API?*
- *Why does the ingestion service check `match_exists()` before fetching?*
- *What's the advantage of the "hybrid DB/API" pattern in riot_live_service?*
- *What is a database savepoint and why is it used for draft_actions?*

---

## 10. The ML Pipeline <a name="10-ml-pipeline"></a>

### Overview of All 6 Models

```
┌─────────────────────────────────────────────────────────────┐
│                    ML MODEL PIPELINE                         │
├──────────────────┬──────────────┬───────────────────────────┤
│  TRAINING        │  MODEL       │  PREDICTION               │
├──────────────────┼──────────────┼───────────────────────────┤
│                  │              │                           │
│ POST /ai/train/  │  .joblib     │  GET /ai/playstyle/       │
│   playstyle      │  files in    │  GET /ai/predict/         │
│   win-prediction │  ml_models/  │  GET /ai/predict/kda/     │
│   kda-regression │              │  GET /ai/predict/cs/      │
│   cs-regression  │              │  GET /ai/early-game/      │
│   early-game     │              │  GET /ai/champions/       │
│   champion-clust │              │                           │
│                  │              │                           │
│  DB data         │  Trained     │  Live features            │
│  → features      │  artifacts   │  → prediction             │
│  → train()       │  on disk     │  → response               │
└──────────────────┴──────────────┴───────────────────────────┘
```

### Model Details

#### 1. Playstyle Clustering (KMeans, k=4)
- **Input:** 14 features per player (avg KDA, CS/min, vision, damage %, etc.)
- **Output:** 4 archetypes: `carry`, `skirmisher`, `support_utility`, `farm_efficiency`
- **Auto-labeling:** Centroids are matched to archetypes based on which features are highest
- **Min data:** 20 players with 10+ ranked games each

#### 2. Win Prediction (XGBoost Classifier)
- **Input:** 27 features — player rolling stats, team averages, opponent stats, differentials
- **Output:** Win probability 0.0–1.0 + top-5 contributing factors
- **Train/test split:** Temporal (oldest 80% / newest 20%) — never random shuffle
- **Min data:** 100 labeled match rows

#### 3. KDA Regression (XGBoost Regressor)
- **Input:** Rolling 20-game averages (no current-game data to avoid leakage)
- **Output:** Expected KDA for next match
- **Min data:** 100 rows

#### 4. CS/min Regression (XGBoost Regressor)
- **Input:** Same as KDA but predicts CS/min
- **Output:** Expected CS/min
- **Min data:** 100 rows

#### 5. Early-Game Predictor (Logistic Regression)
- **Input:** Gold/XP/level/CS differentials at T=10 and T=15 minutes
- **Output:** Win probability based on early-game state
- **Min data:** 50 matches with timeline data

#### 6. Champion Clusters (KMeans, k=3–4)
- **Input:** Champion-level aggregate stats (win rate, KDA, CS/min per champion)
- **Output:** Archetypes: `farm_carry`, `skirmisher`, `utility`, `versatile`
- **Min data:** 8 distinct champions with 3+ games each

### Critical ML Concept: Data Leakage Prevention

Your models carefully avoid **data leakage** — using information from the
current game to predict the current game's outcome:
- Win predictor uses only **prior-game rolling averages** (not current-game stats)
- KDA/CS regressors use only **pre-match features**
- Timeline model uses only **first 15 minutes** (not final game state)

### Model Storage

Models are saved as `.joblib` files in `backend/ml_models/`:
```
win_predictor.joblib          + win_predictor_meta.json
kda_regressor.joblib          + kda_regressor_meta.json
cs_regressor.joblib           + cs_regressor_meta.json
earlygame_predictor.joblib    + earlygame_predictor_meta.json
playstyle_kmeans.joblib
champion_clusters.joblib
matchup_predictor.joblib
```

The `_meta.json` files store: training timestamp, metrics (AUC, RMSE), 
sklearn/xgboost versions for compatibility checking.

### 🔑 Study questions:
- *What is KMeans clustering and why 4 clusters for playstyles?*
- *What is XGBoost and how does it differ from Logistic Regression?*
- *What is data leakage and why is temporal splitting important?*
- *What is ROC-AUC and why is it used to evaluate the win predictor?*
- *What are "feature importances" and how do they help explain predictions?*
- *What does joblib do and why not just save models as JSON?*

---

## 11. Data Flow Walkthroughs <a name="11-data-flows"></a>

### Flow 1: "I want to track a new player"

```
Frontend: POST /ingest/player {game_name: "Faker", tag_line: "KR1", platform: "KR"}
    │
    ▼
routes/ingest.py → ingestion_service.ingest_player()
    │
    ├─ 1. riot_client.get_puuid("Faker", "KR1")
    │      → calls Riot Account-V1 API → returns PUUID
    │
    ├─ 2. crud_ingest.upsert_player(puuid, "Faker", "KR1", "asia")
    │      → INSERT INTO players ... ON CONFLICT UPDATE
    │
    ├─ 3. riot_client.get_match_ids(puuid, count=20, queue=420)
    │      → calls Riot Match-V5 API → returns 20 match IDs
    │
    ├─ 4. Filter: skip IDs already in DB
    │
    ├─ 5. riot_client.get_matches_concurrent(new_ids)
    │      → fetch 5 at a time with rate limiting
    │
    └─ 6. For each match: crud_ingest.insert_match_bundle_for_player()
           → INSERT INTO matches, participant_stats (×10),
             team_objectives (×2), team_bans, derived_metrics,
             draft_actions (in savepoint)
```

### Flow 2: "Show me this player's analytics"

```
Frontend: GET /analytics/player/{puuid}/trends
    │
    ▼
routes/analytics.py
    │
    ├─ 1. Query derived_metrics + participant_stats (last 20 games)
    │
    ├─ 2. feature_extractor.get_rolling_features(db, puuid)
    │      → computes 20-game rolling averages
    │
    ├─ 3. Build per-game time series (KDA, CS/min, win/loss, champion)
    │
    └─ 4. Return {rolling: {...}, per_game: [...]}
```

### Flow 3: "Train the win predictor and make a prediction"

```
Admin: POST /ai/train/win-prediction
    │
    ▼
ai_service.train_win_predictor(db)
    │
    ├─ 1. feature_extractor.get_all_rolling_features_bulk(db)
    │      → SQL query → DataFrame with all players' rolling stats
    │
    ├─ 2. Build feature matrix: player + team + opponent + differential
    │
    ├─ 3. Temporal split: oldest 80% train, newest 20% test
    │
    ├─ 4. Train XGBClassifier + StandardScaler
    │
    ├─ 5. Evaluate: ROC-AUC, accuracy, top feature importances
    │
    └─ 6. Save to ml_models/win_predictor.joblib + meta.json

─── Later ───

Frontend: GET /ai/predict/{puuid}/{match_id}
    │
    ▼
ai_service.predict_win(db, puuid, match_id)
    │
    ├─ 1. Load win_predictor.joblib from disk (cached in memory)
    │
    ├─ 2. feature_extractor.get_win_prediction_features(db, match_id)
    │      → extract player + opponent rolling averages
    │
    ├─ 3. model.predict_proba(features) → [0.37, 0.63]
    │
    └─ 4. Return {prediction: 0.63, confidence: "medium", top_factors: [...]}
```

### Flow 4: "Backfill missing data"

```
Admin: POST /backfill/derived
    │
    ▼
routes/backfill.py
    │
    ├─ 1. Query: matches that have participant_stats but NO derived_metrics
    │
    ├─ 2. For each match: derived_metrics_calculator.compute_derived_metrics()
    │      → pure math: KDA, CS/min, gold/min, etc.
    │
    └─ 3. Bulk INSERT INTO derived_metrics ... ON CONFLICT DO UPDATE
           → handles re-runs safely (idempotent)
```

---

## 12. Key Concepts You Should Be Able to Explain <a name="12-key-concepts"></a>

### Architecture Concepts

| Concept | Where It's Used | One-Sentence Explanation |
|---------|----------------|------------------------|
| **Dependency Injection** | `Depends(get_db)` in routes | FastAPI creates and injects objects (like DB sessions) automatically |
| **Connection Pooling** | `db/session.py` | Reuse database connections instead of opening new ones (faster) |
| **Rate Limiting** | `limiter` on ingest routes | Prevent too many API calls per minute |
| **CORS Middleware** | `main.py` | Allow the frontend (different origin) to call the API |
| **Async/Await** | `riot_client.py`, routes | Non-blocking I/O — one request can wait for Riot API while another serves |
| **Context Manager** | `RiotClient` | Ensures HTTP connections are properly cleaned up (`async with`) |
| **Savepoint** | `crud_ingest.py` | Partial rollback — if draft fails, match data still saves |
| **Lifespan** | `main.py` | Code that runs once at startup/shutdown |
| **Idempotent Operations** | Backfill `ON CONFLICT` | Running the same operation twice produces the same result |
| **Temporal Train/Test Split** | `ai_service.py` | Split by time, not randomly, to avoid future-data leakage |

### Database Concepts

| Concept | Where It's Used | One-Sentence Explanation |
|---------|----------------|------------------------|
| **Foreign Key** | All models → Match | Enforces that a participant_stat row must reference a real match |
| **Cascade Delete** | Match relationships | Deleting a match auto-deletes all its stats, objectives, etc. |
| **Unique Constraint** | `(match_id, puuid)` on derived_metrics | Prevents duplicate rows for the same player in the same match |
| **Index** | `champion_id`, `puuid`, etc. | Speeds up queries that filter by these columns |
| **JSONB** | `timeline_events.raw_event_json` | Store flexible JSON data in PostgreSQL (queryable) |
| **Upsert (ON CONFLICT)** | `crud_ingest.py` | Insert if new, update if already exists |
| **PgBouncer Transaction Mode** | `session.py` pool settings | Connection multiplexer that shares DB connections across clients |

### ML Concepts

| Concept | Where It's Used | One-Sentence Explanation |
|---------|----------------|------------------------|
| **KMeans Clustering** | Playstyle model | Groups players into k similar archetypes based on stats |
| **XGBoost** | Win/KDA/CS prediction | Gradient-boosted decision trees — powerful, handles non-linear patterns |
| **Logistic Regression** | Early-game predictor | Simple classifier — good baseline for binary outcomes |
| **Feature Engineering** | `feature_extractor.py` | Transforming raw data into meaningful inputs for ML models |
| **Rolling Window** | 20-game averages | Smooths out variance by averaging over recent games |
| **Data Leakage** | All models | Accidentally using future/target info during training (invalidates model) |
| **StandardScaler** | Before KMeans/LogReg | Normalizes features to mean=0, std=1 so no feature dominates |
| **ROC-AUC** | Win predictor eval | Area Under the Curve — measures how well the model separates wins/losses |
| **Brier Score** | Calibration backtest | Measures accuracy of probability predictions (lower = better) |
| **Feature Importance** | XGBoost models | Which input features contribute most to the prediction |
| **Bayesian Smoothing** | Champion recommendations | Pulls win rates toward average when sample size is small |

---

## 13. Glossary <a name="13-glossary"></a>

| Term | Definition |
|------|-----------|
| **PUUID** | Player Universally Unique ID — Riot's global player identifier |
| **Riot ID** | Player's display name (e.g., "Faker#KR1") |
| **Queue 420** | Ranked Solo/Duo queue |
| **Team 100/200** | Blue side (100) vs Red side (200) |
| **DDragon / Data Dragon** | Riot's CDN for static game data (champion names, images, etc.) |
| **KDA** | (Kills + Assists) / Deaths — core performance metric |
| **CS** | Creep Score — minions killed |
| **Kill Participation** | % of team kills you were involved in |
| **Damage Share** | % of team damage you dealt |
| **Keystone** | Primary rune (e.g., Conqueror, Electrocute) |
| **Draft** | Champion select phase (picks and bans) |
| **Backfill** | Retroactively computing data for already-stored matches |
| **Temporal Split** | Dividing data by time (train on older, test on newer) |
| **Joblib** | Python library for serializing ML models to disk |
| **Savepoint** | Nested transaction — can roll back independently |
| **Upsert** | INSERT + UPDATE in one operation (ON CONFLICT) |
| **PgBouncer** | Connection pooler that sits between app and PostgreSQL |
| **ASGI** | Async Server Gateway Interface — Python's async web server standard |
| **Uvicorn** | ASGI server that runs FastAPI |

---

## 📚 Suggested Study Order

1. **Start with `main.py`** — understand the app skeleton
2. **Read `core/settings.py` + `db/session.py`** — config and DB connection
3. **Skim the ORM models** — understand the data shapes
4. **Trace the ingestion flow** — `ingest.py` route → `ingestion_service.py` → `riot_client.py` → `crud_ingest.py`
5. **Trace the analytics flow** — `analytics.py` route → `metrics_service.py` → `feature_extractor.py`
6. **Understand the ML pipeline** — `ai.py` route → `feature_extractor.py` → `ai_service.py`
7. **Read the backfill routes** — understand why gaps exist and how they're filled
8. **Explore champions/matchups** — how static data + research data combine

> **Tip:** Run the server locally and hit endpoints with `curl` or the
> auto-generated docs at `http://localhost:8000/docs` (Swagger UI) to see
> real responses.
