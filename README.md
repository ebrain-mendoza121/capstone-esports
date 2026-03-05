# Esports Analytics Platform

League of Legends analytics platform that ingests player match data from the Riot Games API and provides REST API endpoints for querying player statistics and performance metrics.

## Quick Start

```bash
# Start database
cd infra && docker-compose up -d

# Setup backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment (create backend/.env)
RIOT_API_KEY=YOUR_RIOT_DEV_KEY
DATABASE_URL=postgresql+psycopg://esports:esports@localhost:5432/esports
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Run migrations
alembic upgrade head

# Start server (from backend directory)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API Documentation: http://localhost:8000/docs

## Documentation

- **SETUP_GUIDE.md** - Complete setup instructions for local and production environments
- **TECHNICAL_DOCUMENTATION.md** - Technical reference (architecture, algorithms, API endpoints, database models)
- **README.md** - This file (quick start and overview)

## Features

- Player ingestion via Riot API with automatic retry logic
- Match history storage with participant statistics
- Derived metrics calculation (KDA, CS/min, gold/min, kill participation, damage share, vision/min)
- Backfill system for historical data
- Coverage tracking (≥95% goal)
- PostgreSQL with Alembic migrations

## Tech Stack

- Python 3.11, FastAPI, PostgreSQL 16, SQLAlchemy 2.0, Alembic, httpx, Uvicorn

## Example Usage

```bash
# Ingest player data
curl -X POST http://localhost:8000/ingest/player \
  -H "Content-Type: application/json" \
  -d '{"gameName": "Doublelift", "tagLine": "NA1", "platform": "NA", "count": 20}'

# Check metrics coverage
curl http://localhost:8000/backfill/status

# Get player metrics
curl http://localhost:8000/metrics/player/{puuid}
```

## Project Structure

```
esports-capstone/
├── backend/
│   ├── app/
│   │   ├── api/routes/      # API endpoints
│   │   ├── core/            # Settings
│   │   ├── db/              # Database operations
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   └── services/        # Business logic
│   ├── alembic/             # Database migrations
│   └── requirements.txt
└── infra/
    └── docker-compose.yml   # PostgreSQL container
```

## Need Help?

See **SETUP_GUIDE.md** for:
- Detailed setup instructions
- Environment configuration (local vs production)
- Troubleshooting common issues
- Database management
- Development workflow