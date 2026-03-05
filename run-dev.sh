#!/usr/bin/env bash
set -e

echo "Starting database..."
cd infra
docker compose up -d

cd ..

echo "Starting backend..."
cd backend
source .venv/bin/activate
exec python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
