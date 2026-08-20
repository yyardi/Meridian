# Folding the laptop's history into the live server database

```bash
# on the server, in /opt/meridian
deploy/aws/merge_history.sh --dry-run    # counts only, writes nothing
deploy/aws/merge_history.sh --yes
```

This runs at least twice: once for the bulk history, and again at cutover for
the laptop's final days of recording. It is a script rather than a session of
psql for that reason.

## The direction is the opposite of the Supabase import

`scripts/import_supabase_export.py` treated the export as authoritative — a
stale local mirror row took the export's values. **Here the server wins.** Its
capture of the first night beat the laptop's by **+2.7% ticks/game**, so on any
overlapping row the live copy stays and the history row is skipped:

```sql
INSERT INTO public.<table> (...) SELECT ... ON CONFLICT (<natural key>) DO NOTHING
```

Getting this backwards would quietly replace the better capture with the worse
one and change no row count, which is why the direction is stated here, in the
script's header, and in the commit that added it.

## Ids are never trusted

Both databases have their own sequences and their id spaces overlap
meaninglessly. Every table is matched on a natural key:

| table | natural key |
|---|---|
| `market_snapshots` | `(market_slug, captured_at)` |
| `book_levels` | `(snapshot_id, side, level_index)` — **snapshot_id remapped first** |
| `predictions` | `(market_slug, predicted_at, model_version, config_hash)` |
| `orders`, `shadow_orders` | `(idempotency_key)` |
| `sportsbook_odds` | `(espn_game_id, provider_name, captured_at)` |
| `kalshi_snapshots`, `kalshi_contracts` | `(ticker, captured_at)` |
| `team_game_logs` | `(espn_game_id, team_id)` |
| `resolved_outcomes` | `(market_slug)` |

`book_levels.snapshot_id` is rewritten through a map built from the parent's
natural key: history id → `(market_slug, captured_at)` → live id. **The join is
indexed before it runs** — that is the 33-minute lesson, and the map, the
staging table and the remap are all indexed and `ANALYZE`d first.

A `book_levels` row whose parent does not map is **skipped and counted**, never
attached to a guessed snapshot.

## The check that matters most

**A restore in flight looks exactly like a small database.** Merging from one
folds in partial history and reports success — every count is internally
consistent and simply wrong.

Observed while writing this: `meridian_history` sat at 3,288 MB of an expected
~11 GB with an active `COPY public.market_snapshots_y2026m08`. Twenty minutes
later it was 7,686 MB and still going.

So the script refuses to start unless **both** are true:

1. no active `COPY` / `ALTER TABLE` / `CREATE INDEX` on the source, and
2. `pg_database_size` is unchanged across a 15-second sample — because a
   restore between statements shows zero active queries.

Verified live: run against the server mid-restore, it aborted at step 0 without
creating a staging schema or touching a base table.

## What it will not do

* **No deletes.** No `DROP`, `DELETE` or `TRUNCATE` of a base table. Staging
  lives in its own `merge_stage` schema and is the only thing removed.
* **Never touches `espn_live_*`.** Those five tables
  (`espn_live_box_snapshots`, `_player_snapshots`, `_plays`,
  `_win_probability`, `_injury_observations`) exist only on the server and are
  simply absent from the table list, so the merge cannot reach them. There is a
  safety dump at `/backups/signal-night1.dump` regardless.
* **Does not drop `meridian_history`.** See below.

## Receipts

Every table prints `before / staged / inserted / after`, and the run aborts if
any count goes **down** — this merge only ever inserts, so a decrease means
something other than the merge is happening.

Sequences are set above `max(id)` per table at the end.

## Dropping the history database is a separate, human step

The script deliberately stops short of `DROP DATABASE meridian_history`.

It is recoverable — the source dump is still on the instance at
`/backups/laptop.dump` (312,796,702 bytes) — but a `DROP DATABASE` is
irreversible in itself, and the whole point of the receipts is that somebody
reads them before the fallback disappears. It costs one command once you have:

```bash
docker compose exec -T postgres psql -U meridian -d postgres \
  -c 'DROP DATABASE meridian_history'
```

Do that **after** the receipts have been read, not as the last line of a script
whose output nobody has looked at yet.

## Two live bugs folded in from the first migration

* **`migrate.sh` defaulted to the old account's bucket**
  (`meridian-backups-298030125776`). It exists, it just is not ours, so the
  failure read as a credentials problem. Now `meridian-backups-623955527388`,
  and the runbook was corrected to match — a script and a doc disagreeing about
  a bucket name is what caused this.
* **`provision.sh` used `sudo -u meridian --preserve-env=HOME`**, which keeps
  `HOME=/root`. The docker CLI looks for plugins under `$HOME/.docker/cli-plugins`,
  so `compose` vanishes and the error surfaces as `unknown flag: --env-file`
  rather than "no such subcommand". Now `sudo -H -u meridian`, verified working
  on the live instance.
