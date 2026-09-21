#!/usr/bin/env bash
# Meridian schedule pings, run off the api image with the checkout mounted.
#
#   schedule_ping.sh --hours 24              the day's slate, once
#   schedule_ping.sh --starting-within 15    ping what tips soon
#   schedule_ping.sh --hours 24 --dry-run    print, send nothing
#
# The DATABASE_URL is written here. The previous version grepped it out of
# launch_live_ladder.sh, so retiring that script on 2026-09-19 broke the
# every-five-minutes tipoff ping instantly and silently: a wrapper that reads
# its configuration out of an UNRELATED script has a dependency nobody can
# see from either end.
set -euo pipefail
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
exec docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -e MERIDIAN_READS_DIR=/out \
  -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts \
  -v /opt/meridian/artifacts/reads:/out -w /app "$API" \
  python3 scripts/game_schedule.py "$@"
