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

HOST="${MERIDIAN_SERVER:-100.60.80.165}"
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
