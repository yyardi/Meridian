#!/usr/bin/env bash
# launch_stream_slate.sh <league> <minutes> <tag>
#
# The whole slate off the venue's WebSocket, read-only. It costs NO request
# budget, so it is the only instrument that scales to a 49-game Saturday: REST
# sampling four games already starves the live recorder's 12 of 20 req/s.
#
# Each run writes into its own directory under reads/stream/<tag>. Two runs
# overlap in time on purpose -- one resolves the slate at its start and only
# subscribes games tipping within --lookahead-hours, so a later wave needs a
# later run -- and two processes appending to one game's file is a corrupt tape,
# not a longer one. Separate directories make the overlap harmless.
set -euo pipefail
L=$1; M=${2:-300}; TAG=${3:-$L}
OUT=/opt/meridian/artifacts/reads/stream/$TAG
mkdir -p "$OUT"
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
docker run -d --rm --name "stream-$TAG" --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb -v "$OUT":/out -w /app \
  "$API" sh -c "python cfb/run_stream_slate.py --league $L --minutes $M --lookahead-hours 4 --out-dir /out > /out/_recorder.log 2>&1"
