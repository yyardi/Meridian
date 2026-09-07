# E3 — the spread-rung cover model, and the gate it fails

**One model, P(final home margin > K) for any half-point rung K.** The
greerreNFL construction on CFB: the WP recipe, target swapped to
`cover_result`, one feature added — `spread_line_differential` = current
margin − K — and a monotone constraint in K so the ladder cannot invert.
Trained on CFBD 2022–2024 (3,252 games, 605k plays), tested on 813 held-out
CFBD games and on our own 55 recorded 2026 games. HOME frame throughout.
Every interval game-clustered; G and G_eff printed on every row.

## The gate, and where it splits

| leg | result |
|---|---|
| monotone across rungs | **pass** — 0 / 138,000 violations on 2,000 real states × 69 steps |
| beat or match ESPN spread-cover Brier | **fail** — ESPN 0.1548, model 0.1848; **+0.0300 [+0.0155, +0.0445]**, G=55 |

## Against the principled baseline it wins, everywhere

Baseline is Stern's normal extended in-game — final ~ N(m + E·t/T, (15·√(t/T))²),
E = −spread — i.e. what *line + score + clock* prices a rung at.

| test set | model | normal | diff, game-clustered | rungs won / 12 |
|---|---|---|---|---|
| CFBD held-out, 813 games | 0.0956 | 0.0972 | **−0.0014 [−0.0021, −0.0008]** | 4 (none lost) |
| 2026 tape, 55 games | 0.0710 | 0.0786 | **−0.0076 [−0.0107, −0.0046]** | 10 (none lost) |

Skill vs normal: +1.6% on the big set, +9.7% on the 2026 tape. The 2026
number is larger because that slate was blowout-heavy (favourite won 49/53),
a regime where σ=15 is a poor fit and the trees are not.

**But at the game's own line the model is dead even with the normal**
(0.1848 vs 0.1842). The +9.7% is earned at rungs away from the line, where
both are confident and a small edge accumulates. ESPN beats both at the line
by ~0.03.

## Why ESPN is a real bar here when its WP was not

E2 showed ESPN's *win probability* was line-blind — beating it was line
knowledge. Its *cover probability* is different:

| at the game's own line, 55 games, 9,379 plays matched on play_id | Brier | vs normal |
|---|---|---|
| ESPN `spreadCoverProbHome` | 0.1548 | **−0.0294 [−0.0495, −0.0093]** |
| in-game normal | 0.1842 | — |

Same confidence trajectory as the normal quarter by quarter (Q4: 0.397 vs
0.407) — not more confident, better placed. ESPN carries in-game information
beyond line+score+clock. Its line is DraftKings, the same provider as ours
(19/19 agree where both are on tape), so the comparison is at the same K.

## The one pre-stated retrain, refuted

Hypothesis, written before running: random-K augmentation puts most training
rows at easy rungs far from the line, so capacity goes where the own-line
evaluation is not; drawing 3 of 5 rungs within ±10.5 of the expected margin
should close the ESPN gap.

| | v1 random K | v2 near-line K | v2 + isotonic |
|---|---|---|---|
| CFBD holdout vs normal | −0.0014 | −0.0020 | −0.0021 |
| 2026 tape vs normal | −0.0076 | −0.0083 (12/12 rungs) | −0.0082 |
| **vs ESPN at own line** | **+0.0300** | **+0.0324** | +0.0325 |

Far rungs improved a little; the line did not move. Isotonic calibration on
a game-disjoint fold changed nothing measurable. **Refuted, and stopped —
one retrain was the pre-registered budget.**

What ESPN plausibly has that this does not: the situational features
(`down`, `distance`, `ytg`, possession) carry **<1.5% of gain combined** in
both versions. Whether that is the constraints, the augmentation, or CFB
situational state genuinely mattering little for cover is not resolved here,
and resolving it is more model tuning, which the plan forbids.

## Verified on the way

- **Train/serve spread bridge: 55/55 matched, 54/55 within 0.5pt, max
  difference 1.0, sign 55/55.** Had been left "UNVERIFIED (n=19 < 30)" since
  the WP fit. The first version of this check matched 0/55 because
  `backfill_games.home/away` are ESPN team *ids*, not names — a check that
  could not fire. Names come from `cfb_game_map`.
- Calibration is compressed in the middle (v2: +0.030 at 10–20%, −0.021 at
  70–80%) and isotonic does not fix it, which says the compression is in the
  ranking, not the scale.

## What this is and is not

A model result on held-out games. **Not edge.** Edge on a rung is measured
against that rung's contemporaneous venue price — that is E5, which this
gates. The model is a coherent, monotone ladder pricer that beats
line+score+clock on both test sets and is not ESPN-grade at the line. Whether
that is sufficient for a *tape* test of relative value across rungs (E5), as
opposed to the *live* pricing the gate's wording names, is the operator's
call, not this document's.

Artifacts on prod: `artifacts/cfb_cover_regulation.json` (v1),
`artifacts/cfb_cover_regulation_nearline.json` (v2), `cfbd_cover_cache.json`.
Script: `cfb/run_cover_fit.py` (`K_NEAR_LINE=1` for v2, `SMOKE=1` for a
10-second dry run). Run via the trainer image; see the invocation in the
Saturday runbook's ref table.
