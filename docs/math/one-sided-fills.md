# The circuit breaker we don't have — 2026-09-04

**Operator flagged one trade. It is a specimen of the largest single loss
mechanism we have measured, and the fix is a guard, not a model.**

## The trade

`tsc-cfb-albny-buf-2026-09-03-total-40pt5` — **six fills, all BID, zero ASK**,
settling 0. The mid fell 0.66 → 0.095 across the game as the total went under,
and we bought it the whole way down:

| our bid | mid at quote | mid at fill | rested |
|---:|---:|---:|---:|
| 0.58 | 0.595 | **0.180** | 36s |
| 0.40 | 0.465 | **0.130** | 11s |
| 0.48 | 0.525 | 0.285 | 2s |
| 0.64 | 0.660 | 0.520 | 338s |

**We were not making a market. We were the standing bid in a one-way market.**

## The signal, measured — REAL FILLS ONLY (phantoms excluded)

| our fills in that market | markets | fills | settlement P&L / fill |
|---|---:|---:|---:|
| **≥80% one side** | 39 | 252 | **−10.91¢** |
| 65–80% one side | 75 | 1,407 | **−7.37¢** |
| **balanced (<65%)** | 300 | 11,745 | **−1.68¢** |

**Six and a half times worse when one-sided, monotonic.** It is not a phantom
artifact — the signal is STRONGER with phantoms removed (all-fills reads
−5.54 / −2.23 / −0.14).

**Read the bottom row again: when we genuinely make a market — both sides
filling — we lose 1.68¢. When we are run over, 10.91¢.** Nearly all the damage
lives in 10% of the volume.

## Why this is a guard, not a pricing problem

A maker quoting both sides should fill both sides. **Sustained one-sidedness in
a single market is direct evidence the market is moving through us**, and it is
observable in real time from our own fills — no model, no forecast, no fair
value required. This is the "risk management circuit breaker" the practitioner
sources list as required infrastructure. We have none.

**Proposed, to be pre-registered before it runs:** track the last N fills per
market; if ≥65% land on one side, **stop quoting that side in that market** for
the remainder of the game. Balanced quoting resumes only if the imbalance
decays.

## What it does NOT fix

Balanced markets still lose **−1.68¢**. The circuit breaker removes the tail,
it does not create edge — that is what the favourite–longshot correction is for
(`docs/math/favourite-longshot.md`). **Two separate fixes: this one stops the
bleeding, that one is the edge.**

*In-sample, 88 games, one league. The forward test is the evidence.*
