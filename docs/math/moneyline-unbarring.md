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
The comparison is real, but **it does not isolate the moneyline, and I was
wrong to record it as an ML-specific caution.** The operator caught this.

The moneyline is `prob_home_win(projected_margin, sigma)`; the spread is
`prob_cover(projected_margin, threshold, sigma)`. Same projection, same sigma —
verified at `core/backtest/moneyline.py:368` and `:398`. **The moneyline is the
spread at line 0.** A margin estimate worse than the market's therefore indicts
both markets by exactly the same amount, and the spread sat in `ANCHOR_MARKETS`
the entire time.

So the MAE could never have been the reason the moneyline *alone* was barred.
It is an argument that proves too much: applied consistently it excludes the
spread as well. Set it aside and what remains is the hit-rate statistic — the
C11 error below. The exclusion was not a strong claim plus a weak one; it was
one incoherent claim with a respectable-sounding one draped over it.

This also settles what looked like two competing findings. ANCHOR pregame
already failed under measured fills (C14, −23.2% clustered) **with the spread
in the set throughout**. "Our margin estimate is weak" and "the pregame spread
trades lost money" are the same finding seen twice, not a contradiction.

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

## Where the margin gap lives — diagnostic, not a gate

`python -m core.backtest.margin_quality`. If our margin were competitive in
close games and hopeless in blowouts, that would be a different animal from
uniformly behind — and close games are the regime actually traded. 826 games,
2024–2026, bootstrapped on the **paired** per-game difference.

Overall: ours 10.21, market 9.50, **delta +0.71, CI [+0.39, +1.03]**. The gap is
real.

| bucket (ex-ante, known before tip) | n | ours | market | delta | CI95 |
|---|---|---|---|---|---|
| expected close (0–3) | 154 | 9.11 | 8.79 | +0.31 | [−0.36, +1.02] |
| expected 3–7 | 316 | 10.76 | 9.95 | +0.81 | [+0.26, +1.36] |
| expected 7–12 | 254 | 10.54 | 9.68 | +0.86 | [+0.32, +1.43] |
| expected 12+ | 102 | 9.31 | 8.73 | +0.59 | [−0.26, +1.46] |

Post-hoc, by actual margin, the point estimates rise monotonically: +0.44
(0–3), +0.49 (4–9), +0.76 (10–19), **+1.40 (20+)**.

**The tempting read is wrong.** Two buckets clear zero and two do not, which
looks like concentration — but that is not the test. A small bucket has a wide
interval, so "not significant" often means "not enough games". Concentration is
a claim about the *difference between* buckets, so the difference is what must
be resampled:

| comparison | difference | CI95 | verdict |
|---|---|---|---|
| expected close → expected 3–7 | +0.50 | [−0.35, +1.32] | not distinguishable |
| expected close → expected 7–12 | +0.55 | [−0.32, +1.41] | not distinguishable |
| expected close → expected 12+ | +0.27 | [−0.81, +1.34] | not distinguishable |
| actual close → actual 10–19 | +0.32 | [−0.62, +1.29] | not distinguishable |
| actual close → actual 20+ | +0.96 | [−0.18, +2.10] | not distinguishable |

**No between-bucket difference is distinguishable from zero.** The point
estimates order the way the hypothesis predicts — smallest in close games,
largest in blowouts — and that ordering is consistent with a real effect this
sample is too small to resolve. It is equally consistent with noise. The honest
answer to "uniform or concentrated?" is **the data cannot tell yet**, and the
closest thing to a lead is `actual close → actual 20+` (+0.96, upper CI +2.10,
lower −0.18), which is worth re-running as the sample grows.

What must NOT be done with this: gate anything on the post-hoc split. You do
not know at tip time whether a game will be close. Only the ex-ante buckets are
knowable in advance, and none of those differences clears zero either.

## The verdict

The bar is not defensible **as a relative judgment**. It permits the market
that scores worse and refuses the one that scores better, on evidence that
cannot distinguish them. That asymmetry is an artifact of which market got
audited, not a finding about either — and with the MAE argument set aside as
proving too much, there is no remaining claim that separates the two.

That is the whole argument for lifting it. It is deliberately not the argument
the dispatch requesting this work assumed — that the exclusion was "half a
measurement error" and the moneyline is therefore fine. Correcting the error
still leaves the moneyline unprofitable in every sample here. Anyone reading
this as a green light has read it backwards.

**The standing caution is about the margin projection, not about the
moneyline.** Our margin estimate is measurably worse than the market's
(+0.71, CI [+0.39, +1.03]), and *every margin-derived market inherits that* —
the moneyline and the spread equally, because they are the same projection at
two thresholds. It is a caution on the whole ANCHOR margin family. Recording it
against the moneyline alone is what let an incoherent bar look justified for as
long as it did, and it is the specific mistake this document exists to undo.

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
* **Margin-quality caution, applying to the whole margin family**: the
  projection behind both markets is measurably worse than the market's. Re-run
  `core.backtest.margin_quality` at each read. If the gap closes, both markets
  improve together; if it widens, both degrade together. It is not evidence
  about one of them.
* **Provenance**: the incoherence in the original exclusion — that a margin-MAE
  argument cannot single out the moneyline when the spread shares the
  projection — was identified by the operator, not by this codebase's own
  review, and not by the builder who wrote the re-score and repeated the MAE as
  an ML-specific caution before being corrected.

## What this does not touch

PULSE's in-game policy (`PULSE_MARKETS`) is unchanged and still empty. These are
pregame forecasting numbers; a latency strategy's edge comes from somewhere
else, and carrying this across would repeat the original mistake in the
opposite direction.
