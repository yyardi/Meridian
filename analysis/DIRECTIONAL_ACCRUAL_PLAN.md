# Directional thesis: games required, sources, dates

Every figure scales from a **measured** half-width at G=34, not an assumption.
Half-width goes as 1/sqrt(G), so `G_needed = 34 x (hw_measured / hw_target)^2`.

Measured anchors (entered branch, game-clustered, this substrate):

    lambda*                 half-width 0.4321   G=34
    Brier difference        half-width 0.0154   G=34
    entered-vs-hold split   half-width 0.0146   G=33  (paired per game)

## 1. GAMES REQUIRED

**DETECT** = interval excludes zero if the effect is that size.
**ESTIMATE** = interval half-width is half the effect, so the size is known and
not merely present.

| question | target | DETECT | ESTIMATE |
|---|---:|---:|---:|
| Brier difference 0.010 | 0.010 | **81** | 322 |
| entered-vs-declined 0.010 | 0.010 | **70** | 281 |
| lambda* = 0.15 | 0.150 | **282** | 1,129 |
| lambda* = 0.10 | 0.100 | **635** | 2,539 |
| Brier difference 0.005 | 0.005 | 322 | 1,290 |

## 2. SOURCES AND RATES

WNBA is finished — season ended 2026-08-31, 88 games, of which **34 produced
usable decisions: a 39% capture rate.** That rate is the planning input, not the
schedule of games played.

| league | games/season | weeks | games/week | **captured/week at 39%** |
|---|---:|---:|---:|---:|
| CFB | ~800 + bowls | ~14 | ~57 | **~22** |
| NFL | 272 + 13 playoff | ~22 | ~15 | **~6** |
| both | | | | **~28** |

## 3. HOW LONG, AND THE DATE

From 2026-09-06, assuming the football pipeline is fixed and capture holds at
39%:

| target | games | CFB only | both leagues | date (both) |
|---|---:|---|---|---|
| Brier 0.010 DETECT | 81 | 3.7 wk | **2.9 wk** | ~2026-09-27 |
| entered-vs-declined | 70 | 3.2 wk | **2.5 wk** | ~2026-09-24 |
| lambda* 0.15 DETECT | 282 | 13 wk | **10 wk** | ~2026-11-15 |
| lambda* 0.15 ESTIMATE | 1,129 | — | **~2.7 seasons** | 2029 |
| lambda* 0.10 DETECT | 635 | — | **~1.5 seasons** | late 2027 |

**The split in this table is the decision.** The Brier questions resolve inside
a month. **lambda* at estimation precision is a three-season commitment**, and
CFB alone cannot reach it in one season because the season is only ~14 weeks.

## 4. WHAT MUST BE TRUE FIRST

**The counter does not start today. It cannot start at all right now.**

* **NFL games cannot be mapped.** All 32 NFL rows carry NULL start times, no
  ESPN id and no venue slug, and no `nfl_game_map` exists. We are recording
  **3,042 NFL markets** on the venue tape with nothing to attach them to. Until
  a mapping table exists, NFL contributes **0 games/week**, not 6 — and the
  "both leagues" column above collapses to the CFB column.
* **PULSE has never made a football prediction.** Its live features are
  basketball-shaped and three of them have no football analogue.

### Spec for a football live model — what is missing, not a fit

The current live feature set is `score, margin, period, minutes_left,
total_so_far, projected_total, total_sigma`. Football needs, and does not have:

1. **Possession.** First-order in football and absent entirely. Down three with
   the ball at 2:00 is a different state from down three without it; basketball
   has no equivalent because possessions alternate quickly.
2. **Down and distance.** No basketball analogue. 4th-and-1 and 4th-and-15 at
   the same clock and margin are different distributions.
3. **Field position.** No analogue.
4. **Lumpy scoring.** Football scores in 3/6/7/8; basketball is near-continuous
   in 2/3. **A Normal `total_sigma` is worse-specified on football**, especially
   late, when the remaining distribution is a small number of discrete outcomes.
5. **`total_sigma` cannot keep tracking the clock the same way.** It currently
   correlates +0.967 with `minutes_left`. Football's residual variance does not
   decay smoothly with the clock — it **steps down at possession changes** and
   barely moves during a kneel-down. A clock-linear sigma will be badly wrong in
   exactly the late-game states where the money is.

**Items 1-3 are data the recorder does not currently capture.** ESPN's summary
endpoint carries all three, and the programme already reads that endpoint for
other purposes.

## 5. THE RECOMMENDATION IN ONE LINE

**Fund the Brier questions — they resolve by late September for the cost of a
mapping table. Do not fund lambda* at estimation precision: it is three seasons,
and nothing about the current model justifies a three-season commitment.**
