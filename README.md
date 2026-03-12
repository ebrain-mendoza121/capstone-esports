# Esports Analytics Platform

This repository contains a League of Legends analytics platform with:
- `frontend/`: Next.js application
- `backend/`: FastAPI service configured to use Supabase Postgres via `DATABASE_URL`

## Quick Start

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed setup instructions.

### Prerequisites
- Python 3.11+
- Node.js 18+
- Supabase account (free tier works)
- Riot Games Developer API key

## Backend Quick Start (Supabase)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env
```

Edit `backend/.env` and set your Supabase values:

```env
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
PRISMA_DATABASE_URL=postgresql://postgres.<project-ref>:<db-password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
RIOT_API_KEY=YOUR_RIOT_DEV_KEY
```

Start the backend:

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

## Database Migrations (Prisma)

Prisma is configured in `backend/prisma/schema.prisma` and reads `PRISMA_DATABASE_URL` from `backend/.env`.

```bash
cd backend
npm install
npm run prisma:validate
npm run prisma:pull
npm run prisma:migrate:dev -- --name <change_name>
```

Notes:
- Use the Supabase session pooler URL (`aws-0-<region>.pooler.supabase.com:5432`).
- `DATABASE_URL` is for FastAPI/SQLAlchemy (`postgresql+psycopg://...`).
- `PRISMA_DATABASE_URL` is for Prisma (`postgresql://...`).
- For existing Supabase schemas, run `npm run prisma:pull` first, then create migration steps as needed.
- For production migration rollout, use `npm run prisma:migrate:deploy`.

## Frontend Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Current Backend Endpoints

### Health & Status
- `GET /` - Root status check
- `GET /health` - Health check
- `GET /health/db` - Database connection test
- `GET /db-test` - Database query test

### Ingestion
- `POST /ingest/player` - Fetch and store player match history
  - Body: `{ gameName, tagLine, platform, count, queue }`
  - Queue IDs: 420 (Ranked Solo), 440 (Ranked Flex)

### Players
- `GET /players/` - List all players
- `GET /players/{puuid}` - Get specific player

### Matches
- `GET /matches/player/{puuid}?limit=20` - Get player's match history

### Metrics
- `GET /metrics/player/{puuid}` - Get aggregate player statistics

### Backfill
- `POST /backfill/derived` - Backfill derived metrics
- `GET /backfill/status` - Check metrics coverage
- `POST /backfill/draft-actions` - Backfill draft actions
- `GET /backfill/draft-actions/status` - Check draft actions coverage

### Analytics
- `GET /analytics/player/{puuid}/bans` - Get ban analytics for player
- `GET /analytics/champion/{id}/ban-rate` - Get champion ban rate
- `GET /analytics/bans/most-banned` - Get most banned champions

## Project Structure

```text
capstone-esports/
├── frontend/
│   ├── src/app/          # Next.js pages
│   ├── package.json
│   └── next.config.ts
├── backend/
│   ├── app/
│   │   ├── api/routes/   # API endpoints
│   │   ├── core/         # Configuration
│   │   ├── db/           # Database session & CRUD
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic
│   │   └── main.py       # FastAPI app
│   ├── prisma/
│   │   ├── schema.prisma # Database schema
│   │   └── migrations/   # Migration history
│   ├── package.json      # Node deps (Prisma)
│   └── requirements.txt  # Python deps
├── SETUP_GUIDE.md        # Detailed setup instructions
├── PROJECT_SUMMARY.md    # Project overview
├── IMPLEMENTATION_STATUS.md  # Implementation status
└── README.md             # This file
```

## Documentation

- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Complete setup instructions
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Detailed project overview
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Implementation status and roadmap
- [MODELS_AND_CALCULATIONS.md](MODELS_AND_CALCULATIONS.md) - Database schema and metrics

## Database Schema

The platform uses 7 main tables:
- `players` - Riot account information
- `matches` - Match metadata
- `participant_stats` - Per-player match performance
- `team_objectives` - Team-level objectives (towers, dragons, barons)
- `team_bans` - Champion bans from draft phase
- `draft_actions` - Complete draft tracking (picks and bans)
- `derived_metrics` - Pre-calculated performance metrics (KDA, CS/min, gold/min, etc.)

## Example Usage

### Ingest Player Data
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

### Get Player Metrics
```bash
curl http://localhost:8000/metrics/player/{puuid}
```

### Get Ban Analytics
```bash
curl http://localhost:8000/analytics/player/{puuid}/bans?limit=50
```

## Technology Stack

### Backend
- FastAPI - Web framework
- SQLAlchemy - ORM
- Prisma - Database migrations
- Supabase Postgres - Database
- httpx - Async HTTP client for Riot API

### Frontend
- Next.js 16 - React framework
- React 19 - UI library
- TypeScript - Type safety

## Support

For detailed setup instructions, see [SETUP_GUIDE.md](SETUP_GUIDE.md).

For project overview and features, see [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md).

For implementation status, see [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).
