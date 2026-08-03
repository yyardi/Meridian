# Getting the live recorder to 200 milliseconds

**27s → 1.003s → 202ms per cycle.** All measured live on 2026-08-02.
Module: [`core/live_recorder.py`](../../core/live_recorder.py)

Read in order: the first pass fixed the *shape* of the loop, the second fixed
the *rate*, and the second turned up two things that had nothing to do with the
venue — the database was the real bottleneck, and storage is now a problem.

## The problem

The live recorder reused `Recorder.run_once`, which re-polls the entire
131-market board and issues one order-book call per market. That is ~132
requests, took 26–34 seconds, and gave an effective cadence of ~35s.

No amount of tuning inside that shape reaches 1s. At the gateway's documented
20 req/s per-IP ceiling, **132 requests cannot fit in a second.** The loop was
not slow; it was the wrong shape.

## Step 1: is there a push feed? (No)

Checked before optimising anything, because a websocket would delete the
problem rather than shrink it.

| Probe | Result |
|---|---|
| WS upgrade to `/ws`, `/v1/ws`, `/v2/ws`, `/websocket`, `/stream`, `/` | **404** on every path |
| `Accept: text/event-stream` on every known endpoint | returns `application/json` — no SSE |
| `/socket.io/` | 301 to a 404 |

There is no push feed and no trades endpoint (`/trades`, `/activity` etc. all
404), so **order-book depth is the only market microstructure available** and
polling is the only way to get it. Worth re-checking occasionally: a feed
appearing would make most of this module obsolete, which would be good news.

## Step 2: the board call already carries top-of-book

This is the whole finding. Every market in
`/v2/leagues/{league}/events` embeds `bestBidQuote` and `bestAskQuote`.

> **Top-of-book for all 131 markets costs one request, not 131.**

The 131 book calls were only ever buying *depth*. Price and depth had been
fused together for no reason other than that `run_once` did them in the same
loop.

## Step 3: does the board actually move at 1s?

A faster poll is worthless if the payload is cached. Polling once a second for
45s during a live game:

| | |
|---|---|
| Consecutive frame-pairs that differed | **43 / 44** |
| Distinct states of the live board in 45s | **44** |
| Board latency | median 194ms, p90 333ms |
| Book-call latency | median **21ms** |

The data is not cached upstream (`cf-cache-status: DYNAMIC`), so a 1s poll
resolves real changes. Note the book call is ~9× *faster* than the board call —
the board is the big gzipped payload. The cost of the old design was never
latency, it was spending 131 requests on depth nobody needed.

## The design

| Loop | Cadence | Requests | What |
|---|---|---|---|
| **Price** | 200ms | **1** | one board call → top-of-book for every live market |
| **Depth, near** | 10s | ~9/game | the 4 rungs nearest the money, per market type, concurrent |
| **Depth, deep** | 120s | rest | a slow sweep so the deep book is still audited |

Depth runs on a **background thread**, sharing the client's token bucket. That
is not decoration: 36 book calls at 11 req/s is ~3.3s, which would blow a 1s
budget if it ran inline. The bucket is thread-safe, so concurrency raises
utilisation without raising the rate.

"Nearest the money" is $|{\text{mid}} - 0.5|$, ranked **independently within
each market type** so a tight spread ladder cannot crowd out every totals rung.
Moneyline is a single market and always included — it was also the most active
thing on the board (29 changes in 45s, more than any ladder rung).

Deep rungs still get a *price* snapshot every 30s — the cadence this recorder
had before. They are the 0.95/0.05 rungs carrying measured 22–26¢ spreads that
do not trade; a row a second there is a storage bill, not a dataset.

## Request budget

The gateway allows 20 req/s per IP and the pregame recorder holds 5, so the
live recorder's budget is 12 (`MERIDIAN_RPS` in `docker-compose.yml`). With a
full four-game slate:

```
price   1 board call / 200ms             =  5.0 req/s
near    4 games x 9 rungs / 10s          =  3.6 req/s
deep    4 games x 9 rungs / 120s         =  0.3 req/s
                                      total ~8.9 req/s
```

