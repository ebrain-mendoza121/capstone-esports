# Esports Analytics Platform

This repository contains:
- `frontend/`: Next.js application
- `backend/`: FastAPI service configured to use Supabase Postgres via `DATABASE_URL`

## Backend Quick Start (Supabase)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## Current Backend Endpoints

- `GET /health`
- `GET /health/db`

## Project Structure

```text
capstone-esports/
├── frontend/
└── backend/
    ├── app/
    │   ├── api/routes/
    │   ├── core/
    │   └── db/
    ├── prisma/
    ├── package.json
    └── requirements.txt
```
