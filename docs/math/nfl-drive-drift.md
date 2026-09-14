# NFL replication of the drive-scalp drift result

2026-09-15. The operator's own strategy, measured on the league they were actually
watching. meridian-06 measured it on 59 CFB games; this is 15 NFL games, by a
different implementation, after that session stopped responding.

## What was measured

Per drive, the first play inside the opponent's 40 (`yards_to_goal <= 40`, downs
1-4, overtime excluded) is the **MIDFIELD** trigger. Every scoring play is the
**SCORING** control. For each trigger the winner-market mid is taken at the first
quote at or after the play's wall clock, and again at the first quote at or after
+30s and +300s. The move is signed toward the team with the ball, using
`drive_is_home_offense` rather than name matching, because YES is the away side on
every slug here.

## Result, game-clustered (equal-weight game means, t on 14 df)

| arm | horizon | n | G | mean | 95% CI |
|---|---|---:|---:|---:|---|
| MIDFIELD | 30s | 187 | 15 | +0.332¢ | [−0.091, +0.755] **spans zero** |
| MIDFIELD | 300s | 181 | 15 | +0.927¢ | [−0.217, +2.070] **spans zero** |
| SCORING | 30s | 127 | 15 | +1.467¢ | [+0.327, +2.606] **excludes zero** |
| SCORING | 300s | 126 | 15 | +1.973¢ | [+0.733, +3.212] **excludes zero** |

Per-fill means, named because the estimator is not the interval: MIDFIELD +0.250
and +0.641, SCORING +1.169 and +1.669. **The median move is 0.00¢ in every arm at
every horizon**, as it was on CFB.

## What it says

**The control fires and the trigger does not.** The same measurement detects a
scoring play at both horizons and finds nothing when a drive crosses into the
opponent's 40. That is what makes the null a measurement rather than a failure to
look, and it is the same structure meridian-06 found on 59 CFB games.

**The upper bound is the honest limit.** At 300s the midfield interval reaches
+2.07¢. A round trip pays the taker fee twice, about 3¢ at mid prices, so even
the top of the interval does not clear costs — but with G=15 this cannot exclude
a 2¢ effect, and it should not be read as if it could.

## What this is NOT

Not a replication of the whole CFB study. The excursion table — the fraction of
triggers touching ±5¢ — is not reproduced here, and the entry rule is the first
quote at or after the play rather than 06's trigger-plus-latency rule. What
replicates is the **drift** result and the control that makes it meaningful.
