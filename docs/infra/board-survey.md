# Board survey — the October NBA decision, tooled in August

```bash
python -m core.survey --league nba              # the October run
python -m core.survey --league mlb              # reproduces V7
python -m core.survey --league wnba --source recorded
```

Module: [`core/survey.py`](../../core/survey.py) · generalises finding
[V7](../findings.md)

## Why it exists

MLB was killed in an afternoon by five numbers — spread width, tick size,
depth at the touch, fee coefficient, rungs per game (**V7**: *"1¢ wide with
half-cent ticks, 30 events, 405 markets. No venue gap. Decided we stay
WNBA."*). It was done by hand and **the numbers were never persisted**.

When Polymarket US lists NBA preseason boards in October the same question
arrives with real money behind it. Re-deriving the method under time pressure
is how a decision gets made on whichever statistic is easiest to compute that
day. So the method is a module now, built while nothing is at stake.

## It reaches no conclusion, on purpose

There is **no gate, no threshold, no PASS/FAIL** anywhere in the module, and
`tests/test_survey.py` asserts their absence against the parsed AST (docstrings
stripped, so the module's own disclaimer cannot satisfy the test).

Every other measurement in this project carries a pre-registered gate because
it tests a stated hypothesis. This one describes a board nobody has seen. A
threshold written in August would be a guess about October dressed as a
criterion — and once it existed, the decision would belong to whoever picked
the number rather than to someone looking at the board.

**The verdict is the October run plus a findings entry, written by a human.**

## The direction that matters

Worth stating because it inverts the usual instinct: the venue gap this project
trades exists because WNBA is a **thin** corner of the venue. Thinness is the
product. A board that is *tighter, deeper and better quoted* than the baseline
has **less** to trade, not more. That is why MLB's 1¢ spread was a rejection.

## The control that makes it honest

**Spread swings 12× with time to tip-off on the same board.** Measured on the
recorded WNBA board, near-money markets:

| hours to tip-off | median spread | n |
|---|---:|---:|
| inside 3h | **1.00¢** | 103 |
| 12–24h | **12.00¢** | 46 |

An October NBA preseason board will be days out. The recorded WNBA baseline is
dominated by snapshots near tip-off. Compared headline-to-headline, NBA would
look ~12× wider than it is — and *wider* reads as *thinner*, which reads as
*tradable*. **An unmatched comparison argues for entering a market on a clock
artifact.**

So every spread is also reported per horizon bucket, and the report:

- flags when the two columns' median horizons differ by ≥6h;
- names which buckets have data on **both** sides — the only like-for-like rows;
- says explicitly when **no** bucket overlaps, so adjacent rows are not read as
  a comparison.

That last case is live right now — see below.

## Validation: it reproduces V7

Run 2026-08-07 against the live MLB board (V7's numbers were never persisted,
so the validation re-measures the board exactly as V7 did):

| | MLB (live) | WNBA (recorded) |
|---|---|---|
| events / markets | 50 / 505 | 20 / 360 |
| median markets per event | 12.0 | 18.0 |
| tick sizes | **0.005 (58%)**, 0.01 (42%) | 0.01 (100%) |
| fee coefficients | 0.06 (100%) | 0.06 (100%) |
| near-money median spread | **1.00¢** | 2.00¢ |
| near-money p10 spread | 0.50¢ | 1.00¢ |
| median tick / mid | 1.46% | 2.15% |
| top-of-book notional, median | $79 | $253 |

**V7 reproduced**: half-cent ticks and a ~1¢ near-money spread, on a board of
similar scale (50 events / 505 markets against V7's 30 / 405 — a different
day). Fee coefficient 0.06 across the board also reproduces **V9**, and the
WNBA column reproduces **V2** (1¢ tick, 100%).

**And the control immediately earned its place.** The two columns sit **27.7h
apart** in median time to tip-off, and **no horizon bucket has data on both
sides**:

| bucket | MLB | WNBA |
|---|---|---|
| live/past | — | 2.00¢ (n=60) |
| 0–3h | — | 1.00¢ (n=48) |
| 6–12h | 1.00¢ (n=213) | — |
| 12–24h | — | 12.00¢ (n=37) |
| 24–72h | 20.00¢ (n=238) | — |
| >72h | 38.50¢ (n=24) | — |

So the headline "MLB 1.00¢ vs WNBA 2.00¢" is **not a valid comparison** — it
compares a 6–12h MLB board against a near-tip-off WNBA one. The report says so
rather than letting the numbers sit next to each other looking comparable.

Note this does not overturn V7. MLB at 6–12h is 1.00¢ where WNBA at 12–24h is
12.00¢; MLB is tighter even allowing for horizon, and it carries half-cent
ticks WNBA does not. The point is that the *report* now refuses to assert that
from mismatched rows, and would refuse just as firmly in October.

## What to do in October

1. Run `python -m core.survey --league nba` as soon as boards appear. It is
   read-only and costs one board request plus `--depth-sample` book calls.
2. If the horizons do not overlap the WNBA baseline, **record the NBA board
   through a full pregame cycle first** and re-run with `--source recorded`.
   One afternoon's snapshot of a far-dated board is not a survey.
3. Read the bucket rows, not the headlines.
4. Write the finding into [findings.md](../findings.md) with a date — the way
   V7 was written, but this time with the numbers attached.

## Known limits

- **Depth is sampled**, not exhaustive: one book call per market, so
  `--depth-sample` markets are drawn (near-money preferred, fixed seed so two
  runs diff cleanly). The count sampled is always printed.
- **Only WNBA is recorded.** `--source recorded` works for nothing else until
  a recorder runs against another league.
- **One snapshot per market** on the recorded path — the most recent pregame
  row. That is a board survey, not a time series.
- **No conclusions.** By design. See above.
