#!/usr/bin/env bash
# Repair foreign keys that merge_history.sh carried over verbatim.
#
#   deploy/aws/repair_fk_links.sh --dry-run     # counts only, writes nothing
#   deploy/aws/repair_fk_links.sh --yes
#
# THE DEFECT THIS REPAIRS
# -----------------------
# merge_history.sh remapped exactly one id link — book_levels.snapshot_id — and
# inserted every other foreign key straight from the history id space. The two
# databases number independently, so those ids landed pointing at whatever
# happened to occupy the same number in the live database.
#
# Measured on production after the merge, of 14,485 shadow_orders:
#
#     10,507  prediction_id points at NO prediction     -> reads "unresolved"
#      3,808  points at a REAL prediction for a DIFFERENT market
#
# The 3,808 are the dangerous half. core/game_detail.py:212 reads
# `p.resolved_outcome` through `LEFT JOIN predictions p ON p.id =
# so.prediction_id`, so a dangling id renders as unresolved — visibly wrong —
# while a mismatched one renders another market's outcome as this trade's
# result. Plausible and wrong beats blank and wrong for staying unnoticed.
#
# WHY A REPAIR AND NOT A RE-MERGE
# -------------------------------
# The rows are already present and match on their natural keys, so re-running
# the merge skips them. The values have to be corrected in place.
#
# THE REMAP, which is the same shape book_levels got:
#     live row  --(natural key)-->  history row  --(its stored id)-->
#     history parent  --(parent's natural key)-->  live parent id
#
# Nothing is deleted and no row is inserted. Only foreign keys change, and only
# where the correct value differs from the current one.
set -euo pipefail

SRC_DB="${MERIDIAN_HISTORY_DB:-meridian_history}"
DST_DB="${MERIDIAN_LIVE_DB:-meridian}"
STAGE=repair_stage
MODE="${1:---dry-run}"

cd "${MERIDIAN_HOME:-/opt/meridian}"
DC() { sudo -H -u meridian docker compose "$@"; }
SRC() { DC exec -T postgres psql -U meridian -d "$SRC_DB" -v ON_ERROR_STOP=1 "$@"; }
DST() { DC exec -T postgres psql -U meridian -d "$DST_DB" -v ON_ERROR_STOP=1 "$@"; }
log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

health() {   # $1 label
  DST -At -F'|' -c "select
    (select count(*) from shadow_orders) total,
    (select count(*) from shadow_orders s left join predictions p on p.id=s.prediction_id
      where s.prediction_id is not null and p.id is null) dangling,
    (select count(*) from shadow_orders s join predictions p on p.id=s.prediction_id
      where p.market_slug <> s.market_slug) mismatched" \
  | awk -F'|' -v l="$1" '{printf "  %-8s total=%-8s dangling=%-8s mismatched=%s\n", l, $1, $2, $3}'
}

log "0/4  preconditions"
DST -At -c "select 1 from pg_database where datname='$SRC_DB'" | grep -q 1 \
  || die "$SRC_DB is gone — it is the only source of the original id links.
Restore it from /backups/laptop.dump before repairing."
echo "  mode: $MODE"
health "before"

log "1/4  stage the history side (natural key + the id it pointed at)"
DST -c "DROP SCHEMA IF EXISTS $STAGE CASCADE; CREATE SCHEMA $STAGE;" >/dev/null
DST -c "CREATE TABLE $STAGE.h_pred (id bigint, market_slug text, predicted_at timestamptz,
                                    model_version text, config_hash text);
        CREATE TABLE $STAGE.h_so (idempotency_key text, prediction_id bigint);" >/dev/null
DC exec -T postgres sh -c \
  "psql -U meridian -d $SRC_DB -c \"COPY (SELECT id, market_slug, predicted_at, model_version, config_hash FROM predictions) TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.h_pred FROM STDIN\"" >/dev/null
DC exec -T postgres sh -c \
  "psql -U meridian -d $SRC_DB -c \"COPY (SELECT idempotency_key, prediction_id FROM shadow_orders) TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.h_so FROM STDIN\"" >/dev/null

# Index before joining. Millions of rows on both sides; this is the 33-minute
# lesson and it applies every time.
DST -c "CREATE UNIQUE INDEX ON $STAGE.h_pred (id);
        CREATE INDEX ON $STAGE.h_pred (market_slug, predicted_at, model_version, config_hash);
        CREATE INDEX ON $STAGE.h_so (idempotency_key);
        ANALYZE $STAGE.h_pred; ANALYZE $STAGE.h_so;" >/dev/null
echo "  staged $(DST -At -c "select count(*) from $STAGE.h_pred") history predictions"
echo "  staged $(DST -At -c "select count(*) from $STAGE.h_so") history shadow_orders"

log "2/4  build the id remap through the parent's natural key"
DST -c "CREATE TABLE $STAGE.remap AS
          SELECT h.idempotency_key, lp.id AS correct_prediction_id
            FROM $STAGE.h_so h
            JOIN $STAGE.h_pred hp ON hp.id = h.prediction_id
            JOIN public.predictions lp
              ON lp.market_slug   = hp.market_slug
             AND lp.predicted_at  = hp.predicted_at
             AND lp.model_version = hp.model_version
             AND lp.config_hash   = hp.config_hash;
        CREATE UNIQUE INDEX ON $STAGE.remap (idempotency_key);
        ANALYZE $STAGE.remap;" >/dev/null
mapped=$(DST -At -c "select count(*) from $STAGE.remap")
unmapped=$(DST -At -c "select count(*) from $STAGE.h_so h
                        left join $STAGE.remap r on r.idempotency_key=h.idempotency_key
                        where r.idempotency_key is null")
echo "  resolvable links: $mapped"
echo "  unresolvable (history parent absent from live — left alone, never guessed): $unmapped"

log "3/4  repair"
would=$(DST -At -c "select count(*) from shadow_orders s join $STAGE.remap r
                     on r.idempotency_key = s.idempotency_key
                    where s.prediction_id IS DISTINCT FROM r.correct_prediction_id")
echo "  rows whose prediction_id is wrong: $would"
if [[ "$MODE" == "--yes" ]]; then
  DST -c "UPDATE shadow_orders s SET prediction_id = r.correct_prediction_id
            FROM $STAGE.remap r
           WHERE r.idempotency_key = s.idempotency_key
             AND s.prediction_id IS DISTINCT FROM r.correct_prediction_id;" >/dev/null
  echo "  updated"
else
  echo "  (dry run — nothing written)"
fi

log "4/4  verification"
health "after"
cat <<MSG

Both dangling and mismatched must be 0 for rows whose history parent exists.
Any residual belongs to \$unmapped above — a history prediction that is not in
the live database — and those are left pointing where they were rather than
guessed at.

Staging left for inspection:
    docker compose exec -T postgres psql -U meridian -d $DST_DB -c 'DROP SCHEMA $STAGE CASCADE'
MSG
