# Is Polymarket's ladder too narrow?

**Question:** the model and the market agree on the total but disagree on how *uncertain* it is. Who is right?

Found 2026-08-02 while breaking down a single game's board. **Not yet established** — read the caveats.

## The observation

Fitting a normal to both ladders on LA–POR:

| | Implied mean | Implied sigma |
|---|---|---|
| Polymarket ladder | 186.4 | **15.8** |
| Model's own curve | 186.2 | **21.0** |
| Disagreement | **−0.2 pts** | **+5.1 pts** |

The two agree on the total to within a fifth of a point. **Every displayed edge on that board was a volatility disagreement, not a directional one.** That is why the sides looked contradictory — UNDER on the low rungs, OVER on the high ones. It is not a view on the game; it is a straddle.

## It is not one ladder

Fitting all 362 recorded pregame Polymarket ladders:

| | |
|---|---|
| Implied sigma, median | **15.9** |
| Mean | 16.4 |
| sd across ladders | 1.4 |
| 10th–90th percentile | 15.6 – 17.6 |

Remarkably tight. Polymarket appears to shape its ladder with a near-constant ~16-point sigma.

## What sigma actually is

How far totals land from a pregame line, measured:

| Season | n | sd(actual − book line) |
|---|---|---|
| 2024 | 261 | 15.7 |
| 2025 | 311 | 16.1 |
| **2026** | 213 | **20.1** |

2024 and 2025 sit right on Polymarket's ~16. **2026 does not.** The scoring environment shifted — league mean went from ~166 to ~174 — and variance went with it.

So the hypothesis is narrow and mechanical: **Polymarket is shaping 2026 ladders with 2024's volatility.** If true, both tails are systematically cheap, and the mispricing is structural rather than game-specific.

The model is not obviously the smart one here either. Its own sigma tracks the *unconditional* season spread:

| Season | sigma used | sigma realised | error |
|---|---|---|---|
| 2024 | 16.8 | 16.3 | +0.5 |
| 2025 | 16.8 | 16.8 | −0.0 |
| 2026 | 19.2 | 21.7 | **−2.4** |

In 2026 the model *understates* by 2.4 points. It is closer than Polymarket's 15.9, but it is not calibrated — it is lagging the regime rather than leading it.

## Why this is not yet a result

The direct outcome test — do far-from-money contracts settle YES more often than their price implies? — cannot be run on what we have:

| Price bucket | n | Market says | Actually hit | Diff |
|---|---|---|---|---|
| longshot (0.15–0.30) | 39 | 0.255 | 0.154 | −0.101 |
| below mid (0.30–0.50) | 97 | 0.393 | 0.639 | **+0.247** |
| favourite (0.70–0.85) | 71 | 0.760 | 0.620 | −0.140 |

That +0.247 is not a finding, it is **5 games**. 305 rows from 5 games is ~60 correlated rows each. Every bucket here is noise, and the direction happens to contradict the hypothesis, which is exactly what noise does.

Other reasons to withhold judgement:

- **2026 is one partial season (n=213).** A variance regime that shifted once can shift back, and the whole hypothesis rests on 2026 being genuinely different rather than temporarily unlucky.
- **The comparison mixes references.** Polymarket's ladder sigma is fitted against Polymarket's own implied mean; the 20.1 is measured against the *sportsbook* line. Close, not identical.
- **It may already be priced into the measured edge.** The champion's +2.5% comes disproportionately from tail rungs, so its edge may *be* this sigma effect rather than the directional venue gap we have been attributing it to. That reframing matters: it would mean the model is accidentally selling correctly-shaped volatility, and would break the moment Polymarket updates its sigma.

## The pre-registered test

Do not act on this before it passes:

> Across **n ≥ 40 games** of resolved Polymarket totals, bucket contracts by price. If the ladder is too narrow, contracts priced below 0.30 settle YES **more** often than their price implies, and contracts above 0.70 settle YES **less** often — both with 95% CIs excluding zero, and in the same direction.

Sample size is **games**, not rows. At ~60 correlated rows per game, 40 games is the minimum for the buckets to mean anything.

If it passes, the trade is mechanical and needs no basketball model at all: buy both tails, sell the middle. If it fails, the model's tail preference is an artifact and should be damped.

## Corroborating context, added 2026-08-07 — the gate above is unchanged

Two independent measurements landed since this was written. **Neither touches
the pre-registered test**, and neither is evidence that it passes; they are
recorded here because both bear on the premise that one constant sigma
describes this market.

**1. Live margin sigma is not constant across a game.**
[win-curve.md](win-curve.md) fits P(win | margin, minutes left) over 787 games
and gets sigma = **2.628** points per sqrt-minute — but the implied value
**decays by period**: 2.98 at end-Q1, 2.77 at the half, **2.40** at end-Q3. A
pure sqrt-time random walk would hold one sigma at every horizon. It does not,
so late points are worth more than sqrt(t) predicts.

**2. Tail activity is not constant across a game either.**
[tail-volatility.md](tail-volatility.md) measures |30s mid move| by game phase
and finds the tails **quieter** at the open than mid-game (−0.731¢, 8 games —
under-powered, reported as NO DATA) and livelier at the close (+0.555¢) —
though the *body* rungs gain +2.135¢ over the same phase, roughly 4x more.

Together these say the same thing from two directions: **variance in this
market is time-dependent**, so a ladder shaped with one constant sigma is
mis-shaped in a way that varies through the game rather than uniformly.

That is a reason the 15.9-vs-20.1 gap might be *structural* rather than a
mispricing anyone will correct — and equally a reason it might be concentrated
in particular game states rather than spread evenly across the settled sample
this doc's gate will score. **It does not move the gate.** If anything it
argues for reading the eventual result by game phase as well as by price
bucket, which the current test does not do and should not be retrofitted to do
after the fact.

## Status

**Hypothesis, unproven** (2026-08-02; context added 2026-08-07). The sigma gap
is real and consistent across 362 ladders; whether it converts to money is
untested and needs ~35 more games of resolved data. The pre-registered test is
unchanged.

---

## Reference prices for the 2026-08-25 re-run — DECLARED BEFORE COMPUTING

The registration fixes the buckets (<0.30, >0.70), the floor (n >= 40 games)
and the direction, but it **never pinned a reference price**. That gap is real:
"the price" of a totals contract is a choice, and a test whose answer depends
on an unpinned choice is not yet a finding.

So both arms are written down here **before any number is computed**, and the
commit that adds this section precedes the commit that adds the verdict. Read
the git history if you want to check that rather than trust it.

* **Arm A — primary: the LAST pregame two-sided mid.** The last snapshot before
  `is_live` with both a bid and an ask, priced `(bid + ask) / 2`. This is the
  research agent's declared choice on the 56-game mirror, kept identical so the
  two runs are comparable rather than merely both present.
* **Arm B — sensitivity: the MEDIAN of every pregame two-sided mid** for that
  market. Arm A rests on a single snapshot and inherits whatever that snapshot
  was — stale, wide, or mid-drift. The median cannot be moved by one bad quote.

**What each outcome means, also fixed now:** if the arms agree, the verdict does
not depend on the unpinned choice and the registration's gap did not matter
here. If they disagree, the verdict is that **this test is not identified
without pinning a reference price**, and that is the finding — not whichever arm
reads better.

Sample: **69 resolved-totals games** from the off-prod eval copy (621 totals
markets, resolved 2026-08-01 to 08-24), against the mirror's 56. Larger and
overlapping rather than independent, which is stated plainly: this corroborates
by extending the sample, it does not replicate on disjoint data.
