# Esports Analytics Platform - Setup Guide

Complete guide for setting up and running the application in different environments.

---

## Prerequisites

Before starting, ensure you have:

- **Python 3.11** installed
- **Docker** and **Docker Compose** installed
- **Riot Developer API Key** (get one at https://developer.riotgames.com/)
- **Git** installed

---

## Initial Setup (One-Time)

### 1. Clone the Repository

```bash
git clone <repository-url>
cd esports-capstone
```

### 2. Create Python Virtual Environment

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Configuration

You have two options for running the application:

### Option A: Local Development (Recommended)
Uses Docker PostgreSQL running on your machine.

### Option B: Production/Supabase
Uses a hosted PostgreSQL database (e.g., Supabase, AWS RDS, etc.).

---

## Option A: Local Development Setup

### Step 1: Create Local Environment File

Create `backend/.env` with the following content:

```env
DATABASE_URL=postgresql+psycopg://esports:esports@localhost:5432/esports
RIOT_API_KEY=YOUR_RIOT_API_KEY_HERE
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

**Replace `YOUR_RIOT_API_KEY_HERE`** with your actual Riot API key.

### Step 2: Start PostgreSQL Database

```bash
# From project root
cd infra
docker-compose up -d
```

**Verify database is running:**
```bash
docker ps
# Should show: esports_db container running on port 5432
```

### Step 3: Run Database Migrations

```bash
cd ../backend
alembic upgrade head
```

**Expected output:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 499c867b9244, create phase 1 raw tables
INFO  [alembic.runtime.migration] Running upgrade 499c867b9244 -> 670ed9082d20, add derived metrics table
```

### Step 4: Start the API Server

**Option 1: Run from backend directory (recommended)**
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Option 2: Run from project root**
```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 5: Verify Server is Running

Open your browser and navigate to:
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

---

## Option B: Production/Supabase Setup

### Step 1: Get Database Connection String

If using Supabase:
1. Go to your Supabase project
2. Navigate to Settings → Database
3. Copy the connection string (URI format)
4. Note: Use the "Connection Pooling" string for better performance

Example format:
```
postgresql+psycopg://user:password@host:5432/postgres?sslmode=require
```

### Step 2: Create Production Environment File

Create `backend/.env.prod` with the following content:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
RIOT_API_KEY=YOUR_RIOT_API_KEY_HERE
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://your-production-domain.com
```

**Important:**
- Replace `USER`, `PASSWORD`, `HOST` with your actual database credentials
- If your password contains special characters, URL-encode them:
  - `@` → `%40`
  - `#` → `%23`
  - `$` → `%24`
  - `%` → `%25`
  - `&` → `%26`

### Step 3: Load Production Environment

```bash
cd backend
# Copy .env.prod to .env
cp .env.prod .env
```

**Or manually set environment variables:**
```bash
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
export RIOT_API_KEY="YOUR_RIOT_API_KEY_HERE"
export CORS_ORIGINS='["http://localhost:5173","http://localhost:3000"]'
```

### Step 4: Run Database Migrations

```bash
cd backend
alembic upgrade head
```

### Step 5: Start the API Server

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Switching Between Environments

### Method 1: Using Different .env Files

**Switch to Local:**
```bash
cd backend
cp .env.local .env  # If you have .env.local
# Or just edit .env to use local DATABASE_URL
```

**Switch to Production:**
```bash
cd backend
cp .env.prod .env
```

### Method 2: Using Environment Variables

**For Local:**
```bash
export DATABASE_URL="postgresql+psycopg://esports:esports@localhost:5432/esports"
export RIOT_API_KEY="YOUR_KEY"
```

**For Production:**
```bash
export DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
export RIOT_API_KEY="YOUR_KEY"
```

### Verify Active Database

```bash
cd backend
python -c "from app.core.settings import settings; print(settings.DATABASE_URL)"
```

---

## Testing the Application

### 1. Health Check

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{"status": "healthy"}
```

### 2. Ingest Player Data

```bash
curl -X POST http://localhost:8000/ingest/player \
  -H "Content-Type: application/json" \
  -d '{
    "gameName": "Doublelift",
    "tagLine": "NA1",
    "platform": "NA",
    "count": 5
  }'
```

**Expected response:**
```json
{
  "puuid": "...",
  "platform": "NA",
  "routing": "americas",
  "inserted": 5,
  "skipped": 0,
  "failed": 0
}
```

### 3. Check Metrics Coverage

```bash
curl http://localhost:8000/backfill/status
```

**Expected response:**
```json
{
  "total_matches": 5,
  "with_derived_metrics": 5,
  "missing_derived_metrics": 0,
  "coverage_percentage": 100.0,
  "meets_95_percent_goal": true
}
```

### 4. Query Player Metrics

```bash
curl http://localhost:8000/players/
```

---

## Database Management

### Connect to Local Database

```bash
docker exec -it esports_db psql -U esports -d esports
```

**Useful SQL commands:**
```sql
-- List all tables
\dt

