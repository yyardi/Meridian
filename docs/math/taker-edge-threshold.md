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

**1.5 pp at the extremes, 2.7 pp in the middle.** The half-spread is the floor
and the fee adds 0.3–1.5 pp on top. *(A 1.55¢ half-spread appears elsewhere in
the repo from a one-game sample; at that value every figure rises by 0.36 pp and
nothing below changes.)*

## The inversion: what Brier improvement does an edge produce?

If the market says `p`, the truth is `q = p + e`, and the model is calibrated at
`q`:

```
Brier(market) = (p−q)² + q(1−q)
Brier(model)  =          q(1−q)
Brier(market) − Brier(model) = e²        exactly, and independent of p
```

**A tradeable edge produces a squared-tiny Brier improvement.**

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
