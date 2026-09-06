# The minimum taker edge, and why Brier cannot see it

**DESCRIPTIVE. NO GATE.** Cost first, then ask whether any measured quantity
clears it — the same order that closed the cross-venue question.

**The headline inverts the expectation this was commissioned under.** The
required edge is not "far outside our confidence interval". It is **far inside
it** — 25× smaller than the interval's own width. The problem is not that the
model falls short of the threshold. It is that **the instrument we have been
using cannot resolve a tradeable edge at all.**

## ⚠️ THE HALF-SPREAD INPUT WAS WITHDRAWN. τ IS 3.07 pp, NOT 2.69.

**Superseded 2026-09-06 by c7's audit.** Every number on this page scales off
one input, and the input this page was published with — `s = 1.193¢` — **had no
owner and has been withdrawn.** c7 stated it was not theirs and that they never
measured it; neither c7 nor A could source it. It nonetheless set every figure
below, including the published 57.8% breakeven floor.

The replacement arrived ambiguous — described as both a half-spread and a full
spread in successive messages, which moved τ in opposite directions and is why
this page carried a three-way table rather than a number. **c7's audit resolves
it: the half-spread is `s = 1.569¢`.**

| | half-spread | τ at p = 0.50 |
|---|---:|---:|
| published (withdrawn) | 1.193¢ | 2.69 pp |
| **corrected** | **1.569¢** | **3.07 pp** |

**The correction runs AGAINST us: +0.38 pp, a harder bar.** That direction is
the reason to trust it rather than to re-open it — an error that made trading
easier would deserve more scrutiny than one that makes it harder.

**3.07 pp is still not a scalar.** τ varies by market type by roughly a factor
of seven — winner ~0.5 pp, spread ~2.0 pp, total ~3.5 pp on A's CFB tape — and
the blend behind `s = 1.569¢` was never recorded. See the surface caveat below
before quoting any single number from this page.

**A spread quoted without "full" or "half" attached is not a measurement, it is
two measurements.** That is the same label-the-policy failure this project has
hit on estimators and on P&L conventions, arriving on a venue microstructure
constant.

**CFB: withdrawn, unmeasured, awaiting tonight's tape.** A withdrew the CFB
taker bar. It had been measured on the frozen 09-05 tape, where 99% of markets
with ≥20 snapshots showed ≤2 distinct book states — a spread computed from a
board nobody was quoting. There is no CFB number on this page and there should
not be one until a live tape supports it. **Every figure below is WNBA.**

**What survives regardless, and it is the argument this page is for:** τ stays
in the 2.5–3.5 pp band, an order of magnitude above the 0.0009-scale Brier
improvements the accuracy work resolves, and above the 1.20 pp that λ* = 0.15
buys. **The direction of every conclusion below is unchanged.**

One second-order effect is worth stating because it is counterintuitive: a
HIGHER bar is EASIER to detect, so the games required to resolve it falls from
21,039 to **12,401**. The bar moved away from us and the instrument's relative
coarseness fell from 25× to 19×. Both are true and neither rescues the
programme — 12,401 games is still ~46 NFL seasons.

## ⚠️ τ IS A SURFACE OVER (TYPE, PRICE). EVERY SCALAR ON THIS PAGE IS A MIXTURE.

**Added 2026-09-06, from A's per-type measurement.** This page computes τ as a
function of `p` and treats the half-spread as one constant. It is not one
constant — **it varies by market type by an order of magnitude.** On A's CFB
tape:

| market type | τ |
|---|---:|
| winner (moneyline) | **~0.5 pp** |
| spread | ~2.0 pp |
| total | **~3.5 pp** |

**The pooled 2.5–3.5 pp band this page argued from was totals-dominated.** A
winner market at 0.5 pp is a *seventh* of the bar the pooled figure implies.

**So the 3.07 pp WNBA figure is also a type-mixture, and its composition is not
stated anywhere.** `s = 1.569¢` was measured over some blend of winner, spread
and total markets; nobody recorded the blend. That makes 3.07 pp a number
without a population — the same defect this page opened by documenting in
`1.193¢`, one level up. It is the fourth population mixture this programme has
found, after the estimator, the lineage policy, and the near-money/tail split
already flagged below.

**Operationally: a trade's edge must be compared against τ at its own type and
its own price.** A single scalar cannot gate a mixed book — it over-rejects
winner markets and under-rejects totals, and it does both silently because
every comparison it makes is arithmetically valid.

**What survives, and one thing that may not.** The negative conclusions below
rest on a comparison against the *instrument*, which is 19× coarser in Brier
terms than even the tightest bar here. That argument is unaffected.

But the λ* comparison is not. λ* = 0.15 buys 1.20 pp, which clears a 0.5 pp
winner-market bar and does not clear a 3.5 pp totals bar — **opposite verdicts
inside one pooled number.** So the winner-market case cannot be called closed
from this page any more.

