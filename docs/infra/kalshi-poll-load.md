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

## What Saturday will actually sample at (measured model, not nominal)

Effective throughput measured on tonight's real cycles — **4.09 req/s**
(42 requests in 10.28s; the discovery cycle independently gives 4.19),
which is the limiter and per-request latency combined, not the nominal
5/s. At 3 requests per game per cycle:

| date | peak games | cycle | period @60s | period @120s |
|---|---|---|---|---|
| 2026-09-05 | 92 (18:30Z) | 68s | 128s (2.1 min) | **188s (3.1 min)** |
| 2026-09-12 | 106 (18:00Z) | 78s | 138s (2.3 min) | **198s (3.3 min)** |

Across 09-05 the period runs 2.0–3.1 min, exceeding 3 min only in the
17:30–18:30Z hour.

**Verdict for the pregame series: not materially harmed.** A 6h pregame
window at ~3 min sampling is ~116 samples per game, which is ample for
pregame price movement. What IS coarse at 3 min is the in-game portion —
and the window covers in-game only as a side effect of
`occurrence_datetime` being the sole clock the venue publishes, not as a
registered objective. If in-game college prices ever become the target,
the cadence must be revisited before the data is trusted.

**Assumption stated:** this holds only while ~4.09 req/s holds. Venue
latency under a full Saturday (everyone polling at once) would stretch
it, and the discovery cycle lands ~100+ extra requests when new games
appear. Watch `effective_period_seconds` rather than re-deriving it.

## The 120s is a stopgap, not a preference

Recorded so nobody later reads it as a considered steady state: 120s was
taken under a same-day deadline because predictability under load beat
resolution on pregame tape. Now that the drift semantics are understood,
120s is known to make an already-stretched period longer — it buys
headroom by spending exactly what it was meant to protect. **The next
move is tiering, not a third interval bump**, which would be treating the
symptom twice.

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
