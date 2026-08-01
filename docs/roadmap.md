# Roadmap decision — 2026-08-01

**Question:** deepen WNBA, or expand to MLB?

## The MLB probe settled it

Polymarket US MLB, measured live: 30 events, 405 markets, **1¢ spreads with
half-cent ticks** across the board. A book that tight tracks the sportsbooks —
there is no venue gap to trade. And the "use MLB data to validate techniques
for WNBA" argument fails on its own terms: sport-specific findings do not
transfer (possession structure just failed in the league it is textbook for),
and the sport-agnostic discipline is already built and validated here.

**Decision: stay WNBA.** Thin markets are the thesis; WNBA is the thin market.
MLB re-enters only if we ever want its *own* thesis, which would need its own
discovery program.

## Where the edge concentrates, per the literature

Injury and lineup news creates short windows where lines lag — the edge is
being right *faster*, and the documented pattern is a sharp book moving while
"a follower book is still hanging the old number". Our structure maps onto
this exactly: sportsbooks are the leader, Polymarket's thin WNBA book is the
candidate follower. It also explains our scanner's first night (no standing
gap on a quiet evening) *and* the hand-observed 6–8 point gaps (likely news
windows).

## Consequences, in build order

1. **Both legs of the pair must be time-resolved.** The PM leg is sampled
   every 15 min; the book leg was every 6h — blind to windows. The scheduler
   now polls book lines every 20 min. (Done.)
2. **Window detector:** flag book-line moves ≥ 1.5 pts between polls, then
   measure whether PM lagged and for how long. This is the tradable event.
3. **Pregame injury/lineup awareness** (the v2 idea from the original brief):
   the model prices rosters it cannot see. Even a flag — "star listed out,
   projection stale" — prevents the worst bets and marks likely windows.
4. **Shadow + scanner accrual** continue throughout; the 60-day shadow gate
   on the recency champion is unchanged.

## What we are explicitly not doing

- No MLB build (measured: no venue gap there).
- No model-class escalation (NNs memorise at n≈700; boosted-trees ceiling
  probe stays queued behind feature work).
- No further config iteration on the WNBA totals backtest without a new
  pre-registered hypothesis.
