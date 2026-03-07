# Esports Analytics Platform - Project Summary

## Overview
A comprehensive League of Legends analytics platform that ingests player match data from the Riot Games API, stores it in PostgreSQL, computes derived performance metrics, and provides REST API endpoints for querying player statistics, draft analytics, and match insights. The system supports automated data ingestion, backfill operations, and advanced analytics including ban analysis and champion statistics.

---

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.11)
- **Database:** PostgreSQL 16 (Docker)
- **ORM:** SQLAlchemy 2.0
- **Migrations:** Alembic
- **HTTP Client:** httpx (async)
- **Server:** Uvicorn with uvloop
- **Environment Management:** python-dotenv, pydantic-settings

### Infrastructure
- **Containerization:** Docker Compose
- **Database Container:** postgres:16
- **Virtual Environment:** Python venv
- **Deployment Scripts:** Shell scripts for dev/prod environments

---

## Database Schema

### 1. `players`
Stores Riot account information
- `id` (PK, auto-increment)
- `riot_id` - Game name (with comment)
- `tag_line` - Account tag (with comment)
- `puuid` - Unique player identifier (indexed, unique, with comment)
- `region` - Routing region (e.g., "americas")
- `created_at` - Timestamp

### 2. `matches`
Match metadata
- `match_id` (PK, string)
- `game_creation` - Unix timestamp (indexed)
- `game_duration` - Seconds (normalized)
- `queue_id` - Game mode identifier (indexed)
- `patch_version` - Game version
- `created_at` - Timestamp

