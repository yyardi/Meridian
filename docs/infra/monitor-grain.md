# Per-game or per-league? — design note

Both proposed monitors currently assert **per league**. Each has a blind spot
the grain causes, and each would be fixed by going per game. The question is
what that costs, and the cost is not compute.

## What per-league misses

| monitor | watches | misses at league grain |
|---|---|---|
| external evaluator | row **arrival** | one game's rows stop while 40 others record — 2026-09-06's kickoff-window defect |
| value-change alarm | price **movement** | a freeze confined to the in-play subset, because pooling averages it against quiet pregame markets |

## The cost is false-alarm rate, not compute

Fifty games on a Saturday means fifty comparisons per interval instead of one.
Compute is free. **The rate is not.** At a 1% per-game false-positive rate and
10-minute intervals over a 12-hour slate, that is ~36 false alarms per slate —
which destroys the alarm, and destroys it in the specific way that matters: it
trains the reader to ignore it.

So per-game is only viable if the per-game false-positive sources are removed
first, and there are three.

## Source 1: scheduled start ≠ actual start — and this one is not hypothetical

**A per-game rule keyed on the scheduled window would have fired on
2026-09-06.** WSU @ WASH was scheduled 20:00Z; at 20:04Z ESPN still read `pre`.
A rule expecting rows from the scheduled start would have alarmed for however
long the game ran late, on a completely healthy system.

That is the same fact that caused the recorder defect that night — the recorder
*stopped* at scheduled start, an alarm would *fire* at scheduled start. One
fact, two opposite bugs.

**Fix:** the per-game expectation must use ESPN's **actual state** (`state ==
'in'`), never the scheduled window. The schedule table already carries
`actual_state` for this reason.

Note this is *stricter* than the per-league version needs, which can use the
scheduled window because some game is nearly always genuinely in progress.

## Source 2: sampling — a quiet interval is not a gap

A game with few markets may legitimately produce zero rows in a short interval.

**Fix:** an expected-rows floor, `numMarkets × cadence × interval`, alarming
only below some fraction of it. `marketCounts.numMarkets` (241 on a typical CFB
game) comes from **the venue's own events payload**, so it is available at
schedule-fetch time and does **not** come from our write stream — which is the
whole constraint the evaluator exists to satisfy.

## Source 3: the venue may not list the game at all

FCS games are frequently absent from the venue while present on ESPN.

**Fix:** a game with no venue mapping yields `UNKNOWN`, never `ALARM`. This
needs the per-game bridge — `cfb_game_map` exists for CFB; **NFL has none yet**
(the venue supplies no ESPN id, and sportradar bridges nothing), so NFL cannot
go per-game until that lands.

## Shared grain, separate preconditions

**Yes, both instruments should share the per-game grain** — and they should
*not* share preconditions:

| | arrival evaluator | value-change alarm |
|---|---|---|
| grain | per game | per game |
| expectation | ESPN `state == 'in'` | ESPN `state == 'in'` |
| precondition | expected-rows floor | **liquidity floor** |

The movement alarm needs a different guard: a blowout with nobody trading shows
no price movement *legitimately*. Absence of movement in a dead market is not a
freeze. That precondition has no analogue on the arrival side, where rows
arrive regardless of whether anyone trades.

**Sharing the grain and the expectation, while keeping preconditions separate,
is the whole design.** Collapsing them would give one instrument the other's
false alarms.

## What stays uncovered

Per-game grain does not change the disjointness: **arrival and movement are
different failures and neither instrument subsumes the other.** Rows can arrive
while prices stop (the 09-05 freeze, 1.17M rows/hour); rows can stop while
prices would have moved (the 09-05 container collision). Per-game makes each
sharper within its own axis. It does not make either total.

## Status

Design note. Neither monitor is authorised; this is the grain decision they
would both need, written because it was unowned and both designs are blocked on
the same answer.
