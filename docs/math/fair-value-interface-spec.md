# Specification — what any fair-value model must expose

**Status:** SPEC, written 2026-09-04 by Quant D. Deliberately written against a
model that **does not exist yet**, so the rebuild has somewhere to land and
NBA/CFB/NFL become three fits rather than three ports.

**Why now:** v4's directional signal is dead where it acts (Brier +0.0192
[+0.0047, +0.0337] worse than the market on >5c disagreements, λ\* = −0.16
[−0.65, +0.34]). Enumerating what is league-specific *in v4* is archaeology.
The forward question is what any successor must expose.

---

## 1. Derived by working backwards from the consumers

| consumer | what it needs |
|---|---|
| QUOTE skew `r(λ) = m + λ(fv − m)` | `fv` on the same scale as `m`; `λ`, which needs the model's own error size |
| PULSE entry | `fv`, plus a threshold; the threshold is a policy constant, not a model output |
| Kelly sizing | a probability and the payoff; for a binary these are `fv` and the price |
| FLATTEN / inventory | nothing from the model |

`m`, `s` and `tick` come from the **venue**, not the model. So the model side
of the interface is small — which is the hint worth following rather than
resisting.

## 2. The interface

    estimate(market, game_state) -> {
        fv       : float in [0,1]   price for THIS contract, same scale as the mid
        sigma    : float > 0        the model's own ESTIMATION error sd on fv
        as_of    : timestamp        the game-state instant fv is conditioned on
        valid    : bool + reason    the model may decline to answer
    }

Four fields. Nothing sport-specific appears, and nothing venue-specific.

### 2.1 `fv` is PER CONTRACT, not per game

A ladder prices many rungs on one underlying. The model must price **each
rung**, so the unit of the interface is the market, not the game. A model that
emits "the home team wins with probability p" does not satisfy this interface;
it has to be turned into a price for every listed line.

### 2.2 ★ It should be DERIVED FROM A DISTRIBUTION, not emitted per rung

Strongly recommended, and it is the difference between an interface that
composes and one that needs guarding:

    model exposes  F(x) = P(underlying > x)      then   fv(line) = F(line)

Three properties fall out for free:

- **Ladder coherence is automatic.** Independently-priced rungs can violate
  monotonicity — `P(total > 160) < P(total > 165)` — which is an arbitrage the
  engines would trade into. This programme has already recorded one such
  episode. A distribution cannot produce it.
- **New lines cost nothing.** A rung listed mid-game is priced without refitting.
- **`sigma` has a natural source** — the uncertainty in the distribution's own
  parameters, propagated to each rung, rather than a number invented per market.

If a model cannot expose a distribution, it must expose per-rung `fv` **plus a
monotonicity guarantee**, and the guarantee has to be tested rather than
asserted.

## 3. ★ `sigma` is the field models usually omit, and it is worth 42%

`sigma` is **not** the outcome variance. For a binary the outcome variance is
`fv(1−fv)` and is already known from `fv`. `sigma` is the model's uncertainty
about **its own estimate** — how wrong `fv` itself might be.

It is what sets the skew, per observation:

    λ(σ) = σ_market² / (σ_market² + σ²)

**It must be per-observation, not a constant.** A model is sharper on a rung
far from the money late in a game than on one near the money early, and
exposing that is worth a great deal. Simulated with a model whose error is
0.015 / 0.03 / 0.08 depending on the situation, against a constant market error
of 0.03:

    mid only                         MSE 0.000900
    GLOBAL λ  (sigma hidden)         MSE 0.000814
    PER-OBS λ (sigma exposed)        MSE 0.000473
    => exposing per-observation sigma buys 42% of the remaining error

**A single global λ throws most of the available gain away.** And the skew then
shrinks automatically when the model is unsure, with no extra machinery.

### 3.1 The `sigma` claim must be validated, and understatement is worse

A misstated `sigma` corrupts λ directly:

    model OVERSTATES sigma by 2x    MSE +22.6% vs honest
    model UNDERSTATES sigma by 2x   MSE +42.1% vs honest

**Understating — claiming more certainty than you have — costs roughly twice as
much as overstating.** So the interface's guidance is to err toward humility,
and the claim must be tested rather than trusted:

> **Second-moment calibration.** Standardised residuals `(fv − outcome)/sigma`
> must have unit variance, checked out-of-sample and clustered by game. A model
> whose `fv` is well calibrated and whose `sigma` is not will still size the
> skew wrongly.

Nobody runs this test. First-moment calibration (is `fv` right on average) is
routine; second-moment calibration (is `sigma` right) is the one that decides
how much we act on it.

## 4. `σ_market` is NOT a model output

`λ` needs the market's error variance too, and that is **fitted from data per
league and regime** — how well the mid predicts settlement — not supplied by
the model. It belongs to the coupling's configuration, not to this interface.
Stated explicitly because it is the obvious thing to mistakenly demand of a
model that cannot know it.

## 5. What must NOT appear in the interface

No pace, no possession count, no shot clock, no period structure, no scoring
granularity, no sport identifier. **Those are how a model computes `fv`, not
what it exposes.** The moment one of them appears in the interface, the
consumers become sport-aware and the port stops being a fit.

Same for the venue: the interface must not name Polymarket's market structure.
Consumers take `(m, s, tick)` from wherever the book comes from.

## 6. `valid` — the model must be able to decline

An estimate before enough game state, or in a regime the model was not fit for,
is worse than no estimate: it enters the skew at full weight unless `sigma`
happens to be honest about it. An explicit abstention is cheaper than trusting
`sigma` to encode ignorance.

This is also the field PULSE's existing tape lacks the analogue of — `edge_net`
is recorded only when it acted, so declines are invisible. **Whatever consumes
this interface must record the estimate on declines too**, or it will inherit
the same unmeasurable-threshold defect.

## 7. What the spec buys

    three leagues x (fit a distribution + calibrate sigma) = three FITS
    versus
    three leagues x (port the decision path)               = three PORTS

The consumers — skew, entry, sizing — are written once against four fields. A
new league adds a fitted distribution and nothing else. A new venue adds a book
adapter and nothing else.

**And it is testable before any model exists**: the second-moment calibration
test, the monotonicity guarantee, and the decline-recording requirement can all
be written as acceptance criteria now, so the rebuild is measured against them
rather than after them.

---

No in-sample result justifies capital. The forward test is the evidence.
