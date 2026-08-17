# Retention — monthly partitions, archive-then-detach, no tick ever deleted

**Implemented 2026-08-07** (`core/retention.py`). This replaces the earlier
proposal on this page, and is stricter than it: the proposal's downsampling
tiers (30s thinning, dropping deep book levels) are **not built and not
planned**. Every future in-game hypothesis replays the tick archive, so the
invariant is absolute — **no row is ever deleted without a verified copy
existing first**, and nothing is thinned at all. "Retention" moves whole
months out of the live database into compressed dumps; it never discards.

## The shape

`market_snapshots` and `book_levels` are natively partitioned by
`captured_at`, one partition per calendar month (`market_snapshots_y2026m08`,
…), plus a DEFAULT partition as a safety net: a row whose month has no
partition lands in DEFAULT rather than erroring, so a missed maintenance run
can never cost data — the health check reports a non-empty DEFAULT instead.

Conversion measured on 2026-08-07: 3,582,007 snapshot rows + 1,439,117 book
rows copied in ~3 minutes inside one transaction, old tables kept until row
counts matched exactly, then dropped. Legacy NULL `captured_at` book rows
(328,753 — from the era when depth and price were fetched together) were first
backfilled from their parent snapshot's timestamp, which is exact for that era.

Schema deltas the conversion made (Postgres requires the partition key in
every unique constraint):

* PKs are now `(id, captured_at)`; `id` keeps its sequence.
* `uq_snapshot_market_time` unchanged — recorder idempotency intact by name
  and semantics (`tests/test_retention.py` pins it).
* `uq_book_level` gained `captured_at`; every writer stamps one value per
  batch, so rerun-idempotency is preserved.
* The `book_levels → market_snapshots` FK is gone (cannot reference a
  partitioned table without the key). The join column is unchanged; test
  fixtures now delete levels explicitly instead of riding the cascade.

**Local only.** The conversion is an explicit operator command, deliberately
NOT an Alembic migration — `alembic upgrade head` runs on every container
start against both databases, and a full-table rewrite must never happen
implicitly against Supabase (395 of 500 MB). Only the small `retention_log`
receipts table travels through Alembic.

## Archival of a month — the order is the invariant

```bash
python -m core.retention archive --yes     # refuses while a game is live
```

For each month wholly older than **30 days** (`KEEP_DAYS`), per table:

1. `pg_dump -Fc` the partition to `ticks/` under the artifact root ([infra/artifact-paths.md](artifact-paths.md); bind-mounted into the
   postgres container — the host has no pg client tools).
2. **Verify the dump restores**: scratch database, parent schema, `pg_restore`,
   then row count and min/max id must equal the live partition exactly.
3. Record rows, bytes, sha256 and `verified_at` in `retention_log`.
4. Only then `DETACH PARTITION` and drop the detached table.

Any failure aborts **before** step 4 — proven in anger on the first run, when
a pg_restore constraint-replay quirk failed verification and the partition
stayed attached. The worst reachable outcome is a stale dump file; a missing
month is unreachable by construction.

Restoring an archived month later (two steps, because replaying the dump's
post-data against the live parent duplicates the cascaded constraint):

```bash
docker compose exec -T postgres env PGUSER=meridian PGDATABASE=meridian \
  pg_restore -d meridian --section=pre-data --section=data /backups/<partition>.dump
```

then attach it: `alter table market_snapshots attach partition
market_snapshots_y2026m07 for values from ('2026-07-01') to ('2026-08-01');`

## Operations

| command | does |
|---|---|
| `python -m core.retention status` | partitions, DEFAULT row counts, what's archivable, log tail |
| `python -m core.retention ensure` | create current + 2 future monthly partitions |
| `python -m core.retention archive --yes` | dump → verify → detach eligible months |
| `python -m core.retention migrate --yes` | the one-time conversion (done 2026-08-07) |

`migrate` and `archive` refuse to run while a game is live (the conversion
holds an ACCESS EXCLUSIVE lock and the 200ms writer would drop ticks once its
30s buffer fills). Run between slates, like rebuilds.

Health: `check_retention` in [`core/healthchecks.py`](../../core/healthchecks.py)
— evaluated by `scripts/health.py` and pushed by the alerter — warns on rows
stranded in DEFAULT, a missing current-month partition, and any month still
attached 15 days past eligibility (`GRACE_DAYS`). Disk free already warns at
20 GB.

## The Supabase rolling window (added 2026-08-07, flow emergency)

The primary grows ~59 MB/day against its 500 MB cap with no cold stock to
shed (nothing older than 14 days exists). `python -m core.retention
supabase-rolling --yes` applies the same invariant to the three big tables
(`book_levels`, `predictions`, `market_snapshots` — **not** `kalshi_snapshots`,
whose rows the pre-registered venue-gap gate counts):

1. Export the >72h slice per table as CSV via `\copy` (version-agnostic —
   pg_dump 16 refuses the PG 17 server, measured; CSV is also readable
   forever, a virtue in an archive) to `supabase/` under the artifact root.
2. Load into a local scratch database and require an exact count match on the
   closed set (rows older than the cutoff can neither appear nor vanish).
3. Receipt in `retention_log`, then DELETE the archived rows, then
   `VACUUM FULL` smallest-table-first (the enforced number is the *reported*
   size, which DELETE alone never shrinks).

Any verification failure aborts with nothing deleted **and pushes urgent to
the phone** — both failure pushes observed live on 2026-08-07 behaved exactly
so. Every run's receipts appear in the alerter's daily digest, alongside the
`Supabase: <MB> · ~MB/day · days-to-cap` line.

The scheduler runs it automatically every ~3 days (`rolling_if_due` — the
receipts are the cadence state, so restarts cannot double-run it; it skips
itself while a game is live). "Log every prediction, forever" holds: every
row lives on in the verified archive; the live table is the working set.

## What this deliberately does not do

* **No downsampling, no dropping `raw`, no depth thinning.** The earlier
  proposal's Tier B/C are superseded: disk is bounded by moving months into
  compressed dumps, not by discarding resolution the microstructure gates may
  yet need.
* **No automation of the archive step.** It runs by hand (or a future cron)
  precisely because it ends in a `DROP`; the health check nags when it is
  overdue rather than anything dropping data on a timer.
* **Nothing touches Supabase.** Its 395 MB problem is separate (archive &
  VACUUM FULL, tracked by its own WARN).
