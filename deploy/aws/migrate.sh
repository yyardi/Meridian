#!/usr/bin/env bash
# Move the database from the laptop to the EC2 instance. Run FROM THE LAPTOP.
#
#   deploy/aws/migrate.sh <instance-ip>
#   deploy/aws/migrate.sh <instance-ip> --dump-only     # stop after S3 upload
#   deploy/aws/migrate.sh <instance-ip> --verify-only   # re-run the row-count check
#
# Nothing is deleted, here or on the instance. The laptop stack is untouched
# and stays the source of truth until the runbook's parallel-run confirms
# parity. Rollback is "keep using the laptop", which costs nothing because
# nothing was removed.
set -euo pipefail

INSTANCE_IP="${1:-}"
MODE="${2:-}"
[[ -n "$INSTANCE_IP" ]] || { echo "usage: $0 <instance-ip> [--dump-only|--verify-only]" >&2; exit 2; }

# The bucket lives in the CURRENT account. The first default here named the
# old account's bucket and the migration failed on a bucket that exists but
# is not ours — an access error that reads like a credentials problem.
BUCKET="${MERIDIAN_S3_BUCKET:-meridian-backups-623955527388}"
KEY_PATH="${MERIDIAN_SSH_KEY:-$HOME/.ssh/meridian-aws.pem}"
SSH_USER="${MERIDIAN_SSH_USER:-ubuntu}"
LOCAL_PG="${MERIDIAN_PG_CONTAINER:-meridian-postgres}"
REMOTE_DIR=/opt/meridian
DB=meridian
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="meridian-${STAMP}.dump"

SSH=(ssh -i "$KEY_PATH" -o StrictHostKeyChecking=accept-new "${SSH_USER}@${INSTANCE_IP}")

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# The tables whose counts must match. Not `all tables`: this list is the
# contract, and a table added later should force a deliberate edit here rather
# than silently not being checked.
TABLES=(
  market_snapshots book_levels predictions shadow_orders orders
  team_game_logs player_game_logs sportsbook_odds resolved_outcomes
  injury_reports injury_polls kalshi_snapshots kalshi_games kalshi_contracts
  service_heartbeats account_balances model_calibration retention_log
)

counts_sql() {
  # One row per table: name, count. Missing tables report -1 rather than
  # aborting, so a fresh target that legitimately lacks a table is visible
  # instead of fatal.
  local first=1
  for t in "${TABLES[@]}"; do
    [[ $first -eq 1 ]] || printf ' UNION ALL '
    first=0
    printf "SELECT '%s' AS t, CASE WHEN to_regclass('public.%s') IS NULL THEN -1 ELSE (SELECT count(*) FROM %s) END AS n" "$t" "$t" "$t"
  done
  printf ' ORDER BY 1'
}

local_counts() {
  docker exec -i "$LOCAL_PG" psql -U meridian -d "$DB" -At -F',' -c "$(counts_sql)"
}
remote_counts() {
  "${SSH[@]}" "cd $REMOTE_DIR && docker compose exec -T postgres psql -U meridian -d $DB -At -F',' -c \"$(counts_sql)\""
}

verify() {
  log "verifying row counts table by table"
  local before after fail=0
  before=$(local_counts)  || die "could not read local counts"
  after=$(remote_counts)  || die "could not read remote counts"
  printf '\n%-24s %14s %14s   %s\n' TABLE LAPTOP INSTANCE ""
  while IFS=, read -r t n; do
    local m
    m=$(echo "$after" | awk -F, -v k="$t" '$1==k{print $2}')
    m="${m:-MISSING}"
    if [[ "$m" == "$n" ]]; then
      printf '%-24s %14s %14s   ok\n' "$t" "$n" "$m"
    else
      printf '%-24s %14s %14s   \033[31mMISMATCH\033[0m\n' "$t" "$n" "$m"
      fail=1
    fi
  done <<< "$before"
  echo
  [[ $fail -eq 0 ]] || die "row counts differ — the instance is NOT a faithful copy.
The laptop stack is untouched; investigate before cutting over."
  echo "All ${#TABLES[@]} tables match."
}

if [[ "$MODE" == "--verify-only" ]]; then verify; exit 0; fi

# --------------------------------------------------------------------------- #
log "1/5  preflight"
# --------------------------------------------------------------------------- #
[[ -f "$KEY_PATH" ]] || die "ssh key not found at $KEY_PATH"
docker inspect "$LOCAL_PG" >/dev/null 2>&1 || die "local container $LOCAL_PG is not running"
command -v aws >/dev/null || die "aws cli not found — needed to move the dump through S3"
aws s3 ls "s3://$BUCKET" >/dev/null || die "cannot list s3://$BUCKET (credentials or bucket name)"
"${SSH[@]}" true || die "cannot ssh to $INSTANCE_IP"

