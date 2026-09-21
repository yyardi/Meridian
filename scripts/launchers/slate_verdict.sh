#!/usr/bin/env bash
# Tonight's verdict: scan every stream tape the slate produced, gated on how
# fresh BOTH legs of a crossing were, and push the two lines that matter.
set -euo pipefail
R=/opt/meridian/artifacts/reads
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
REPORT=$R/slate_verdict_$STAMP.txt
API=$(docker inspect meridian-api --format "{{.Config.Image}}")

# Only tapes written in the last 20 hours: tonight's slate, not every slate
# on disk. Saturday's 1.1 GB would otherwise be rescanned every night.
DIRS=""
for d in $(find "$R"/stream -mindepth 1 -maxdepth 1 -type d -mmin -1200); do
  case "$d" in *smoke*|*_fixture*) continue;; esac
  DIRS="$DIRS /out/stream/$(basename "$d")"
done
[ -n "$DIRS" ] || { echo "no stream tapes"; exit 0; }

docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -v /opt/meridian/core:/app/core -v "$R":/out \
  -v "$R"/slate_freshness_scan.py:/app/s.py -w /app "$API" \
  python s.py $DIRS > "$REPORT" 2>&1 || true
cat "$REPORT"

# The settlement P&L the operator asked for: every ticket written today,
# held to settlement against the venue's final score, three sizings, split
# by which detector wrote it. Appended to the same report.
DATE=$(date -u -d "6 hours ago" +%Y-%m-%d)
docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -v /opt/meridian/core:/app/core -v "$R":/out \
  -v "$R"/slate_pnl.py:/app/p.py -w /app "$API" \
  python p.py "$DATE" >> "$REPORT" 2>&1 || true
echo; tail -n +2 "$REPORT" | sed -n "/HYPOTHETICAL/,\$p"

# The edge ledger: one row per league per gate for tonight's tapes, appended
# to edge_ledger.jsonl so the running table answers "is the number solid".
docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts -v "$R":/out -w /app "$API" \
  python3 scripts/edge_ledger.py --date "$DATE" >> "$REPORT" 2>&1 || true
echo; sed -n "/^edge_ledger:/,\$p" "$REPORT"

# The headline is the 2-second row: crossings whose two legs the venue was
# publishing at the same instant. That number, not the ungated one, is what
# decides whether there is anything to trade.
FRESH=$(awk '$1=="2s"{print $2" crossings, "$3" over $25"}' "$REPORT" | head -1)
ANY=$(awk '$1=="any"{print $2" crossings, "$3" over $25"}' "$REPORT" | head -1)
GAMES=$(head -1 "$REPORT")
docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -e MERIDIAN_READS_DIR=/out -v /opt/meridian/core:/app/core -v "$R":/out -w /app "$API" \
  python3 -c "
import sys; sys.path.insert(0,'/app')
from core import notify
notify.push('schedule', 'Slate verdict $STAMP',
  '''$GAMES
both legs quoted within 2s: $FRESH
no freshness gate at all:   $ANY
Full table: $REPORT''', tags='microscope', timeout=15)
" || true
