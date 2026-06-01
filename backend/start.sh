#!/bin/sh
set -eu

if [ "${RUN_DB_MIGRATIONS_ON_START:-false}" = "true" ]; then
  python -m alembic upgrade head
fi

exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
