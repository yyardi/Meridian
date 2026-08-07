# Live totals fair value

**Status: built, display only, deliberately ungated.** Its validation is the
user watching it against a real game, not a pre-registered bar.

Module: [`core/live_totals_fv.py`](../../core/live_totals_fv.py) ·
strip on `/picks` · feeds [`core/ev_guard.py`](../../core/ev_guard.py) ·
ledger row [#12](../pulse-hypotheses.md)

## Why totals

The hand-trade audit found exactly one measured-positive pocket in the user's
own trading: **live totals, +9.4% over n=31, descriptive**. What was missing
there was not a button — it was a number to hold a price against. This is that
number, and it closes the coverage gap `ev_guard` used to name outright
("formula FV covers live moneylines only").

## The model

$$
\text{expected}_t = \mu_{\text{pre}}\cdot s(t), \qquad
\text{surprise}_t = S_t - \text{expected}_t
$$
$$
\hat{T} = \mu_{\text{pre}} + b(t)\cdot\text{surprise}_t, \qquad
P(\text{Over }\ell) = 1 - \Phi\!\left(\frac{\ell - \hat{T}}{\sigma(t)}\right)
$$

**Raw pace is never extrapolated.** $S_t \cdot 40/t$ implies a 320-point game
from 12–12 after three minutes. The surprise form moves the projection by a
*fraction* of the divergence and keeps the pregame anchor, so it cannot do
that — pinned by test.

Worked example, a real recorded game (lv-ind 2026-08-06, v4 anchor 197.2):

| at | score | scored | expected | surprise | naive pace | **model** |
|---|---|---:|---:|---:|---:|---:|
| end Q1 | 18–20 | 38 | 50.1 | −12.1 | 152 | **181.3** |
| half | 37–42 | 79 | 99.1 | −20.1 | 158 | **173.0** |
| end Q3 | 56–51 | 107 | 149.2 | −42.2 | 143 | **149.6** |

The model sits between naive pace and the pregame anchor throughout, moving
toward pace as the game banks points. That is the whole behaviour.

## Two numbers in the original design were wrong

Both fitted 2026-08-07 from the same 787 games as
[win-curve.md](win-curve.md), regressing final total on the cumulative total
at each period boundary.

### 1. 1.32 is a Q1 coefficient, not a constant

| boundary | b | |
|---|---:|---|
| end Q1 | **1.318** | reproduces the project's long-standing 1.32 |
| half | **1.208** | |
| end Q3 | **1.128** | |
| full time | 1.000 | forced: every point is banked |

The decay is structural. A point already scored is worth 1.0 on the final by
arithmetic, **plus** whatever it says about the scoring still to come; as the
game runs out that second term goes to zero. Holding 1.32 throughout would
over-weight the surprise by ~9% at the half and ~17% at end-Q3.

That the Q1 fit lands on 1.318 against a number derived independently long ago
is a useful check that this is the same regression, not a new one.

### 2. The win curve's sigmas are MARGIN sigmas and do not transfer

2.98 / 2.77 / 2.40 describe $P(\text{win}\mid\text{margin})$ — the *difference*
between the scores. Totals are a different quantity: the model's pregame total
sigma is ~19 where the full-game margin sd is ~16.6. The totals analogue,
fitted the same way:

| boundary | residual sd of the final total | per √minute-remaining |
|---|---:|---:|
| end Q1 | **15.88** | 2.899 |
| half | **13.03** | 2.914 |
| end Q3 | **9.67** | 3.059 |

**Note the direction.** Per √minute the margin sigma *decays* through the game
(2.98 → 2.40) while the totals sigma is *flat to slightly rising*
(2.90 → 3.06). Borrowing the margin numbers would have understated remaining
totals uncertainty by **~27% at end-Q3** — overconfidence at exactly the point
in a game where someone would act on the number.

So the module uses fitted totals residual sd directly rather than imposing a
√t law on a borrowed constant. The √t column exists only to show it does not
hold.

### 3. Quarter shares are measured, not assumed

Share of regulation scoring: Q1 0.2541, Q2 0.2481, Q3 0.2544, Q4 0.2434 —
near-uniform, so `elapsed/40` would have been defensible. Using the measured
cumulative shares is free and removes a known ~1-point bias at end-Q3.

## The anchor, and a query shape that would have failed at tip-off

$\mu_{\text{pre}}$ is v4's own projected total, recovered by fitting a normal
to the **model's** pregame probability ladder
([`fit_ladder`](../../strategies/wnba_totals/model/curve_fit.py), the method in
[ladder-curve-fit.md](ladder-curve-fit.md)). Fit quality r² = 1.000 on every
game.

**Inverting a single rung does not work**, and was tried first: the recovered
projection drifts **3.99 points across the ladder in every game**, because the
stored probabilities carry v4's post-shrinkage effective sigma (~20.75
measured) rather than the config's 19. Fitting the ladder recovers both
parameters and removes the drift.

**And the anchor query nearly repeated a known bug.** The first version took
`predicted_at = (SELECT max(predicted_at) FROM predictions)` — the same global-
max shape [`core/board.py`](../../core/board.py) exists to kill. It bites
harder here: the prediction logger stops pricing a game once it tips off, so
the game falls out of the newest run and **the anchor would vanish at exactly
the moment the live FV needs it.** Now `DISTINCT ON (market_slug) … ORDER BY
predicted_at DESC` — each market's own most recent prediction. Games with an
anchor went from 6 to 19.

## Frames

**YES = OVER** on a totals market (V14, 490 settled markets). So
$P(\text{Over }\ell)$ *is* the YES-side price and compares to the book with no
conversion. An UNDER position is $1 - \text{FV}$, which is what `ev_guard`
does in the position's own cost frame. Both directions unit-tested.

## Where it refuses to answer

Same discipline as the [moneyline strip](../infra/live-fv-strip.md):

| situation | shows | why |
|---|---|---|
| **overtime** | `—` | A regulation projection cannot price a game still adding points, and the surprise coefficient is defined on regulation scoring. |
| **clock estimate exhausted** | `—` | No game clock is published; a quarter runs 15–20 wall-clock minutes for 10 game-minutes, so the estimate saturates every game. At $t=0$ the formula becomes a step function and prints certainty where the estimate is worst. |
| **no v4 pregame ladder** | `—` | Without an anchor the only alternative is a league-average total, which is a wrong assumption rather than a neutral one. |

## What it is not

**No gate, no threshold, no pre-registered bar** — this is an input/display
build. Adding one later would be a guess about a number nobody has watched
yet. The strip carries `formula FV — unvalidated, display only`, has no click
handler, no ticket, and no import of the executor.

Its validation is the user eyeballing it against a live game. If it is
obviously wrong on the floor, that is the signal — and it is a cheaper signal
than any backtest of a display.
