# E6 — one pre-registered dead-window making stratum

**Stratum, verbatim from the plan and written before the run:** quote only
when there has been *no play in the last 45s and no score change in the last
120s*, evaluated on observed plays (a play inside the 30s feed lag is
invisible — that is the maker's lag risk and it is left in). Instants every
15s between plays; rest until the next play arrives or 90s. Everything else
is E1's harness untouched: touch-joined quotes, prints-based fills, θ_maker=0,
optimistic no-queue on 99% of quotes, game-clustered. **One stratum. No search.**

## Coverage

| | count |
|---|---|
| instants generated | 45,581 |
| qualified as dead | 30,101 (66% of game time) |
| with a book within 5 min | 15,597 |
| games with any fill | **29 of 51** |

## Result

| arm | fills | net/fill | game-clustered 95% | G / G_eff | adverse by markout |
|---|---|---|---|---|---|
| A naive touch maker | 1,566 | −0.66¢ | [−4.65, +3.32] | 29 / 12.8 | **29.6%** |
| B model as shield | 1,261 | −2.13¢ | [−9.62, +5.35] | 29 / 14.5 | 27.3% |
| C shield + skew | 1,267 | −2.06¢ | [−9.64, +5.51] | 29 / 14.4 | 27.5% |
| withdrawn by shield | 305 | +5.40¢ | [−6.43, +17.24] | 13 / 6.4 | — |

**Gate ("game-clustered positive edge, 25-game floor"): fails — could-not-measure.**
Every arm spans zero; the UNDERPOWERED guard fired on 29 games.

## What did move, and what it is

Against E1 at plays (A: −3.09¢, adverse 45.8%), the dead window shows
**adverse-by-markout 46% → 30%** and the point estimate less negative. That is
the mechanism the plan predicted — less informed flow between plays — showing
up in **fill composition**, and it is the one measured thing tonight that
behaved as the theory said. It does not reach P&L at G_eff 12.8, and a
composition shift is not an edge.

The shield hurts again in point estimate (B − A = −1.47¢), the same sign as
E1 and the same withdrawn-fills-are-positive shape (+5.40¢ on G_eff 6.4).
Three arms in two strata now say the WP model's disagreements with the market
lean the wrong way. None of the three is significant. See E2 for why that is
the expected shape of a model that is a leveraged bet on the pregame line.

## What this is not

Not a verdict on dead-window making. It is 29 games of fills on a winner
market that is 1.8% of the board. The stratum reduces adverse selection as
designed and cuts the sample in half doing it. The place this test has power
is a deeper book — E8, NFL, from 09-10.

Script: `cfb/run_making_touch.py` with `DEAD_WINDOW=1`. Output preserved as
`e6_dead_window.out` in the session scratchpad.

## Pooled re-run, 2026-09-07 — after the map rebuild added Saturday's slate

Backfill (Wed–Fri, 55 games) + live-only Saturday games (18), dedup by game.

| arm | fills | net/fill | game-clustered 95% | G / G_eff | adverse |
|---|---|---|---|---|---|
| A naive touch maker | 2,760 | **+0.50¢** | [−1.95, +2.94] | 32 / 11.2 | 30.3% |
| B model as shield | 2,182 | −0.53¢ | [−5.34, +4.27] | 32 / 11.8 | 28.5% |

First positive point estimate in any arm, all night. **It is not a result** — G_eff 11.2,
interval spans zero by ±2.4¢. What is stable across every run: the dead window shifts the
naive maker ~2.4¢ favourable versus at-plays (E1 pooled: −1.94¢) and cuts adverse fills
47%→30%. Composition moves the way the theory says; P&L is not measurable on a winner
market that barely prints. Fills landed in 32 of 70 games.
