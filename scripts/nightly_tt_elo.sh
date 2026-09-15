#!/usr/bin/env bash
# THE ELO FIT, FIRED AUTOMATICALLY. Runs every night, prints NOT YET with the
# counts until eligibility is met, and produces the verdict the moment it is.
# The point of building it three days early is that nobody has to be watching.
#
#   crontab (UTC):  20 5 * * *  sudo -n /opt/meridian/scripts/nightly_tt_elo.sh
#
# A SEPARATE SCRIPT, not a step inside nightly_scan.sh, deliberately: the scan
# is the load-bearing job and a new step that can fail must not be able to
# change its exit status or truncate its 480-character push.
#
# PUSHES ONLY ON A TRANSITION. A verdict that has not changed is not news, and
# four NOT YETs a night is how a channel earns being ignored before it carries
# the one message that matters. The artifact is written every run regardless,
# so the history exists whether or not anything was sent.
set -u
cd /opt/meridian || exit 1
OUT=/opt/meridian/artifacts/reads; mkdir -p "$OUT"
TS=$(date -u +%Y-%m-%dT%H%MZ)
F="$OUT/tt_elo_$TS.txt"
STATE="$OUT/tt_elo_state.json"
IMG=$(docker inspect meridian-api --format "{{.Config.Image}}" 2>/dev/null || echo meridian-api)

# The api IMAGE with the checkout mounted, never `docker exec` into the running
# container: that one carries whatever code it was built with.
docker run --rm --network host \
  -v /opt/meridian:/app -w /app --env-file /opt/meridian/.env \
  -e PYTHONPATH=/app \
  "$IMG" python cfb/run_tt_elo.py \
    --settlements "$OUT/settlements.json" --state "$STATE" \
  > "$F" 2>&1
RC=$?

# grep -c prints 0 AND returns 1 when it matches nothing, so the assignment
# must not be the last command of a `set -e` script and the value needs a
# default. This script uses `set -u` only, but the default stays: a bare
# ${MOVED} would be empty, not zero, and `[ -eq ]` would fail on it.
MOVED=$(grep -c "TT ELO TRANSITION" "$F" 2>/dev/null); MOVED=${MOVED:-0}
VERDICTS=$(grep -E "^  (setka[a-z]+) " "$F" | awk '{print $1": "$5}' | tr '\n' ' ')

if [ "$RC" -ne 0 ]; then
  BODY="TT ELO FAILED exit $RC
$(grep -vE '^[[:space:]]*$' "$F" | tail -1 | cut -c1-200)
full: $F"
elif [ "$MOVED" -gt 0 ]; then
  BODY="TT ELO VERDICT CHANGED
$(grep 'TT ELO TRANSITION' "$F" | sed 's/^ *//' | head -4)
$VERDICTS
full: $F"
else
  echo "no transition; not pushed" >> "$F"
  echo "wrote $F"
  exit 0
fi

MSG=$(printf 'TT ELO %s\n%s' "$TS" "$BODY" | cut -c1-480)
TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  curl -s -m 20 -H "Title: Meridian TT Elo$([ "$RC" -ne 0 ] && echo ' FAILED')" \
       -d "$MSG" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 \
    && echo "pushed" >> "$F" || echo "push failed" >> "$F"
else
  echo "no ntfy topic in .env; not pushed" >> "$F"
fi
echo "wrote $F"
