#!/usr/bin/env bash
# Merge a restored history database INTO the live one, server-side.
#
#   deploy/aws/merge_history.sh --dry-run     # counts only, writes nothing
#   deploy/aws/merge_history.sh --yes         # do it
#
# Runs ON THE SERVER, inside /opt/meridian. Both databases live in the same
# postgres instance, so rows move by COPY pipe rather than through dblink or
# postgres_fdw — neither extension is worth installing on a live database for
# a merge that happens twice.
#
# THE DIRECTION MATTERS AND IS THE OPPOSITE OF THE SUPABASE IMPORT.
# There, the export was authoritative and won. Here the SERVER is: its capture
# of the first night beat the laptop's by +2.7% ticks/game, so on any overlap
# the live row stays and the history row is skipped. Every insert is
# ON CONFLICT (natural key) DO NOTHING.
#
# IDS ARE NEVER TRUSTED. Both databases have their own sequences and their id
# spaces overlap meaninglessly. Rows are matched on natural keys only, and the
# one id-link that matters (book_levels.snapshot_id) is rewritten through a
# map built from the parent's natural key.
#
# NOTHING IS EVER DELETED. No DROP, no DELETE, no TRUNCATE of a base table.
# Staging lives in its own schema and is the only thing removed.
#
# The espn_live_* tables exist only on the server and are NOT in the table
# list, so the merge cannot touch them.
set -euo pipefail

SRC_DB="${MERIDIAN_HISTORY_DB:-meridian_history}"
DST_DB="${MERIDIAN_LIVE_DB:-meridian}"
STAGE=merge_stage
MODE="${1:---dry-run}"

cd "${MERIDIAN_HOME:-/opt/meridian}"
DC() { sudo -H -u meridian docker compose "$@"; }   # -H: without it HOME=/root
                                                    # and compose plugin lookup
                                                    # fails ("unknown flag").
SRC() { DC exec -T postgres psql -U meridian -d "$SRC_DB" -v ON_ERROR_STOP=1 "$@"; }
DST() { DC exec -T postgres psql -U meridian -d "$DST_DB" -v ON_ERROR_STOP=1 "$@"; }

log() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# table | natural key columns | id-link column (optional) | parent table
# Dependency order. book_levels after market_snapshots; shadow_orders after
# predictions; orders after both; pending_exits last.
TABLES=(
  "team_game_logs|espn_game_id,team_id||"
  "player_game_logs|espn_game_id,athlete_id||"
  "injury_reports|athlete_id,captured_at||"
  "injury_polls|captured_at||"
  "model_calibration|metric,as_of||"
  "sportsbook_odds|espn_game_id,provider_name,captured_at||"
  "resolved_outcomes|market_slug||"
  "kalshi_games|game_key||"
  "kalshi_contracts|ticker,captured_at||"
  "kalshi_snapshots|ticker,captured_at||"
  "market_snapshots|market_slug,captured_at||"
  "book_levels|snapshot_id,side,level_index|snapshot_id|market_snapshots"
  "predictions|market_slug,predicted_at,model_version,config_hash||"
  "shadow_orders|idempotency_key||"
  "orders|idempotency_key||"
  # --- added 2026-08-20 after an information_schema audit found the first
  # --- list was hand-written and short. See ANTIJOIN below for why these
  # --- five do not use ON CONFLICT.
  "pending_exits|entry_order_id||"
  "retention_log|partition_name||"
  "pulse_decisions|market_slug,decided_at,action||"
  "shadow_quote_fills|market_slug,quoted_at,side||"
  "account_balances|observed_at||"
)

#: Tables merged by anti-join rather than ON CONFLICT.
#:
#: ON CONFLICT (cols) REQUIRES a unique index on exactly those columns. These
#: tables have none beyond the primary key `id`, so the obvious
#: `ON CONFLICT (market_slug, decided_at, action)` does not fall back to
#: something reasonable — it raises "no unique or exclusion constraint matching
#: the ON CONFLICT specification" and the merge stops.
#:
#: The alternative would be creating unique indexes on the live database to
#: suit the merge. That is a schema change to production, invisible to
#: core/storage/models.py, made to satisfy a tool. `WHERE NOT EXISTS` has
#: identical semantics — the live row wins — and needs nothing.
#:
#: `DISTINCT ON` is the price of the swap: ON CONFLICT deduplicates the STAGED
#: set as a side effect (the second colliding row simply does nothing), and an
#: anti-join does not. Without it, duplicates inside history would both insert.
ANTIJOIN="pending_exits retention_log pulse_decisions shadow_quote_fills account_balances"

# --------------------------------------------------------------------------- #
log "0/6  preconditions"
# --------------------------------------------------------------------------- #
DC ps >/dev/null 2>&1 || die "docker compose not usable here (are you on the server, in /opt/meridian?)"

