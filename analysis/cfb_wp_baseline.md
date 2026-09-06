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
