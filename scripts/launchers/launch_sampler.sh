#!/usr/bin/env bash
# launch_sampler.sh <winner-slug> <minutes>
# READ-ONLY ladder sampler: no tickets, no phone. For families the fill test is
# not registered on (basketball, baseball) -- measure only.
set -euo pipefail
S=$1; M=${2:-200}
G=${S#aec-*-}   # the game key without aec-<league>-; a fixed ${S:8} left WNBA names with a leading hyphen (sexec--atl-ny)
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
docker run -d --rm --name "sampler-${G:0:20}" --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts/reads:/out -w /app \
  "$API" sh -c "python cfb/run_live_ladder.py --prefix $S --every 20 --minutes $M > /out/live_ladder_${S}.txt 2>&1"
