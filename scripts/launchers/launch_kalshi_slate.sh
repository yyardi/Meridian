#!/usr/bin/env bash
# launch_kalshi_slate.sh <series-csv> <date-tags-csv> <minutes> <tag>
#
# Kalshi's in-play books and prints for one slate, off its websocket, to
# reads/kalshi/<tag> -- the twin of launch_stream_slate.sh on the other venue, so
# the two tapes can be matched instant to instant (docs/math/cross-venue-inplay-football.md).
# One signed socket (the KALSHI_* lines in .env), no REST after discovery, places nothing.
#
#   launch_kalshi_slate.sh KXNFLGAME,KXNFLSPREAD 26OCT04 740 nfl-1004
#   launch_kalshi_slate.sh KXNCAAFGAME,KXNCAAFSPREAD 26OCT03,26OCT04 800 cfb-1003
set -euo pipefail
S=$1; D=$2; M=${3:-600}; TAG=${4:-kalshi}
OUT=/opt/meridian/artifacts/reads/kalshi/$TAG
mkdir -p "$OUT"
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
docker run -d --rm --name "kalshi-$TAG" --memory 256m --env-file /opt/meridian/.env \
  -v /opt/meridian/core:/app/core:ro -v "$OUT":/out -w /app \
  "$API" sh -c "python -m core.kalshi.book_recorder --series $S --date $D --minutes $M --out /out > /out/_recorder.log 2>&1"
