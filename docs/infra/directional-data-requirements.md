# What a rich-feature directional model would need — a collection specification

**Status: specification, 2026-09-04.** Written after the cheap feature space was
shown to be not merely weak but **placebo-equivalent**, and grounded in that
result rather than in a wish list.

## The result this is built on, because it constrains the answer

Gradient boosting on 13,143 NBA games, forward by season, three targets, one
pre-declared configuration:

| target | model vs line | placebo | model's actual signal content |
|---|---|---|---|
| totals | +0.01214 [+0.00941, +0.01486] | +0.01217 | **~0.00003 — nothing** |
| spread | +0.01028 [+0.00769, +0.01286] | +0.01331 | 0.0030 |
| moneyline | +0.00967 [+0.00755, +0.01179] | +0.01090 | 0.0012 |

Every CI is off zero **against** the model. The *real-minus-placebo* gap is the
only signal the feature space contains, and on totals it is indistinguishable
from zero: **a model trained on destroyed labels performs as well as one trained
on the truth.**

**THE DIRECTION THIS POINTS, AND IT IS THE SPEC'S ORGANISING CLAIM.** The
features were team-history features — rest days, 10-game rolling scoring,
conceding, pace deviation, games played. They carry **literally nothing** on
totals. That is not "we need more team history"; a longer window or a better
weighting of the same quantity is more of what already measured zero. **The
closing line has already absorbed team history completely** — it is precisely
the thing a market with a week's notice and everyone's models is best at.

So the informative features, if any exist, are the ones describing **THIS
SPECIFIC GAME'S STATE**, especially state that (a) arrives late, (b) is
unevenly observed, or (c) is hard to aggregate. Everything below is ranked by
that criterion, not by how interesting it sounds.

## What we actually hold today

| store | rows | games | coverage |
|---|---:|---:|---|
| `team_game_logs` | 3,466 | 1,733 | **WNBA only** (12–15 teams) |
| `player_game_logs` | 20,282 | 875 | from 2024-05, WNBA |
| `injury_reports` | 835 | — | from 2026-08-01 — **5 weeks** |
| `sportsbook_odds` | 22,048 | 1,733 | 2020-07 → 2026-08 |
| NBA games CSV | 13,143 | 13,143 | lines, teams, dates, scores only |

**There is no football team-game history, no football player logs, and no
football injury history anywhere in the database.** For the sport where the
operator sees most potential, the feature space is the one just shown dead.

## The shopping list, ranked by expected value given the result above

### Tier 1 — late-arriving state the line cannot have fully absorbed

**1. Confirmed starting lineups + inactives, timestamped.**
*What:* who is actually playing, and **when that became public**. The timestamp
is the feature, not a nicety — value exists only in the window between
information arriving and the line moving.
*Source:* NBA/NFL official injury reports and beat-writer feeds publish ~30–90
min pre-tip; ESPN and the venue's own feed carry some of it. **Our
`injury_reports` table exists but holds 5 weeks and is WNBA.**
*Expected worth:* **the highest of anything here, and the only item I would
predict beats the line at all.** A star ruled out 40 minutes before tip is
exactly (a) late, (b) unevenly observed and (c) hard to aggregate. But note the
honest bound: books move fast on this, so the edge is a *latency* edge, and
F8's feed-lag work says our in-play latency is already too slow to race. The
pregame version has a longer window and is worth measuring before assuming.

**2. Line MOVEMENT, not just the closing line.**
*What:* open → close path with timestamps, plus the current price at decision
time. We store only the close.
*Source:* our own recorder already captures venue prices; sportsbook opens are
available from odds APIs. **Cheapest item on this list — it is a schema change
to something we already collect.**
*Expected worth:* moderate and *diagnostic even if it is not tradable*. The
direction and timing of a move is a proxy for where informed money went, and it
would let us ask "does the model agree with the move" — which is the λ*
question on a different axis.

**3. Referee assignment.**
*What:* the crew, published pre-game.
*Source:* NBA publishes assignments the morning of; NFL similar.
*Expected worth:* modest but genuinely orthogonal to team history — crews differ
measurably in foul rate, which maps to totals. It is the one classic totals
feature that is *not* a team property, which is exactly the class the result
above says to look in.

### Tier 2 — structural state, cheap to derive, probably already priced

**4. Travel and schedule load** — miles since last game, time-zone crossings,
third-game-in-four-nights. *Derivable today from the game table for the NBA.*
*Expected worth:* **low, and I would not fund it as a priority.** It is a
deterministic function of a public schedule, which makes it precisely the kind
of thing a closing line absorbs completely — the same class as rest days, which
measured zero here.

**5. Pace-adjusted efficiency (offensive/defensive rating, possessions).**
*What:* the standard basketball adjustment my rolling features approximate
crudely.
*Source:* derivable from play-by-play we already ingest for the WNBA; NBA
requires a season-history backfill.
*Expected worth:* **low for beating the line, high for the FV's second moment.**
It will not find what raw scoring missed, but see the sigma note below.

### Tier 3 — needed for correctness rather than for edge

**6. Per-observation sigma, and the data to validate it.**
D's fair-value interface spec (b3a55e0) requires a **second-moment calibration
test nobody currently runs**: standardised residuals `(fv − outcome)/sigma` must
have unit variance out-of-sample, with **understating sigma costing about twice
what overstating it does**. Our own history agrees from the other direction —
the R4/R4b arc found the stack's variance was systematically too wide because
sigma was fitted to an unshrunk mean, and fixing the *fitting order* beat
fixing the *level*.
*Expected worth:* **this is the item I would do first**, and it is not an edge
item at all. Every result in this document is a Brier comparison, and Brier
punishes miscalibrated confidence — which is exactly how all three models above
lost. **The measured failure mode is overconfidence, not ignorance**, and sigma
is the direct handle on overconfidence.

## What I would NOT collect, and why it belongs in a spec

- **More team history at longer windows.** Measured zero. More of it is more zero.
- **Public "advanced stats" aggregates** (season-to-date ratings, ELO). Same
  class: slow-moving, universally available, fully absorbed by the line.
- **Anything requiring a subjective judgement to encode** (e.g. "motivation",
  rivalry flags). Unfalsifiable features are how a flexible learner finds
  structure that is not there, and this programme has spent a day cataloguing
  that failure family.

## The honest summary

**The rich-feature hypothesis is untested, and the data to test it does not
exist for the sport where the operator sees most potential.** That is a
specification, not a refutation. But the result constrains what is worth
collecting: **team history is exhausted, and the only defensible candidates are
late-arriving, unevenly-observed game state — lineups first, line movement
second, referees third — with sigma calibration ahead of all of them because the
measured failure was overconfidence rather than ignorance.**

And the standing caution, given a flexible learner and a new feature set: every
item above must arrive with a point-in-time proof and re-enter the same
placebo-and-control harness (`analysis/nba_totals_ml.py`). **A feature that
cannot be shown to have been knowable before tip-off is a leak with a
justification attached.**

*No in-sample result justifies capital. The forward test is the evidence.*
