# The |edge| gradient: two mechanisms, not one, and the outcome axis cannot see either

> **Intervals below are ~5–9% too narrow.** Computed with an inline estimator
> using z = 1.96 and no finite-sample correction; the correct construction for
> few clusters is CR1 √(G/(G−1)) with t at df = G−1 (1.054× at G = 34, 1.091×
> at G = 21, 1.216× at G = 10). Point estimates are unaffected. **No conclusion
> changes**, but two are closer than they read: the q3/q4 calibration errors
> still exclude zero after widening, q4 only just (−0.087 → about [−0.167,
> −0.008]). The drift/half-spread ratio is re-issued at −1.809 [−1.901, −1.716]
> and still excludes the mechanical null of −1.0. Cause and full re-issue:
> [my-clustered-intervals-were-narrow](my-clustered-intervals-were-narrow.md).

Three sightings were proposed as one mechanism — "the more confident the model,
the worse the result": PULSE's disagreement>5¢ cut being the worst slice,
withdrawn orders beating filled ones, and realised markout worsening with
|edge|. **They are not one mechanism, and they do not carry equal weight.**

Population: 2,974 filled-or-withdrawn PULSE entry decisions, pin
`20260901T195202Z`, 1,944 filled across 34 games. All intervals game-clustered.

## The selection story, as posed, is refuted

The hypothesis was that large-|edge| orders fill *less* often, so the ones that
do fill are those the market ran through. **Fill rate rises with |edge|:**

| \|edge\| quintile | mean \|edge\| | fill rate | half-spread |
|---|---:|---:|---:|
| q1 lo | 0.041 | 63.8% | 1.70¢ |
| q2 | 0.066 | 62.9% | 2.93¢ |
| q3 | 0.093 | 63.1% | 3.77¢ |
| q4 | 0.131 | 64.1% | 4.10¢ |
| q5 hi | 0.238 | **72.9%** | 4.10¢ |

Flat, then *up*. High-confidence orders are filled more readily, not less.

## Where the gradient actually lives

For a resting order, `markout = (mid_dec − limit) + (mid_fill − mid_dec)` —
a **static** term, which for a touch order is +half-spread and is *favourable*,
plus **drift**, the true adverse selection. Identity verified exactly (max
residual 0.000000000).

| \|edge\| | markout per leg | static | **drift** |
|---|---:|---:|---:|
| q1 lo | −1.154¢ | +1.625¢ | **−2.778¢** [−3.045, −2.512] |
| q2 | −1.303¢ | +2.593¢ | −3.896¢ [−4.283, −3.509] |
| q3 | −1.753¢ | +3.369¢ | −5.122¢ [−5.637, −4.606] |
| q4 | −1.487¢ | +3.533¢ | −5.020¢ [−5.456, −4.584] |
| q5 hi | −1.952¢ | +3.794¢ | **−5.745¢** [−6.197, −5.294] |

The static term grows too, and *offsets* — posting into a wider spread earns
more. Drift overwhelms it.

## Most of the |edge| gradient is spread wearing edge's name

`corr(half_spread, drift) = −0.717`; `corr(|edge|, half_spread) = +0.315`.
PULSE acts in wider markets when it sees more edge, and wide markets punish
resting orders.

| model | \|edge\| coefficient |
|---|---:|
| drift ~ \|edge\| | −12.24 |
| drift ~ \|edge\| + half_spread | **−3.38** |

72% of it is spread. An edge-specific residual does survive, and within the
narrow and wide strata the high/low-|edge| difference is individually
significant (narrow −1.963 vs −2.628; wide −6.879 vs −7.811, non-overlapping).

## The structural number, which is the real finding

$$\frac{\text{drift}}{\text{half-spread}} = -1.809 \quad [-1.896,\ -1.721]$$

**The mechanical null is exactly −1.0.** An order resting at the touch that
fills when the market merely *reaches* it sees the mid travel one half-spread
— no information, pure fill-when-touched. We measure −1.81, and the interval
excludes −1.0 decisively.

So the mid does not stop at the resting price. It goes **through** it and
keeps going, by another 0.81 half-spreads. That is genuine adverse selection,
it is present at **every** edge level including the lowest (q1 drift −2.78¢ on
a 1.70¢ half-spread), and it is a property of resting passively in this
market rather than of the model's confidence.

## The model is separately, and genuinely, overconfident

Realised minus model probability (negative = overconfident):

| \|edge\| | model p | market p | realised | model error |
|---|---:|---:|---:|---|
| q1 lo | 0.504 | 0.479 | 0.500 | −0.004 [−0.067, +0.060] |
| q3 | 0.552 | 0.490 | 0.449 | **−0.103** [−0.174, −0.032] |
| q4 | 0.573 | 0.474 | 0.486 | **−0.087** [−0.163, −0.012] |
| q5 hi | 0.657 | 0.460 | 0.553 | −0.104 [−0.250, +0.042] |

Monotone, and q3/q4 exclude zero. Note q5: the model was directionally
**right** — realised 0.553 against a market 0.460 — it merely overshot to
0.657. Overconfident about magnitude, not wrong about side.

## ★ The outcome axis has no power here, and that governs the synthesis

Every settlement-based interval spans zero, hugely:

| \|edge\| | net P&L per contract |
|---|---|
| q1 lo | +0.98¢ [−7.05, +9.00] |
| q5 hi | +4.10¢ [−16.83, +25.03] |
| all | +1.17¢ [−8.41, +10.76] |

Brier(model) − Brier(market) = **+0.0048 [−0.0123, +0.0219]**. At 34 games
with a binary outcome, "the model is worst where it acts" **cannot be
established or refuted** on settlement. Drift can be measured to ±0.4¢;
settlement to ±20¢. These are not three comparable confirmations.

And the withdrawn/filled comparison **cannot be made from this table at all**:
`settlement` is populated on 1,944 of 1,944 filled rows and **0 of 1,019
withdrawn** ones. Any such figure comes from an external outcome join, and its
interval needs stating before it enters a synthesis — the filled arm alone is
+1.76pp [−4.18, +7.70], so a 6pp gap on this sample would very likely span
zero.

## Answer

**Two mechanisms, not one, and the third sighting is not yet a measurement.**

1. A **structural execution cost** — resting orders suffer 1.81 half-spreads
   of drift against a mechanical floor of 1.0, at every edge level. Large,
   tightly measured, and the dominant effect.
2. A **model calibration error** that grows with |edge|, significant in the
   middle quintiles, and directionally right at the top.

The apparent "confidence → bad execution" link is mostly (72%) the first
operating through spread selection: more edge → wider markets → more drift.
What is left is real but small, and the outcome-side evidence for the strong
version of the claim is uninformative at this sample size.

**This does not explain why a market-tying model makes no money — it says the
explanation is not on the outcome axis, where we cannot yet see.** The
structural −0.81 half-spreads of excess drift is the one thing here big enough
and well-measured enough to act on.
