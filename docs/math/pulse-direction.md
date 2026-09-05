# PULSE: the level is wrong, the direction is undecided

**Status: my retirement recommendation is WITHDRAWN.** It rested on the wrong test.

## What I got wrong

I recommended retiring PULSE because its mean absolute error (40.53c) is worse
than the market mid's (39.01c), and because it is 3.08c worse where the two
disagree by >5c.

That is the wrong test, for two reasons.

1. **A fair-value model does not have to beat the mid on MAE to be worth having.**
   The operator's objection is the correct one: *if the market were unbeatable
   there would be no edge for anybody.* Disagreement is not a defect in a signal;
   it is the only place value can come from. A model can be badly calibrated in
   LEVEL and still carry information in DIRECTION, and direction is all a market
   maker needs — it tells you which side to lean, not what to price.

2. **It is a pooled average**, the same aggregation error already recorded in the
   WNBA+CFB pooling retraction. A model that loses on average can win in a subset.

## What the right test says

The estimand: **at a fixed price, do markets PULSE calls cheap settle higher than
markets it calls rich?** Holding the price fixed is what makes it a measurement —
it cancels the one-sided-sampling artifact that produced (and retracted) the
favourite-longshot finding, because both groups are drawn at the same price.

Restricted to disagreements >5c, 1-cent price control, 76,979 predictions:

| check | result |
|---|---|
| pooled, price-controlled | **+8.55c** |
| residual price gap between the two groups | 0.014c (balanced — not a price confound) |
| min cell size 1 -> 200 obs per side | 8.55 -> 8.85c (**flat**; not a small-cell artifact) |
| cells with >=200 obs per side | 29 cells, 8,098 matched pairs, +8.85c |
| degenerate cells (one observation a side) | 1 of 82 |
| **leave-one-game-out jackknife, 88 games** | **+8.55c, SE 6.74c, CI [-4.66, +21.76]** |

**The confidence interval spans zero.** The point estimate is positive and
survives every robustness check EXCEPT the one that matters for inference: the
independent unit is the game, there are only 88 of them, and dropping a single
game moves the estimate between 5.54c and 10.67c.

So the honest status is **UNDECIDED, leaning positive** — not "retire", and not
"edge found".

## Two instruments that could not look

Recorded because both read as controls and neither was one (rule 27):

- **Time-to-settlement bucketing returned a single row**: all 13,054 matched
  predictions read ">4h". `resolved_at` is a batch resolution stamp, not game
  end, so it cannot separate pregame from endgame. The endgame-staleness
  hypothesis — that PULSE only "beats" prices frozen while the game moved on —
  **remains untested.** It is the leading alternative explanation.
- **My first game-clustered estimate** (+12.43c, CI [2.57, 22.30], "excludes
  zero") was computed on game x price cells, which hold a handful of rows each.
  Its median was 0.00, its p25 was 0.00 and its maximum was exactly 100.00 — the
  signature of cells whose achievable image is {-100, 0, +100}. The pooled
  estimate is sound; that game-level construction was not. Cluster by jackknifing
  the pooled statistic, not by averaging tiny per-game cells.

## What this does and does not license

- It does **not** license trading PULSE. Nothing here excludes zero.
- It **does** withdraw the retirement case. The measurement that condemned PULSE
  tested the wrong property.
- The spread bands are non-monotone (+11.49c tight, +28.52c at 3-6c, **-5.76c**
  at 6-15c, +6.13c wide). A real effect should not flip sign in the middle band.
  Tradeability is unestablished.

## Every one of these 88 games is WNBA

PULSE has never made a prediction on a football game: it is hardcoded to
`strategies.wnba_totals` in ~15 places. For CFB and NFL it is **untested, not
tested-and-failed** — a distinction I collapsed when I recommended retirement.

## What would decide it

Games. SE scales as 1/sqrt(n); at 88 games the SE is 6.74c, so an effect of this
size needs roughly 215 games to separate from zero. **CFB supplies ~100 games a
weekend.** Two or three CFB weekends with PULSE running would settle a question
that WNBA cannot settle before the season ends.

That requires making PULSE league-general first, and it requires the
endgame-staleness control that `resolved_at` cannot provide — a real game clock,
which the ESPN summary endpoint already carries.
