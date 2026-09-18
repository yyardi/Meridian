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

# --- THE PAPER BOOK, every registered strategy, priced at the pregame close and
# settled by the venue. The operator asked for nightly numbers on the strategies,
# and the scan reports CELLS, which are a different object: a cell is a price
# decile inside a market type, a strategy is a rule somebody registered. Until now
# the strategy table ran only in the Monday and daily reads and never reached the
# push, so the one surface the operator reads carried the object they did not ask
# about. Runs off the api image because settlement needs the venue client; a warm
# settlement cache makes it minutes, not the two hours a cold one costs.
PB="$OUT/paper_book_$TS.txt"
docker run --rm -i --network meridian_default \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -e SETTLE_CACHE="$OUT/settlements.json" \
  -e PB_JSON="$OUT/paper_book_$TS.json" \
  -v /opt/meridian/core:/app/core -v /opt/meridian/strategies:/app/strategies \
  -v /opt/meridian/artifacts:/opt/meridian/artifacts -w /app \
  "$IMG" python - < cfb/run_paper_book.py > "$PB" 2>&1
PB_RC=$?
echo "paper book: $PB (exit $PB_RC)" >> "$F"

# The strategy line. Counted from the ALL WEEKS table, which is the one with a
# verdict per strategy. `grep -c` prints its count and RETURNS 1 on no match, so
# it is never given a `|| echo` fallback here -- that is the defect that put a
# stray bare zero above the nomination count on every healthy night.
if [ "$PB_RC" -eq 0 ] && grep -q "strategy, ALL WEEKS" "$PB" 2>/dev/null; then
  PB_N=$(sed -n '/strategy, ALL WEEKS/,$p' "$PB" | grep -cE "spans 0|excludes 0|UNDERPOWERED")
  PB_POS=$(grep -cE "POSITIVE, excludes 0" "$PB")
  PB_LINE="strategies $PB_N tested, $PB_POS excluding zero"
  # A line that excludes zero is the only per-strategy fact worth 480 characters,
  # and it is named rather than counted so the operator can check its twin.
  # Name, MEAN and INTERVAL, not the name alone. A bare strategy name in a push
  # is an invitation to act on a number nobody has seen, and the arm closest to
  # nominating (mlb_spread_yes_70_100, +15.51c, G=11 at 09-15) is the away-team
  # confound: YES is the AWAY side on this venue, so a YES-side price-bucket
  # nomination has a home twin that must be read beside it before it means
  # anything -- three such headlines have already been this confound. The
  # caution is attached to the SHAPE (`_yes_`), not to any particular arm, so it
  # fires for arms that do not exist yet. This changes the PUSH only; the gate
  # is untouched, because tuning a decision rule around the arm you can see
  # about to trip it is how a rule stops being pre-registered.
  if [ "$PB_POS" -gt 0 ]; then
    NOM=$(grep -E "POSITIVE, excludes 0" "$PB" \
          | awk '{printf "%s %s %s%s ", $1, $(NF-5), $(NF-4), $(NF-3)}' | cut -c1-200)
    PB_LINE="$PB_LINE: $NOM"
    grep -E "POSITIVE, excludes 0" "$PB" | grep -q "_yes_" \
      && PB_LINE="$PB_LINE[YES-side = AWAY: read the home twin before believing]"
  fi
else
  # Absent, not zero -- the same distinction the scan half of this script makes.
  PB_LINE="strategies NOT COUNTED: paper book exit $PB_RC, no ALL WEEKS table"
fi

# --- the push: distribution first, then the nominations, then the coverage ---
DIST=$(grep -A5 "=== DISTRIBUTION" "$F" | grep -E "cells excluding|Var\(t\)|max\|t\|" \
       | sed 's/^ *//' | tr '\n' ' ' | cut -c1-220)
# NOT a top-three leaderboard. The best of ~250 cells is large by construction, and a
# nightly leaderboard of noise draws would train exactly the habit the pre-registration
# exists to break -- the numbers win that fight against a caveat in the same 480 chars.
# What goes in this slot is the only per-cell fact that means anything before stage 2:
# how many cleared the nomination bar. Usually 0. When it is not, THAT is worth a push.
# ★ NO `|| echo 0` HERE. `grep -c` PRINTS "0" AND RETURNS 1 when nothing
# matches, so the fallback appended a SECOND zero and this expanded to
# "0\n0", rendering the push as:
#     0
#     0 cells cleared the nomination bar
# on every healthy null night. `grep -c` always prints a count, so the only
# case needing a default is a missing file, which gives an empty string.
NOM=$(grep -cE "NOMINATED" "$F" 2>/dev/null); NOM=${NOM:-0}
COV=$(grep -E "^markets with a pregame close|^settled |^cells scored" "$F" | tr '\n' ' ' | cut -c1-120)

