#!/usr/bin/env bash
# WAIT FOR A CONTAINER TO FINISH, and report when it actually did.
#
# Built after two wrong wall-times in one day, both the same shape: inferring
# completion from the newest thing visible rather than from a signal that only
# exists after completion.
#
#   1. `pgrep -f nightly_scan.sh` MATCHES ITS OWN COMMAND LINE. The only process
#      it ever found was the shell running the pattern, so it reported RUNNING
#      forever while the scan had finished 2h earlier. A waiter that never fires
#      is indistinguishable from a job that never finishes.
#   2. Reading the LAST LINE of a log still being written and calling it the end
#      dropped 3m44s, turned a 34% improvement into 10%, and reversed the
#      conclusion about which change bought the speed.
#
# So this waits on the container's DISAPPEARANCE -- a fact that cannot exist
# while the job runs -- and takes the finish time from the log's mtime, which is
# exact because the redirect closes when the process exits.
#
# It also REFUSES to report success for a job it never saw: a container absent
# on the first poll is "never started", not "done". That is the other half of
# today's lesson, and the half a retry loop gets wrong by default.
#
#   scripts/wait_for_container.sh --name my_run --log /path/run.txt
#   scripts/wait_for_container.sh --env-contains isolate_rows --log /path/run.txt
#
# Exit 0 = it ran and finished. 2 = never started. 3 = timed out. 4 = usage.
# 5 = the docker probe itself failed (NOT reported as finished).
set -u

NAME=""; ENVSTR=""; LOG=""; POLL=20; TIMEOUT=14400; SUDO="sudo -n"
while [ $# -gt 0 ]; do
  case "$1" in
    --name)         NAME="$2"; shift 2 ;;
    --env-contains) ENVSTR="$2"; shift 2 ;;
    --log)          LOG="$2"; shift 2 ;;
    --poll)         POLL="$2"; shift 2 ;;
    --timeout)      TIMEOUT="$2"; shift 2 ;;
    --no-sudo)      SUDO=""; shift ;;
    *) echo "unknown argument: $1" >&2; exit 4 ;;
  esac
done
[ -n "$NAME$ENVSTR" ] || { echo "need --name or --env-contains" >&2; exit 4; }

# One probe. Prints the count of matching RUNNING containers, or fails.
# Deliberately NOT pgrep: docker's output cannot contain this script's own
# command line, so it cannot match itself.
# GNU `stat -c` and BSD `stat -f`, in that order. Prints an ISO-ish UTC stamp,
# or fails so the caller can say it fell back rather than pretending.
# ★ CAPTURE, THEN TRANSFORM. `stat -c %y "$1" | cut -c1-19 && return 0` takes
# the PIPELINE's status, which is `cut`'s -- and cut succeeds on empty input, so
# a failed stat returned 0 with an empty string. That is the third appearance of
# this exact shape today (`grep -c ... || echo 0` in the nightly push, then
# `docker ps | grep -c` in this file's own probe), and it is always the same
# cause: the last command in a pipeline owns the exit status.
mtime_utc() {
  local o
  o=$($SUDO stat -c %y "$1" 2>/dev/null) && [ -n "$o" ] && {
    printf '%s\n' "${o:0:19}"; return 0; }
  o=$($SUDO stat -f %Sm -t "%Y-%m-%d %H:%M:%S" "$1" 2>/dev/null) && [ -n "$o" ] && {
    printf '%s\n' "$o"; return 0; }
  return 1
}
fsize() { $SUDO stat -c %s "$1" 2>/dev/null || $SUDO stat -f %z "$1" 2>/dev/null || echo "?"; }

# ★ DOCKER'S OWN EXIT STATUS, NOT THE PIPELINE'S. The first version was
# `docker ps ... | grep -c . || true`, and when docker FAILED the pipeline
# status came from `grep -c` (1, no match) and `|| true` swallowed it -- so a
# dead daemon printed "0" and read as "no containers running", i.e. finished.
# That is the same `grep -c` pipeline mask I had fixed in nightly_scan.sh hours
# earlier, reproduced in the tool built to stop exactly this class of error. The
# output is captured first so the failure can propagate.
probe() {
  local out id n=0
  if [ -n "$NAME" ]; then
    out=$($SUDO docker ps --filter "name=$NAME" --format '{{.ID}}') || return 1
    printf '%s' "$out" | grep -c . || true
  else
    out=$($SUDO docker ps -q) || return 1
    for id in $out; do
      # ★ AND INSPECT'S OWN STATUS TOO. `docker inspect | grep -q` reads a
      # FAILED inspect as "no match", so a transient failure undercounts and --
      # if it hit every container -- would report the job finished. One line
      # below the identical fix for `docker ps`, found by a deliberate sweep
      # rather than by reading my own diff.
      local env_out
      env_out=$($SUDO docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' \
                  "$id" 2>/dev/null) || return 1
      if printf '%s' "$env_out" | grep -q -- "$ENVSTR"; then n=$((n + 1)); fi
    done
    echo "$n"
  fi
}

started_at=""; seen=0; waited=0
while [ "$waited" -lt "$TIMEOUT" ]; do
  if ! n=$(probe); then
    echo "docker probe FAILED -- not reporting this as finished" >&2
    exit 5
  fi
  case "$n" in
    ''|*[!0-9]*) echo "docker probe returned $n, not a count" >&2; exit 5 ;;
  esac

  if [ "$n" -gt 0 ]; then
    if [ "$seen" -eq 0 ]; then
      seen=1
      started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      echo "seen running at $started_at"
    fi
  elif [ "$seen" -eq 1 ]; then
    # Gone AFTER being seen. The log's mtime is the exact finish; the poll loop
    # only bounds it to within one interval, so prefer the file when given.
    fin=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    if [ -n "$LOG" ] && [ -e "$LOG" ]; then
      # ★ `stat -c` IS GNU-ONLY. The box is Linux, but a darwin dev machine
      # silently fell through to the poll clock instead -- so the exact-finish
      # path was never exercised by a local test and a mutation deleting it
      # passed. Both spellings, and the fallback is announced rather than silent.
      fin=$(mtime_utc "$LOG") || fin=""
      if [ -n "$fin" ]; then
        echo "FINISHED. log last written: $fin ($(fsize "$LOG") bytes)"
      else
        fin=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        echo "FINISHED near $fin -- could not stat $LOG, so this is the POLL"
        echo "    clock and is bounded by ${POLL}s, not the log's own mtime"
      fi
      $SUDO tail -3 "$LOG" 2>/dev/null | sed 's/^/    /'
    else
      echo "FINISHED between the last two polls (within ${POLL}s of $fin)"
      [ -n "$LOG" ] && echo "    note: --log $LOG does not exist, so this is bounded, not exact"
    fi
    exit 0
  else
    # Absent and never seen. This is the case a naive loop calls "done".
    echo "NEVER STARTED -- no matching container on the first poll." >&2
    echo "  A container absent before it was ever seen is not a finished one." >&2
    exit 2
  fi
  sleep "$POLL"; waited=$((waited + POLL))
done
echo "TIMED OUT after ${TIMEOUT}s; still running as of $(date -u +%H:%M:%SZ)" >&2
exit 3