# Server versions must match, or pg_restore will refuse a newer dump. The
# LOCAL client comes from inside the container on purpose: the host has no
# postgres client tools (see the compose comment on the /backups mount).
LOCAL_V=$(docker exec "$LOCAL_PG" psql -U meridian -d "$DB" -At -c 'show server_version')
REMOTE_V=$("${SSH[@]}" "cd $REMOTE_DIR && docker compose exec -T postgres psql -U meridian -d $DB -At -c 'show server_version'" | tr -d '\r')
echo "  postgres  laptop=$LOCAL_V  instance=$REMOTE_V"
[[ "${LOCAL_V%%.*}" == "${REMOTE_V%%.*}" ]] \
  || die "major versions differ ($LOCAL_V vs $REMOTE_V); pg_restore will not accept the dump"

# --------------------------------------------------------------------------- #
log "2/5  dump (custom format, from inside the container)"
# --------------------------------------------------------------------------- #
# Writes to /backups, which compose binds to $MERIDIAN_DATA_DIR/ticks on the
# host — the same path core/retention.py already stages dumps through, so no
# new mount and no new host dependency.
docker exec "$LOCAL_PG" pg_dump -U meridian -d "$DB" -Fc -Z6 -f "/backups/$DUMP"

# The host-side path comes from the project's own path contract, NOT from
# `docker inspect --format '{{.Mounts}}'`. On Docker Desktop for Mac — which is
# where this script runs — inspect reports the VM-internal source
# (/host_mnt/Users/...), so the `-f` test against it fails on a dump that
# landed perfectly well. Caught by running it.
#
# core/paths.py is the authority: MERIDIAN_DATA_DIR (default <repo>/backups),
# and compose binds $MERIDIAN_DATA_DIR/ticks to /backups.
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DATA_DIR="${MERIDIAN_DATA_DIR:-}"
if [[ -z "$DATA_DIR" && -f "$REPO_ROOT/.env" ]]; then
  DATA_DIR=$(grep -E '^MERIDIAN_DATA_DIR=' "$REPO_ROOT/.env" | cut -d= -f2- || true)
fi
DATA_DIR="${DATA_DIR:-$REPO_ROOT/backups}"
HOST_DUMP="$DATA_DIR/ticks/$DUMP"
[[ -f "$HOST_DUMP" ]] || die "dump not visible on the host at $HOST_DUMP
(pg_dump wrote /backups/$DUMP inside the container; if that path is wrong the
compose bind for \$MERIDIAN_DATA_DIR/ticks:/backups has changed)"
echo "  $(du -h "$HOST_DUMP" | cut -f1)  $HOST_DUMP"

# --------------------------------------------------------------------------- #
log "3/5  upload to s3://$BUCKET"
# --------------------------------------------------------------------------- #
aws s3 cp "$HOST_DUMP" "s3://$BUCKET/$DUMP" --only-show-errors
aws s3 ls "s3://$BUCKET/$DUMP" || die "upload did not land"

[[ "$MODE" == "--dump-only" ]] && { echo; echo "Stopped after upload as asked."; exit 0; }

# --------------------------------------------------------------------------- #
log "4/5  restore on the instance"
# --------------------------------------------------------------------------- #
# The instance pulls from S3 itself rather than taking an scp: the dump is
# already there, S3 egress inside the region is free, and a resumable download
# beats a broken pipe on a multi-GB scp over a laptop's uplink.
"${SSH[@]}" bash -se <<REMOTE
set -euo pipefail
cd $REMOTE_DIR
DATA_DIR=\$(grep -E '^MERIDIAN_DATA_DIR=' .env | cut -d= -f2- || true)
DATA_DIR="\${DATA_DIR:-$REMOTE_DIR/backups}"
aws s3 cp "s3://$BUCKET/$DUMP" "\$DATA_DIR/ticks/$DUMP" --only-show-errors
docker compose exec -T postgres pg_restore -U meridian -d $DB \
  --no-owner --no-privileges --single-transaction "/backups/$DUMP"
REMOTE

# --------------------------------------------------------------------------- #
log "5/5  verification"
# --------------------------------------------------------------------------- #
verify

cat <<MSG

Restored. The laptop stack is UNTOUCHED and still recording.

Do not cut over yet. The runbook's parallel run is the actual test: let both
stacks record one full slate, then compare tick counts over the same window.
Row counts matching here proves the copy, not the copier.

    deploy/aws/migrate.sh $INSTANCE_IP --verify-only
MSG
