#!/usr/bin/env bash
# CODE DRIFT, NIGHTLY, SPEAKING ONLY WHEN THE ANSWER CHANGES.
#
#   crontab (UTC):  30 9 * * *  sudo -n /opt/meridian/scripts/nightly_code_drift.sh
#
# WHY NIGHTLY RATHER THAN IN THE DEPLOY PATH. A check that runs after a rebuild
# confirms the rebuild worked; it cannot see the failure this exists for, which
# is a fix merged and then NOT deployed for days while everyone believes it is
# live. That gap is only visible to something that looks when no one is
# deploying. The deploy-path run is still worth having -- it is just a
# different question.
#
# AND IT PUSHES ONLY ON A TRANSITION, for the reason the TT Elo job does: the
# steady state here is "N files inert", which is true every night and is not
# news. What IS news is the set CHANGING -- a merge making something inert, or
# a rebuild clearing it. Same state-file discipline as nightly_tt_elo.sh:
# a MISSING state file is a FIRST RUN, not "everything changed", or night one
# pushes the entire fleet and teaches the reader to ignore the channel.
set -u
cd /opt/meridian || exit 1
OUT=/opt/meridian/artifacts/reads; mkdir -p "$OUT"
TS=$(date -u +%Y-%m-%dT%H%MZ)
F="$OUT/code_drift_$TS.txt"
STATE="$OUT/code_drift_state.txt"

/opt/meridian/scripts/code_drift.sh > "$F" 2>&1
RC=$?

# The detector exits 0 whether or not anything drifted -- DIFFERS is a finding,
# not an error -- and reserves non-zero for "I could not answer" (exit 2 is a
# bad reference, which it refuses to guess past). So the exit code is the
# HEALTH of the instrument and the body is the answer. Do not conflate them.
if [ "$RC" -ne 0 ]; then
  BODY="CODE DRIFT CHECK FAILED exit $RC
$(grep -vE '^[[:space:]]*$' "$F" | tail -1 | cut -c1-200)"
else
  # the drifting FILE SET, deduplicated and ordered -- the fleet nearly always
  # shares one set, so the files are the signal and the container list is noise
  NOW=$(grep -E '^      [a-z].*\.py$' "$F" | tr -d ' ' | sort -u)
  SUMMARY=$(grep -E '^[0-9]+ match, [0-9]+ DIFFER' "$F" | tail -1)
  if [ ! -f "$STATE" ]; then
    printf '%s\n' "$NOW" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
    { echo; echo "first run: state recorded, no transition by definition"; } >> "$F"
    echo "wrote $F"; exit 0
  fi
  PREV=$(cat "$STATE")
  if [ "$NOW" = "$PREV" ]; then
    { echo; echo "no change in the drifting file set; not pushed"; } >> "$F"
    echo "wrote $F"; exit 0
  fi
  GONE=$(comm -13 <(printf '%s\n' "$NOW") <(printf '%s\n' "$PREV") | head -4)
  NEW=$(comm -23 <(printf '%s\n' "$NOW") <(printf '%s\n' "$PREV") | head -4)
  BODY="CODE DRIFT CHANGED
$SUMMARY
$([ -n "$NEW" ]  && printf 'now inert: %s\n' "$(echo $NEW)")
$([ -n "$GONE" ] && printf 'now deployed: %s\n' "$(echo $GONE)")"
  printf '%s\n' "$NOW" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
fi

MSG=$(printf 'MERIDIAN %s\n%s\nfull: %s' "$TS" "$BODY" "$(basename "$F")" | cut -c1-480)
TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  # Scope switch (docs/ops/notifications.md): default is tickets only.
  # rc 0 allowed, 1 muted; anything else (2 bad kind, 127 no python3, an
  # ImportError from a stale checkout) is a broken gate, not a choice.
  RC_GATE=0; python3 "$(dirname "$0")/ntfy_allowed.py" nightly || RC_GATE=$?
  if [ "$RC_GATE" -eq 0 ]; then
    curl -s -m 20 -H "Title: Meridian code drift$([ "$RC" -ne 0 ] && echo ' FAILED')" \
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
