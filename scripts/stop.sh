#!/usr/bin/env bash
# Stop everything Meridian is running and let the Mac sleep again.
#
#   ./scripts/stop.sh
#
# Safe to run when things are already stopped — every step is a no-op then.
# Nothing here deletes data; the databases and every recorded row survive.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

echo "Stopping dashboard..."
pkill -f "uvicorn core.api:app" && echo "  stopped" || echo "  not running"

echo "Stopping containers..."
docker compose down

echo "Releasing the sleep guard..."
pkill caffeinate && echo "  stopped" || echo "  not running"

echo
echo "Done. Verifying nothing is left:"
printf "  port 8008:   "
lsof -nP -iTCP:8008 -sTCP:LISTEN >/dev/null 2>&1 && echo "STILL IN USE" || echo "free"
printf "  containers:  "
test -z "$(docker compose ps -q)" && echo "none running" || echo "STILL RUNNING"
printf "  caffeinate:  "
pgrep -x caffeinate >/dev/null && echo "STILL RUNNING" || echo "stopped"
echo
echo "Recording has stopped. Market snapshots cannot be backfilled, so do not"
echo "leave it off through a game."
