# Retention: what to keep at full resolution, and for how long

**Proposal, not yet applied.** Nothing has been deleted. The market stream is
the one unrecoverable dataset in this project, so pruning it is a decision to
take deliberately rather than a change to slip in.

## Where it stands

Measured 2026-08-03, roughly one day after the recorder moved to 200ms:

| | rows | on disk | bytes/row |
|---|---|---|---|
| `market_snapshots` | ~857,000 | 598 MB | ~700 |
| `book_levels` | ~735,000 | 118 MB | ~161 |
| **total** | | **751 MB** | |

From the recorder's own per-minute log, one live game writes **~1,750 snapshot
rows/min** and ~950 book levels/min. Over a two-hour game:

```
snapshots   210,000 rows x 700 B  = 147 MB
book_levels 114,000 rows x 161 B  =  18 MB
                              per game ~165 MB
```

At roughly 90 games a month and ~4 months of season left, that is **~55-60 GB**.
Supabase Pro includes 8 GB.

The table is already past the point of being queryable in the obvious ways:
`count(*)` exceeds the two-minute statement timeout, and so does a grouped
aggregate over a *six-hour* window. That is not only a cost problem — it is
already shaping what analysis is possible.

## What the data is actually for

This is the part that decides the policy, and it is narrower than it looks.

| Consumer | Resolution it needs | Window it needs |
|---|---|---|
| Microstructure gates ([adverse-selection](../math/adverse-selection.md), [run-overreaction](../math/run-overreaction.md), [depth-signal](../math/depth-signal.md)) | **full 200ms** | **~10 games** |
| ANCHOR / CLV | one point near tip-off, plus the close | whole season |
| Venue-gap and news windows | ~30s | whole season |
| Long-run audit, "what did the board look like" | ~1 min | whole season |

Only the first row needs 200ms, and it needs about **ten games** of it — the
pre-registered gates are n ≥ 10 games, and a second run after a bug fix is
worth budgeting for. Ten games is **~1.7 GB**. Four months of 200ms is 55 GB.
We are proposing to store thirty times what the only consumer of it requires.

## Proposal

**Tier A — full resolution, last 7 days.** Everything exactly as recorded.
At ~3 games a slate day that is ~20 games, twice the gate requirement, with
room to re-run. Steady state ~3.5 GB.

**Tier B — beyond 7 days, downsample to one row per market per 30 seconds.**
30s is precisely the cadence this recorder ran at until 2026-08-02, and it was
adequate for everything except microstructure. A 150x reduction: a game's
snapshots go from 147 MB to ~1 MB.

**Tier C — beyond 7 days, drop `book_levels` except `level_index = 0`.**
Depth outside the experiment window serves no analysis we have defined, and
top-of-book is already denormalised onto `market_snapshots` as
`best_bid`/`best_ask`. This is ~85% of the depth table.

Steady state: **~3.5 GB rolling plus ~1 MB per archived game** — flat, rather
than 60 GB and climbing.

## Mechanism: partition first, and do it soon

Use monthly `RANGE` partitions on `captured_at` for both tables.

The reason is not elegance. Ageing data out of an unpartitioned table means
`DELETE` over tens of millions of rows, which leaves dead tuples that need a
`VACUUM FULL` — an `ACCESS EXCLUSIVE` lock and a full table rewrite needing
double the disk. On a table that already cannot be counted, that is not a
maintenance operation, it is an outage. With partitions, ageing out is
`DETACH`/`DROP PARTITION`: O(1), no lock on live writes, no vacuum.

**This gets harder every day.** Converting a table to partitioned requires
copying it. At 751 MB that is minutes; at 20 GB it is a maintenance window we
do not have a way to take without losing recording time. If any part of this
proposal is adopted, adopt the partitioning part first.

Order:

1. Partition `market_snapshots` and `book_levels` by month (do this now).
2. Add the downsampling job, run it dry first and diff the row counts.
3. Only then start dropping old partitions.

## What is deliberately not proposed

**Dropping `raw` retrospectively.** It is already sampled at 30s going forward
(the live recorder keeps it once per market per 30s rather than five times a
second), which took the row from 2,576 bytes to ~700. Rewriting history to
strip it from older rows would mean an `UPDATE` over the whole table — the same
vacuum problem as `DELETE`, for a one-off gain the partitioning plan gets for
free as those partitions age out.

**A time-based rule stated in days when the requirement is in games.** Seven
days is a proxy. The honest rule is "the last N completed games", and if the
schedule thins out late in the season the window should be measured in games,
not days. Partition boundaries have to be time, but the *downsampling* job
should take a game count and derive the cutoff.

## Before any of this runs

The gates need ~10 games at full resolution and currently have **6 games total
in the database, most of them at the old 30s cadence**. Do not prune until the
microstructure experiments have actually run against a full-resolution sample —
pruning first would destroy the only data they have been waiting for.