**That sentence splices two populations and is therefore not a conclusion.**
The 1.20 pp is WNBA, from λ* on PULSE's live entered decisions; the 0.5 pp is
**A's CFB tape**. A WNBA λ* against a CFB τ shares no population policy, which
is the exact splice this project has been caught making before. What the
arithmetic establishes is that **the pooled bar was hiding a factor of seven
between market types**; what it does not establish is that any specific market
clears. The per-type τ must be measured **on the same league and the same
cohort as the λ*** before anyone acts on either sign.

## The threshold

Hold-to-settlement, so **there is no exit leg**: a binary contract settles at 0
or 1 and is never sold. That is one spread and one fee, not two — half the
cross-venue case, and the reason this is the cheaper strategy.

```
EV per contract = e − s − fee(ask)        e = model edge vs mid (q − p)
                                          s = half-spread paid on entry
                                          fee(a) = 0.06·a·(1−a),  a = p + s
```

At the corrected half-spread **s = 1.569¢** (WNBA):

| p | fee(ask) | half-spread | **minimum edge** |
|---:|---:|---:|---:|
| 0.50 | 1.499¢ | 1.569¢ | **3.07 pp** |
| 0.30 | 1.296¢ | 1.569¢ | 2.87 pp |
| 0.20 | 1.015¢ | 1.569¢ | 2.58 pp |
| 0.10 | 0.614¢ | 1.569¢ | 2.18 pp |
| 0.05 | 0.368¢ | 1.569¢ | 1.94 pp |

**⚠️ THE TABLE ABOVE IS NEAR-MONEY ONLY, AND ITS TAIL ROWS ARE WRONG.** It holds
`s = 1.569¢` constant in `p`. That is the *near-money* half-spread. The same
repo records, in three places, that **the 0.95/0.05 rungs carry 22–26¢ spreads
and do not trade** — a half-spread of 11–13¢, ten times the value used.

Corrected at the tails:

| p | threshold at s=1.569¢ | threshold at the measured tail spread |
|---:|---:|---:|
| 0.10 | 2.18 pp | **12.0 pp** |
| 0.05 | 1.94 pp | **11.8 pp** |

**So the threshold does not fall toward the extremes — it rises steeply**, because
the spread term dominates and the spread is an order of magnitude wider there.
Caught by Quant B asking what spread was assumed and whether it varies with `p`.
I had cited the 22–26¢ figure myself in the cross-venue close and did not apply
it here.

**Valid range: `0.15 ≲ p ≲ 0.85`, where 2.2–2.7 pp holds.** That is where live
entries sit, so the join below is unaffected — but the curve must not be read
past its edges. *(A 1.55¢ near-money half-spread appears elsewhere from a
one-game sample; at that value the mid-range figures rise by 0.36 pp.)*

## The inversion: what Brier improvement does an edge produce?

If the market says `p`, the truth is `q = p + e`, and the model is calibrated at
`q`:

```
general:   Brier(market) − Brier(model) = e_market² − e_model²
                                          (a difference of SQUARED ERRORS)

only if the model is exactly right (e_model = 0):
           Brier(market) − Brier(model) = e²
```

**The `e²` form requires the model to be exactly right, and that is a real
restriction, not a technicality.** Quant B's correction: a Brier gain does not
convert to an edge without a stated assumption, because it is a difference of
two squared errors and neither is observed separately. **Do not read an edge off
a Brier number.**

The direction still holds and it is what matters here: `e²` is the **maximum**
improvement a given edge can produce, so the figures below are an upper bound on
what any real model would show. A tradeable edge produces a squared-tiny Brier
improvement **at best**.

| edge | Brier improvement |
|---:|---:|
| 1.00 pp | 0.00010 |
| **3.07 pp (tradeable at p=0.5)** | **0.00094** |
| 5.00 pp | 0.00250 |
| 13.40 pp | 0.01796 |

## Against what we can actually measure

The live model's paired Brier at G=34 is **−0.0048 [−0.0231, +0.0135]** — a tie.
The interval's half-width is ~0.018.

* **Smallest edge that interval could detect: √0.018 = 13.4 pp.**
* **Edge needed to trade: 3.07 pp.**
* **The instrument is 19× coarser in Brier terms, 4.4× in edge terms.**

The required improvement, 0.00094, sits **deep inside** the confidence interval.
It is not that the model failed to clear a bar; the measurement never had the
resolution to say either way.

Two things make this worse rather than better:

* **The `e²` relation is an upper bound.** It assumes the model is *perfectly
  calibrated* at the true probability. A real model's improvement is smaller.
