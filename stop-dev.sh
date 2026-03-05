#!/usr/bin/env bash
set -e

echo "Stopping Esports Backend..."

# Kill uvicorn process if running
if pgrep -f "uvicorn app.main:app" > /dev/null
then
    echo "Stopping FastAPI server..."
    pkill -f "uvicorn app.main:app"
else
    echo "FastAPI server not running."
fi

# Stop Docker containers
echo "Stopping database..."
cd infra
docker compose down
cd ..

# Deactivate venv if active
if [[ "$VIRTUAL_ENV" != "" ]]
then
    echo "Deactivating virtual environment..."
    deactivate 2>/dev/null || true
fi

echo "Shutdown complete."
