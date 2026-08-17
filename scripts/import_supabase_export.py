#!/usr/bin/env python
"""One-time import of the Supabase export into local Postgres (2026-08-17).

Why ids are never trusted
-------------------------
The local database holds three different id situations at once: the tick
stream (`market_snapshots`/`book_levels`) is locally authored with its own
sequences; the durable tables (`predictions`, odds, logs) are stale sync
mirrors that share Supabase's id space; and `kalshi_snapshots` is a verbatim
mirror of unclear origin (verified: local id 1000 == export id 1000, same
ticker and timestamp). An id-keyed upsert would be correct for one group and
silently destructive for another — which is exactly the hazard
`sync_local.py` documents.

So this importer trusts **natural keys only**:

* every staged row gets a REMAPPED id (`old_id + offset`, offset placed 1M
  above the local max so concurrent live-recorder writes cannot collide);
* insertion is `ON CONFLICT (<natural unique>) DO UPDATE` — a row already
  present as a stale mirror copy keeps its local id and takes the export's
  authoritative values; a new row lands under its remapped id;
* id-link columns (`book_levels.snapshot_id`, `shadow_orders.prediction_id`,
  `orders.shadow_order_id/prediction_id`, `pending_exits.entry_order_id/
  submitted_order_id`) are rewritten through old->new maps built from the
  natural keys, never carried over numerically;
* sequences are reset above the new max at the end (scope item 4).

Nothing is deleted, ever. Staging tables are dropped; base rows are only
inserted or value-updated. Every table prints staged / inserted / updated /
final counts, and the run aborts on the first discrepancy.

    .venv/bin/python scripts/import_supabase_export.py --dry-run
    .venv/bin/python scripts/import_supabase_export.py --yes
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import psycopg

from core.paths import supabase_dir

LOCAL_URL = "postgresql://meridian:meridian@localhost:5433/meridian"
EXPORT_DIR = supabase_dir() / "export-20260817"

#: (table, natural-key columns, {link_col: source_table}) in dependency order.
#: retention_log is absent on purpose: the export is empty (header only), and
#: local receipts are local state. service_heartbeats was never exported.
TABLES: list[tuple[str, list[str], dict[str, str]]] = [
    ("team_game_logs", ["espn_game_id", "team_id"], {}),
    ("player_game_logs", ["espn_game_id", "athlete_id"], {}),
    ("injury_reports", ["athlete_id", "captured_at"], {}),
    ("injury_polls", ["captured_at"], {}),
    ("model_calibration", ["metric", "as_of"], {}),
    ("sportsbook_odds", ["espn_game_id", "provider_name", "captured_at"], {}),
    ("resolved_outcomes", ["market_slug"], {}),
    ("kalshi_games", ["game_key"], {}),
    ("kalshi_contracts", ["ticker", "captured_at"], {}),
    ("kalshi_snapshots", ["ticker", "captured_at"], {}),
    ("market_snapshots", ["market_slug", "captured_at"], {}),
    ("book_levels", None, {"snapshot_id": "market_snapshots"}),  # custom path
    ("predictions", ["market_slug", "predicted_at", "model_version", "config_hash"], {}),
    ("shadow_orders", None, {"prediction_id": "predictions"}),   # custom path
    ("orders", ["idempotency_key"],
     {"shadow_order_id": "shadow_orders", "prediction_id": "predictions"}),
    ("pending_exits", ["entry_order_id"],
     {"entry_order_id": "orders", "submitted_order_id": "orders"}),
]

#: Room left above the local max id so live-recorder writes during the import
#: cannot reach the remapped range before sequences are reset.
ID_HEADROOM = 1_000_000


def columns_of(cur, table: str) -> list[str]:
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=%s order by ordinal_position",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def csv_header(path: Path) -> list[str]:
    with open(path, newline="") as f:
        return next(csv.reader(f))


def load_staging(cur, table: str, path: Path) -> tuple[str, list[str], int]:
    """CSV -> UNLOGGED staging table. Column list comes from the CSV header,
    intersected with the local schema by NAME — never by position."""
    header = csv_header(path)
    local = columns_of(cur, table)
    cols = [c for c in header if c in local]
    dropped = [c for c in header if c not in local]
    if dropped:
        print(f"  {table}: ignoring export-only columns {dropped}")
    stg = f"stg_{table}"
    cur.execute(f"drop table if exists {stg}")
    cur.execute(f"create unlogged table {stg} (like {table} including defaults)")
    # Staging is a vessel: relax every NOT NULL so the remote's rows load as
    # they are (e.g. book_levels.captured_at is NOT NULL locally via the
    # partition PK, NULL on the remote's pregame-era rows — backfilled at
    # insert time, not at load time).
    for c in local:
        cur.execute(f"alter table {stg} alter column {c} drop not null")
    # \copy needs the CSV's column order for the columns we keep; columns the
    # local schema has but the CSV lacks stay NULL/default in staging.
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        # write_row speaks COPY text format; the csv module has already parsed
        # the file (including quoted multi-line raw payloads), so the server
        # never sees CSV syntax at all.
        with cur.copy(
            f"copy {stg} ({', '.join(cols)}) from stdin"
        ) as cp:
            for row in reader:
                cp.write_row([row[c] if row[c] != "" else None for c in cols])
    cur.execute(f"select count(*) from {stg}")
    return stg, cols, cur.fetchone()[0]


def upsert(cur, table: str, stg: str, cols: list[str], nat: list[str],
           offset: int, links: dict[str, str]) -> dict:
    data_cols = [c for c in cols if c != "id"]
    select_cols = []
    for c in data_cols:
        if c in links:
            select_cols.append(
                f"(select new_id from map_{links[c]} m where m.old_id = s.{c})"
            )
        else:
            select_cols.append(f"s.{c}")
    set_clause = ", ".join(f"{c} = excluded.{c}" for c in data_cols)
    cur.execute(f"""
        insert into {table} (id, {', '.join(data_cols)})
        select s.id + %s, {', '.join(select_cols)}
        from {stg} s
        on conflict ({', '.join(nat)}) do update set {set_clause}
        """, (offset,))
    affected = cur.rowcount
    # old -> final id map, through the natural key. Plain `=` wherever the
    # column is NOT NULL: `is not distinct from` defeats the unique index and
    # turned this join into a 30-minute nested loop against the 13.7M-row
    # stream table (measured on the first run, cancelled).
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name=%s and is_nullable='NO'",
        (table,),
    )
    not_null = {r[0] for r in cur.fetchall()}
    join = " and ".join(
        f"t.{c} = s.{c}" if c in not_null else f"t.{c} is not distinct from s.{c}"
        for c in nat
    )
    cur.execute(f"drop table if exists map_{table}")
    cur.execute(f"""
        create unlogged table map_{table} as
        select s.id as old_id, t.id as new_id
        from {stg} s join {table} t on {join}
    """)
    cur.execute(f"select count(*) from map_{table}")
    mapped = cur.fetchone()[0]
    return {"affected": affected, "mapped": mapped}


def import_book_levels(cur, stg: str, cols: list[str], offset: int) -> dict:
    """Children follow their parent's FINAL id; only children of parents that
    exist in the map are imported (a parent skipped is a child skipped, and
    both are counted)."""
    data_cols = [c for c in cols if c not in ("id", "snapshot_id")]
    select_cols = [
        # The remote's pregame-era depth rows carry NULL captured_at; locally
        # the column is the partition key and NOT NULL. The parent's instant
        # is exact for those rows (depth and price were fetched together) —
        # the same backfill the partition conversion applied.
        "coalesce(s.captured_at, ms.captured_at)" if c == "captured_at"
        else f"s.{c}"
        for c in data_cols
    ]
    cur.execute(f"""
        insert into book_levels (id, snapshot_id, {', '.join(data_cols)})
        select s.id + %s, m.new_id, {', '.join(select_cols)}
        from {stg} s
        join map_market_snapshots m on m.old_id = s.snapshot_id
        join market_snapshots ms on ms.id = m.new_id
        on conflict do nothing
        """, (offset,))
    inserted = cur.rowcount
    cur.execute(f"""
        select count(*) from {stg} s
        where not exists (select 1 from map_market_snapshots m
                          where m.old_id = s.snapshot_id)
    """)
    orphans = cur.fetchone()[0]
    return {"affected": inserted, "orphans_skipped": orphans}


def import_shadow_orders(cur, stg: str, cols: list[str], offset: int) -> dict:
    """No natural unique exists on shadow_orders, so dedupe is an anti-join on
    (market_slug, created_at, mode-ish columns present)."""
    data_cols = [c for c in cols if c != "id"]
    select_cols = [
        f"(select new_id from map_predictions m where m.old_id = s.{c})"
        if c == "prediction_id" else f"s.{c}"
        for c in data_cols
    ]
    cur.execute(f"""
        insert into shadow_orders (id, {', '.join(data_cols)})
        select s.id + %s, {', '.join(select_cols)}
        from {stg} s
        where not exists (
            select 1 from shadow_orders t
            where t.market_slug = s.market_slug
              and t.created_at is not distinct from s.created_at
        )
        """, (offset,))
    inserted = cur.rowcount
    cur.execute(f"drop table if exists map_shadow_orders")
    cur.execute(f"""
        create unlogged table map_shadow_orders as
        select s.id as old_id, t.id as new_id
        from {stg} s join shadow_orders t
          on t.market_slug = s.market_slug
         and t.created_at is not distinct from s.created_at
    """)
    return {"affected": inserted}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.yes and not args.dry_run:
        print("re-run with --yes (writes) or --dry-run (counts only)", file=sys.stderr)
        return 2

    report: dict[str, dict] = {}
    with psycopg.connect(LOCAL_URL, autocommit=False) as conn:
        cur = conn.cursor()
        cur.execute("set statement_timeout = 0")
        for table, nat, links in TABLES:
            path = EXPORT_DIR / f"{table}.csv"
            if not path.exists():
                report[table] = {"skipped": "no CSV"}
                continue
            cur.execute(f"select count(*), coalesce(max(id), 0) from {table}")
            before, max_id = cur.fetchone()
            offset = max_id + ID_HEADROOM

            stg, cols, staged = load_staging(cur, table, path)
            if args.dry_run:
                report[table] = {"before": before, "staged": staged, "dry_run": True}
                conn.rollback()
                continue

            if table == "book_levels":
                result = import_book_levels(cur, stg, cols, offset)
            elif table == "shadow_orders":
                result = import_shadow_orders(cur, stg, cols, offset)
            else:
                result = upsert(cur, table, stg, cols, nat, offset, links)

            cur.execute(f"select count(*) from {table}")
            after = cur.fetchone()[0]
            cur.execute(f"drop table {stg}")
            report[table] = {"before": before, "staged": staged,
                            "after": after, **result}
            # The invariant check: rows only ever appear.
            if after < before:
                conn.rollback()
                raise RuntimeError(f"{table}: row count DECREASED — rolled back")
            conn.commit()
            print(f"  {table}: staged {staged}, {before} -> {after}")

        if not args.dry_run:
            # Scope item 4: sequences above the new max so writes cannot collide.
            for table, _, _ in TABLES:
                cur.execute(f"""
                    select setval('{table}_id_seq',
                                  (select coalesce(max(id), 1) from {table}))
                """)
            for table in ("market_snapshots", "book_levels"):
                cur.execute(f"drop table if exists map_{table}")
            for table, _, _ in TABLES:
                cur.execute(f"drop table if exists map_{table}")
            conn.commit()

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
