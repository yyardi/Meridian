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
)

# --------------------------------------------------------------------------- #
log "0/5  preconditions"
# --------------------------------------------------------------------------- #
DC ps >/dev/null 2>&1 || die "docker compose not usable here (are you on the server, in /opt/meridian?)"

for db in "$SRC_DB" "$DST_DB"; do
  DC exec -T postgres psql -U meridian -d postgres -At \
    -c "select 1 from pg_database where datname='$db'" | grep -q 1 \
    || die "database $db does not exist"
done

# THE CHECK THAT MATTERS MOST. A restore in flight looks exactly like a small
# database, and merging from one folds in partial history and reports success.
# Observed while writing this: meridian_history sat at 3.3GB of an expected
# ~11GB with an active COPY on market_snapshots_y2026m08.
BUSY=$(DC exec -T postgres psql -U meridian -d postgres -At -c \
  "select count(*) from pg_stat_activity
    where datname='$SRC_DB' and state='active'
      and (query ilike 'COPY %' or query ilike 'ALTER TABLE %' or query ilike 'CREATE INDEX%')" | tr -d '\r')
[[ "${BUSY:-1}" == "0" ]] || die "$SRC_DB still has $BUSY active restore statement(s).
Merging from a partially restored database folds in partial history and reports
success. Wait for pg_restore to finish, then re-run."

# Size must also be stable — a restore between statements shows 0 active.
S1=$(DC exec -T postgres psql -U meridian -d postgres -At -c "select pg_database_size('$SRC_DB')" | tr -d '\r')
sleep 15
S2=$(DC exec -T postgres psql -U meridian -d postgres -At -c "select pg_database_size('$SRC_DB')" | tr -d '\r')
[[ "$S1" == "$S2" ]] || die "$SRC_DB grew $(( S2 - S1 )) bytes in 15s — still restoring."
echo "  $SRC_DB stable at $(( S2 / 1024 / 1024 )) MB, no restore statements active"
echo "  mode: $MODE"

# --------------------------------------------------------------------------- #
log "1/5  staging schema (dropped and rebuilt; base tables untouched)"
# --------------------------------------------------------------------------- #
DST -c "DROP SCHEMA IF EXISTS $STAGE CASCADE; CREATE SCHEMA $STAGE;" >/dev/null

# --------------------------------------------------------------------------- #
log "2/5  copy history into staging"
# --------------------------------------------------------------------------- #
for spec in "${TABLES[@]}"; do
  IFS='|' read -r tbl keys link parent <<< "$spec"
  # Skip a table the source does not have rather than aborting the whole run.
  HAS=$(SRC -At -c "select to_regclass('public.$tbl') is not null" | tr -d '\r')
  [[ "$HAS" == "t" ]] || { echo "  $tbl: absent in $SRC_DB, skipped"; continue; }

  DST -c "CREATE TABLE $STAGE.$tbl (LIKE public.$tbl INCLUDING DEFAULTS);" >/dev/null
  DC exec -T postgres sh -c \
    "psql -U meridian -d $SRC_DB -c \"COPY public.$tbl TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.$tbl FROM STDIN\"" >/dev/null
  n=$(DST -At -c "select count(*) from $STAGE.$tbl" | tr -d '\r')
  printf '  %-22s staged %s\n' "$tbl" "$n"
done

# --------------------------------------------------------------------------- #
log "3/5  remap book_levels.snapshot_id through the parent's natural key"
# --------------------------------------------------------------------------- #
# The 33-minute lesson: this join is over millions of rows on both sides and is
# unusable without indexes. Build the map, index it, THEN join.
if DST -At -c "select to_regclass('$STAGE.book_levels') is not null" | grep -q t; then
  DST -c "CREATE TABLE $STAGE.snap_map (old_id bigint, market_slug text, captured_at timestamptz);" >/dev/null
  DC exec -T postgres sh -c \
    "psql -U meridian -d $SRC_DB -c \"COPY (SELECT id, market_slug, captured_at FROM public.market_snapshots) TO STDOUT\" | psql -U meridian -d $DST_DB -c \"COPY $STAGE.snap_map FROM STDIN\"" >/dev/null
  DST -c "
    CREATE INDEX ON $STAGE.snap_map (old_id);
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
  orphan=$(DST -At -c "select count(*) from $STAGE.book_levels b
                        left join $STAGE.snap_remap r on r.old_id=b.snapshot_id
                        where r.new_id is null" | tr -d '\r')
  echo "  snapshot ids mapped: $mapped"
  echo "  book_levels with no mapped parent (will be skipped, never guessed): $orphan"
fi

# --------------------------------------------------------------------------- #
log "4/5  merge — ON CONFLICT DO NOTHING, the live row always wins"
# --------------------------------------------------------------------------- #
printf '\n%-22s %12s %12s %12s %12s\n' TABLE BEFORE STAGED INSERTED AFTER
FAIL=0
for spec in "${TABLES[@]}"; do
  IFS='|' read -r tbl keys link parent <<< "$spec"
  DST -At -c "select to_regclass('$STAGE.$tbl') is not null" | grep -q t || continue

  before=$(DST -At -c "select count(*) from public.$tbl" | tr -d '\r')
  staged=$(DST -At -c "select count(*) from $STAGE.$tbl" | tr -d '\r')

  # Column lists are built by POSTGRES, not by sed. Prefixing a
  # comma-separated list with a regex is the kind of thing that works until a
  # column name is a substring of another one, and then silently writes the
  # wrong column. information_schema knows the answer exactly.
  cols=$(DST -At -c "select string_agg(quote_ident(column_name), ', ' order by ordinal_position)
                       from information_schema.columns
                      where table_schema='public' and table_name='$tbl'
                        and column_name <> 'id'" | tr -d '\r')
  sel=$(DST -At -c "select string_agg(
                        case when column_name = '$link'
                             then 'r.new_id'
                             else 's.' || quote_ident(column_name) end,
                        ', ' order by ordinal_position)
                       from information_schema.columns
                      where table_schema='public' and table_name='$tbl'
                        and column_name <> 'id'" | tr -d '\r')
  if [[ -n "$link" ]]; then
    src="FROM $STAGE.$tbl s JOIN $STAGE.snap_remap r ON r.old_id = s.$link"
  else
    src="FROM $STAGE.$tbl s"
  fi

  if [[ "$MODE" == "--yes" ]]; then
    DST -c "INSERT INTO public.$tbl ($cols) SELECT $sel $src
            ON CONFLICT ($keys) DO NOTHING;" >/dev/null
    after=$(DST -At -c "select count(*) from public.$tbl" | tr -d '\r')
    inserted=$(( after - before ))
  else
    after="$before"; inserted="(dry-run)"
  fi
  printf '%-22s %12s %12s %12s %12s\n' "$tbl" "$before" "$staged" "$inserted" "$after"
  [[ "$after" -lt "$before" ]] && { echo "  ROW COUNT WENT DOWN on $tbl"; FAIL=1; }
done
[[ $FAIL -eq 0 ]] || die "a table lost rows — this merge only ever inserts"

# --------------------------------------------------------------------------- #
log "5/5  sequences above the new maxima"
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
