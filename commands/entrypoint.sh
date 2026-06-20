#!/bin/sh

# Stop execution if any command fails
set -e

echo "⚙️ Applying migrations..."
alembic -c /app/alembic.ini upgrade head

echo "🌱 Running seed..."
python -m src.utils.seed

echo "🔥 Starting FastAPI server..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000