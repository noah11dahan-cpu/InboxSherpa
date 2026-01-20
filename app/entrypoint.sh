#!/bin/sh
set -e

# Only one container should run migrations to avoid race conditions.
# Default: run migrations unless explicitly disabled.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic -c /app/alembic.ini upgrade head
fi

exec "$@"
