# First-score fade — does the opening basket move the price too much?

**Status: NO DATA.** 18 filled trades across **3 games**, against a
pre-registered minimum of 30 across 10. The strategy is built, tested and
accruing.

Module: [`core/pulse/first_score.py`](../../core/pulse/first_score.py) ·
Strategy #1 for **PULSE** · Hypothesis #2 in
[pulse-hypotheses.md](../pulse-hypotheses.md)

## Why this one first

The overreaction family has four members (#1 runs, #2 first score, #3 lead cut,
#4 late runs) and they are one mechanism asked four ways. #2 is the cleanest
form of the question, for a reason that is already measured rather than
assumed:

> Q1 combined total correlates **+0.55** with the final total (n=787), and each
> extra Q1 point is worth **1.32** on the final, not 4.0. Hot starts regress
> about 3×. Residual sd after conditioning on Q1 is ~16 points.

So one opening basket is worth roughly **1.3 points** of final total against a
16-point residual. That is as close to zero information as a scoring event in
this sport gets. Any price move on it is almost entirely noise, and noise is
what reverts. If the market does not overshoot *here*, it is unlikely to
overshoot on events that actually carry information — which makes a null result
here close to fatal for the whole family, and a pass the strongest version of
the signal.

It is also a different question from
[run-overreaction.md](run-overreaction.md), not a re-test of it. That module
triggers on 8-point runs and carries its own gate.

## The pre-registered gate

Fixed 2026-08-02, before any number was computed.

| | |
|---|---|
| **PASS** | mean net P&L per filled trade > 0 at **+5 min**, **and** its 95% CI (clustered by game) lies entirely above 0, **and** n ≥ 30 filled trades, **and** ≥ 10 games |
| **FAIL** | sample size met, but the mean or the interval fails |
| **NO DATA** | sample size not met |

**Why the bar is zero here and 6¢ in [run-overreaction.md](run-overreaction.md).**
That module measures raw mid reversion, so the round trip has to be subtracted
afterwards and the bar is the cost. This one measures **P&L**: entry is a maker
fill at the touch, which *earns* the half-spread, and the exit mark *pays* one.
Both costs are already inside the number. Same bar, accounted for in a different
place — and the exit charge uses the spread observed **at exit**, not a
favourable average, so a blow-out costs what it costs.

+2 and +10 min are reported as secondaries and carry **no gate**. Nominating the
best of three after the fact turns a 5% test into a 14% one.

## The trade

1. Observe the market quoting while the score is still **0-0**. That last
   quotable mid is the baseline.
2. The score goes non-zero. Wait 30s for the lurch to land.
3. `lurch = mid(t_score + 30s) − baseline`. Fade it — sell into an up-lurch,
   buy into a down-lurch, resting **at the touch**.
4. [`replay.py`](../../core/pulse/replay.py) fills it only when the book later
   trades through it, never on the tick that placed it. Unfilled after 2
   minutes it is cancelled, and an order that never filled is not a trade.
5. Mark at the horizon: `pnl = ±(mid_H − fill) − spread_H / 2`.

Maker-only by construction. There is no code path here that crosses a spread.

**No parameter was fitted.** Three free parameters against a 10-game minimum,
each inherited from a constant pre-registered elsewhere for a different study:
the 30s reaction window is `adverse_selection.DEFAULT_HORIZON_SECONDS`, the
2-minute entry patience is `overreaction.RUN_MINUTES`, the 5-minute primary
horizon is `overreaction.PRIMARY_HORIZON_MINUTES`. The quotable band
(mid ∈ [0.20, 0.80], spread ≤ 15¢) is imported outright rather than restated.

## What happened

9 games replayed, 830,554 ticks, cadence median **0.20s** (p90 0.26s).

**The 0-0 → first-score transition was observed in all 9 games.** That was the
open risk — the live recorder starts when the board flags a game live, which is
after tip-off — and it turns out not to bite, because the board carries
`event_score` on pregame rows too. Loading only `is_live` rows would have
discarded every baseline; the study loads both.

### But only 3 games can carry it

| game | ticks | median gap | signals | fills |
|---|---:|---:|---:|---:|
| wnba-conn-dal-2026-08-02 | 329,168 | 0.20s | 13 | 11 |
| wnba-tor-gsv-2026-08-02 | 276,219 | 0.20s | 5 | 2 |
| wnba-la-por-2026-08-02 | 218,851 | 0.20s | 15 | 5 |
| wnba-ind-min-2026-08-02 | 2,248 | 921.93s | 0 | 0 |
| wnba-ny-phx-2026-08-01 | 1,422 | 919.65s | 0 | 0 |
| wnba-lv-chi-2026-08-01 | 1,296 | 920.69s | 0 | 0 |
| wnba-ind-por-2026-07-31 | 594 | 909.83s | 0 | 0 |
| wnba-sea-atl-2026-07-31 | 378 | 909.78s | 0 | 0 |
| wnba-dal-wsh-2026-07-31 | 378 | 909.78s | 0 | 0 |

**This is the real content of the run.** Six of nine games were sampled every
~15 minutes, and a 15-minute gap cannot resolve a 30-second reaction window.
They contribute coverage and no signal. Three orders of magnitude separate the
two regimes in row count and **zero games** separate them in sample size —
which is the whole reason this project counts games.

### The lurch itself

| | |
|---|---|
| mean \|lurch\| on the first score | **3.44¢** |
| direction | 25 up, 8 down |
| by market type | total 18, spread 14, winner 1 |
| age of the 0-0 baseline | median 4.0 min, p90 7.8 min |

The 25:8 up/down split is the most interesting descriptive number here and it
is **not** evidence of anything yet at n=33 across 3 games. Worth a look once
the sample exists.

Baseline age is reported, not filtered on. A stale 0-0 quote folds pregame
drift into the "lurch"; pregame travel is a measured 8.5¢ across the *entire*
pregame window, so at a 4-minute median this is second-order against a 3.44¢
lurch — but it is a real contaminant and the gate does not correct for it.

### The numbers, all under-powered

Net P&L per filled trade, clustered by game (G=3, so df=2 and t≈4.3):

| horizon | n | mean | 95% CI (clustered) |
|---|---:|---:|---|
| +2 min | 18 | −0.0872 | [−0.1597, −0.0147] |
| **+5 min** | 18 | **−0.0561** | **[−0.2161, +0.1039]** ← gate |
| +10 min | 18 | −0.0006 | [−0.0567, +0.0556] |

Signal-only reversion — every detected lurch, filled or not. **Ungated**, and
present so that a future FAIL can be told apart from the fill proxy discarding
the easy trades:

| horizon | n | mean | 95% CI (clustered) |
|---|---:|---:|---|
| +2 min | 33 | −0.0274 | [−0.1150, +0.0601] |
| +5 min | 33 | +0.0089 | [−0.1588, +0.1767] |
| +10 min | 33 | +0.0459 | [−0.1209, +0.2128] |

Every interval spans zero. **Nothing here is a finding**, including the −0.0872
at +2 min whose interval excludes zero: it is a secondary with no gate, at
three clusters, and reporting it as a result would be exactly the
best-of-three error the pre-registration exists to prevent.

The clustering is doing visible work. At +5 min the row-level interval would
have been [−0.0963, −0.0159] — excluding zero, and **wrong**. Clustering widens
the standard error 2.0×, and that is with only three clusters; the row-level
version would have manufactured a significant loss out of 18 correlated
observations of three games.

## `PULSE_MARKETS` is still undecided, correctly

[`core/executor.py`](../../core/executor.py) leaves `PULSE_MARKETS` empty. The
report prints the table it should eventually be set from, marked ungated:

| type | signals | filled | games | mean P&L | 95% CI |
|---|---:|---:|---:|---:|---|
| spread | 14 | 3 | 2 | +0.0100 | [−0.4982, +0.5182] |
| total | 18 | 14 | 3 | −0.0857 | [−0.2064, +0.0350] |
| winner | 1 | 1 | 1 | +0.1600 | n/a (<2 games) |

Do not read this table yet. Splitting an under-powered sample three ways and
adopting the best arm is how three tests become one finding. ANCHOR's moneyline
exclusion is a *pregame forecasting* result and still must not be inherited
here — but one filled trade is not the measurement that replaces it.

## The caveat that decides how to read a future result

The replay engine fills a resting sell only when the best **bid** rises to it —
the whole book has to come up to you. In reality a taker crosses the spread and
lifts your offer without the bid moving, but top-of-book snapshots cannot see a
trade, so the engine uses the conservative proxy. The consequence is specific
and directional:

> Recorded fills are biased toward the lurch **continuing**, which is the worst
> case for a fade. A **PASS** is therefore a lower bound and trustworthy. A
> **FAIL** is confounded with the proxy and must not be read as "the phenomenon
> is absent".

This is the mirror image of [adverse-selection.md](adverse-selection.md), whose
fill rule biases the other way. The signal-only column above exists precisely so
the two can be told apart when the sample arrives.

## What it needs

**7 more games at 200ms cadence.** Not more rows — the three usable games
already carry 824,238 of the 830,554 replayed, or **99%**. At ~4 games a slate
that is about two more nights,
assuming the live recorder stays up.

Nothing in this module needs changing when that happens. Re-run it:

```bash
python -m core.pulse.first_score
```

**Do not re-tune the gate after seeing a number.** It is pinned in the module
docstring with the date it was fixed.
