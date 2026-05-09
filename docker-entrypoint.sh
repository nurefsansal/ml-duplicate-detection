#!/bin/sh
set -e
cd /app

if [ -n "${SKIP_DB_MIGRATIONS:-}" ]; then
  echo "SKIP_DB_MIGRATIONS is set; skipping database migrations."
else
  echo "Running database migrations..."
  python backend/migrations/run_migration.py
fi

exec "$@"
