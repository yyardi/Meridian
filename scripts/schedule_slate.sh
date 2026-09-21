#!/usr/bin/env bash
# schedule_slate.sh [--hours N] [--dry-run]
#
# Runs scripts/schedule_slate.py in the api image against the recorder's
# board and installs the cron block it prints. Crontab lives on the host and
# the planner runs in a container, so the two halves are split here: the
# container decides, the host writes.
#
# Idempotent: every existing "# TEMP" line is dropped before the new block is
# appended, so running it twice in a day yields one plan, and a game already
# launched today is never launched twice (its time is in the past and cron
# does not fire in the past). Lines without TEMP -- the nightly jobs, the
# schedule pings, this job itself -- are kept as they are.
#
# Installed by hand once as:
#   10 12 * * * sudo -n /opt/meridian/scripts/schedule_slate.sh >> /opt/meridian/artifacts/reads/cron.log 2>&1
set -euo pipefail
R=/opt/meridian/artifacts/reads
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
# The crontab this manages is the OPERATOR user's, by name. This script runs
# under sudo (docker needs it), and a bare `crontab -` under sudo edits
# ROOT's crontab: the first real run on 2026-09-21 installed the day's block
# there while the hand-written block, the pings and this job's own line all
# lived in ubuntu's, so the night would have launched everything twice.
CRON_USER=${CRON_USER:-ubuntu}
DRY=0
ARGS=()
for a in "$@"; do
  case "$a" in --dry-run) DRY=1; ARGS+=("$a");; *) ARGS+=("$a");; esac
done

BLOCK=$(docker run --rm --network meridian_default --env-file /opt/meridian/.env \
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian \
  -e MERIDIAN_READS_DIR=/out \
  -v /opt/meridian/core:/app/core -v /opt/meridian/scripts:/app/scripts \
  -v "$R":/out -w /app "$API" \
  python3 scripts/schedule_slate.py --launchers-dir /opt/meridian/scripts/launchers --reads-dir "$R" "${ARGS[@]}")

if [ "$DRY" = "1" ]; then
  echo "$BLOCK"
  exit 0
fi

if ! echo "$BLOCK" | grep -q "^[0-9]"; then
  echo "schedule_slate: nothing to schedule"
  exit 0
fi

# Keep every non-TEMP line; the self-clean line contains TEMP too and goes.
( crontab -u "$CRON_USER" -l 2>/dev/null | grep -v "TEMP" ; echo "$BLOCK" ) | crontab -u "$CRON_USER" -
echo "schedule_slate: installed $(echo "$BLOCK" | grep -c '^[0-9]') lines into $CRON_USER's crontab"