-- Count records
SELECT COUNT(*) FROM players;
SELECT COUNT(*) FROM matches;
SELECT COUNT(*) FROM derived_metrics;

-- View recent matches
SELECT match_id, game_creation, queue_id 
FROM matches 
ORDER BY game_creation DESC 
LIMIT 5;

-- Exit
\q
```

### Reset Local Database

**Warning: This deletes all data!**

```bash
# Stop the server first (Ctrl+C)

# Downgrade database
cd backend
alembic downgrade base

# Upgrade again
alembic upgrade head
```

### Backup Local Database

```bash
docker exec esports_db pg_dump -U esports esports > backup.sql
```

### Restore Local Database

```bash
docker exec -i esports_db psql -U esports esports < backup.sql
```

---

## Common Issues & Solutions

### Issue 1: Port 5432 Already in Use

**Error:** `port is already allocated`

**Solution:**
```bash
# Check what's using port 5432
lsof -i :5432

# Stop existing PostgreSQL
brew services stop postgresql  # macOS
sudo systemctl stop postgresql  # Linux

# Or change port in docker-compose.yml
ports:
  - "5433:5432"  # Use 5433 instead
# Then update DATABASE_URL to use port 5433
```

### Issue 2: RIOT_API_KEY Not Found

**Error:** `Field required [type=missing, input_value={}, input_type=dict]`

**Solution:**
- Ensure `.env` file exists in `backend/` directory
- Check that `RIOT_API_KEY=` line has no spaces
- Verify the API key is valid at https://developer.riotgames.com/

### Issue 3: Database Connection Failed

**Error:** `could not connect to server`

**Solution:**
```bash
# Check if database is running
docker ps

# Restart database
cd infra
docker-compose restart

# Check logs
docker logs esports_db
```

### Issue 4: Migration Already Applied

**Error:** `Target database is not up to date`

**Solution:**
```bash
# Check current version
alembic current

# Check history
alembic history

# If needed, downgrade and upgrade
alembic downgrade -1
alembic upgrade head
```

### Issue 5: Rate Limited by Riot API

**Error:** `429 Too Many Requests`

**Solution:**
- Wait 2 minutes before retrying
- Reduce `count` parameter in ingestion requests
- Development keys have limits: 20 requests/second, 100 requests/2 minutes

### Issue 6: CORS Error in Frontend

**Error:** `Access-Control-Allow-Origin`

**Solution:**
- Add your frontend URL to `CORS_ORIGINS` in `.env`
- Format: `CORS_ORIGINS=http://localhost:5173,http://localhost:3000`
- Restart the server after changing `.env`

---

## Development Workflow

### Daily Development

```bash
# 1. Start database (if not running)
cd infra
docker-compose up -d

# 2. Activate virtual environment
cd ../backend
source .venv/bin/activate

# 3. Start server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Make changes to code (server auto-reloads)

# 5. When done, stop server (Ctrl+C)
```

### After Pulling New Code

```bash
# 1. Update dependencies
cd backend
pip install -r requirements.txt

# 2. Run new migrations
alembic upgrade head

# 3. Restart server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Creating New Migrations

```bash
# After modifying models in backend/app/models/
cd backend
alembic revision --autogenerate -m "describe your changes"
alembic upgrade head
```

---

## Production Deployment Checklist

- [ ] Use production database (not local Docker)
- [ ] Set strong database password
- [ ] Enable SSL for database connection (`?sslmode=require`)
- [ ] Use production Riot API key (if available)
- [ ] Update `CORS_ORIGINS` with production domain
- [ ] Remove `--reload` flag from uvicorn command
- [ ] Use a process manager (systemd, supervisor, PM2)
- [ ] Set up reverse proxy (nginx, Caddy)
- [ ] Enable HTTPS
- [ ] Set up monitoring and logging
- [ ] Configure database backups
- [ ] Set environment variables securely (not in .env file)

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `RIOT_API_KEY` | Yes | - | Riot Games API key |
| `RIOT_ROUTING` | No | `americas` | Regional routing (americas, europe, asia, sea) |
| `CORS_ORIGINS` | No | `[]` | Comma-separated list of allowed origins |
| `HTTP_TIMEOUT_SECONDS` | No | `15.0` | HTTP request timeout |
| `RIOT_MAX_RETRIES` | No | `6` | Max retry attempts for Riot API |
| `RIOT_BACKOFF_BASE_SECONDS` | No | `1.0` | Base backoff time for retries |

---

## Quick Reference Commands

```bash
# Start local database
cd infra && docker-compose up -d

# Stop local database
cd infra && docker-compose down

# View database logs
docker logs esports_db

# Run migrations
cd backend && alembic upgrade head

# Start server (from backend dir)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Check server health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs

# Connect to database
docker exec -it esports_db psql -U esports -d esports
```

---

## Support

For issues or questions:
1. Check the error message and consult "Common Issues" section
2. Review logs: `docker logs esports_db` or server console output
3. Verify environment variables: `python -c "from app.core.settings import settings; print(settings.DATABASE_URL)"`
4. Check Riot API status: https://developer.riotgames.com/api-status/
