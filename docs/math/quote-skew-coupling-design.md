# Design — coupling PULSE's fair value into QUOTE's quote placement

**Status:** DESIGN, nothing built, nothing run on real data. Written
2026-09-04 by Quant D at the manager's request.

**The idea (operator's):** QUOTE currently quotes around the mid. A maker with
an alpha signal quotes around its own fair value, so it is *paid* to accumulate
the position it wanted, instead of crossing the spread to get it.

---

## 1. The skew rule

Let `m` be the mid, `s` the spread, `fv` PULSE's fair value. Define a
**reference price**

    r(λ) = m + λ·(fv − m),        λ ∈ [0, 1]

and quote `bid = r − h`, `ask = r + h` for half-width `h`.

- `λ = 0` is today's QUOTE (quote the mid).
- `λ = 1` is a pure fair-value quoter.
- `λ` is exactly **how much you trust `fv` relative to the market**.

### What sets λ

If both estimates are unbiased for the true value `v`, with `m = v + η` and
`fv = v + ε`, the reference minimising `E[(r − v)²]` is the inverse-variance
blend:

    λ* = σ_η² / (σ_η² + σ_ε²)

Verified by simulation: fitted λ recovers theory to 3 decimals across
signal-to-noise regimes. **λ\* is estimable from C's data without any fill
model** — regress the outcome jointly on `m` and `fv` over the 88 games, fit
out-of-sample, cluster by game. The parameter is a measurement, not a choice.

### The clamp, and why it matters more on football

Post-only is physics (the FLATTEN lesson): a maker's ask cannot rest at or
below the bid. So the **effective** skew is

    skew_eff = clamp( λ·(fv − m),  −(s/2 − tick),  +(s/2 − tick) )

**In a tight market the skew is inert.** At WNBA's median 4¢ spread the whole
usable range is ±1¢; at CFB's median 11¢ it is ±4.5¢. This is the same
structure as FLATTEN's k, where every k ≥ 1¢ was the same quote in a 2¢
market — and it means **the coupling has roughly 4× more room on football than
on basketball**, which is the opposite of where the fair-value model exists.

## 2. ★ What it costs when the signal is wrong — and the optimum is NOT λ\*

Two separate penalties, and only the first is obvious.

**Penalty A — reference error.** `r − v = (1−λ)η + λε`, so

    MSE(λ) = (1−λ)²σ_η² + λ²σ_ε²

quadratic, minimised at λ\*, and **equal to the no-skew baseline at exactly
2λ\***. Skewing is worse than not skewing once `λ > 2λ*`. That is the analytic
form of FLATTEN's k-curve.

**Penalty B — the fill rate moves with the skew, and it is the dangerous one.**
Skewing the reference up raises the bid, so we get *more* fills on the side we
are leaning toward. When the signal is wrong we therefore buy **more** of it,
**at a worse price**. Volume and error are positively coupled.

Simulated with σ_ε = 0.04, σ_η = 0.03 (λ\* = 0.360), fill intensity rising
linearly with the lean:

    λ       ref MSE   vs no-skew    P&L/fill   rel fills   P&L per unit time
    0.000   0.00090       1.000x      1.993c       1.000        1.993c
    0.200   0.00064       0.713x      2.379c       1.004        2.389c   <- P&L optimum
    0.360   0.00058       0.642x      1.989c       1.059        2.107c   <- λ*, MSE optimum
    0.500   0.00063       0.698x      1.388c       1.148        1.594c
    0.720   0.00090       1.004x      0.248c       1.324        0.328c   <- 2λ*
    0.900   0.00131       1.454x     -0.766c       1.482       -1.135c
    1.000   0.00160       1.782x     -1.346c       1.573       -2.117c

**The trading optimum sits strictly BELOW the estimation optimum.** At λ\*
itself, P&L is already past its peak. At 2λ\* the MSE says "break even" while
P&L has lost 84% of its value.

> **The estimator-optimal blend is not the trading-optimal skew. Fit λ\*, then
> quote below it.**

The size of the gap depends on how fill intensity responds to the lean, which
is **unmeasured** — my linear stand-in fixes the direction, not the magnitude.
That response is exactly what the resting-order probe's Leg B would measure, so
the two pieces of work compose.

**Consequence: err low.** Under-skewing forfeits edge linearly; over-skewing
loses on price *and* volume simultaneously.

## 3. Is it measurable in shadow mode? No — not on the existing tape

A skewed quoter posts at a **different price**, so it is a different quote path
and cannot be recovered from a tape where we never quoted there. Worse, the
scoring would inherit the defect established today:

- the shadow fill rule books only `mid ≤ B`, so it can represent only fills
  where the market came to us, and **capture ≤ 0 on every row by construction**;
- the profitable maker case — a seller crossing the spread to a resting bid
  while the ask stays above — produces no row at all;
- our own order is absent from the recorded book, so the counterfactual book is
  not the observed one.

A replay *would produce a number*. Today established that the number would be
about the fill rule, not the strategy — and skewing changes precisely the
quantity (`B` relative to the touch) that the fill rule mis-handles. **So a
replay is not merely noisy here, it is measuring the wrong thing in the
direction of the parameter under test.**

**Verdict: this needs a live arm, or the fill model repaired first.** The
resting-order probe is the repair, which makes it a prerequisite rather than a
parallel effort.

## 4. ★ The gate — and the proposed gate is the wrong test

The assignment states the idea is worth nothing if the Brier test says the
model does not beat the market. **That is too strong, and simulation shows it
is false.**

    σ_model   σ_mid    λ*      MSE mid   MSE model   MSE blend
      0.03     0.03   0.500    0.00090     0.00090     0.00045
      0.05     0.03   0.265    0.00090     0.00250     0.00066   <- model LOSES to the
                                                                    market and the blend
                                                                    still beats both
      0.02     0.03   0.692    0.00091     0.00040     0.00028

A model with **2.8× the market's error variance** — one that would lose a Brier
comparison decisively — still carries λ\* = 0.265 and improves the reference
price by 27%. Forecast combination needs *independent information*, not
*superior information*.

**The correct gate is incremental, not comparative:**

> Does `fv` add information **given** `m`? Equivalently, is λ\* significantly
> greater than zero in a joint out-of-sample fit, game-clustered?

C's Brier test answers a different question. It is still worth having — a model
that beats the market is a stronger position — but **a Brier loss does not kill
this design, and reporting it as the gate would discard a live option on a
technicality.** The joint regression that estimates λ\* *is* the right gate, and
it is the same computation, on the same 88 games, with no fill model in it.

## 5. League- and venue-agnosticism

The skew rule needs only `(fv, m, s)` and a tick size. **Nothing in it is
sport-specific** — the league-specific object is the fair-value model itself.
So the coupling ports wherever a fair value exists, and needs no rewriting when
basketball returns or football gains a model.

Same for venue: the rule assumes a two-sided book with a tick and post-only
semantics, which is not Polymarket-specific. It should be written against
`(fv, m, s, tick)` and not against any venue's market structure.

## 6. Dependency order

    1. λ* estimable        <- C's joint fit on 88 games; gates the whole design
    2. fill model trusted  <- the resting-order probe; gates MEASURABILITY
    3. λ_trade < λ*        <- needs Leg B's fill-intensity response to size the gap
    4. live arm or replay  <- decided by (2)

Steps 1 and 2 are already commissioned for other reasons. **This design adds no
new data requirement**, which is its strongest property: it is a question that
the work already queued would answer as a by-product.

---

No in-sample result justifies capital. The forward test is the evidence.
