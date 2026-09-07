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
| CFB held-out, 261 games (**2022 only**, see below) | +0.0002 [−0.0026, +0.0031] | 261 / 239.1 |
| CFB 2026 tape, 55 games | +0.0000 [−0.0022, +0.0023] | 55 / 54.5 |

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

## Defect on the way, and it is mine

The CFB fit is **2022 only.** CFBD returned zero plays for 2023 and zero games
for 2024 — quota exhausted after the three-season cover fetch earlier the same
night — and the fetch loop swallowed it and labelled the artifact 2022–2024.
A check that could not fail. The script now exits naming the empty season; the
artifact's meta on prod is corrected to `[2022]` with a note. Refit when quota
resets; the conclusion is not expected to move, since 261 CFB and 163 NFL
held-out games already agree.

Artifacts: `artifacts/nfl_total_regulation.json`, `artifacts/cfb_total_regulation.json`
(+ meta, + caches). Script: `cfb/run_total_fit.py`, `LEAGUE=nfl|cfb`, `SMOKE=1`.