Near-depth widened from 5s to 10s to pay for the faster price loop; at the old
5s the total would have been 12.5 req/s, over the allowance. Depth yields
because its own horizons are 30s and 60s, so 10s sampling costs it nothing
measurable, whereas price resolution was *measured* to matter at 200ms. Yielding
the measured requirement to protect the unmeasured one would have been the wrong
way round.

`tests/test_live_recorder.py::test_steady_state_request_rate_fits_the_budget`
asserts this arithmetic, so widening the near-money set or tightening a cadence
past the budget fails a test rather than quietly crowding the ceiling.
**`MERIDIAN_RPS` was not raised.**

## Measured result

60 cycles against the live gateway during a game:

| | |
|---|---|
| Achieved cadence (start-to-start) | **median 1.003s**, p90 1.005s, max 1.005s |
| Work per cycle (board call + write) | median 179ms, max 341ms |
| Snapshots written | 558 in 60s |
| Depth levels written | 1,799, **0 book errors** |

## Sparsity is recorded, not implied

Two columns added (migration `7c1a9f4b2e10`):

- **`market_snapshots.book_tier`** — `'near'` | `'deep'` | `NULL`. Lets a later
  analysis distinguish *no resting size* from *we did not look*. Without it, an
  unsampled market reads as an empty book and every deep rung silently counts
  as whale-free. [depth-signal.md](../math/depth-signal.md) depends on this.
- **`book_levels.captured_at`** — when the book call returned. Now that depth
  runs on a slower loop than price, the parent snapshot's timestamp would
  backdate it by seconds, and the depth-signal question is precisely a question
  about ordering.

Both nullable, so existing rows stay honest: `NULL` means "written before the
tiered sampler existed", not "not sampled".

---

# Second pass: 1s → 200ms

## Finding the true resolution

The obvious statistic is a trap. "Fraction of consecutive frames that differ"
**rises monotonically with the interval**, because a longer gap has more chances
to contain a change:

| interval | frames differ |
|---|---|
| 200ms | 57% |
| 1s | 91% |
| 5s | 100% |

That measures the sampling interval, not the market. It also swings hard with
game state — two windows on the *same game* gave 31% and 57% at the same 200ms.
It cannot be used to choose a poll rate.

The scale-free version is **how many changes you detect per second**. Capture at
200ms for three minutes, then subsample that one capture to each candidate
interval:

| interval | changes/sec | vs peak |
|---|---|---|
| 200ms | 5.22 | 90% |
| **300ms** | **5.80** | **100%** |
| 500ms | 4.79 | 83% |
| 1s | 3.47 | 60% |
| 2s | 2.65 | 46% |
| 5s | 1.80 | 31% |

It saturates at 200–300ms and falls away above. **The 1s loop was seeing about
60% of the changes it could** — the rest superposed or reversed inside a frame
and were lost. Below 200ms nothing more is detected.

## You cannot poll faster than replies return — structurally

Asked for 100ms, the loop achieved 175ms, because the round trip is ~171ms. It
self-paces: `_sleep_remaining` sleeps until `started + interval` and returns
immediately if that has already passed, so the next board call is only issued
after the previous one has returned and been handed off. The practical floor is
`max(interval, round-trip)` and overlapping requests are unrepresentable rather
than merely avoided.

## The database was the bottleneck, not the venue

First deploy at a 200ms target achieved **497ms**, with `work_ms_p50` at 492ms
against a 158ms board call. The container writes to Supabase and a single remote
INSERT round trip is ~330ms. The venue was never the limit.

Polling and persisting are now different threads. `SnapshotWriter` takes rows
off the loop and writes whatever has accumulated in one statement, so DB latency
changes the **batch size** rather than the sampling rate.

| | before | after |
|---|---|---|
| achieved cadence | 497ms | **202ms** (p90 252ms) |
| work per cycle | 492ms | 168ms |
| cycles/minute | 121 | **281** |
| db write | — | 303ms p50 (off the loop) |
| dropped rows | — | 0 |