### 3. `participant_stats`
Player performance per match
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `player_id` (FK → players, indexed)
- `team_id` - 100 or 200
- `champion` - Champion name (indexed)
- `role` - Lane position (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
- `kills`, `deaths`, `assists`
- `gold_earned` - Total gold
- `total_damage` - Damage to champions
- `cs` - Creep score (minions + jungle)
- `vision_score`
- `win` - Boolean

### 4. `team_objectives`
Team-level objectives per match
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `team_id` - 100 or 200
- `towers`, `dragons`, `barons` - Objective counts
- `win_flag` - Boolean

### 5. `team_bans`
Champion bans from draft phase
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `team_id` - 100 or 200 (with comment)
- `champion_id` - Banned champion ID (indexed, with comment)
- `pick_turn` - Ban order 1-5 per team (with comment)
- Composite index on (match_id, team_id)

### 6. `draft_actions`
Complete draft phase tracking (picks and bans)
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `team_id` - 100 or 200 (with check constraint)
- `action_type` - PICK or BAN (enum, indexed)
- `phase` - PICK or BAN (enum)
- `champion_id` - Champion involved (indexed)
- `role` - Position for picks (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY), NULL for bans (indexed)
- `turn` - Order within phase per team (1-5)
- `action_order` - Optional global draft order
- Unique constraint on (match_id, phase, team_id, turn)
- Multiple composite indexes for efficient queries

### 7. `derived_metrics`
Pre-calculated performance metrics per player per match
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `puuid` (FK → players, indexed)
- `kda` - Kill/Death/Assist ratio
- `cs_per_min` - Creep score per minute
- `gold_per_min` - Gold per minute
- `kill_participation` - Team kill participation rate (0.0-1.0)
- `damage_share` - Team damage share (0.0-1.0)
- `vision_per_min` - Vision score per minute
- Unique constraint on (match_id, puuid)

---

## API Endpoints

### Health & Status
- `GET /` - Root status check
- `GET /health` - Health check
- `GET /db-test` - Database connection test

### Ingestion
- `POST /ingest/player` - Fetch and store player + match history
  - **Request:** `{ gameName, tagLine, platform, count, queue }`
  - **Response:** `{ puuid, platform, routing, inserted, skipped, failed }`
  - Fetches up to 100 recent matches for a player
  - Supports platform validation (NA, EUW, KR, etc.)
  - Queue filtering (420=Ranked Solo, 440=Ranked Flex)

### Players
- `GET /players/` - List all players
- `GET /players/{puuid}` - Get specific player details

### Matches
- `GET /matches/player/{puuid}?limit=20` - Get player's match history
  - Returns matches ordered by most recent
  - Joins with participant_stats and player tables

### Metrics
- `GET /metrics/player/{puuid}` - Calculate aggregate player statistics
  - Returns: matches played, win rate, KDA, CS/min, gold/min, vision/min

### Backfill Operations
- `POST /backfill/derived` - Backfill derived metrics for existing matches
  - **Parameters:** `puuid` (optional) - Target specific player
  - **Response:** `{ status, message, processed, failed, failed_matches }`
- `GET /backfill/status` - Check derived metrics coverage
  - **Parameters:** `puuid` (optional) - Check specific player
  - **Response:** `{ total_matches, with_derived_metrics, missing_derived_metrics, coverage_percentage, meets_95_percent_goal }`
- `POST /backfill/draft-actions` - Backfill draft actions for existing matches
  - **Response:** `{ status, message, processed, failed, failed_matches }`
- `GET /backfill/draft-actions/status` - Check draft actions coverage
  - **Response:** `{ total_matches, with_draft_actions, missing_draft_actions, coverage_percentage }`

### Analytics
- `GET /analytics/player/{puuid}/bans` - Get ban analytics for a player
  - **Parameters:** `limit` (default: 100) - Number of matches to analyze
  - **Response:** Bans against player, bans by team, most banned champions, statistics
- `GET /analytics/champion/{champion_id}/ban-rate` - Get ban rate for a champion
  - **Response:** `{ champion_id, total_matches, times_banned, ban_rate }`
- `GET /analytics/bans/most-banned` - Get most banned champions globally
  - **Parameters:** `limit` (default: 20)
  - **Response:** List of champions with ban counts

---

## Core Services

### 1. `RiotClient` (riot_client.py)
HTTP client for Riot Games API with:
- Automatic retry logic (up to 6 retries)
- Exponential backoff for rate limits (429) and server errors (5xx)
- Configurable timeout (15 seconds default)
- Methods:
  - `get_puuid(game_name, tag_line, routing)` - Account-V1 API
  - `get_match_ids(puuid, routing, count, start, queue)` - Match-V5 API
  - `get_match(match_id, routing)` - Match-V5 API

### 2. `IngestionService` (ingestion_service.py)
Orchestrates data ingestion:
1. Fetches player PUUID from Riot API
2. Upserts player record in database
3. Fetches list of recent match IDs (with queue filtering)
4. For each match:
   - Checks if already exists (skip if yes)
   - Fetches full match details
   - Normalizes game duration (handles patch 11.20 change)
   - Inserts match, participant stats, team objectives, team bans
   - Inserts draft actions (picks and bans)
   - Computes and upserts derived metrics
5. Returns summary: inserted, skipped, failed counts

### 3. `MetricsService` (metrics_service.py)
Calculates aggregate player statistics:
- Queries all matches for a player
- Computes totals and averages
- Returns calculated metrics (KDA, CS/min, gold/min, etc.)

### 4. `DerivedMetricsCalculator` (derived_metrics_calculator.py)
Pure functions for metric computation:
- `normalize_game_duration()` - Handles Riot API duration format changes
- `compute_derived_metrics()` - Calculates all 6 performance metrics
- `extract_team_participants()` - Filters team members for calculations
- Handles edge cases: zero deaths, zero team stats, zero duration

### 5. `CRUD Operations` (crud_ingest.py)
Database operations:
- `upsert_player()` - Insert or update player
- `match_exists()` - Check if match already stored
- `insert_match_bundle_for_player()` - Insert match + stats + objectives + bans + draft actions + metrics atomically
- Role-to-turn mapping for deterministic pick order
- Automatic deletion of existing draft_actions on re-ingestion

---

## Configuration

### Environment Variables (backend/.env)
```
RIOT_API_KEY=RGAPI-xxxxx
DATABASE_URL=postgresql+psycopg://esports:esports@localhost:5432/esports
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### Settings (settings.py)
- `RIOT_API_KEY` - Required
- `DATABASE_URL` - PostgreSQL connection string
- `HTTP_TIMEOUT_SECONDS` - Default: 15.0
- `RIOT_MAX_RETRIES` - Default: 6
- `RIOT_BACKOFF_BASE_SECONDS` - Default: 1.0
- `CORS_ORIGINS` - Comma-separated string or JSON array (default: "http://localhost:5173")
- Automatic .env file resolution from backend directory

### Platform Support
Supported platforms with automatic routing:
- **Americas:** NA, BR, LAN, LAS → "americas"
- **Asia:** KR, JP → "asia"
- **Europe:** EUNE, EUW, ME1, TR, RU → "europe"
- **SEA:** OCE, SG2, TW2, VN2 → "sea"

### Docker Compose (infra/docker-compose.yml)
PostgreSQL container:
- Port: 5432
- User: esports
- Password: esports
- Database: esports
- Persistent volume: esports_pgdata
- Container name: esports_db

### Deployment Scripts
- `run-dev.sh` - Start database and backend with .env.local
- `run-prod.sh` - Start backend with .env.prod
- `stop-dev.sh` - Stop all services and deactivate venv

---

## Project Structure

```
esports-capstone/
├── backend/
│   ├── .env.example           # Example environment file
│   ├── .env.local             # Local development config
│   ├── .env.prod              # Production config
│   ├── .venv/                 # Python virtual environment
│   ├── requirements.txt       # Python dependencies
│   ├── alembic.ini            # Alembic configuration
│   ├── alembic/
│   │   ├── versions/          # Migration files
│   │   │   ├── 499c867b9244_create_phase_1_raw_tables.py
│   │   │   ├── e22f3c14ba64_create_derived_metrics_table.py
│   │   │   ├── f0a6ca7bbdf5_clarify_players_region_stores_routing.py
│   │   │   ├── 35d07bf9aaeb_add_team_bans_table.py
│   │   │   └── cbda3e7830e3_add_draft_actions_table.py
│   │   └── env.py             # Alembic environment
│   ├── matchV5-schema.yaml    # Riot API schema reference
│   └── app/
│       ├── main.py            # FastAPI application entry
│       ├── api/
│       │   ├── router.py      # Main API router
│       │   └── routes/        # Route modules
│       │       ├── ingest.py      # Player ingestion
│       │       ├── players.py     # Player queries
│       │       ├── matches.py     # Match queries
│       │       ├── metrics.py     # Aggregate metrics
│       │       ├── backfill.py    # Backfill operations
│       │       └── analytics.py   # Ban analytics
│       ├── core/
│       │   └── settings.py    # Pydantic settings with .env resolution
│       ├── db/
│       │   ├── session.py     # Database connection
│       │   └── crud_ingest.py # CRUD operations with draft actions
│       ├── models/            # SQLAlchemy models
│       │   ├── player.py
│       │   ├── match.py
│       │   ├── participant_stats.py
│       │   ├── team_objectives.py
│       │   ├── team_bans.py
│       │   ├── draft_actions.py
│       │   └── derived_metrics.py
│       ├── schemas/           # Pydantic schemas
│       │   └── ingest.py      # Platform enum and validation
│       ├── services/          # Business logic
│       │   ├── riot_client.py
│       │   ├── ingestion_service.py
│       │   ├── metrics_service.py
│       │   └── derived_metrics_calculator.py
│       └── utils/
├── frontend/
│   ├── .env.example
│   └── src/
│       └── apt.ts
├── infra/
│   └── docker-compose.yml     # PostgreSQL container
├── comparison.txt             # Capstone implementation plan
├── run-dev.sh                 # Development startup script
├── run-prod.sh                # Production startup script
├── stop-dev.sh                # Shutdown script
├── README.md                  # Quick start guide
├── SETUP_GUIDE.md             # Detailed setup instructions
├── MODELS_AND_CALCULATIONS.md # Database and metrics documentation
├── IMPLEMENTATION_SUMMARY.md  # Implementation details
└── PROJECT_SUMMARY.md         # This file
```

---

## Current Status

### ✅ Completed Features
- Database schema with 7 tables (players, matches, participant_stats, team_objectives, team_bans, draft_actions, derived_metrics)
- Complete Alembic migration history
- FastAPI application with CORS support
- Riot API client with retry logic and exponential backoff
- Player ingestion with platform validation and queue filtering
- Automatic derived metrics computation during ingestion
- Draft actions tracking (picks and bans)
- Backfill system for derived metrics and draft actions
- Coverage tracking endpoints (≥95% goal monitoring)
- Ban analytics endpoints (player bans, champion ban rates, most banned)
- Query endpoints (players, matches, metrics)
- Docker Compose setup for PostgreSQL
- Deployment scripts for dev and prod environments
- Comprehensive documentation (README, SETUP_GUIDE, MODELS_AND_CALCULATIONS, IMPLEMENTATION_SUMMARY)

### 🎯 Key Capabilities
- **Automated Ingestion:** Fetch and store player match history with single API call
- **Derived Metrics:** 6 performance metrics computed automatically (KDA, CS/min, gold/min, kill participation, damage share, vision/min)
- **Draft Intelligence:** Complete draft phase tracking with picks, bans, roles, and turn order
- **Ban Analytics:** Player-specific ban analysis, champion ban rates, global ban statistics
- **Backfill Operations:** Populate historical data for existing matches
- **Coverage Monitoring:** Track data completeness with percentage goals
- **Platform Support:** 15 regional platforms with automatic routing
- **Error Handling:** Robust retry logic, edge case handling, transaction safety

### 📊 Data Quality
- Game duration normalization (handles Riot API patch 11.20 change)
- Edge case handling (zero deaths, zero team stats, missing fields)
- Upsert logic prevents duplicates
- Foreign key cascades ensure referential integrity
- Unique constraints on critical combinations
- Comprehensive indexing for query performance

### 🔄 Future Enhancements (from comparison.txt)
The project has a roadmap for advanced features:
- **Timeline Data:** Match timeline frames and events for spatial analysis
- **Map Analytics:** Position tracking, heatmaps, gank detection, teamfight analysis
- **Machine Learning:** Draft win probability, mid-game predictions, team performance evaluation
- **Advanced Analytics:** Synergy scores, counter matchups, role performance, macro metrics
- **Dashboard:** React-based visualization with interactive charts and recommendations

### 📋 Potential Next Steps
- Implement timeline ingestion (match_timeline_frames, match_timeline_events tables)
- Add spatial analytics (map regions, position classification, movement patterns)
- Build ML models (draft prediction, win probability, performance scoring)
- Create frontend dashboard with React
- Add authentication/authorization
- Implement rate limiting for API endpoints
- Add caching layer for frequently accessed data
- Create aggregation endpoints (champion stats, role performance)
- Add batch ingestion for multiple players
- Implement filtering/sorting on match queries

---

## Running the Application

### Quick Start (Development)
```bash
# Using the convenience script
./run-dev.sh
```

### Manual Start (Development)

#### Start Database
```bash
cd infra
docker-compose up -d
```

#### Run Migrations
```bash
cd backend
alembic upgrade head
```

#### Start API Server
```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Start
```bash
./run-prod.sh
```

### Stop Services
```bash
./stop-dev.sh
```

### Example API Calls

#### Ingest Player Data
```bash
curl -X POST http://localhost:8000/ingest/player \
  -H "Content-Type: application/json" \
  -d '{
    "gameName": "Doublelift",
    "tagLine": "NA1",
    "platform": "NA",
    "count": 20,
    "queue": 420
  }'
```

#### Check Coverage
```bash
curl http://localhost:8000/backfill/status
```

#### Get Player Ban Analytics
```bash
curl http://localhost:8000/analytics/player/{puuid}/bans?limit=50
```

#### Get Most Banned Champions
```bash
curl http://localhost:8000/analytics/bans/most-banned?limit=20
```

#### Backfill Draft Actions
```bash
curl -X POST http://localhost:8000/backfill/draft-actions
```

---

## Dependencies (requirements.txt)

**Core Framework:**
- fastapi==0.131.0
- uvicorn==0.41.0
- starlette==0.52.1

**Database:**
- sqlalchemy==2.0.46
- alembic==1.18.4
- psycopg==3.3.3 (PostgreSQL adapter)
- psycopg-binary==3.3.3

**Data Validation:**
- pydantic==2.12.5
- pydantic-settings==2.13.1
- pydantic_core==2.41.5

**HTTP Client:**
- httpx==0.28.1 (async HTTP client)
- httpcore==1.0.9

**Utilities:**
- python-dotenv==1.2.1
- uvloop==0.22.1 (performance)
- watchfiles==1.1.1 (auto-reload)
- click==8.3.1
- PyYAML==6.0.3

**Type Support:**
- typing-extensions==4.15.0
- typing-inspection==0.4.2
- annotated-types==0.7.0
- annotated-doc==0.0.4

**Template Engine:**
- Mako==1.3.10 (for Alembic)
- MarkupSafe==3.0.3

**Network:**
- certifi==2026.1.4
- idna==3.11
- h11==0.16.0
- httptools==0.7.1
- websockets==16.0
- anyio==4.12.1

---

## Key Features & Implementation Details

### Draft Actions System
The draft_actions table provides comprehensive draft phase tracking:
- **Dual Tracking:** Both team_bans (legacy) and draft_actions (unified) tables
- **Pick Order:** Deterministic turn assignment based on role (TOP=1, JUNGLE=2, MIDDLE=3, BOTTOM=4, UTILITY=5)
- **Ban Filtering:** Automatically filters championId=-1 (no ban)
- **Re-ingestion Safe:** Deletes existing draft_actions before inserting new data
- **Comprehensive Indexing:** 9 indexes for efficient querying by match, team, phase, role, champion

### Derived Metrics System
Automatic computation of 6 performance metrics:
- **KDA:** (kills + assists) / max(deaths, 1) - handles perfect KDA
- **CS/min:** Total CS divided by game minutes
- **Gold/min:** Gold earned divided by game minutes
- **Kill Participation:** (kills + assists) / team_kills - handles zero team kills
- **Damage Share:** player_damage / team_damage - handles zero team damage
- **Vision/min:** Vision score divided by game minutes

All metrics handle edge cases and use normalized game duration.

### Game Duration Normalization
Riot API changed duration format in patch 11.20:
- **Pre-11.20:** gameDuration in milliseconds
- **Post-11.20:** gameDuration in seconds (when gameEndTimestamp exists)
- **Solution:** Automatic detection and normalization to seconds

### Platform & Routing System
- **15 Platforms:** NA, BR, LAN, LAS, KR, JP, EUNE, EUW, ME1, TR, RU, OCE, SG2, TW2, VN2
- **4 Routing Regions:** americas, asia, europe, sea
- **Automatic Mapping:** Platform enum validates and maps to correct routing
- **Case Insensitive:** Platform validation normalizes to uppercase

### Error Handling & Resilience
- **Retry Logic:** Up to 6 retries with exponential backoff
- **Rate Limit Handling:** Automatic backoff on 429 responses
- **Transaction Safety:** Failed matches don't poison entire batch
- **Upsert Operations:** Prevents duplicates on re-ingestion
- **Edge Case Handling:** Zero deaths, zero team stats, missing fields

### Coverage Tracking
- **Real-time Monitoring:** Calculate coverage percentage on-demand
- **Goal Tracking:** Boolean flag for ≥95% coverage goal
- **Per-player or Global:** Support for both scopes
- **Multiple Datasets:** Separate tracking for derived_metrics and draft_actions

### API Design Patterns
- **Dependency Injection:** Database sessions via FastAPI Depends
- **Pydantic Validation:** Request/response schemas with field validators
- **Async Operations:** Non-blocking I/O for Riot API calls
- **RESTful Design:** Resource-based endpoints with standard HTTP methods
- **Error Responses:** HTTPException with appropriate status codes

---

## Notes

- All timestamps use UTC
- Match IDs follow Riot's format: `{platform}_{matchId}`
- PUUID is the primary player identifier across Riot services
- API uses async/await for non-blocking I/O
- Database transactions ensure data consistency
- Failed match ingestions don't poison the entire batch
- championId=-1 indicates no ban (filtered out)
- Role field is NULL for bans, populated for picks
- Team IDs are always 100 or 200
- Queue ID 420 = Ranked Solo/Duo, 440 = Ranked Flex
- Coverage percentage goal is 95% for derived metrics
- Draft actions use deterministic turn order based on role
- Settings automatically resolve .env file from backend directory
- CORS origins support comma-separated string or JSON array format

---

## Architecture Highlights

### Data Flow
```
User Request
    ↓
FastAPI Endpoint
    ↓
Service Layer (Business Logic)
    ↓
CRUD Layer (Database Operations)
    ↓
SQLAlchemy Models
    ↓
PostgreSQL Database
```

### Ingestion Pipeline
```
Riot API
    ↓
RiotClient (retry + backoff)
    ↓
IngestionService (orchestration)
    ↓
CRUD Operations (atomic transactions)
    ↓
Database (7 tables)
```

### Metrics Computation
```
Match JSON
    ↓
normalize_game_duration()
    ↓
extract_team_participants()
    ↓
compute_derived_metrics()
    ↓
Upsert to derived_metrics table
```

### Analytics Query
```
User Request
    ↓
Analytics Endpoint
    ↓
SQLAlchemy Query (joins + aggregations)
    ↓
Response Formatting
    ↓
JSON Response
```

---

## Documentation Files

- **README.md** - Quick start guide and overview
- **SETUP_GUIDE.md** - Detailed setup instructions for local and production
- **MODELS_AND_CALCULATIONS.md** - Database schema and metric formulas
- **IMPLEMENTATION_SUMMARY.md** - Implementation details and testing results
- **PROJECT_SUMMARY.md** - This file (comprehensive project overview)
- **comparison.txt** - Complete capstone implementation plan with future roadmap
