#!/usr/bin/env bash
# NIGHTLY SCAN + PUSH. Runs the strategy scan over every league and venue on
# tape, writes the full table to artifacts/reads, and pushes a terse summary to
# ntfy. The topic is read from .env and NEVER echoed.
#
#   crontab (UTC):  40 4 * * *  sudo -n /opt/meridian/scripts/nightly_scan.sh
#
# The push carries the DISTRIBUTION first, because with ~250 cells the best one
# is large by construction: under a pure null the top |t| is ~3.2 and P(any
# cell > 3) is ~0.74. A striking cell is the modal output of noise. The full
# cell table and the nominations live in the artifact, which the dashboard reads.
set -u
# SCAN_SINCE is a PARTITION BOUNDARY, written here rather than left to the
# environment so the exclusion is visible in version control. Without it the
# query does two serial full scans of all five market_snapshots partitions per
# league pattern (planner cost 7,023,098); with it, 4,671,180 -- a 33.5% cut,
# because August alone costs 2,525,216 to return a few thousand rows that
# predate every league we scan. It must sit ON a boundary: 2026-08-25 lands
# inside the August partition and made the cost go UP. The scan refuses a
# non-boundary value and prints the floor it used on its coverage line, so a
# reader never sees a close count without seeing what was excluded to get it.
cd /opt/meridian || exit 1
OUT=/opt/meridian/artifacts/reads; mkdir -p "$OUT"
TS=$(date -u +%Y-%m-%dT%H%MZ)
F="$OUT/scan_$TS.txt"
IMG=$(docker inspect meridian-api --format "{{.Config.Image}}" 2>/dev/null || echo meridian-api)

# The api IMAGE with the checkout mounted, never `docker exec` into the running
# container: that one carries whatever code it was built with (2026-09-13: it was
# eight days stale and died on a module that was sitting on the box).
docker run --rm -i --network meridian_default \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -e SETTLE_CACHE="$OUT/settlements.json" \
  -e SCAN_SINCE="${SCAN_SINCE:-2026-09-01}" \
  -e ROWS_JSON="$OUT/scan_rows.json" -e CELLS_JSON="$OUT/scan_cells.json" \
  -v /opt/meridian/core:/app/core -v /opt/meridian/strategies:/app/strategies \
  -v /opt/meridian/artifacts:/opt/meridian/artifacts -w /app \
  "$IMG" python - < cfb/run_scan.py > "$F" 2>&1
RC=$?
echo "exit $RC" >> "$F"

# --- the push: distribution first, then the nominations, then the coverage ---
DIST=$(grep -A5 "=== DISTRIBUTION" "$F" | grep -E "cells excluding|Var\(t\)|max\|t\|" \
       | sed 's/^ *//' | tr '\n' ' ' | cut -c1-220)
# NOT a top-three leaderboard. The best of ~250 cells is large by construction, and a
# nightly leaderboard of noise draws would train exactly the habit the pre-registration
# exists to break -- the numbers win that fight against a caveat in the same 480 chars.
# What goes in this slot is the only per-cell fact that means anything before stage 2:
# how many cleared the nomination bar. Usually 0. When it is not, THAT is worth a push.
NOM=$(grep -cE "NOMINATED" "$F" 2>/dev/null || echo 0)
COV=$(grep -E "^markets with a pregame close|^settled |^cells scored" "$F" | tr '\n' ' ' | cut -c1-120)
MSG="SCAN $TS
$COV
$DIST
$NOM cells cleared the nomination bar
null: best of ~250 cells shows |t|~3.2 by chance -- the spread is the result, not the max
full table: $F"
MSG=$(printf '%s' "$MSG" | cut -c1-480)

TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  curl -s -m 20 -H "Title: Meridian nightly scan" -d "$MSG" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 \
    && echo "pushed" >> "$F" || echo "push failed" >> "$F"
else
  echo "no ntfy topic in .env; not pushed" >> "$F"
fi
echo "wrote $F"
