# Esports Analytics Platform - Project Summary

## Overview
A League of Legends analytics platform that ingests player match data from the Riot Games API, stores it in a PostgreSQL database, and provides REST API endpoints for querying player statistics and performance metrics.

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

---

## Database Schema

### 1. `players`
Stores Riot account information
- `id` (PK, auto-increment)
- `riot_id` - Game name
- `tag_line` - Account tag
- `puuid` - Unique player identifier (indexed)
- `region` - Routing region (e.g., "americas")
- `created_at` - Timestamp

### 2. `matches`
Match metadata
- `match_id` (PK, string)
- `game_creation` - Unix timestamp (indexed)
- `game_duration` - Seconds
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
- `role` - Lane position
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

### 5. `derived_metrics`
Pre-calculated performance metrics per player per match
- `id` (PK, auto-increment)
- `match_id` (FK → matches, indexed)
- `puuid` (FK → players, indexed)
- `kda` - Kill/Death/Assist ratio
- `cs_per_min` - Creep score per minute
- `gold_per_min` - Gold per minute
- `kill_participation` - Team kill participation rate
- `damage_share` - Team damage share
- `vision_per_min` - Vision score per minute
- Unique constraint on (match_id, puuid)

---

## API Endpoints

### Health & Status
- `GET /` - Root status check
- `GET /health` - Health check

### Ingestion
- `POST /ingest/player` - Fetch and store player + match history
  - **Request:** `{ gameName, tagLine, count }`
  - **Response:** `{ puuid, inserted, skipped, failed }`
  - Fetches up to 100 recent matches for a player

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

---

## Core Services

### 1. `RiotClient` (riot_client.py)
HTTP client for Riot Games API with:
- Automatic retry logic (up to 6 retries)
- Exponential backoff for rate limits (429) and server errors (5xx)
- Configurable timeout (15 seconds default)
- Methods:
  - `get_puuid(game_name, tag_line)` - Account-V1 API
  - `get_match_ids(puuid, count, start)` - Match-V5 API
  - `get_match(match_id)` - Match-V5 API

### 2. `IngestionService` (ingestion_service.py)
Orchestrates data ingestion:
1. Fetches player PUUID from Riot API
2. Upserts player record in database
3. Fetches list of recent match IDs
4. For each match:
   - Checks if already exists (skip if yes)
   - Fetches full match details
   - Inserts match, participant stats, and team objectives
5. Returns summary: inserted, skipped, failed counts

### 3. `MetricsService` (metrics_service.py)
Calculates aggregate player statistics:
- Queries all matches for a player
- Computes totals and averages
- Returns calculated metrics (KDA, CS/min, gold/min, etc.)

### 4. `CRUD Operations` (crud_ingest.py)
Database operations:
- `upsert_player()` - Insert or update player
- `match_exists()` - Check if match already stored
- `insert_match_bundle_for_player()` - Insert match + stats + objectives atomically

---

## Configuration

### Environment Variables (backend/.env)
```
RIOT_API_KEY=RGAPI-xxxxx
DATABASE_URL=postgresql://esports:esports@localhost:5432/esports
```

### Settings (settings.py)
- `RIOT_API_KEY` - Required
- `RIOT_ROUTING` - Default: "americas"
- `HTTP_TIMEOUT_SECONDS` - Default: 15.0
- `RIOT_MAX_RETRIES` - Default: 6
- `RIOT_BACKOFF_BASE_SECONDS` - Default: 1.0

### Docker Compose (infra/docker-compose.yml)
PostgreSQL container:
- Port: 5432
- User: esports
- Password: esports
- Database: esports
- Persistent volume: esports_pgdata

---

## Project Structure

```
esports-capstone/
├── backend/
│   ├── .env                    # Environment variables
│   ├── .venv/                  # Python virtual environment
│   ├── requirements.txt        # Python dependencies
│   ├── alembic.ini            # Alembic configuration
│   ├── alembic/
│   │   ├── versions/          # Migration files
│   │   │   ├── 499c867b9244_create_phase_1_raw_tables.py
│   │   │   └── 670ed9082d20_add_derived_metrics_table.py
│   │   └── env.py             # Alembic environment
│   └── app/
│       ├── main.py            # FastAPI application entry
│       ├── api/
│       │   ├── router.py      # Main API router
│       │   └── routes/        # Route modules
│       │       ├── ingest.py
│       │       ├── players.py
│       │       ├── matches.py
│       │       └── metrics.py
│       ├── core/
│       │   └── settings.py    # Pydantic settings
│       ├── db/
│       │   ├── session.py     # Database connection
│       │   └── crud_ingest.py # CRUD operations
│       ├── models/            # SQLAlchemy models
│       │   ├── player.py
│       │   ├── match.py
│       │   ├── participant_stats.py
│       │   ├── team_objectives.py
│       │   └── derived_metrics.py
│       ├── schemas/           # Pydantic schemas
│       │   └── ingest.py
│       └── services/          # Business logic
│           ├── riot_client.py
│           ├── ingestion_service.py
│           └── metrics_service.py
├── infra/
│   └── docker-compose.yml     # PostgreSQL container
└── README.md
```

---

## Current Status

### ✅ Completed
- Database schema designed and migrated (5 tables)
- FastAPI application structure complete
- Riot API client with retry logic
- Player ingestion endpoint functional
- Basic query endpoints (players, matches, metrics)
- Docker Compose setup for PostgreSQL
- Alembic migrations configured

### 🔄 In Progress
- Derived metrics table created but not yet populated
- Metrics calculation currently done on-demand (not pre-computed)

### 📋 Potential Next Steps
- Populate derived_metrics table during ingestion
- Add batch ingestion for multiple players
- Implement caching for frequently accessed metrics
- Add filtering/sorting to match queries
- Create aggregation endpoints (champion stats, role performance)
- Add frontend application
- Implement authentication/authorization
- Add rate limiting for API endpoints

---

## Running the Application

### Start Database
```bash
cd infra
docker-compose up -d
```

### Run Migrations
```bash
cd backend
alembic upgrade head
```

### Start API Server
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Example API Call
```bash
curl -X POST http://localhost:8000/ingest/player \
  -H "Content-Type: application/json" \
  -d '{"gameName": "PlayerName", "tagLine": "NA1", "count": 20}'
```

---

## Dependencies (requirements.txt)

**Core:**
- fastapi==0.131.0
- uvicorn==0.41.0
- sqlalchemy==2.0.46
- alembic==1.18.4
- pydantic==2.12.5
- pydantic-settings==2.13.1

**Database:**
- psycopg==3.3.3 (PostgreSQL adapter)

**HTTP:**
- httpx==0.28.1 (async HTTP client)
- httpcore==1.0.9

**Utilities:**
- python-dotenv==1.2.1
- uvloop==0.22.1 (performance)
- watchfiles==1.1.1 (auto-reload)

---

## Notes

- All timestamps use UTC
- Match IDs follow Riot's format: `{region}_{matchId}`
- PUUID is the primary player identifier across Riot services
- API uses async/await for non-blocking I/O
- Database transactions ensure data consistency
- Failed match ingestions don't poison the entire batch
