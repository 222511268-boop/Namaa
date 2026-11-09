#!/usr/bin/env sh
# Run the Playwright end-to-end suite against an isolated Docker stack (project "namaa-e2e").
# Needs internet access for map tiles and Sentinel-2 data.
# Usage: scripts/test-e2e.sh [playwright args]     e.g. scripts/test-e2e.sh e2e/map.spec.ts
#        KEEP_STACK=1 scripts/test-e2e.sh          keep the stack running afterwards
set -e
cd "$(dirname "$0")/.."
export E2E_PORT="${E2E_PORT:-3200}"
COMPOSE="docker compose -p namaa-e2e --env-file .env -f docker-compose.yml -f docker-compose.e2e.yml"

$COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true
$COMPOSE up -d --build --wait
status=0
(cd frontend && E2E_BASE_URL="http://127.0.0.1:${E2E_PORT}" npx playwright test "$@") || status=$?
if [ -z "$KEEP_STACK" ]; then $COMPOSE down -v --remove-orphans >/dev/null; fi
exit $status
