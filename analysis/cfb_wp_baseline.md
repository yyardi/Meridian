# CFB win-probability baseline: plays only, benchmarked against ESPN

**The first football model in this programme that fits and scores end to end.**
No market feature yet — this is the state half, built to establish a baseline
before the price feature is added.

## Why it was buildable when nothing else was

`espn_cfb_live_plays` and `espn_cfb_game_state` are **both ESPN-keyed**, so they
join directly: **49 of 50 games, no `cfb_game_map` involved.** Every blocker
today has been the venue↔ESPN bridge or the venue tape's cadence; neither
touches an ESPN-only model.

## Data

    plays        8,634 rows, 50 games, features 100% non-null
    outcome      home win, from the last `post` state row
    cohort       4,828 play-rows across 28 settled games

Joined on **`wall_clock`, not `first_seen_at`** — the recorder backfilled to
19:30Z from a 22:08Z start, median lag 1 min and **max 159 min**, so
`first_seen_at` would misdate every backfilled play and silently truncate two
hours.

Features, all knowable at the play: `reg_left`, `period`, `down`, `distance`,
`yards_to_goal`, `home_has_ball`, `home_score_diff`. Held out **by game**
(GroupKFold, 5 folds) — the outcome is one draw per game, so a row split is
pure leakage.

## ★ RESULT: THE MODEL DOES NOT BEAT ESPN

    Brier model   0.08061
    Brier ESPN    0.06942
    difference   -0.01119  [-0.04316, +0.02077]   G=28   INDISTINGUISHABLE

Against ESPN's own `espn_home_win_pct`, on ESPN's own data, joined on **game
clock** rather than wall time. ce set this test as *"if you cannot beat ESPN's
public number on ESPN's own data, that is the result"* — **the point estimate
favours ESPN and the interval spans zero, so the honest statement is a tie with
ESPN ahead on the point.**

## The echo check, and it passes for a real reason

    corr(model, espn) = +0.728    mean |model − espn| = 0.1272

**ESPN's WP was never a feature**, so the agreement comes from shared game
state rather than from echoing an input. This is the MID_ECHO analogue and it
is the check I most wanted on my own model.

## ★ WHAT THIS COHORT CANNOT SUPPORT

**Home teams won 89.3% of these 28 games.** A base-rate-only model scores
0.10538 against the fitted 0.07443, so **most of the apparent skill is
available from knowing the base rate**, and the cohort is far too lopsided to
generalise. 28 games with one outcome draw each is a small sample by any
measure and the interval above says so.

## What comes next, and what it will and will not answer

d5 is right that the market can enter as a **feature** with settlement as the
target — nflfastR's own `spread_line` is a per-game constant and `vegas_wp` is
built from a pregame spread. My objection applied to scoring model-Brier
*against* a frozen mid, which is empty; it does not apply to a frozen line as
an input.

So the next fit adds the pregame anchor and asks whether it improves on the
baseline above, **scored against settlement**. Two things it will not answer:

* **whether live price MOVEMENT helps** — that needs a tape that moves, and
  09-05's did not (0.1% of markets moved in the dense hour);
* **whether any of it is tradeable** — a frozen quote is not necessarily a
  transactable one, and A's bar is per-traded-market edge over τ ≈ 2.0–2.5pp,
  not population Brier.

---

# ★ THE PREGAME ANCHOR: ce's channel is real, and one parameter beats seven features

## ce's diagnosis verified on my own cohort

    ESPN first in-game WP, 23 kickoff-observed games
      mean 0.5935   sd 0.0176   range 0.572 .. 0.623
      games with a strong prior (>0.80 or <0.20):  0 of 23

**ESPN opens every CFB game between 0.57 and 0.62.** That is home-field
advantage and nothing else. So my −0.01119 tie was against an opponent carrying
no pregame information, and "we tie ESPN" reads very differently once that is
known.

## ★ THE ANCHOR WAS THE FEATURE I THREW AWAY

`live_spread` is **constant within a game in 46 of 50** — which is exactly why I
removed it from the feature list this afternoon, and exactly what makes it a
**pregame anchor**. nflfastR's `spread_line` is a per-game constant by design.

**And it needs no map** — it is already in the ESPN-keyed state table.

    live_spread present on 50 of 50 games
    sd 15.62 points, |spread| > 10 on 84% of games
    implied P(home) sd 0.1879 against ESPN's 0.0176  ->  10.7x dispersion

## RESULT — play-level Brier, out-of-fold, held out by game (n 3,642, G 28)

**★ POPULATION, added 2026-09-06 after this table was quoted elsewhere without
one.** These rows are the 28-game fit set joined to ESPN state on game clock with
`merge_asof(direction="nearest", tolerance=30s)`. That join is **not** the one
used by `analysis/c7_identity_test.py`, which is `direction="forward"` — nearest
can match a state up to 30s in the FUTURE. Do not stack this table against that
one; different population (n 3,642 vs 14,458), different cohort predicate, and
`down`/`distance` exist here and not there.

    game state only  (7 features)        0.08061   reproduced exactly 2026-09-06
    anchor only      (1 parameter)       0.07413   <- WITHDRAWN, see below
    state + constrained anchor           0.10443
    ESPN                                 0.06942   reproduced exactly 2026-09-06

    vs ESPN:  state only    -0.01119 [-0.04316, +0.02077]  tie
              anchor only   -0.00472 [-0.06355, +0.05412]  tie
              state+anchor  -0.03502 [-0.15963, +0.08959]  tie

**★ THE 0.07413 ROW IS WITHDRAWN.** Re-running on the identical population
(nearest/30s, n 3,642, G 28 — confirmed by `p_base` and `ESPN` reproducing to
five decimals) a game-level out-of-fold logistic on `live_spread` gives
**0.05609**, not 0.07413. I cannot identify what construction produced 0.07413
and it should not be quoted. The claim it supported — that one pregame parameter
beats seven game-state features — **survives and strengthens** under every
construction tried (0.05609 nearest/30s, 0.06371 forward/60s, both below the
0.08061 state-only row), so the finding stands and only the figure is bad.

**A single logistic parameter on the pregame spread, using no in-game state at
all, beats a seven-feature model of down, distance, field position, clock and
score.** That is the strongest evidence for ce's missing-channel argument, and
it comes from a feature already in hand.

## ★ AND THE COMBINATION FAILS FOR A REASON THAT IS NOT INFORMATION

    in-sample / out-of-fold Brier
      game state only    0.03239 / 0.07443   gap +0.04204
      with anchor        0.00307 / 0.10940   gap +0.10632   <- 2.5x

**The anchor has 22 distinct values across 28 outcome draws — a near-unique game
key.** A flexible model fits 22 game-level points almost perfectly (in-sample
0.00307) and does not generalise to the 6 held out. GroupKFold reveals it; it
does not prevent it.

**So the joint fit is a G problem, not an information problem.** Constrained to
one parameter the anchor helps; given to a GBM it memorises. **The fix is
constraint or more games, not a better feature.**

## What this changes about the earlier negative

The five negative subsets and the pooled tie stand **as claims about game state
alone**, which is the narrower and more useful reading. **They were never
evidence that no edge exists** — they are evidence that none is reachable from
the in-game features we have, on 28 games, against an opponent that also lacks
the prior.