* **Brier averages over every market, including those where the model has no
  opinion.** If the model has edge on a fraction `f` of markets, the observed
  improvement is `f·e²`, not `e²`. PULSE trades only where it disagrees by >5¢ —
  a minority — so `f` is well below 1.

## What accrual buys, and why the season plan is aimed at the wrong instrument

Interval half-width scales as `1/√G`.

| G | | half-width | detectable edge |
|---:|---|---:|---:|
| 34 | today | 0.01800 | 13.4 pp |
| 272 | full NFL regular season | 0.00636 | 8.0 pp |
| 600 | NFL + CFB season | 0.00428 | 6.5 pp |
| **12,401** | **required for 3.07 pp** | 0.00094 | 3.1 pp |

**A full football season moves the detectable edge from 13.4 pp to 8.0 pp. The
tradeable threshold is 3.1 pp.** With dilution at `f = 0.25` the requirement is
**198,422 games**.

So the accrual plan is not aimed at an unreachable *target* — it is aimed
through an unusable *instrument*. Resolving λ* or a paired Brier to any
precision a season affords still leaves a gap of 3–5× in edge terms, and no
amount of football closes it.

## ⚠️ This threshold prices CROSSING, and PULSE does not cross

**Quant B measured the engine 100% passive**: `side=yes` posts at `market_bid`
on **100.0% of 1,342 entries**, `side=no` at `market_ask` on **100.0% of 1,632**.
Both arms join the touch.

So everything above is the bar for a **taker** strategy. **PULSE's economics are
maker economics**, and comparing its λ* to this curve compares a maker engine
against a taker bar. The curve stands as the threshold any *future* crossing
strategy must clear; it is not the threshold for this engine.

The right instrument for PULSE is money on real fills, which B has:

| arm | P&L | |
|---|---:|---|
| all entries | +6.880 pp [+2.774, +10.985] | excludes zero |
| **filled only** | **+4.761 pp [−1.455, +10.978]** | **spans zero** |
| withdrawn | +10.857 pp [+7.554, +14.160] | excludes zero |

**34.3% of entries never traded.** On real fills it does not clear zero, and the
withdrawn arm carrying twice the filled arm's P&L is adverse selection visible
in money rather than in fill rates.

## The λ* join (Quant B's conversion, which does work)

λ* converts cleanly where Brier does not: the real part of the model's
disagreement is `λ*·(fv − mid)`, so **expected edge = λ* × |fv − mid|**. On live
entered decisions `|fv − mid| ≈ 0.08`.

| p | threshold | λ* needed | edge at λ* = 0.15 | clears? |
|---:|---:|---:|---:|---|
| 0.50 | 3.07 pp | **0.384** | 1.20 pp | **no** |
| 0.30 | 2.87 pp | 0.359 | 1.20 pp | **no** |
| 0.20 | 2.58 pp | 0.323 | 1.20 pp | **no** |

**λ* = 0.15 buys 1.20 pp against a 2.6–3.1 pp threshold — under half.** The
required λ* is **0.27–0.34, roughly twice the accrual target.**

**But the measured λ* is convention-dependent and the required 0.337 sits inside
its range**, so this comparison decides nothing on its own:

| dedupe | λ* | 95% CI | edge | vs 0.337 |
|---|---:|---|---:|---|
| earliest row per market | +0.364 | [−0.110, +0.929] | 2.96 pp | clears |
| all rows | +0.219 | [−0.045, +0.796] | 1.70 pp | below |
| entries, all rows | +0.217 | [−0.061, +0.753] | 1.74 pp | below |

**Every interval contains zero.** And while the point estimate sits below the
target, more games move the interval *toward* the point and away from clearing —
the accrual can confirm failure, never success.

Two caveats that belong with the number. `|fv − mid| ≈ 0.08` is measured **on
entries only**, which is the right population — those are the bets that would
trade — but it is a selected one, and the comparison inherits that selection.
And `fv > mid` on 100% of `side=yes` entries and 0% of `side=no`: the sign is
fixed per arm by construction, so 0.08 is a magnitude, not a signed edge.

## The constructive half

**Measure money, not accuracy.** The threshold above is a statement about a
price and a fee — so is the thing being tested. The project already has the
machinery: money-at-price in the C11 frame, game-clustered, on the bets the
model would actually take.

That estimator does not average over markets where the model is silent, which is
the dilution term, and it measures the quantity the decision depends on rather
than a proxy that squares it. **A Brier difference is the wrong instrument for a
money question, and squaring is why.**

---

*Computed 2026-09-06. Fee `0.06·p(1−p)` from `core/quote/wallet.py:42`;
half-spread 1.569¢ per c7's audit, superseding the withdrawn 1.193¢.
WNBA only; CFB per-type figures are A's. **Every scalar here is a mixture over
market type — see the surface caveat above.** Descriptive only.*
