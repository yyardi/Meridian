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

---

# ★ CORRECTION: the 39% capture rate was mine and it was wrong

**39% divided a live-model game count by a pregame-model window count.** Two
different models, two different windows:

    predictions (pregame)  2026-07-31 -> 08-31   88 games
    decisions   (live)     2026-08-18 -> 08-31   34 games

Restricting predictions to the live window gives **36 games**, of which 34
produced live decisions: **94% capture, not 39%.** The 54 "lost" games predate
the live model's deployment on 08-18. **Structural for the past and irrelevant
to the future, because it runs now.**

## The funnel, within the live window — nothing else drops

    games with any prediction              36
    games with a live decision             34   (-2)
    games with an ENTER                    34   (-0)
    games surviving the settlement join    34   (-0)
    games with fv + two-sided quote        34   (-0)
    the scored set                         34   (-0)

**Every stage after the first is lossless.** There is no a1-style rescuable
field here: the join, the settlement and the quote all pass 34/34. The only
loss is two games, and the recoverable fraction of the funnel is **zero because
nothing is being lost.**

## Re-dated at 94%

Captured per week: **CFB 54, NFL 14, both 68** (was 22 / 6 / 28).

| target | games | CFB only | both | date (both) | previously said |
|---|---:|---:|---:|---|---|
| Brier 0.010 DETECT | 81 | 1.5 wk | 1.2 wk | **2026-09-14** | 2026-09-27 |
| entered-vs-declined | 70 | 1.3 wk | 1.0 wk | **2026-09-13** | 2026-09-24 |
| lambda* 0.15 DETECT | 282 | 5.2 wk | 4.1 wk | **2026-10-05** | 2026-11-15 |
| lambda* 0.10 DETECT | 635 | 11.8 wk | 9.3 wk | **2026-11-10** | 2027-02-11 |
| lambda* 0.15 ESTIMATE | 1,129 | 21 wk | 16.6 wk | **2026-12-31** | ~2029 |

One-season ceiling: CFB ~754 captured, NFL ~312, combined ~1,065.

## ★ THE RECOMMENDATION REVERSES

I wrote *"do not fund lambda* at estimation precision: it is three seasons."*
**At the corrected capture rate it is 1.1 seasons on both leagues and 1.5 on CFB
alone** — a real commitment, but not the disqualifying one I described. **The
sentence I gave was wrong and it was wrong because of my arithmetic, not because
of the data.**

Corrected: **lambda\* 0.15 DETECT lands in early October and should be funded.
Estimation precision is roughly one-and-a-half CFB seasons — a decision, not a
foregone conclusion.**

## Two caveats that do not move the dates but bound them

* **94% is measured on 36 games.** A small denominator; treat it as ~90%+ rather
  than as 94% exactly.
* **It is a WNBA rate applied to football.** Football has more markets per game
  and a different quote structure, so it is an **upper** estimate until a
  football game is actually captured end to end.
* **The NFL blocker still stands.** Until `nfl_game_map` exists, NFL contributes
  0/week and every "both" column collapses to the CFB column.
