# PULSE reversion shrink — a calibration arm, NOT a signal (registration)

**Status: REGISTERED, NOTHING BUILT.** Written 2026-08-24, before
implementation. Floors gate on games recorded after this timestamp. This
section may not be edited after the eval first runs at floor — append below
the line.

## What this is, and emphatically what it is not

The research agent measured (797 games 2024–26, mutation-tested estimator,
relayed by manager dispatch 2026-08-24): live margin deviations from the
prorated closing spread revert 15–17% by final — pooled beta −0.171
[−0.226, −0.116], not garbage-time, uniform across composition and recency.
Per-phase at the exact boundaries: Q1 −0.28 per point of deviation, half
−0.157, Q3 −0.137.

The same agent then REGISTERED AND FAILED the signal version (#18): the
reversion carries no residual information beyond the live winner mid
(c = +0.054, CI spans zero; the mid's own coefficient 0.881). **The market
already prices this reversion. Therefore this arm claims NO edge, and its
gate is forbidden from being read as one.**

## The testable benefit, distinct from "matches the market better"

The manager's challenge, answered directly: the gate is **calibration
against OUTCOMES, not against the price**. The paired Brier criterion this
family already uses scores P(win)/P(cover) against actual settlement — a
market-independent target. The reversion regression is a regression on
FINALS, so it predicts, falsifiably: shrinking the margin deviation by the
measured phase betas improves the model's own Brier against outcomes. If
the improvement only exists relative to the market and not against
outcomes, the gate reads FAIL and the arm dies — which is exactly the
distinction demanded.

**Predicted side effect, registered up front**: better calibration moves FV
toward the market, so the shrunk arm should take FEWER entries. Reduced
activity is an expected consequence, not a failure mode; the trading clause
(money-at-price not measurably worse, paired) still applies and catches any
harm.

## The rule — external constants, none fit here

Expected final margin in the winner/spread model becomes:

    deviation      = margin − E · (elapsed / 40)
    expected_final = margin + E · (t_left / 40) − s(elapsed) · deviation

with `s(elapsed)` piecewise-linear through the MEASURED boundary points
(10′, 0.28), (20′, 0.157), (30′, 0.137), the forced endpoint (40′, 0)
(banked points cannot revert), and held at 0.28 below 10′ (deviations are
small there regardless). The constants are the research agent's
measurements, adopted verbatim — nothing is fit in this registration.
Totals are untouched. The correction is state-based (F8's 36.7s feed-lag
finding is irrelevant to it by construction).

## Gate

Eval arm = the incumbent estimates + this shrink, vs the incumbent, on the
registered criterion family: paired Brier (incumbent − shrunk) clustered by
game, 95% CI excluding zero in the shrunk arm's favour at floor, AND paired
money-at-price not measurably worse. **Floors: ≥ 10 signal-covered games
first recorded after this registration AND ≥ 3,000 paired points.** Adopted
into live estimates only on PASS, as its own dated regime change.

---

*Registered 2026-08-24. Results append below this line, never above it.*

## 2026-08-26 — correction: the registration's true instant

The header's "Written 2026-08-24" was a conversation-date drift by the
author: this document's first commit is c375aab,
**2026-08-25T23:08:20Z**, merged at 23:09Z the same night. The gate
therefore counts games first recorded after 2026-08-25T23:08:20Z — the
2026-08-25 00:00–04:15Z slate was recorded before this registration
existed and is backtest, never gate. Corrected before the eval arm was
built or any number read, so no result is touched.
