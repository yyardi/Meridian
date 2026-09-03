# Kalshi poll load — the college Saturdays breach the bucket

**Measured 2026-09-03 against the venue's own open events and their
`occurrence_datetime` stamps.** Written before the first big Saturday so
the ceiling is known rather than discovered as a shortfall.

## The arithmetic

A game is pollable while `now` is inside its window, and each pollable
game costs **3 requests per cycle** (one per series). With the default
60s cycle, requests/second = `concurrent_games * 3 / 60`.

College windows are `pregame_window + 3h` wide, because the venue
publishes no tip time for leagues we do not quote and the only clock it
gives — `occurrence_datetime` — sits at **kickoff + 3h**
(docs: `venue_occurrence_time`, migration `b7e2f91a4c33`).

## Peak concurrency, measured per date

| date | games | pre=6h (win 9h) | pre=4h | pre=3h | pre=2h |
|---|---|---|---|---|---|
| Sat 2026-09-05 | 103 | **92 games, 4.60 req/s** | 75, 3.75 | 69, 3.45 | 66, 3.30 |
| Sat 2026-09-12 | 113 | **106 games, 5.30 req/s** | 87, 4.35 | 82, 4.10 | 79, 3.95 |

The bucket is **5 req/s** (`KALSHI_RPS`, burst 5). So:

* **2026-09-12 BREACHES at default settings** (5.30 > 5.00).
* 2026-09-05 runs at 92% of the bucket, and a serialized cycle takes
  ~55s inside a 60s interval — no headroom for retries or a fourth
  league.
* Thursday 2026-09-03, for scale: 14 games, 0.7 req/s. Tonight bounds
  nothing.

## What to change, and why this order

**Lengthen the interval; do not shrink the window.** At a 120s cycle
every column above halves — 2026-09-12 lands at **2.65 req/s** with the
full 6h pregame window intact:

| date | pre=6h @120s | pre=3h @120s |
|---|---|---|
| 2026-09-05 | 2.30 req/s | 1.73 |
| 2026-09-12 | 2.65 req/s | 2.05 |

The trade is not symmetric. Shrinking the pregame window discards tape
that **cannot be recovered afterwards**; lengthening the interval only
lowers sampling resolution on tape we still get. Prefer
`KALSHI_INTERVAL=120` on college Saturdays, and treat window reduction
as the second lever.

## The loop drifts; it does not stack or skip

Read `run_forever` before reasoning about occupancy: the interval is a
**sleep taken after the cycle**, not a period. So

    effective sampling period = cycle_duration + interval

Nothing stacks (the loop is sequential) and nothing is silently dropped —
but the real cadence stretches as the slate grows, and until now nothing
reported that. A recorder sampling every 3 minutes looked exactly like one
sampling every 2.

This also corrects the "92% occupancy / 55s cycle inside a 60s interval"
framing: there is no overrun cliff, because the client's own 5/s limiter
simply makes the cycle longer, which makes the period longer. The failure
is not a breach — it is **silent cadence degradation**, which is worse in
the way rule 22 cares about: the tape thins while every log line stays
green. At 106 games the cycle alone costs ~64s of rate-limited fetching,
so a 60s interval was never buying 60s sampling.

The recorder now prints `cycle_seconds` and `effective_period_seconds`
every cycle and counts `kalshi_cycle_overran_interval` when the cycle
alone outruns its interval.

## Follow-up: tiered cadence (the structurally right fix)

A flat interval spends the same attention on a game six hours out as on
one twenty minutes from kickoff, and it is the far games that push the
near ones toward the limit. The Polymarket live recorder already samples
near-money rungs faster than the rest; the same tiering applied here
scales past 113 games without spending resolution where it matters.
Deliberately NOT done under tonight's deadline — 120s is the right call
with hours to spare, tiering is a build with a week.

## Why this is a rule-22 item

A throttled cycle does not announce itself. It returns fewer contracts,
which reads exactly like a quiet venue. That is why the recorder now
logs `events_requested` beside `events_returned` and `markets_returned`
every cycle: a shortfall must be visible **as a shortfall**. Watch those
two numbers diverge before trusting any Saturday volume figure.
