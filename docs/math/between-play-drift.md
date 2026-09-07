# Between-play drift: the move is 87% done before we can see it

The research report's one speed-independent edge hypothesis: if venue prices
underreact to a play and finish moving over the following minutes, a follower
with a 30-second lag still has something to buy. **Measured directly, no model
in the loop**, on 73 CFB games / 12,701 plays / 130,666 winner-market snapshots.
Pre-specified: pre = mid before the play; obs = mid at +30s (what we see);
later = mid at obs+h inside the dead window only — a horizon the next play
interrupts is dropped and counted. Moves with |jump| ≥ 1¢.

| | |
|---|---|
| moves ≥1¢ at h=30s | 145, G=20 |
| horizons dropped because the **next play arrived first** | **4,542** |
| β, subsequent drift on observed jump | −0.044 [−0.088, +0.001] — spans zero |
| mean continuation | −0.03¢ [−0.42, +0.36] |
| **fraction of the eventual move realised at +30s** | **0.87 ± 0.08** |
| h = 60 / 120 / 300 | 90 / 53 / 3 observations — nothing can be said |

## What it says

Two things, and the second matters more than the first.

**Nothing is left to ride.** 87% of the post-play move is in by the time a
30-second feed shows it, and the residual is indistinguishable from zero in
sign — if anything mild reversal, not continuation. The report's 0.64
"realised at first" figure was for discrete news on a slow clock; a football
play is priced in tens of seconds.

**There is no between-play window at our lag.** Plays arrive ~40s apart; the
lag consumes 30 of them. Of ~6,000 plays with a usable pre and obs mid, 4,542
could not even reach a 30-second horizon before the next snap. E6's dead-window
stratum was defined on observed plays and found 66% of game *time* qualifying;
this shows why that time does not translate into *windows a lagged quoter can
use*: the dead time is real, and by the time we know it has started, it is
nearly over.

## What it cannot say

n=145 at h=30 is thin, and 6,525 plays had no pre-play mid within five
minutes — the winner-market tick is bursty, not continuous. The point estimates
lean the wrong way for the hypothesis and the realised fraction is reasonably
tight, but "efficient" here means "no detectable inefficiency on 145 moves,"
not a proof. The place to re-run this is NFL winner markets, where ticks are
dense enough that the pre/obs/later triplet exists for most plays.

Script: `cfb/run_drift.py`. Output preserved as `drift.out` in the session scratchpad.