# ★ THE 05:28Z RUN OF 2026-09-14 EXITED 1 (a json.dump TypeError) and this block
# still pushed "0 cells cleared the nomination bar" -- the SAME sentence a healthy
# null night prints. The push was indistinguishable from success at the only place
# the operator actually looks. A count over a table that was never written is not
# zero, it is absent, so on a non-zero exit the body says so and carries the last
# line of the traceback. The nomination line is only earned by a completed run.
# ★ TWO MORE SHAPES, FOUND BY RUNNING THIS BLOCK AGAINST SIX ARTIFACTS.
#
# 1. `raise SystemExit("msg")` PRINTS NO EXCEPTION NAME. Python writes the bare
#    message, so `^...(Error|Exception):` never matches and the push said "no
#    exception line in the artifact" while the artifact's last line stated the
#    reason in plain English. Every guard in run_scan.py exits that way -- NO
#    DATA, the SCAN_SINCE boundary refusal, the SCAN_EXPECT mismatch,
#    like_to_needle, the ambiguous-slug check -- so the SIX most likely failures
#    all threw their reason away. Falls back to the artifact's last real line.
#
# 2. EXIT 0 HAVING WRITTEN NOTHING read as a healthy null night: blank coverage,
#    blank distribution, then "0 cells cleared the nomination bar" and the null
#    caveat -- the exact sentence this block was changed to stop printing.
#    Reachable: `python - < cfb/run_scan.py` on an EMPTY or truncated file reads
#    nothing, runs nothing and exits 0. A count over a table that was never
#    written is not zero whether the exit code is 1 or 0, so the nomination line
#    is earned by the CELL TABLE being present, not by the exit code.
DONE=$(grep -c "=== DISTRIBUTION" "$F" 2>/dev/null); DONE=${DONE:-0}
LAST=$(grep -vE "^exit [0-9]+$" "$F" 2>/dev/null | grep -vE "^[[:space:]]*$" | tail -1 | cut -c1-140)
if [ "$RC" -ne 0 ]; then
  ERR=$(grep -E "^[A-Za-z_.]*(Error|Exception):" "$F" | tail -1 | cut -c1-140)
  BODY="SCAN FAILED exit $RC -- no cell table, no nomination count
$PB_LINE
${ERR:-${LAST:-no exception line in the artifact}}
$COV
full table: $F"
elif [ "$DONE" -eq 0 ]; then
  BODY="SCAN INCOMPLETE exit 0 -- it wrote no cell table, so there is no count
${LAST:-the artifact is empty}
$COV
full table: $F"
else
  BODY="$PB_LINE
$COV
$DIST
$NOM cells cleared the nomination bar
null: best of ~250 cells shows |t|~3.2 by chance -- the spread is the result, not the max
full table: $F"
fi
MSG="SCAN $TS
$BODY"
MSG=$(printf '%s' "$MSG" | cut -c1-480)

TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  # Scope switch (docs/ops/notifications.md): default is tickets only.
  # rc 0 allowed, 1 muted; anything else (2 bad kind, 127 no python3, an
  # ImportError from a stale checkout) is a broken gate, not a choice.
  RC_GATE=0; python3 "$(dirname "$0")/ntfy_allowed.py" nightly || RC_GATE=$?
  if [ "$RC_GATE" -eq 0 ]; then
    curl -s -m 20 -H "Title: Meridian nightly scan$([ "$RC" -ne 0 ] && echo ' FAILED')" -d "$MSG" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 \
      && echo "pushed" >> "$F" || echo "push failed" >> "$F"
  elif [ "$RC_GATE" -eq 1 ]; then
    printf '%s\tnightly\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(printf '%s' "$MSG" | tr '\n' ' ')" \
      >> /opt/meridian/artifacts/reads/ntfy_muted.log
    echo "push muted by MERIDIAN_NTFY_SCOPE (kept in ntfy_muted.log)" >> "$F"
  else
    echo "ntfy gate failed rc=$RC_GATE; not pushed" >> "$F"
  fi
else
  echo "no ntfy topic in .env; not pushed" >> "$F"
fi
echo "wrote $F"
