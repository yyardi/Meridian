# Conditional move after a drive crosses midfield — pre-registration

**2026-09-14, written before a single outcome is read.** Registers the measurement the
operator's question actually turns on, separately from any trading rule.

## Why this is not the momentum scalp

`cfb/run_momentum_scalp.py` already measures the operator's rule end to end and reports
**mid drift after the trigger ≈ 0 (−0.6 to +0.7¢) in every one of 27 cells**, with the loss
entirely half-spreads (3.8–5.7¢) plus two taker fees (4.1–5.4¢). That is a per-cell **mean**.

**A mean of zero does not settle the question.** A take-profit/stop-loss pair has an
asymmetric payoff, so what it earns depends on the *shape* of the conditional move, not its
first moment. A symmetric thin-tailed move kills every grid corner structurally; a skewed or
fat-tailed one could in principle pay even at zero mean. **Nothing in the project measures
that shape.** This does, with no rule and no fees attached, so the answer survives whether or
not the manager's rule is the right rule.

## The measurement

**Trigger.** Per `drive_id`, the first play with `yards_to_goal < 50` — the offence has
crossed midfield. (The scalp's T1 is `<= 40`; the extra ten yards is reported separately.)
Play filter is the scalp's, verbatim: `down 1..4`, `1 <= ytg <= 99`, `period 1..4`, not OT,
and `play_type` not timeout / kickoff / end-of-period, because those rows carry `ytg = 0`.

**Anchor.** The first winner-market tick strictly after the play's wall clock. The mid at
that tick is `m0`, and the possessing team's side is fixed there: offence away → the YES mid;
offence home → `1 − YES mid`.

**Outcome.** `Δ = m_t − m0` in cents on the possessing team's side, at horizons
**t ∈ {30s, 60s, 120s, 300s, drive end}**, taking the last tick at or before each horizon.

**No fees, no spread, no entry rule.** This is the market's own move, not a P&L.

## ★ The control, which can fail

A drift measured against zero is not evidence on its own: an efficient mid is a martingale, so
*any* conditional set should give zero, and finding zero proves only that the instrument is
not broken. So every horizon also reports:

* **an unconditional baseline** — the same Δ from random in-game ticks matched to the same
  games and horizons, which must also centre on zero;
* **a positive control** — Δ anchored on plays that *score* (a touchdown in the drive), which
  **must** show a large positive move. If it does not, the instrument cannot detect a real
  conditional move and no null from it means anything.

## What is reported

The **distribution**, not only its mean: mean, median, sd, the 10/25/75/90th percentiles, the
share positive, and the mean of the positive and negative halves separately — because an
asymmetric payoff cares about those two numbers and not about their sum.

Clustering is by **game**, `G_eff` on every row. G < 25 is UNDERPOWERED and is kept.

## Declared in advance

**If the conditional move is centred on zero and symmetric at every horizon, no take-profit
and stop-loss pair can rescue the rule**, and that is the answer to the operator in one
sentence rather than 27 cells. **If it is not**, the size and the direction of the asymmetry
say which corner of the grid is worth simulating, and the grid is then worth running.

Either way the trading grid is a second question and this file does not run it.