for db in "$SRC_DB" "$DST_DB"; do
  DC exec -T postgres psql -U meridian -d postgres -At \
    -c "select 1 from pg_database where datname='$db'" | grep -q 1 \
    || die "database $db does not exist"
done

# THE CHECK THAT MATTERS MOST. A restore in flight looks exactly like a small
# database, and merging from one folds in partial history and reports success.
# Observed while writing this: meridian_history at 3.3GB of an expected ~11GB
# with an active COPY on market_snapshots_y2026m08.
BUSY=$(DC exec -T postgres psql -U meridian -d postgres -At -c \
  "select count(*) from pg_stat_activity
    where datname='$SRC_DB' and state='active'
      and (query ilike 'COPY %' or query ilike 'ALTER TABLE %' or query ilike 'CREATE INDEX%')" | tr -d '\r')
[[ "${BUSY:-1}" == "0" ]] || die "$SRC_DB still has $BUSY active restore statement(s).
Merging from a partially restored database folds in partial history and reports
success. Wait for pg_restore to finish, then re-run."

# A restore between statements shows zero active queries, so size must also be
# stable before we believe it.
S1=$(DC exec -T postgres psql -U meridian -d postgres -At -c "select pg_database_size('$SRC_DB')" | tr -d '\r')
sleep 15
S2=$(DC exec -T postgres psql -U meridian -d postgres -At -c "select pg_database_size('$SRC_DB')" | tr -d '\r')
[[ "$S1" == "$S2" ]] || die "$SRC_DB grew $(( S2 - S1 )) bytes in 15s — still restoring."
echo "  $SRC_DB stable at $(( S2 / 1024 / 1024 )) MB, no restore statements active"
echo "  mode: $MODE"

# --------------------------------------------------------------------------- #
log "0b/6  schema audit — does the table list still cover the source?"
# --------------------------------------------------------------------------- #
# THE BUG THIS EXISTS FOR. The first version of TABLES was hand-written from
# the Supabase importer's list and never diffed against the source. It was
# short by five: pulse_decisions, shadow_quote_fills, account_balances,
# pending_exits, retention_log. The merge reported clean receipts for fifteen
# tables and silently carried none of the other five, so PULSE's first three
# nights were absent from production and the era boundary computed a day late.
#
# A hand-written list is the same class of bug one level up: it is correct until
# someone adds a table and forgets to extend it. So the script diffs itself
# against the source rather than trusting that anyone remembered.
EXCLUDED_REASON=(
  "alembic_version|migration state; the live database's own is authoritative"
  "service_heartbeats|live beats are current — merging stale ones asserts writers are dead"
  "espn_live_box_snapshots|server-side signal capture is authoritative"
  "espn_live_player_snapshots|server-side signal capture is authoritative"
  "espn_live_plays|server-side signal capture is authoritative"
  "espn_live_win_probability|server-side signal capture is authoritative"
  "espn_live_injury_observations|server-side signal capture is authoritative"
)
covered=""
for spec in "${TABLES[@]}"; do
  IFS='|' read -r t _ _ _ <<< "$spec"; covered="$covered $t"
done
for spec in "${EXCLUDED_REASON[@]}"; do
  covered="$covered ${spec%%|*}"
done

unaccounted=""
while read -r t; do
  [[ -z "$t" ]] && continue
  # Partitions arrive through their parent.
  [[ "$t" == *_default || "$t" == *_y20[0-9][0-9]m[0-9][0-9] ]] && continue
  [[ " $covered " == *" $t "* ]] || unaccounted="$unaccounted $t"
done < <(SRC -At -c "select tablename from pg_tables where schemaname='public' order by 1")

if [[ -n "$unaccounted" ]]; then
  die "tables in $SRC_DB that this script neither merges nor excludes:$unaccounted

Add each to TABLES (with its natural key) or to EXCLUDED_REASON (with the
reason). Refusing rather than merging a subset: a partial merge reports clean
receipts for what it did carry, which is exactly how the first run lost five
tables without anyone noticing."
fi
echo "  every table in $SRC_DB is either merged or excluded with a reason"

# --------------------------------------------------------------------------- #
log "1/6  staging schema (dropped and rebuilt; base tables untouched)"
# --------------------------------------------------------------------------- #
DST -c "DROP SCHEMA IF EXISTS $STAGE CASCADE; CREATE SCHEMA $STAGE;" >/dev/null

# --------------------------------------------------------------------------- #
log "2/6  copy history into staging"
# --------------------------------------------------------------------------- #
for spec in "${TABLES[@]}"; do
  IFS='|' read -r tbl keys link parent <<< "$spec"
  HAS=$(SRC -At -c "select to_regclass('public.$tbl') is not null" | tr -d '\r')
  [[ "$HAS" == "t" ]] || { echo "  $tbl: absent in $SRC_DB, skipped"; continue; }

  DST -c "CREATE TABLE $STAGE.$tbl (LIKE public.$tbl INCLUDING DEFAULTS);" >/dev/null
  # COPY (SELECT ...) TO STDOUT, never COPY <table> TO STDOUT. A PARTITIONED
  # table rejects the plain form — "cannot copy from partitioned table" — and
  # market_snapshots and book_levels are exactly that. The first run of this
  # script staged 0 rows for both, did NOT stop, and printed a receipts table
  # reading 719131 -> 719131: a merge that looks complete and contains none of
  # the 16M snapshots it exists to move.
  DC exec -T postgres sh -c \
    "psql -U meridian -d $SRC_DB -c \"COPY (SELECT * FROM public.$tbl) TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.$tbl FROM STDIN\"" >/dev/null
  n=$(DST -At -c "select count(*) from $STAGE.$tbl" | tr -d '\r')
  src_n=$(SRC -At -c "select count(*) from public.$tbl" | tr -d '\r')
  printf '  %-22s staged %12s of %12s\n' "$tbl" "$n" "$src_n"
  # A silent zero is the failure mode. Source has rows, staging has none: stop.
  [[ "$src_n" == "0" || "$n" != "0" ]] \
    || die "$tbl: source has $src_n rows but 0 staged. Refusing to continue."
done

printf '\n%-22s %12s %12s %12s %12s\n' TABLE BEFORE STAGED INSERTED AFTER
FAIL=0

merge_one() {   # $1 table  $2 natural-key cols  $3 select-list  $4 from-clause
  local tbl="$1" keys="$2" sel="$3" src="$4" before staged after inserted cols
  before=$(DST -At -c "select count(*) from public.$tbl" | tr -d '\r')
  staged=$(DST -At -c "select count(*) from $STAGE.$tbl" | tr -d '\r')
  cols=$(DST -At -c "select string_agg(quote_ident(column_name), ', ' order by ordinal_position)
                       from information_schema.columns
                      where table_schema='public' and table_name='$tbl'
                        and column_name <> 'id'" | tr -d '\r')
  if [[ "$MODE" == "--yes" ]]; then
    if [[ " $ANTIJOIN " == *" $tbl "* ]]; then
      # Same rule as ON CONFLICT — the live row wins — expressed without
      # requiring a unique index that does not exist.
      local pred=""
      local IFS_SAVE="$IFS"; IFS=','
      for k in $keys; do
        pred="${pred:+$pred AND }p.$k IS NOT DISTINCT FROM s.$k"
      done
      IFS="$IFS_SAVE"
      DST -c "INSERT INTO public.$tbl ($cols)
              SELECT $sel FROM (SELECT DISTINCT ON ($keys) * FROM $STAGE.$tbl
                                ORDER BY $keys, id) s
               WHERE NOT EXISTS (SELECT 1 FROM public.$tbl p WHERE $pred);" >/dev/null
    else
      DST -c "INSERT INTO public.$tbl ($cols) SELECT $sel $src
              ON CONFLICT ($keys) DO NOTHING;" >/dev/null
    fi
    after=$(DST -At -c "select count(*) from public.$tbl" | tr -d '\r')
    inserted=$(( after - before ))
  else
    after="$before"; inserted="(dry-run)"
  fi
  printf '%-22s %12s %12s %12s %12s\n' "$tbl" "$before" "$staged" "$inserted" "$after"
  [[ "$after" -lt "$before" ]] && { echo "  ROW COUNT WENT DOWN on $tbl"; FAIL=1; }
  return 0
}

# --------------------------------------------------------------------------- #
log "3/6  merge everything except book_levels"
# --------------------------------------------------------------------------- #
# Column lists are built by POSTGRES from information_schema, not by sed.
# Prefixing a comma-separated list with a regex works until one column name is
# a substring of another, and then silently writes the wrong column.
for spec in "${TABLES[@]}"; do
  IFS='|' read -r tbl keys link parent <<< "$spec"
  [[ -n "$link" ]] && continue          # book_levels: needs the remap first
  DST -At -c "select to_regclass('$STAGE.$tbl') is not null" | grep -q t || continue
  sel=$(DST -At -c "select string_agg('s.'||quote_ident(column_name), ', ' order by ordinal_position)
                      from information_schema.columns
                     where table_schema='public' and table_name='$tbl'
                       and column_name <> 'id'" | tr -d '\r')
  merge_one "$tbl" "$keys" "$sel" "FROM $STAGE.$tbl s"
done

# --------------------------------------------------------------------------- #
log "4/6  remap book_levels.snapshot_id — AFTER the parent merge, not before"
# --------------------------------------------------------------------------- #
# Ordering is the whole correctness argument. Built before step 3, the remap
# can only match snapshots that ALREADY existed in live, so every genuinely new
# history snapshot orphans its levels. The first run reported "snapshot ids
# mapped: 0" for exactly this reason.
#
# The 33-minute lesson: this join is millions of rows on both sides and is
# unusable without indexes. Build, index, ANALYZE, then join.
if DST -At -c "select to_regclass('$STAGE.book_levels') is not null" | grep -q t; then
  DST -c "CREATE TABLE $STAGE.snap_map (old_id bigint, market_slug text, captured_at timestamptz);" >/dev/null
  DC exec -T postgres sh -c \
    "psql -U meridian -d $SRC_DB -c \"COPY (SELECT id, market_slug, captured_at FROM public.market_snapshots) TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.snap_map FROM STDIN\"" >/dev/null
  DST -c "
    CREATE INDEX ON $STAGE.snap_map (market_slug, captured_at);
    ANALYZE $STAGE.snap_map;
    CREATE TABLE $STAGE.snap_remap AS
      SELECT m.old_id, s.id AS new_id
        FROM $STAGE.snap_map m
        JOIN public.market_snapshots s
          ON s.market_slug = m.market_slug AND s.captured_at = m.captured_at;
    CREATE UNIQUE INDEX ON $STAGE.snap_remap (old_id);
    ANALYZE $STAGE.snap_remap;
    CREATE INDEX ON $STAGE.book_levels (snapshot_id);
    ANALYZE $STAGE.book_levels;
  " >/dev/null
  mapped=$(DST -At -c "select count(*) from $STAGE.snap_remap" | tr -d '\r')
  staged_map=$(DST -At -c "select count(*) from $STAGE.snap_map" | tr -d '\r')
  orphan=$(DST -At -c "select count(*) from $STAGE.book_levels b
                        left join $STAGE.snap_remap r on r.old_id=b.snapshot_id
                        where r.new_id is null" | tr -d '\r')
  echo "  history snapshots: $staged_map · mapped to a live id: $mapped"
  echo "  book_levels with no mapped parent (skipped, never guessed): $orphan"
  if [[ "$MODE" != "--yes" ]]; then
    echo "  NOTE (dry run): nothing was inserted in step 3, so there is nothing"
    echo "  for these to map ONTO. A mapped count of 0 here is expected and says"
    echo "  nothing about the real run — book_levels numbers below are not"
    echo "  predictive. Only --yes can measure this leg."
  fi
  if [[ "$MODE" == "--yes" && "$staged_map" != "0" && "$mapped" == "0" ]]; then
    die "0 of $staged_map snapshots mapped — the parent merge did not happen."
  fi
fi

# --------------------------------------------------------------------------- #
log "5/6  merge book_levels through the remap"
# --------------------------------------------------------------------------- #
if DST -At -c "select to_regclass('$STAGE.snap_remap') is not null" | grep -q t; then
  sel=$(DST -At -c "select string_agg(
                        case when column_name='snapshot_id' then 'r.new_id'
                             else 's.'||quote_ident(column_name) end,
                        ', ' order by ordinal_position)
                      from information_schema.columns
                     where table_schema='public' and table_name='book_levels'
                       and column_name <> 'id'" | tr -d '\r')
  merge_one "book_levels" "snapshot_id,side,level_index" "$sel" \
    "FROM $STAGE.book_levels s JOIN $STAGE.snap_remap r ON r.old_id = s.snapshot_id"
fi

[[ $FAIL -eq 0 ]] || die "a table lost rows — this merge only ever inserts"

# --------------------------------------------------------------------------- #
log "6/6  sequences above the new maxima"
# --------------------------------------------------------------------------- #
if [[ "$MODE" == "--yes" ]]; then
  for spec in "${TABLES[@]}"; do
    IFS='|' read -r tbl _ _ _ <<< "$spec"
    DST -At -c "
      SELECT setval(s, GREATEST(COALESCE((SELECT max(id) FROM public.$tbl),0)+1, 1), false)
        FROM pg_get_serial_sequence('public.$tbl','id') s WHERE s IS NOT NULL;" >/dev/null || true
  done
  echo "  sequences set above max(id) for every merged table"
else
  echo "  skipped (dry run)"
fi

cat <<MSG

Staging schema $STAGE is left in place for inspection. Remove it with:
    docker compose exec -T postgres psql -U meridian -d $DST_DB -c 'DROP SCHEMA $STAGE CASCADE'

The source database $SRC_DB is NOT dropped by this script, deliberately — see
docs/infra/aws-history-merge.md. Verify the receipts first.
MSG
