# The three-hour give-up is generous; the exit condition is not

Two questions asked before rebuilding the ESPN football recorder, both
measured read-only against prod `espn_cfb_game_state` on 2026-09-14. The fix
on `origin/main` (`SETTLE_MAX_SECONDS = 3 * 3600`, counted from when a game
leaves the board, abandoning LOUDLY) is confirmed present and confirmed not
running: the container is on a 2026-09-06 image.

The gate re-measured with `bool_or(state='post')`: **CFB 105 of 186 (56.5%),
NFL 9 of 15 (60.0%)**.

## 1. Is three hours long enough? Yes, by orders of magnitude

The obvious measurement is **censored and cannot answer this.** Among games
that reached `post`, the delay from the last `in` row to the first `post` row
is a median **0.5 minutes**, p90 0.6, max 0.7 (CFB; NFL 0.4) — but that
population is selected on having posted *while polling continued*, which is
exactly the games with a short delay. It says nothing about the 81 stuck ones.

The answer comes from the other side. **The stuck games are not abandoned
mid-game — they are abandoned at the whistle:**

| league | period at last row | games | median span observed | clock at last row |
|---|---|---|---|---|
| cfb | 4 | 69 | 3.28 h | 0:00 – 2:46 |
| cfb | (null) | 11 | 3.25 h | — |
| nfl | 4 | 6 | 3.07 h | 0:00 – 0:34 |
| cfb | 6 (OT) | 1 | 3.62 h | 0:00 |

A median observed span of 3.28 hours is a full college football game. The
recorder follows the game to the end and stops at the finish line, seconds to
minutes before ESPN flips the flag. The gap to bridge is minutes; three hours
is a very large margin.

**The residual risk is real but is not the bound.** One game went
`post` → `in` → `post`, with the `in` row **585.5 minutes (9.75 hours)** after
the first post, and another was re-observed across a **1,335-minute** post
window. A three-hour give-up measured from leaving the board would not cover
a 9.75-hour revert — but in both cases post had already been observed, so the
bound was never the binding constraint. The exit condition was.

## 2. Is `post` sufficient for a final score? Complete, yes. Stable, no

**Complete.** 114 post games: **0 null scores, 0 zero-zero, 0 ties.** Mean
total 54.7 (CFB) and 49.3 (NFL), against the 54.3 measured independently over
the finals population. Nothing is missing.

**Stable, no. 12 of 105 CFB post games (11.4%) carry a post score BELOW a
score seen earlier in the game**, understating the total by 2 to 7 points.

```
game        post score   in-game max   total understated   rows at that max
401856682      23-24        23-31              7                  4
401868316      14-39        14-46              7                  1
401868195       3-30         9-30              6                  0
401869150       0-88         2-88              2                  0
```

**And the obvious fix is the wrong one.** I was about to recommend
`max(home_score), max(away_score)` across the game's rows. Seven of the
twelve have `rows at that max = 0` — the maximum home score and the maximum
away score **never co-existed in a single row**, so the "in-game max" is not a
scoreline that ever existed. These are ESPN publishing a score and correcting
it downward, and the post row carries the corrected value. Taking `max()`
would have overstated twelve totals by 2–7 points and pushed Over markets
toward YES: the same flattering direction as every other defect found today.

The rule is **the LAST `post` row**, and a non-monotone score history is a
flag to inspect, not a reason to reach for `max()`.

## 3. The exit condition takes a wrong score about 5% of the time

The fix polls "until `post` is OBSERVED" and then stops. Does the score move
after the first post?

Naively: 112 of 114 games have first-post score equal to last-post score. **That
number is mostly vacuous** — the median game has exactly ONE post row, so for
77 of 114 the comparison is a row against itself and cannot fail. Restricted
to the games where it can:

| post rows | games | score changed | max span |
|---|---|---|---|
| 1 | 77 | 0 (**vacuous**) | — |
| 2 | 34 | **2** | 1.3 min |
| 3 | 2 | 0 | 586 min |
| 4 | 1 | 0 | 1,335 min |

**2 of the 37 games where the check can fail (5.4%) changed score after the
first post observation**, by up to 9 points on the total, both within about
1.3 minutes. The games re-observed over long spans (586 and 1,335 minutes)
did not change.

So: keep the three-hour bound, it is generous. Change the exit from "first
`post` observed" to "`post` observed twice a few minutes apart with the same
score" — one confirming poll. That is cheap, it costs one extra request per
game, and it addresses a measured 5% rather than an imagined tail.

## What this means for the Kalshi arm

`post` reached 56.5% of the time is the binding constraint on the second
venue, not anything on Kalshi's side. Fixing it makes both the NFL derivation
and every future CFB settlement usable. Deriving a settlement from a game
still at `in` would be a bias and not a gap: a truncated game has a lower
total, so Over markets settle NO when the real total cleared the strike.
Derive only from the last `post` row, and count everything else unsettled.
