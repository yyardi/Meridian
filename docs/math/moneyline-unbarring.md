# Re-scoring the moneyline exclusion

`ANCHOR_MARKETS` excluded the moneyline pregame. This re-scores the evidence
that exclusion cited, in the money frame, and pre-registers what happens if the
bar is lifted.

**Headline: the stated reason for the bar is half wrong, and the moneyline is
still not profitable.** Those are both true, and the second one is why this
document is careful about what it claims.

## A defect in the measuring instrument, found first

Before any conclusion about the moneyline, the tool that produces these numbers
had a bug, and it flattered the moneyline specifically.

`core/backtest/moneyline.py` priced every entry at the book's **de-vigged**
probability. The de-vigged number is the book's *belief*; the raw number is its
*offer*. No one can transact at the belief. Charging it deletes the overround —
measured across 17,804 WNBA moneyline pairs, median **1.0427**, about 2.1
probability points on one side — which is larger than the entire edge being
reported.

    entries at the belief (old):  ROI +1.73%   entry cost 0.4047
    entries at the offer (now):   ROI −2.66%   entry cost 0.4229

A 4.4-point swing, and a sign change, from one substitution. **This invalidates
the `+0.85%` reported in [moneyline-spread-baseline.md](moneyline-spread-baseline.md)**;
that figure was measured the same optimistic way and should be read as −2 to
−3%. The correction is applied there.

`_maybe_bet` had always taken price and belief as separate arguments, so it was
never wrong — the *call site* passed the belief in as the price. A unit test of
`_maybe_bet` passes either way, which is why the defect survived. The guard now
lives at `run_backtest` (`test_run_backtest_charges_the_offer_end_to_end`) and
fails when the call site is reverted; the helper-level test alone does not.

## The two claims the exclusion rested on

**Claim 1 — the market forecasts margin better than we do (MAE 9.65 vs 10.19).**
Stands. Untouched by any of this, and it correctly predicts what the re-score
found: no edge on the moneyline.

**Claim 2 — "33.4% hit rate, entire 95% interval below the 0.524 breakeven."**
This is the C11 category error, and the number reproduces exactly:

| min_edge | n | hit rate | entry cost | ROI |
|---|---|---|---|---|
| 0.25 | 66 | **0.3333** | **0.3495** | −4.61% |

The 33.4% is real. The **0.524** is not its breakeven — that is the breakeven of
a −110 two-way market, and these entries cost 0.35. A 33.3% hit rate on 0.35
tickets is roughly breakeven. Benchmarking a hit rate against a price the
portfolio never paid is precisely what C11 names, and correcting it moves that
arm from "decisively dead" to "uninformative, n=66, CI [−35%, +27%]".

## What the money frame actually says

2024–2026, entries at the offer, game-clustered bootstrap CI (C4):

| min_edge | market | n | hit | entry | ROI | CI95 |
|---|---|---|---|---|---|---|
| 0.03 | moneyline | 668 | 0.412 | 0.4229 | **−2.66%** | [−10.84, +5.59] |
| 0.03 | spread | 682 | 0.502 | 0.5238 | **−4.27%** | [−11.26, +3.29] |
| 0.05 | moneyline | 589 | 0.402 | 0.4152 | −3.08% | [−11.92, +5.74] |
| 0.05 | spread | 602 | 0.495 | 0.5238 | −5.50% | [−13.11, +2.43] |
| 0.08 | moneyline | 446 | 0.392 | 0.4010 | −2.14% | [−12.44, +8.67] |
| 0.08 | spread | 475 | 0.497 | 0.5238 | −5.15% | [−13.59, +3.69] |
| 0.12 | moneyline | 308 | 0.390 | 0.3883 | +0.33% | [−13.10, +14.36] |
| 0.12 | spread | 347 | 0.504 | 0.5238 | −3.72% | [−13.62, +6.18] |
| 0.18 | moneyline | 167 | 0.359 | 0.3630 | −1.02% | [−20.55, +18.71] |
| 0.18 | spread | 198 | 0.475 | 0.5238 | −9.37% | [−22.87, +4.13] |
| 0.25 | moneyline | 66 | 0.333 | 0.3495 | −4.61% | [−35.27, +26.76] |
| 0.25 | spread | 75 | 0.573 | 0.5238 | +9.45% | [−10.91, +29.82] |

Three things, in order of importance:

1. **The moneyline is not profitable.** Every point estimate but one is
   negative, and every interval crosses zero. Nothing here is a reason to
   expect the moneyline to make money.
2. **Neither is the spread** — which is currently tradeable. At matched
   thresholds the spread is *worse*, at five of six.
3. **Neither is proven either way.** Every CI on both markets crosses zero.
   These are two unproven markets, not a good one and a bad one.

## The verdict

The bar is not defensible **as a relative judgment**. It permits the market
that scores worse and refuses the one that scores better, on evidence that
cannot distinguish them. That asymmetry is an artifact of which market got
audited, not a finding about either.

That is the whole argument for lifting it. It is deliberately not the argument
the dispatch requesting this work assumed — that the exclusion was "half a
measurement error" and the moneyline is therefore fine. Half of it *is* a
measurement error, and correcting that error still leaves the moneyline
unprofitable in every sample here. Anyone reading this as a green light has
read it backwards.

The MAE result is the standing caution and belongs in the record: our margin
estimate is worse than the market's, which is a real reason to expect the
moneyline to be hard. That is why it gets its own scored series rather than a
free pass.

## Pre-registration — moneyline as its own scored series

Registered **before** deployment so the result cannot be re-narrated afterwards.
Not yet live: the change to `ANCHOR_MARKETS` awaits operator authorization.

* **Effective**: the deploy date of the `ANCHOR_MARKETS` change, forward only.
  Nothing before it counts, and backfilled moneyline rows are excluded.
* **Series**: moneyline picks accrue separately from totals and spread. Shared
  attribution would let a totals edge hide a moneyline loss.
* **Primary metric**: money-at-price ROI over dollars staked, entries at the
  offer, game-clustered CI. Hit rate is reported only beside its
  stake-weighted entry cost — never alone, which is the error being corrected.
* **Floors before any read is taken**: n ≥ 150 moneyline bets across ≥ 100
  distinct games. Below that the CI cannot separate −10% from +10% and any
  interim number is noise.
* **The bar returns if**: at n ≥ 150, the game-clustered 95% CI on moneyline
  ROI lies **entirely below zero**. That is the same standard the original
  exclusion failed to meet, applied symmetrically.
* **The bar returns for the spread too**, on the identical test. The point of
  this exercise is a rule that does not depend on which market got audited.
* **Not a success criterion**: a positive point estimate with an interval
  crossing zero. That is where both markets already sit and it justifies
  nothing.

## What this does not touch

PULSE's in-game policy (`PULSE_MARKETS`) is unchanged and still empty. These are
pregame forecasting numbers; a latency strategy's edge comes from somewhere
else, and carrying this across would repeat the original mistake in the
opposite direction.
