# The concession is applied per contract — and the size term is not there

> **Intervals below are ~5% too narrow.** They were computed with an inline
> estimator using z = 1.96 and no finite-sample correction; the correct
> construction for few clusters is CR1 √(G/(G−1)) with t at df = G−1
> (1.054× at G = 34, 1.216× at G = 10). Point estimates are unaffected and **no
> conclusion here changes** — widening only strengthens the central claim, that
> QUOTE's 4.70¢ sits *inside* the measured 4.545¢ interval. Cause and re-issued
> figures: [my-clustered-intervals-were-narrow](my-clustered-intervals-were-narrow.md).

`analysis/pulse_execution_decomposition.py:285` charges the pessimistic
execution rule as a flat rate times total size:

```python
contract_legs = legs.contracts.sum() + trips.contracts.sum()
pess_exec = MEASURED_CONCESSION_INGAME * contract_legs      # 4.70¢ × Σ size
```

That is a linearity assumption, and the study behind the constant cannot test
it: `ShadowQuoteFill` has **no size field**, so QUOTE has zero size variation
and zero power to detect size dependence — not low power, zero.

**Resolved on PULSE's own fills. Linearity holds. The assumption is safe, and
for none of the reasons anyone proposed, including me.**

## The proposed test was measuring a mechanism that does not exist

The plan was `p95(contracts / touch_depth)`: below 1, linearity safe; above 1,
the convex book-walking term bites. Both branches are void.

**Every filled leg rests. None crosses.** Of 4,725.5 contract-legs, **0.0%**
are marketable against the decision-time book:

| leg | placement |
|---|---|
| enter yes | **100%** at the bid |
| enter no | **100%** at the ask (YES frame) |
| exit yes | 41.6% above the ask, 40.9% at it, 17.5% inside |
| exit no | 44.8% below the bid, 37.4% at it, 17.8% inside |

A resting order does not consume the touch — it joins the queue behind it.
Book-walking cannot occur, so `contracts / touch_depth` is not a small number
or a large one, it is **the wrong ratio**. It would have returned a value
either way and been believed.

For entries this is the engine's construction (the limit is *set* to the
touch, so the test is circular there and I say so). For exits it is an
observation across a genuinely spread distribution, and they are passive too.

## The real size channel, and it dissolves

With book-walking gone, the remaining channel is adverse selection: is a
larger resting order picked off harder *per contract*? Raw, it looks like yes.
Controlled, no.

Per-leg mean markout at fill by order size, game-clustered:

| size | n | mean markout | 95% CI |
|---|---:|---:|---|
| <0.5 | 1,411 | −1.398¢ | [−1.567, −1.229] |
| 0.5–1 | 980 | −1.524¢ | [−1.761, −1.287] |
| 1–2 | 668 | −1.540¢ | [−1.778, −1.301] |
| 2–5 | 551 | −1.689¢ | [−2.097, −1.281] |
| >5 | 141 | **−2.475¢** | [−2.907, −2.043] |

Monotone, and the extreme intervals do not overlap. **It is a confound.** The
sizer scales with edge, and the >5 bucket sits at mean |edge_net| 0.301
against 0.079 for the smallest. Adding controls to the slope of markout on
size:

| model | size coefficient |
|---|---:|
| uncontrolled | −0.1231¢ per contract |
| + half-spread | −0.1080¢ |
| + half-spread + \|edge\| | **−0.0403¢** |

67% of the raw gradient is edge wearing size's name, and within edge strata
the direction is not even consistent (large orders are *better* at low and mid
edge, worse only at high edge). The |edge| coefficient is −2.87¢, two orders
above size's.

**Per-contract concession is size-independent once the situation is
controlled. The flat rate is the right functional form.**

## What the flat rate is worth, which is a separate question

Realised markout on all 3,751 filled legs, 4,725.5 contracts, 34 games:

| estimator | value | 95% CI (game-clustered) |
|---|---:|---|
| per **leg** | −1.539¢ per leg | [−1.699, −1.380] |
| per **contract** | **−1.808¢ per contract** | [−2.045, −1.572] |
| — entries | −1.825¢ per contract | [−2.109, −1.541] |
| — exits | −1.791¢ per contract | [−2.073, −1.508] |

The per-leg / per-contract gap of 0.27¢ is real: contracts do sit in the
slightly worse-executed legs, so the two estimators must be named apart.
Entries and exits agree, which they need not have.

Against these, the flat charge is **4.70¢ × 4,725.5 = $222.10**, while the
realised per-contract markout implies **$85.46** — the flat rate is **2.60×**
the realised figure.

**This retracts a direction I asserted.** I told the manager the flat rate
"understates, never overstates", so the pessimistic branch was a lower bound.
That rested entirely on convexity from book-walking. With no book-walking the
premise is void and the conclusion does not follow.

### And the 2.60× was a category error — the two agree

Reconciled against the constant's provenance (`adverse_selection.py`,
`E[−dmid | filled]`, 30s, quote-anchored — from Quant A). Both are the same
decomposition; I had compared different lines of it.

| term | PULSE, per leg | QUOTE |
|---|---:|---:|
| half-spread (favourable, earned by resting) | +3.004¢ | +1.96¢ |
| **adverse mid move** | **4.545¢** [4.199, 4.891] | **4.70¢** |
| net (= half-spread − adverse move) | −1.541¢ | −2.74¢ |

**4.70¢ sits inside my interval.** −1.541 = 3.004 − 4.545 and −2.74 = 1.96 −
4.70; the net figures differ only because PULSE rests into a wider spread.
Median elapsed decision→fill is 34s against QUOTE's fixed 30s horizon.

So **4.70¢ is not too high as a gross adverse-move estimate** — PULSE's own
fills reproduce it. What is wrong is its *application*:
`4.70¢ × Σ contracts` charges the gross adverse move while omitting the
**+3.004¢ per leg of spread that resting at the touch actually earns**. The
net execution cost on PULSE's own fills is **−1.541¢ per leg / −1.825¢ per
contract**.

Whether to net the spread credit is a modelling choice — it depends on whether
the alpha term is already mid-anchored, which I have not verified — but it is
not a 2.6× calibration error in the constant, and I withdraw that framing.

## The cadence blocker was real, and is moot here

Flagged before use, and correctly. In `ptd_20260906T195333Z` the per-market
gap between consecutive snapshots is **bimodal**: median 11s, but **p90 921s**
and p99 3,622s. About a tenth of decisions would have ASOF-joined to a book
over fifteen minutes stale.

Market coverage was fine — **399 of 399** PULSE markets present, so the export
did clear the data blocker. It is the statistic that was wrong, not the data.

## Status

**Closed.** Linearity is safe; the code's functional form is right. Two live
questions are left behind and neither is this one: whether 4.70¢ is the right
*level* for PULSE, and why |edge| is the dominant driver of realised markout
at −2.87¢ per unit — a model that captures less when it thinks it sees more.