**The cost, stated plainly:** buffering means a hard kill (SIGKILL, power loss)
drops what has not been written, typically well under a second. That is a real
charge against this project's first rule — snapshots cannot be backfilled — and
it is accepted only because writing inline discarded ~40% of observable changes
*continuously*. `stop()` drains the queue, so an ordinary shutdown or redeploy
loses nothing.

## Storage: yes, retention is now needed

Measured per-row cost, and where it goes:

| table | bytes/row | note |
|---|---|---|
| `market_snapshots` | 2,576 | **1,599 of it (62%) is the `raw` JSONB** |
| `book_levels` | 161 | |

At 200ms with one live game that was **~0.5 GB per game**. A full slate is ~4
games; a remaining WNBA season is ~80–100 games. That is 40–50 GB against a
Supabase Pro disk, and it would have arrived as a surprise.

**Fixed the cheap 62% first.** The `raw` payload is now retained once per market
per 30s instead of five times a second. The standing rule — "keep the raw
payload, parsing can be fixed later" — is about *schema drift*, and a 30s sample
serves that completely. It was never a claim that the same blob is worth storing
300 times a minute. Prices are untouched: they live in typed, indexed columns at
full 200ms resolution. Row cost drops 2,576 → ~977 bytes.

**Still needed, and not done here:**

1. **Retention.** Full-resolution live data is only interesting while the
   microstructure experiments are open. Keep ~30 days at full rate, then
   downsample to 1s or 5s.
2. **Partitioning** `market_snapshots` and `book_levels` by month on
   `captured_at`, so ageing data is a `DROP PARTITION` rather than a `DELETE`
   that has to be vacuumed.

Neither is urgent this week; both are urgent before the season ends.

## The connection ceiling

Supabase's **session-mode** pooler (port 5432) allows **15 clients across the
entire project**, and it is saturated. The scheduler has logged
`EMAXCONNSESSION`, ad-hoc queries are refused, and
[`live-odds.md`](live-odds.md)'s container could not write at all and is
currently stopped.

`get_engine` already caps each process at `pool_size=2, max_overflow=1`, so the
containers are not individually greedy — there are simply too many clients for a
15-connection ceiling.

**The fix is the transaction-mode pooler (port 6543)**, which is built for many
short-lived connections. It is not a drop-in, which is why it has not been done
here without a decision:

- Alembic's advisory locks do **not** work in transaction mode, and all
  containers run `alembic upgrade head` on start. Migrations would need to keep
  using port 5432, or run separately.
- psycopg3 uses prepared statements by default; transaction mode needs
  `prepare_threshold=None`.

This is a change to production connection strings and needs the owner's call.

## The query shape that broke when cadences diverged

This one is worth reading even if you never touch the recorder, because it cost
two and a half hours of the ANCHOR pipeline and it failed *silently*.

The canonical query now lives in one place,
[`core/board.py`](../../core/board.py), so the next consumer inherits the fix
rather than the bug.

### Where it bit

| Caller | Symptom |
|---|---|
| `/api/board`, `/api/events` | 12-game board rendered as one game, 9 markets |
| **`core/predictions.py`** | **zero predictions for the entire duration of every game**, while reporting success |

The prediction case is the serious one. `PredictionLogger.run()` took
`max(captured_at)` and then filtered out live markets as unpriceable. During a
game the newest snapshot is the 200ms live recorder's and contains *only* live
markets — so the filter emptied the list, the job logged `no_pregame_markets`,
wrote nothing, and returned normally.

Measured: **zero predictions between 19:30 and 21:56**, the whole duration of
one game, with the scheduler logging `job_ok` on every 20-minute cycle. No
predictions means no shadow orders, so nothing accrued toward v4's
50-resolved-bet gate — and it would have recurred at every tip-off.

### The original shape

`/api/board` and `/api/events` selected:

```sql
WHERE captured_at = (SELECT max(captured_at) FROM market_snapshots)
```

