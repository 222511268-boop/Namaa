#!/usr/bin/env sh
# Run the backend test suite inside Docker against the dedicated namaa_test database.
# Usage: scripts/test-backend.sh [pytest args]       e.g. scripts/test-backend.sh -k pipeline
#        NAMAA_LIVE=1 scripts/test-backend.sh tests/test_live_sentinel.py -s
set -e
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
docker compose up -d db >/dev/null
docker compose run --rm --no-deps \
  -e DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/namaa_test" \
  -e NAMAA_LIVE="${NAMAA_LIVE:-0}" \
  -v "$(pwd)/backend:/app" \
  backend python -m pytest "$@"
