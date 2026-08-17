# The live win curve, and what it did to hypothesis #16

**Two results, and the second is the interesting one.**

1. **The curve is built.** P(win | margin, minutes left) from 787 completed
   games. Fitted σ = **2.628** points per √minute, against the 2.0 rule of
   thumb — a ratio of **1.31×**. This is the first live model this project
   has had.
2. **Hypothesis #16 PASSED its pre-registered gate and is NOT tradable.**
   +6.84¢, CI [+0.84¢, +12.83¢], 19 games. Anchored on the pregame price the
   same states give **−2.20¢, CI [−3.90¢, −0.49¢]** — the sign flips and the
   interval clears zero on the other side.

Module: [`core/pulse/win_curve.py`](../../core/pulse/win_curve.py) ·
Ledger rows [#15 and #16](../pulse-hypotheses.md)

## Part 1 — the curve

787 completed games with quarter-by-quarter scores, both sides of each game
counted, giving 4,722 team-states. Lead and trail cells are the same games
seen from opposite ends and sum to 1 by construction rather than by luck.

| boundary | bucket | n | P(win) leading | 95% Wilson |
|---|---|---:|---:|---|
| end Q1 | 1–3 | 240 | 0.579 | [0.516, 0.640] |
| end Q1 | 4–6 | 216 | 0.597 | [0.531, 0.660] |
| end Q1 | 7–9 | 121 | 0.669 | [0.582, 0.747] |
| end Q1 | 10+ | 170 | 0.806 | [0.740, 0.858] |
| half | 1–3 | 189 | 0.577 | [0.505, 0.645] |
| half | 4–6 | 157 | 0.631 | [0.553, 0.702] |
| half | 7–9 | 143 | 0.797 | [0.724, 0.855] |
| half | 10+ | 271 | 0.904 | [0.863, 0.934] |
| end Q3 | 1–3 | 157 | 0.624 | [0.546, 0.696] |
| end Q3 | 4–6 | 132 | 0.697 | [0.614, 0.769] |
| end Q3 | 7–9 | 135 | 0.763 | [0.685, 0.827] |
| end Q3 | 10+ | 341 | 0.974 | [0.951, 0.986] |

Trailing cells are `1 − leading`.

### σ, and where the model creaks

$$
P(\text{win}) = \Phi\!\left(\frac{m}{\sigma\sqrt{t}}\right)
\quad\Longrightarrow\quad
\Phi^{-1}(P) = \frac{1}{\sigma}\cdot\frac{m}{\sqrt{t}}
$$

so σ comes from a count-weighted no-intercept regression over 96
(boundary, margin) cells. Weighted because the 10+ cell at end Q3 holds twice
the games that trailing-by-1–3 does, and an unweighted fit would let the
thinnest cells set the slope.

| | |
|---|---|
| fitted σ | **2.628** points per √minute |
| rule of thumb | 2.00 |
| ratio | **1.31×** |
| weighted R² | 0.901 |
| implied full-game margin sd | **16.6 points** over 40 minutes |

**The one-σ model does not quite hold.** Implied σ by boundary:

| boundary | median implied σ |
|---|---|
| end Q1 | 2.98 |
| half | 2.77 |
| end Q3 | **2.40** |

It falls monotonically as the game runs out. A pure random walk would hold one
σ at every horizon; this says late points are worth more than √t predicts —
consistent with games tightening (fouling, clock management) rather than
diffusing freely. **This is why hypothesis #16's gate uses the empirical cells
rather than the fitted curve**: feeding a 10% shape error into the comparison
would charge the market for the model's misfit. The fitted version is reported
alongside and agrees (+6.35¢ vs +6.84¢), so the choice does not carry the
result.

The 2.0 rule of thumb is an NBA number, and the WNBA plays 40 minutes rather
than 48 with a higher per-minute variance. 1.31× is a real difference, not a
rounding: at the half it is the difference between a 4-point lead being worth
0.63 and 0.68.

## Part 1b — per-team lead survival (ledger #15), UNGATED

The origin: *"dallas isnt great at holding onto leads theyve blown so many."*

Against the league curve DAL looks bad, at **−0.067** after shrinkage. That
number is almost entirely an artifact.

The league curve is **team-blind**. A team that wins 74% of its games beats a
50/50-anchored curve in *every* state, leading or trailing, so the column
reproduces the standings and calls it a trait. Anchoring the curve on each
team's own win rate first removes that:

| | widest deviation |
|---|---|
| vs the league curve | **9.0¢** of win probability |
| vs the team's own strength | **2.1¢** |

DAL goes from −0.067 to **−0.012**. MIN from +0.090 to +0.006. Dallas loses
games; there is no measurable tendency to blow leads *specifically*. The
extremes after the control are SEA −0.021 and PHX +0.018, on 300+ states each,
in-sample and therefore biased toward zero already.

**Ledger #15 is answered: the effect is not there at a size worth modelling.**
And the second caution in that row still stands regardless — the market
watches the same games, so even a real trait needs the *price* to be ignorant
of it before it is tradable.

## Part 2 — hypothesis #16

> *"i took IND to win at 30% when they were down just 5 in a tight game...
> cashed at 45."* — 2026-08-06, real money, +50%

### Why only period boundaries

`market_snapshots` carries `event_score` and `event_period` and **no game
clock**. At a general tick, minutes-remaining is unknown and would go straight
into the denominator of the curve. At the instant `event_period` increments it
is exactly 30, 20 or 10. So the comparison lives at those three instants and
nowhere else — which is why the sample is 40 observations across 19 games and
not thousands.

### The gate, and the result

Pre-registered in the ledger row before computing: mean (historical P − market
P) for the trailing team **> 2¢**, 95% CI clustered by game excluding zero,
**≥ 10 games**. Trailing by 1–9 only.

| variant | mean | 95% CI (clustered by game) |
|---|---:|---|
| **empirical cells, 30s median mid** (gated) | **+6.84¢** | **[+0.84, +12.83]** |
| single last tick instead | +6.46¢ | [+0.27, +12.65] |
| fitted curve instead of cells | +6.35¢ | [+0.34, +12.36] |
| **pregame-anchored (confound check)** | **−2.20¢** | **[−3.90, −0.49]** |

n = 40 across 19 games. Mean spread at the boundary 1.08¢.

**PASS on the stated terms. Not tradable.**

### The confound, in one table

The gated number compares a **team-blind** base rate against a **team-aware**
price. So it fires hardest exactly where the market is most right — a heavy
underdog trailing slightly:

| game | pregame price of the trailing team | gated edge | anchored edge |
|---|---:|---:|---:|
| la-min, end Q1, down 1 | 0.085 | **+0.306** | −0.011 |
| tor-gsv, end Q1, down 5 | 0.125 | **+0.298** | −0.015 |
| conn-dal, end Q1, down 6 | 0.175 | **+0.278** | −0.015 |
| tor-gsv, end Q1, down 1 | 0.165 | **+0.236** | −0.004 |

The league curve says a team trailing by 1 at the half wins 42% of the time.
It is averaging over every team that has ever trailed by 1. The market knows
it is Los Angeles, priced at 8.5¢ before tip-off. **The market is right and
the base rate is ignorant, and the gate was measuring the ignorance.**

Buying this "edge" would be selling a correct price to a model that has never
heard of the teams.

### The gate was the wrong question

Recorded as **PASS**, because that is what was pre-registered and retrofitting
a gate after seeing the number is the failure this project is built to avoid.
Recorded as **NOT TRADABLE**, because that is what the number means.

The lesson generalises past this row: **a base rate is only a fair-value
benchmark if it conditions on everything the price conditions on.** Any future
hypothesis of the form "the market disagrees with a historical frequency"
needs the same anchoring check written into its gate *before* it runs.

### What happened to the trade that started it

The originating observation is in the sample:

```
lv-ind-2026-08-06  end Q3  56-51  IND down 5  market 0.315  anchored fair 0.284
```

IND at 31.5% down 5 — the "30%" from the anecdote, recovered independently
from the tick stream. Anchored fair value at that instant was **0.284**, so the
entry was about 3¢ *rich*, not cheap. The trade cashed at 45 and made +50%
because Indiana went on to win. **It was a good outcome from a fairly-priced
bet**, which is the single most expensive thing to mistake for an edge — and
the reason this hypothesis got a pre-registered gate rather than a position.

## Side conventions, verified

`event_score` is `first_team-second_team`, matching the market slug's first
team, and **YES on a winner market = the first team wins**. Checked against all
12 finished games with both a final score and a settled price: **12 of 12**
agree. Recorded as V20 in [findings.md](../findings.md).

This decides the sign of every number above. Getting it backwards inverts the
hypothesis into its own negation with every probability still inside [0, 1] —
the V14/V15 failure mode. Both branches are pinned in
`tests/test_win_curve.py`.

## What is not controlled

- **Injuries, foul trouble, who is actually on the floor.** The curve knows
  none of it; the price knows all of it. The pregame anchor removes the
  season-level part of this and nothing of the in-game part.
- **Three observations per game maximum**, and they are not independent within
  a game — the same lead often persists across two boundaries. Clustering by
  game is what stops that inflating the interval.
- **The anchor is a mid**, so it carries half a spread of noise (measured 1.08¢
  at these instants, which is small relative to the effect).
