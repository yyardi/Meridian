"""The canonical "what is on the board right now" query.

Why this is its own module
--------------------------
Two independent consumers — the dashboard API and the prediction job — both
need "the latest state of every market". Both originally wrote it the same
wrong way, and one of them silently stopped the whole ANCHOR pipeline for two
and a half hours because of it. One copy, in one place, so the next consumer
inherits the fix rather than the bug.

The bug, because it will look reasonable again
----------------------------------------------
::

    WHERE captured_at = (SELECT max(captured_at) FROM market_snapshots)

That was correct while a single recorder wrote the whole board every cycle: the
newest instant *was* a complete picture of the board.

It stopped being correct the moment two writers existed on different cadences.
The live recorder samples **only in-progress games**, every 200ms. The pregame
recorder sweeps the **whole** board, every 15 minutes. So during a game the
global maximum `captured_at` belongs to the live recorder and contains nothing
but that one live game. Any query anchored on it sees a board consisting of a
single game.

For the dashboard that meant a 12-game board rendering as one game. For
`core.predictions` it was worse: it took that same maximum, filtered out live
markets as unpriceable, and was left with an empty list — so it wrote zero
predictions for the entire duration of every game, logged `no_pregame_markets`,
and returned successfully.

Neither failure raised. That is the property that makes this shape dangerous:
it does not break, it just quietly returns less.

The right question is per-market, not per-cycle::

    SELECT DISTINCT ON (market_slug) *
    FROM market_snapshots
    WHERE captured_at <= :as_of
      AND game_start_time >= :cutoff
    ORDER BY market_slug, captured_at DESC

which rides `ix_market_snapshots_slug_time` directly.

The lookback bound is on `game_start_time`, never on `captured_at`
------------------------------------------------------------------
Bounding on when a row was last *written* would reintroduce exactly this bug at
a different scale: a market would drop off the board because its writer is slow,
rather than because its game is over. Bounding on when the game *starts* is a
fact about the world and is unaffected by recorder cadence.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.storage import MarketSnapshot

UTC = dt.timezone.utc

#: A game this far past tip-off is over, so its markets are no longer the
#: board. Generous enough to cover a WNBA game (~2.5h wall) plus overtime and
#: settlement lag.
BOARD_LOOKBACK_HOURS = 6.0


#: Latest row per market, via a skip scan plus one index lookup each.
#:
#: The obvious `DISTINCT ON (market_slug) ... ORDER BY market_slug, captured_at
#: DESC` is correct but does not scale here. Measured on 857k rows, the planner
#: chose `ix_market_snapshots_market_slug` and then an **Incremental Sort over
#: 612,291 rows**, which exceeded the statement timeout — `/api/events` took
#: 120s and returned 500. It was fine at 18k rows and quietly stopped being fine
#: somewhere in between, which is the thing to watch for: this table now grows
#: by ~200k rows a game.
#:
#: The rewrite asks the same question in a way that stays proportional to the
#: number of *markets* (~200) rather than the number of *rows*:
#:
#: 1. Enumerate the distinct `market_slug` values by walking the leading column
#:    of `ix_market_snapshots_slug_time` — a recursive "skip scan", roughly one
#:    index seek per market instead of a scan of every row.
#: 2. For each, take its newest row with `ORDER BY captured_at DESC LIMIT 1`,
#:    which is a single seek on the same index.
#:
#: Measured after: 129ms against 120s. It gets *faster* relative to DISTINCT ON
#: as the table grows, because its cost is set by the market count, which is
#: bounded by the size of the league's board.
_LATEST_PER_MARKET = text("""
with recursive slugs as (
        (select market_slug from market_snapshots order by market_slug limit 1)
    union all
        select (select m.market_slug from market_snapshots m
                where m.market_slug > s.market_slug
                order by m.market_slug limit 1)
        from slugs s where s.market_slug is not null
)
select latest.*
from slugs
cross join lateral (
    select * from market_snapshots m
    where m.market_slug = slugs.market_slug
      and m.captured_at <= :as_of
    order by m.captured_at desc
    limit 1
) latest
where slugs.market_slug is not null
  and latest.game_start_time >= :cutoff
""")


def latest_snapshot_per_market(
    session: Session,
    *,
    as_of: dt.datetime,
    lookback_hours: float = BOARD_LOOKBACK_HOURS,
) -> list[MarketSnapshot]:
    """The newest snapshot of each market at or before `as_of`, one row each.

    `as_of` is keyword-only with no default, per the project's point-in-time
    rule: a caller must say which instant it is asking about, and only data
    strictly at or before it is returned.
    """
    cutoff = as_of - dt.timedelta(hours=lookback_hours)
    return list(
        session.scalars(
            select(MarketSnapshot).from_statement(
                _LATEST_PER_MARKET.bindparams(as_of=as_of, cutoff=cutoff)
            )
        ).all()
    )


def is_pregame(snap: MarketSnapshot, *, as_of: dt.datetime) -> bool:
    """True when this market's game has not tipped off yet.

    Checks the **start time** as well as the `is_live` flag, deliberately. The
    flag is only as fresh as the row carrying it, and the rows that matter here
    are the stale ones: right after tip-off the pregame recorder's last sweep
    can still say `is_live=False` for a game that is already running. Trusting
    the flag alone would price a game in flight — which is precisely the
    contamination the pregame-only rule exists to prevent.
    """
    if snap.is_live:
        return False
    start = snap.game_start_time
    return start is None or start > as_of


def snapshot_age_seconds(snap: MarketSnapshot, *, as_of: dt.datetime) -> float:
    """How stale this market's quote is, in seconds."""
    return (as_of - snap.captured_at).total_seconds()
