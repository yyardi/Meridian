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

## The run of 2026-08-20, and the two bugs the dry run caught

| table | before | staged | inserted | after |
|---|---|---|---|---|
| market_snapshots | 719,131 | 16,030,825 | **16,030,825** | 16,749,956 |
| book_levels | 392,144 | 8,714,534 | **8,582,514** | 8,974,658 |
| predictions | 115 | 120,628 | 120,628 | 120,743 |
| kalshi_snapshots | 0 | 285,772 | 285,772 | 285,772 |
| sportsbook_odds | 290 | 18,116 | 18,116 | 18,406 |
| shadow_orders | 0 | 14,189 | 14,189 | 14,189 |
| team_game_logs | 12 | 3,402 | 3,390 | 3,402 |
| player_game_logs | 153 | 19,507 | 19,354 | 19,507 |
| resolved_outcomes | 0 | 2,202 | 2,202 | 2,202 |
| kalshi_games | 11 | 52 | 41 | 52 |
| orders | 0 | 5 | 5 | 5 |

Snapshot remap: **16,030,825 of 16,030,825 mapped, 0 orphans.**

**`market_snapshots` had zero conflicts** — 719,131 + 16,030,825 lands exactly on
16,749,956. The server's first-night capture and the laptop's history are
disjoint windows, so the server-wins rule never had to fire on the big table. It
did fire on the small ones: 12 `team_game_logs`, 153 `player_game_logs` and 11
`kalshi_games` rows were skipped, each one a server row that stayed.

**`book_levels` skipped 132,020, and every one is accounted for.** It is not
overlap with the server: it is 11,479 groups of duplicate
`(snapshot_id, side, level_index)` *within history's own data*, and the excess
sums to exactly 132,020. `ON CONFLICT DO NOTHING` kept one of each.

### Both bugs were found by the dry run, and both were silent

**`COPY <partitioned table> TO STDOUT` is rejected outright.** `market_snapshots`
and `book_levels` are partitioned, so both staged **0 rows** — and the script did
not stop. It printed a clean receipts table reading `market_snapshots 719131 →
719131`. Run with `--yes`, that is a merge that reports success and contains
none of the 16M snapshots it exists to move. Fixed with the
`COPY (SELECT * FROM ...)` variant, plus an abort when the source has rows and
staging has none.

**The remap was built before the parent merge.** It could therefore only match
snapshots that *already* existed in live, so every genuinely new history
snapshot would have orphaned its levels — the first dry run reported
`mapped: 0`, `orphaned: 8,714,534`. Merging `market_snapshots` first and
building the remap after took it to 16,030,825 mapped and 0 orphans.

Neither bug would have raised an error. Both would have produced a merge that
looked complete.

## Two live bugs folded in from the first migration

* **`migrate.sh` defaulted to a PREVIOUS account's bucket.** It exists, it just
  was not ours, so the failure read as a credentials problem. There is now no
  default at all: `MERIDIAN_S3_BUCKET` is required. That removes the
  stale-default trap and, separately, keeps an AWS account id — which is what a
  bucket name embeds — out of a public repository.
* **`provision.sh` used `sudo -u meridian --preserve-env=HOME`**, which keeps
  `HOME=/root`. The docker CLI looks for plugins under `$HOME/.docker/cli-plugins`,
  so `compose` vanishes and the error surfaces as `unknown flag: --env-file`
  rather than "no such subcommand". Now `sudo -H -u meridian`, verified working
  on the live instance.

## Partition swap verification on a live server

`retention.migrate` renames each tick table to `*_preswap`, builds a partitioned
parent, copies the rows in, and then checks its work before dropping the old
table. The original check compared raw row counts:

    count(market_snapshots) == count(market_snapshots_preswap)

That is only true if nothing writes during the swap — a laptop-era assumption.
On the server the 200ms recorder never stops, so the parent is legitimately
larger the moment the copy commits, the check raises, and both tables are kept.
The swap was correct; the verification was measuring a quantity that cannot
hold still.

The check now compares at the **id boundary**: `max(id)` of the `*_preswap`
table is the high-water mark at swap time, every row at or below it must be
present in the parent, and everything above it arrived afterwards. Ids come
from a sequence and only increase, so no post-swap row can land below the
boundary — which is what makes equality there a proof rather than a
coincidence.

### Receipts from the live swap (2026-08-21, off-slate)

| table | preswap rows | boundary id | parent rows ≤ boundary | post-swap writes |
|---|---|---|---|---|
| `market_snapshots` | 17,795,882 | 97,950,927 | 17,795,882 (exact) | 228 |
| `book_levels` | 9,624,430 | 18,363,023 | 9,624,430 (exact) | 4,872 |

Count equality at the boundary is a strong argument, not a proof, so it was
confirmed by anti-join — for each preswap row, does a row with that id exist in
the parent?

    select (select count(*) from market_snapshots_preswap p
              where not exists (select 1 from market_snapshots m where m.id = p.id)),
           (select count(*) from book_levels_preswap p
              where not exists (select 1 from book_levels b where b.id = p.id))

Result: **0 and 0** — no pre-swap row is missing from either parent. This is the
gating evidence for dropping the `*_preswap` tables.
