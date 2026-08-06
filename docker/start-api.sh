#!/bin/sh
set -e
cd /app

echo "Waiting for PostgreSQL..."
i=0
until pg_isready -h 127.0.0.1 -p 5432 -U postgres >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "PostgreSQL did not become ready in time, continuing anyway."
    break
  fi
  sleep 1
done

echo "Waiting for ChromaDB..."
i=0
until curl -sf "http://127.0.0.1:${CHROMA_PORT:-8001}/api/v1/heartbeat" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "ChromaDB did not become ready in time, continuing anyway."
    break
  fi
  sleep 1
done

alembic upgrade head
python scripts/seed.py

exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
