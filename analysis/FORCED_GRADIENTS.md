# Forced gradients on this substrate — a standing note

**Five instruments in one day reproduced their own algebra and were read as
findings.** Two were published before being caught. This note exists so the
sixth is caught by a check rather than by a peer.

## The property

> **On this substrate, any statistic cut by a variable X, over a population
> selected by an X-dependent rule, is guilty until proven innocent — and the
> burden of proof is a geometry-only null.**

The general form is C's, and the generality is the point. Written narrowly as
*"cut by spread"*, someone cuts by quote-age over a population selected by a
quote-age-dependent rule, sees no mention of spread, and ships it. **The check
must fire on the shape, not on the variable.**

Spread is simply the X that keeps recurring here, and it recurs for a structural
reason: **both of this substrate's selection mechanisms are spread-dependent** —
the classification rule (`real ⟺ excess ≥ s/2`) and the quoting gate
(`MAX_SPREAD = 0.15`). Any X sharing that property will behave the same way.

**Crucially, the statistic being algebraically clean of X is not a defence.**
Composition failed on the *statistic* (s on both sides). Drift *passes* on the
statistic — the quote price cancels, no s anywhere — and fails on the
*selection*. Clean algebra plus dirty selection is still forced.

## The five, 2026-09-04

| # | statistic | how it was forced | caught by |
|---|---|---|---|
| 1 | **capture vs mid** | `capture ≡ −overshoot`; corr +1.0000, residual 0.0000¢ | D (2026-09-03) |
| 2 | **width settlement gradient** | spread on both sides of the identity, so the gradient could not fail | D |
| 3 | **real-share composition by width** | `real ⟺ excess ≥ s/2`; a geometry-only null reproduces the monotone decline on both boards | B |
| 4 | **WIDTH cut's phantom-share column** | same rule; band variable IS the threshold variable | C, in their own shipped artifact |
| 5 | **phantom drift by width** | statistic clean of s, but a wider market *requires* a larger excursion to produce a phantom; excursion grows 3.6×, drift 3.5×, ratio flat at ~0.5 (corr 0.973) | flagged by MGR, null built by B |

## The tells

**A pair, and it is the pair that discriminates:**

1. **Confidence intervals an order of magnitude too tight** for a noisy economic
   quantity, and
2. **suspiciously clean monotonicity.**

The canonical demonstration, on *identical fills*: capture ran monotonic with
~0.3¢ CIs while settlement ran non-monotonic with ~8¢ CIs. One of those is a
measurement.

A third tell, from #3: **a degenerate cell that nobody would defend.** The ≤1¢
band read 99–100% real, because the bar is 0.5¢ and a 1¢ tick almost always
clears it. Nobody would read that as informed flow avoiding tight markets — and
the same algebra produced every other cell in the column.

## The principle, which is already in the record

> **A result that replicates because it CANNOT FAIL is not a replication.**

And its counterpart, from the asymmetry ruling in
`docs/math/adverse-selection-measured.md` — these look identical and are
opposites:

* The **phantom rate** replicating across sports (63.9% WNBA / 65.0% CFB)
  **confirms**: it is a property of the simulator, and stability across boards
  is exactly what the mechanism predicts.
* The **phantom gradient in spread** replicating across sports **confirms
  nothing**: one fill rule, two boards, same algebra.

Same word, opposite epistemic status. **Ask which one you have before quoting a
replication.**

## What to do about it

1. Before cutting a statistic by X, ask whether the population was selected by a
   rule involving X. If yes, build the geometry-only null **first** — hold the
   distribution fixed, move only the threshold, and see whether the gradient
   falls out.
2. If you cannot build the null, **say so in the printed output**, not in a
   message. A caveat in prose is a promise to remember; a caveat the artifact
   prints is a caveat that travels.
3. A statistic that is algebraically clean of X still needs step 1.

## Still open

The **h=0 decomposition** in `docs/math/markout-measured.md` shows 54% of the
phantom/real markout gap is the classification criterion restating itself.
Markout is now the low-variance metric, so someone will reach for that gap
precisely because its intervals are tight. **That is the sixth instance waiting
to happen.**
