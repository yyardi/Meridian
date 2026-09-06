# The minimum taker edge, and why Brier cannot see it

**DESCRIPTIVE. NO GATE.** Cost first, then ask whether any measured quantity
clears it — the same order that closed the cross-venue question.

**The headline inverts the expectation this was commissioned under.** The
required edge is not "far outside our confidence interval". It is **far inside
it** — 25× smaller than the interval's own width. The problem is not that the
model falls short of the threshold. It is that **the instrument we have been
using cannot resolve a tradeable edge at all.**

## The threshold

Hold-to-settlement, so **there is no exit leg**: a binary contract settles at 0
or 1 and is never sold. That is one spread and one fee, not two — half the
cross-venue case, and the reason this is the cheaper strategy.

```
EV per contract = e − s − fee(ask)        e = model edge vs mid (q − p)
                                          s = half-spread paid on entry
                                          fee(a) = 0.06·a·(1−a),  a = p + s
```

At the measured half-spread **s = 1.193¢**:

| p | fee(ask) | half-spread | **minimum edge** |
|---:|---:|---:|---:|
| 0.50 | 1.499¢ | 1.193¢ | **2.69 pp** |
| 0.30 | 1.288¢ | 1.193¢ | 2.48 pp |
| 0.20 | 1.002¢ | 1.193¢ | 2.20 pp |
| 0.10 | 0.596¢ | 1.193¢ | 1.79 pp |
| 0.05 | 0.349¢ | 1.193¢ | 1.54 pp |

**⚠️ THE TABLE ABOVE IS NEAR-MONEY ONLY, AND ITS TAIL ROWS ARE WRONG.** It holds
`s = 1.193¢` constant in `p`. That is the *near-money* half-spread. The same
repo records, in three places, that **the 0.95/0.05 rungs carry 22–26¢ spreads
and do not trade** — a half-spread of 11–13¢, ten times the value used.

Corrected at the tails:

| p | threshold at s=1.193¢ | threshold at the measured tail spread |
|---:|---:|---:|
| 0.10 | 1.79 pp | **12.0 pp** |
| 0.05 | 1.54 pp | **11.8 pp** |

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
| **2.69 pp (tradeable at p=0.5)** | **0.00072** |
| 5.00 pp | 0.00250 |
| 13.40 pp | 0.01796 |

## Against what we can actually measure

The live model's paired Brier at G=34 is **−0.0048 [−0.0231, +0.0135]** — a tie.
The interval's half-width is ~0.018.

* **Smallest edge that interval could detect: √0.018 = 13.4 pp.**
* **Edge needed to trade: 2.69 pp.**
* **The instrument is 25× coarser in Brier terms, 5× in edge terms.**

The required improvement, 0.00072, sits **deep inside** the confidence interval.
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
| **21,039** | **required for 2.69 pp** | 0.00072 | 2.7 pp |

**A full football season moves the detectable edge from 13.4 pp to 8.0 pp. The
tradeable threshold is 2.7 pp.** With dilution at `f = 0.25` the requirement is
**336,616 games**.

So the accrual plan is not aimed at an unreachable *target* — it is aimed
through an unusable *instrument*. Resolving λ* or a paired Brier to any
precision a season affords still leaves a gap of 3–5× in edge terms, and no
amount of football closes it.

## The λ* join (Quant B's conversion, which does work)

λ* converts cleanly where Brier does not: the real part of the model's
disagreement is `λ*·(fv − mid)`, so **expected edge = λ* × |fv − mid|**. On live
entered decisions `|fv − mid| ≈ 0.08`.

| p | threshold | λ* needed | edge at λ* = 0.15 | clears? |
|---:|---:|---:|---:|---|
| 0.50 | 2.69 pp | **0.337** | 1.20 pp | **no** |
| 0.30 | 2.48 pp | 0.310 | 1.20 pp | **no** |
| 0.20 | 2.20 pp | 0.274 | 1.20 pp | **no** |

**λ* = 0.15 buys 1.20 pp against a 2.2–2.7 pp threshold — under half.** The
required λ* is **0.27–0.34, roughly twice the accrual target.**

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
half-spread 1.193¢ as measured. Descriptive only.*
