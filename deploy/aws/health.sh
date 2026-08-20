#!/usr/bin/env bash
# The morning check, from the laptop, against the server.
#
#   deploy/aws/health.sh
#
# Prints exactly what `scripts/health.py` prints when run on the server —
# same groups, same colours, same "Verdict:" line — so there is one format to
# learn and no ssh incantation to remember. The exit code is the script's:
# 0 for OK or DEGRADED, 1 when something is DEAD, which makes it usable in a
# cron or a shell prompt as-is.
set -euo pipefail

# The address is NOT in this file. This repo is public, and a public repo
# should carry the SHAPE of the infrastructure and never its addresses.
# Resolution order, most explicit first:
#   1. MERIDIAN_SERVER=...           (one-off, or a CI secret)
#   2. ~/.meridian-server            (one line: the IP or hostname)
# The file keeps the operator's muscle-memory command to two words without
# putting the address anywhere git can see it.
HOST="${MERIDIAN_SERVER:-}"
if [[ -z "$HOST" && -f "$HOME/.meridian-server" ]]; then
  HOST=$(tr -d '[:space:]' < "$HOME/.meridian-server")
fi
if [[ -z "$HOST" ]]; then
  cat >&2 <<'MSG'
No server address.

  echo <server-ip> > ~/.meridian-server      # once, then `deploy/aws/health.sh`
  MERIDIAN_SERVER=<server-ip> deploy/aws/health.sh   # or one-off

The real address lives in the AWS console and the operator's local notes,
never in this repository.
MSG
  exit 2
fi
KEY="${MERIDIAN_SSH_KEY:-$HOME/.ssh/meridian-aws.pem}"
USER="${MERIDIAN_SSH_USER:-ubuntu}"
REMOTE="${MERIDIAN_HOME:-/opt/meridian}"

[[ -f "$KEY" ]] || { echo "ssh key not found at $KEY" >&2; exit 2; }

# -t only when there IS a local tty. Forcing it in a pipe or a cron makes ssh
# print "Pseudo-terminal will not be allocated" above every run, which is the
# kind of harmless noise that trains people to skim past the output.
# Built as ONE array that is never empty. `"${EMPTY[@]}"` under `set -u` is an
# unbound-variable error on bash 3.2, which is what macOS ships and what this
# script runs on — so the obvious `TTY_FLAG=()` form aborts before connecting.
SSH_OPTS=(-i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new)
[[ -t 1 ]] && SSH_OPTS+=(-t)
# .env is 0600 and owned by `meridian`, so it must be read INSIDE the sudo, not
# outside it. The first version of this line grepped it in the invoking shell —
# as `ubuntu` — and got "Permission denied", so the script ran with no
# DATABASE_URL and reported database checks against nothing. Sourcing it as the
# owning user is both correct and simpler.
# PYTHONPATH is required, not belt-and-braces. Python puts the SCRIPT's
# directory on sys.path — `scripts/` — never the working directory, so
# `scripts/health.py` cannot see `./core` however you cd. Run as shipped
# without this and it dies on "No module named 'core'" before the first check.
exec ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" \
  "cd $REMOTE && sudo -H -u meridian bash -c 'set -a; . ./.env; set +a; \
     export PYTHONPATH=$REMOTE; \
     exec ./.venv-health/bin/python scripts/health.py --server'"
