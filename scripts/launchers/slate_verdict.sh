#!/usr/bin/env bash
# Tonight's verdict: scan every stream tape the slate produced, gated on how
# fresh BOTH legs of a crossing were, and push the two lines that matter.
set -euo pipefail
R=/opt/meridian/artifacts/reads
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
REPORT=$R/slate_verdict_$STAMP.txt
API=$(docker inspect meridian-api --format "{{.Config.Image}}")

# Every tape the verdict has not read yet, dated by its tag -- never a clock
# window. On 2026-09-24 the verdict rolled a day and the previous night's
# WNBA and MLB tapes aged out of a twenty-hour window unread. A tape whose
# recorder is still up waits for the next run; a read tape gets a marker.
RUNNING=$(docker ps --format '{{.Names}}' | sed -n 's/^stream-//p' | tr '\n' ' ')
PAIRS=$(python3 /opt/meridian/scripts/launchers/verdict_tapes.py --root "$R"/stream --running $RUNNING)
[ -n "$PAIRS" ] || { echo "no unread stream tapes"; exit 0; }
DIRS=""; HOST_DIRS=""; DATES=""
while read -r d p; do
  DIRS="$DIRS /out/stream/$(basename "$p")"; HOST_DIRS="$HOST_DIRS $p"
  case " $DATES " in *" $d "*) ;; *) DATES="$DATES $d";; esac
done <<EOF_PAIRS
$PAIRS
EOF_PAIRS
echo "tapes to read:$DIRS"

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

# The edge ledger: one row per league per gate per TAPE DATE, appended to
# edge_ledger.jsonl so the running table answers "is the number solid". A
# late verdict files each tape under the night it recorded, not under today.
LEDGER_RC=1
for TD in $DATES; do
  TD_DIRS=""
  while read -r d p; do [ "$d" = "$TD" ] && TD_DIRS="$TD_DIRS /out/stream/$(basename "$p")"; done <<EOF_PAIRS
$PAIRS
EOF_PAIRS
  docker run --rm --network meridian_default --env-file /opt/meridian/.env \
    -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts -v "$R":/out -w /app "$API" \
    python3 scripts/edge_ledger.py --date "$TD" --dirs $TD_DIRS >> "$REPORT" 2>&1 && LEDGER_RC=0
done
echo; sed -n "/^edge_ledger:/,\$p" "$REPORT"
# Mark the tapes read only once the ledger has their rows; a failed ledger
# leaves them unmarked for the next run rather than silently dropped.
[ "$LEDGER_RC" -eq 0 ] && python3 /opt/meridian/scripts/launchers/verdict_tapes.py --root "$R"/stream --mark $HOST_DIRS >> "$REPORT" 2>&1

# Did anyone trade THROUGH the displayed quote while each over-floor crossing
# stood? A quote that prints trade through is a picture, not a resting order;
# on 2026-09-21, 8 of 29 were. The verdict carries the count so the ledger's
# dollars are read beside it.
docker run --rm -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts -v "$R":/out -w /app "$API" \
  python3 scripts/launchers/phantom_check.py --gate 2 >> "$REPORT" 2>&1 || true
echo; tail -n 1 "$REPORT"

# Does core.fees still match what the venue recorded in the last day? The
# venue raised its coefficient 0.06 -> 0.0695 on 2026-09-17 and nothing
# compared the constant to the field for four days. This line does.
docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts -w /app "$API" \
  python3 scripts/fee_drift.py >> "$REPORT" 2>&1 || true
FEELINE=$(grep -E '^FEE ' "$REPORT" | tail -1)
echo; echo "$FEELINE"

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
$FEELINE
Full table: $REPORT''', tags='microscope', timeout=15)
" || true
