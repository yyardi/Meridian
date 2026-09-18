#!/usr/bin/env bash
# THE LADDER SCAN, NIGHTLY. Reports the venue's own self-contradictions.
#
#   crontab (UTC):  30 11 * * *  sudo -n /opt/meridian/scripts/nightly_ladder.sh
#
# A SEPARATE SCRIPT, not a step inside nightly_scan.sh -- same reason as the TT
# Elo and drift jobs: the scan is load-bearing and a new step must not be able
# to change its exit status or truncate its 480-character push.
#
# 11:30Z: clear of the 04:40Z scan (which has finished as late as 10:16Z), of
# the 09:00Z Elo and 09:30Z drift jobs, and of the 10:40Z MLB read.
#
# WHY IT ACCRUES. The $413.90 in STATUS §0bi was measured over three CFB days.
# Whether that recurs weekly or was one weekend is UNKNOWN, and only a record
# answers it. The artifact is written every night regardless of what is found.
#
# PUSHES ONLY ON A LARGE ONE. The median opportunity is $0.01 and these quotes
# are never consumed (§0bj), so a nightly "we found 350 things worth a penny"
# is how a channel earns being ignored. $50 is the floor; measured, 3 of 350
# exceeded $100 and roughly ten exceeded $50, so this speaks a few times a
# season rather than nightly. PLACES NOTHING.
set -u
cd /opt/meridian || exit 1
OUT=/opt/meridian/artifacts/reads; mkdir -p "$OUT"
TS=$(date -u +%Y-%m-%dT%H%MZ)
F="$OUT/ladder_$TS.txt"
STATE="$OUT/ladder_state.txt"
# PUSH DISABLED PENDING STATUS 0bs. The scan now defaults to in-play, and in-play
# ladders in our snapshots carry a 5-14s (max 110s) fetch skew inside one
# captured_at that can manufacture a violation during a scoring play. Until the
# live sampler has shown whether genuinely simultaneous in-play ladders break,
# a $50 floor on skew-contaminated data is noise wearing a number. The artifact
# is still written every night; only the push is out of reach.
FLOOR=999999999

API=$(docker inspect meridian-api --format "{{.Config.Image}}" 2>/dev/null || echo meridian-api)
RC=0
for LG in cfb nfl mlb; do
  { echo; echo "### $LG"; } >> "$F"
  docker run --rm --network meridian_default \
    -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
    -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb -w /app \
    "$API" python cfb/run_ladder_scan.py --league "$LG" --since "$(date -u -d '3 days ago' +%Y-%m-%d)" \
    >> "$F" 2>&1 || RC=$?
done

# biggest single opportunity across all three leagues, as an integer of dollars
BEST=$(grep -oE '^ +[0-9,]+\.[0-9]{2} ' "$F" | tr -d ' ,' | cut -d. -f1 | sort -rn | head -1)
BEST=${BEST:-0}
echo "biggest single opportunity: \$$BEST (push floor \$$FLOOR)" >> "$F"

if [ "$RC" -ne 0 ]; then
  BODY="LADDER SCAN FAILED exit $RC
$(grep -vE '^[[:space:]]*$' "$F" | tail -1 | cut -c1-200)"
elif [ "$BEST" -lt "$FLOOR" ]; then
  echo "nothing above the floor; not pushed" >> "$F"
  echo "wrote $F"; exit 0
elif [ -f "$STATE" ] && [ "$(cat "$STATE")" = "$BEST" ]; then
  echo "same best as last night ($BEST); not pushed" >> "$F"
  echo "wrote $F"; exit 0
else
  BODY="LADDER: single opportunity \$$BEST
$(grep -E '^ +[0-9,]+\.[0-9]{2} ' "$F" | head -3 | sed 's/^ *//')
SIZE IS QUOTED NOT FILLED"
fi
printf '%s\n' "$BEST" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"

MSG=$(printf 'MERIDIAN %s\n%s\nfull: %s' "$TS" "$BODY" "$(basename "$F")" | cut -c1-480)
TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  # Scope switch (docs/ops/notifications.md): default is tickets only.
  # rc 0 allowed, 1 muted; anything else (2 bad kind, 127 no python3, an
  # ImportError from a stale checkout) is a broken gate, not a choice.
  RC_GATE=0; python3 "$(dirname "$0")/ntfy_allowed.py" nightly || RC_GATE=$?
  if [ "$RC_GATE" -eq 0 ]; then
    curl -s -m 20 -H "Title: Meridian ladder$([ "$RC" -ne 0 ] && echo ' FAILED')" \
         -d "$MSG" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 \
      && echo "pushed" >> "$F" || echo "push failed" >> "$F"
  elif [ "$RC_GATE" -eq 1 ]; then
    printf '%s\tnightly\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(printf '%s' "$MSG" | tr '\n' ' ')" \
      >> /opt/meridian/artifacts/reads/ntfy_muted.log
    echo "push muted by MERIDIAN_NTFY_SCOPE (kept in ntfy_muted.log)" >> "$F"
  else
    echo "ntfy gate failed rc=$RC_GATE; not pushed" >> "$F"
  fi
fi
echo "wrote $F"
