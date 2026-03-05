#!/usr/bin/env bash
set -e

cd backend
set -a
source .env.prod
set +a

source .venv/bin/activate
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000