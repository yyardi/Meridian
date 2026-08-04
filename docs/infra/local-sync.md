# The local sync could not finish, and now it can

**Measured 2026-08-02.** `python -m core.storage.sync_local --stream` went from
**unable to complete** to **837,220 rows in ~15 minutes.**

Module: [`core/storage/sync_local.py`](../../core/storage/sync_local.py)

This matters more than a speed note. The module exists because "an experiment
that costs 11 minutes gets run once and its result stands unchallenged, while
one that costs seconds gets re-run under different settings." A sync that
cannot finish makes every PULSE and QUOTE gate unrunnable.

## It was not slow, it was broken

The copy paginated with `OFFSET`:

```sql
SELECT ... FROM market_snapshots ORDER BY id LIMIT 2857 OFFSET n
```

`OFFSET n` makes Postgres walk and discard the first *n* rows on **every** page,
so a full copy is quadratic in table length. That was survivable when the
recorder wrote every 30s. At 200ms the table reached 837,220 rows and the page
query itself grew past Supabase's statement timeout:

```
canceling statement due to statement timeout
[parameters: {'param_1': 2857, 'param_2': 31427}]
```

It died at row 31,427 of 837,220 — **3.8% in** — and no amount of waiting would
have helped, because the failure is per-page, not cumulative.

`WHERE id > last_id ORDER BY id LIMIT n` rides the primary key. Every page costs
the same as the first.

## The `raw` column was 24× the transfer cost

With keyset paging the copy completed, at ~2,857 rows/minute — **4.7 hours**.
Timing one page both ways found the whole cost in one column:

| page of 2,857 rows | time |
|---|---|
| all 21 columns | **35.7s** |
| without `raw` | **1.5s** |

[live-cadence.md](live-cadence.md) already recorded that `raw` is 62% of the
table's *bytes*. It is 96% of its *transfer time*.

`raw` is a schema-drift archive — kept so a parsing bug can be fixed
retroactively — and **nothing reads it**. No backtest, no microstructure
experiment. So the local copy now omits it by default. `--with-raw` restores it.
The primary keeps it, always; that is where the record lives.

### The omitted value is not NULL

This is the part worth copying elsewhere. `raw IS NULL` already means "the
recorder captured no payload". Reusing it for "the sync did not fetch this"
would make a local query say the recorder was broken.

So omitted columns hold a sentinel instead:

```json
{"_omitted_by": "sync_local", "_see": "primary has the payload"}
```

An absence has to name its own cause. Same reasoning as `book_tier` being
nullable so that "we did not look" is distinguishable from "there was no size".

## Two smaller fixes that were real bugs

**Resume, and only where it is sound.** `market_snapshots` and `book_levels`
are appended by the recorders and never rewritten, so a re-sync can start after
the newest local id. Every other table is upserted in place, and resuming one of
those would keep a stale local row forever. Resume is therefore per-table and
off by default — the failure mode of a wrong resume is silent staleness, which
is the kind this project keeps getting caught by.

**`setval` per chunk, not once at the end.** The id sequence was advanced only
after a whole table finished. A copy that takes minutes gets interrupted, and
every interruption left the sequence behind the ids already committed. The next
local `INSERT` then failed with a duplicate-key violation on a table that looked
fine:

```
duplicate key value violates unique constraint "market_snapshots_pkey"
DETAIL:  Key (id)=(24135) already exists.
```

That is what a half-synced database does to the test suite. One extra statement
per 2,857 rows is not a measurable cost.

## Known, not fixed: the suite shares this database

`tests/conftest.py` pins the suite to the same local Postgres the warm standby
lives in, and says so — the isolation is "a property of the fixtures, not a
guarantee of the setup."

`/api/status` computes freshness as a **global** max over `market_snapshots`, so
`tests/test_api_status.py::test_a_dead_pregame_recorder_is_unhealthy` passes or
fails depending on how recently someone ran a sync. With a fresh copy the newest
real pregame row is ~30 minutes old, which is younger than the 3-hour-old row
the test inserts, so the endpoint reports 1,945s against a 5,400s threshold and
the test fails.

The test is right and the setup is wrong: a suite that writes and reads
aggregates should not share a database with hundreds of thousands of real rows.
The fix is a dedicated test database, which is a separate piece of work.
