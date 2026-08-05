"""Cross-venue gap analysis: Polymarket vs Kalshi. STUB — gate not yet met.

Pre-registered gate (fixed 2026-08-05, before any matched data existed)
-----------------------------------------------------------------------
No conclusion about the venue gap may be drawn until **at least 10 matched
games** have same-minute pregame snapshots on both venues. When the gate is
met, report exactly two statistics, computed on matched contracts and
clustered by game:

1. **Median |mid gap|** — |Polymarket mid − Kalshi mid| on contracts matched
   by market type and identical line (a Kalshi ``floor_strike`` of 15.5 on
   team X matches a Polymarket spread line of 15.5 quoted from team X, and
   nothing else — a half-point off is basis, not a match). Mids are paired at
   the same minute: snapshots whose ``captured_at`` differ by more than 60s do
   not pair.
2. **Sign persistence** — of matched pairs where the gap is nonzero, the
   fraction of games whose *game-level median* gap keeps one sign across the
   pregame window. Clustering by game is mandatory: 360 pregame minutes of one
   game are one observation of the venue relationship, not 360.

The 10-game minimum is the same lesson as PULSE (837k rows was still a 3-game
sample): rows are not games, and per-minute snapshots are wildly dependent
within a game.

Deliberately NOT reported: anything resembling a tradable edge, fee-adjusted
or otherwise. That is a later, separately registered question. This module's
only job when the gate is met is to say how far apart two transactable prices
sit and whether the sign is stable.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import distinct, func, select

from core.storage import KalshiGame, KalshiSnapshot

#: The pre-registered minimum. Do not lower it; a smaller n means "wait".
MIN_MATCHED_GAMES = 10


def count_matched_games(session) -> int:
    """Games linked to a Polymarket event that actually have Kalshi snapshots.

    A `kalshi_games` row with a `polymarket_event_slug` is matched by
    discovery; requiring at least one snapshot row makes this a count of games
    with *data on both venues*, not merely a mapping.
    """
    return session.scalar(
        select(func.count(distinct(KalshiGame.game_key)))
        .select_from(KalshiGame)
        .join(KalshiSnapshot, KalshiSnapshot.game_key == KalshiGame.game_key)
        .where(KalshiGame.polymarket_event_slug.is_not(None))
    ) or 0


def gate_status(session) -> dict:
    """Where the sample stands against the pre-registered gate."""
    n = count_matched_games(session)
    return {
        "matched_games": n,
        "required": MIN_MATCHED_GAMES,
        "gate_met": n >= MIN_MATCHED_GAMES,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def report(session) -> dict:
    """The two pre-registered statistics — refuses to run before the gate.

    Below the gate this returns the gate status and no numbers at all: a
    partial median on 3 games is exactly the kind of premature verdict the
    pre-registration exists to prevent.
    """
    status = gate_status(session)
    if not status["gate_met"]:
        return status
    raise NotImplementedError(
        "Gate met — implement the pre-registered statistics now, exactly as "
        "specified in this module's docstring (median |mid gap| and sign "
        "persistence on matched contracts, clustered by game), and nothing "
        "else."
    )
