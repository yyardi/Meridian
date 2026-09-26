#!/usr/bin/env bash
# launch_stream_exec.sh <winner-slug> <minutes> [attempt_usd] [fresh_s]
# Ticket a ladder off the venue's STREAM at update resolution, fresh legs only.
# Costs no REST budget: it opens the public markets socket and nothing else.
# The third argument was the $25 floor until 2026-09-26; it is now the attempt
# a ticket is sized to and gated by (core/ladder/intent.py), the planner's number.
set -euo pipefail
S=$1; M=${2:-215}; ATTEMPT=${3:-20}; FRESH=${4:-2}
G=${S#aec-*-}   # the game key without aec-<league>-; a fixed ${S:8} left WNBA names with a leading hyphen (sexec--atl-ny)
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
docker run -d --rm --name "sexec-${G:0:20}" --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb \
  -v /opt/meridian/artifacts/reads:/out -w /app \
  "$API" sh -c "python cfb/run_stream_executor.py --prefix $S --minutes $M --attempt-usd $ATTEMPT --fresh-s $FRESH > /out/stream_exec_${S}.txt 2>&1"