That was correct while one recorder wrote the whole board every cycle — the
newest instant *was* a complete picture. Once two writers existed on different
cadences it became wrong, and silently: the global maximum belongs to whichever
live game wrote 200ms ago and contains **only that game**, so every pregame
market is filtered out by an innocuous-looking equality test. A 12-game board
rendered as one game with 9 markets. Nothing errored and nothing logged.

The fix is per-market, not per-cycle:

```sql
SELECT DISTINCT ON (market_slug) *
FROM market_snapshots
WHERE game_start_time >= now() - interval '6 hours'
ORDER BY market_slug, captured_at DESC
```

which rides `ix_market_snapshots_slug_time`.

Note the bound is on **`game_start_time`, not `captured_at`**. Bounding on when
a row was last *written* would reintroduce the same bug at a different scale — a
market would disappear because its writer is slow rather than because its game
is over. Bounding on when the game *starts* is a fact about the world and is
immune to recorder cadence.

Rows now carry `age_seconds` and the UI shows it per row, because a 15-minute-old
pregame quote sitting next to a 200ms-fresh live one must look like what it is.

### Three consequences in the prediction path

1. **`predicted_at` stays uniform per run.** It is the run's own wall-clock
   instant, never a market's `captured_at`. The prediction log's unique
   constraint is `(market_slug, predicted_at, model_version, config_hash)`, and
   `core/shadow_run.py` and `/api/picks` both select `max(predicted_at)`
   expecting it to name one *complete* run. Stamping each row with its own
   snapshot's time would shatter one run into thousands.
2. **Staleness is recorded, not assumed away.** Each row carries
   `features.snapshot_age_seconds` and `features.snapshot_captured_at`.
3. **A stale quote is not priced as current.** Beyond
   `MAX_ACTIONABLE_SNAPSHOT_AGE_SECONDS` (90 min) the row is written as
   `reduced_confidence` and never actionable. The bound is tied to the pregame
   recorder's own idle cadence (60 min) with margin — up to an hour old is
   normal operation for a far-dated market, so flagging that would be noise.

### Silent success was the more dangerous half

The query bug lost data. What let it run undetected for hours was
`_safe()` in the scheduler logging `job_ok` for anything that did not raise.

Jobs may now return a result exposing `ok`, and the scheduler logs
`job_degraded` at WARNING when a job completes without error but did no work.
`PredictionStats.ok` is false precisely when quotable pregame markets existed
and nothing was written — while a board of only live games stays healthy,
because during a full slate there is genuinely nothing to price.

> A job that does nothing and reports success is worse than one that crashes.
> The crash gets noticed.

### Audit: everywhere else this shape appears

`grep -rn "max(.*captured_at\|max(.*predicted_at" core/`

| Site | Verdict |
|---|---|
| `core/predictions.py` | **was the bug** — fixed |
| `core/api.py` board/events | **was the bug** — fixed |
| `core/api.py` status, `core/__main__.py` status | freshness reporting. `max(captured_at)` is always ~0 with a 200ms writer, so it hid a dead pregame recorder. `/api/status` now also reports `stalest_market_minutes`, which is the number that actually detects a stopped writer |
| `core/api.py` picks, `core/shadow_run.py` | `max(predicted_at)` — **correct**, and only because `predicted_at` is uniform per run. That invariant is now load-bearing in three places; do not break it |

## The things that must not regress

- `test_price_cycle_costs_one_request` — if the price loop ever goes back to
  per-market book calls, 200ms becomes arithmetically impossible.
- `test_steady_state_request_rate_fits_the_budget` — fails if someone tightens
  the loop, widens the near-money set, or speeds up depth past 12 req/s.
- `test_writer_drains_everything_on_stop` — the buffer is only acceptable
  because a clean exit flushes it.
- `test_board_returns_markets_written_at_different_times` — pins the
  query-shape bug above, which failed silently rather than loudly.
- `test_pregame_market_survives_a_live_game` — pins the same bug in the
  prediction path, the one that stopped ANCHOR.
- `test_run_that_had_work_and_wrote_nothing_is_not_ok` — pins the silent
  success that let it go unnoticed.
