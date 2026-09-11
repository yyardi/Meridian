# E4 — for totals, the in-game normal *is* the model

**Same construction as E3, applied to totals:** P(final total > T) for any
half-point rung, one model queried at any T, monotone in T by constraint.
Trained on nflverse (NFL) and CFBD (CFB), held out by game. The baseline is an
in-game normal — final ~ N(current + line·t/T, (σ·√(t/T))²) — with **σ measured
on the training games**, not borrowed: 13.07 for NFL, 16.15 for CFB. Rungs are
scored at offsets from each game's own line, half-point snapped.

## Result: nothing beats the normal, in either league, from either source

| | model vs normal | G / G_eff |
|---|---|---|
| NFL held-out, 163 games | −0.0011 [−0.0046, +0.0025] | 163 / 162.2 |
| CFB held-out, **812 games, 2022–2024** | **−0.0002 [−0.0013, +0.0009]** | 812 / 758.4 |
| CFB 2026 tape, 55 games | −0.0008 [−0.0022, +0.0006] | 55 / 54.5 |

Every individual offset in every table spans zero. Monotone 0/118,000 (NFL),
0/178,000 (CFB). In both leagues **78% of the model's gain sits on
`projected − T`**, which is the normal's own mean — XGBoost learned the
baseline and nothing detectable beyond it.

**ESPN's total probability is no different.** At each CFB game's own line,
9,379 plays matched on play_id:

| | Brier | vs normal |
|---|---|---|
| ESPN `totalOverProb` | 0.1633 | **−0.0081 [−0.0185, +0.0022]** — spans zero |
| in-game normal | 0.1715 | — |
| our model | 0.1720 | +0.0087 vs ESPN, spans zero |

Compare E3: ESPN's *cover* probability beat the same normal by −0.0294,
excluding zero. **Margin carries structure past line+score+clock — who has the
ball, where, key numbers. Total, at this resolution, does not.** The E4 gate
("calibrated to ESPN O/U") is met in the only sense available: we are even
with ESPN because there is nothing to beat.

## The consequence for pricing a total ladder

Use the normal. It is free, it is monotone by construction, and two fitted
models and ESPN's feed all reduce to it. What a total rung needs is the line,
the score, the clock, and a σ measured per league — and the σ is the only
thing worth re-estimating as tape accumulates.

## A defect on the way, since fixed

The first CFB fit trained on **2022 only**: CFBD's quota, exhausted by the
three-season cover fetch earlier that night, returned zero plays for 2023 and
2024, and the fetch loop swallowed it and labelled the artifact 2022–2024. A
check that could not fail. The script now exits naming any empty season; the
quota reset the next day and the refit above is the full three seasons (3,247
train / 812 held-out). The conclusion did not move — σ 16.13 vs 16.15, pooled
difference −0.0002 vs +0.0002 — which is what 261 and 163 games had already said.

Artifacts: `artifacts/nfl_total_regulation.json`, `artifacts/cfb_total_regulation.json`
(+ meta, + caches), both three seasons. Script: `cfb/run_total_fit.py`, `LEAGUE=nfl|cfb`, `SMOKE=1`.
