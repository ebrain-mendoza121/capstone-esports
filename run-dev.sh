#!/usr/bin/env bash
set -e

echo "Starting database..."
cd infra
docker compose up -d
cd ..

echo "Starting backend..."
cd backend

# Load local environment variables
if [ -f ".env.local" ]; then
  set -a
  source .env.local
  set +a
else
  echo "ERROR: backend/.env.local not found"
  exit 1
fi

source .venv/bin/activate
exec python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000