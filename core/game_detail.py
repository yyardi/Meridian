"""One game, every shadow trade, in the order the model decided them.

The board and the results table both aggregate: they answer "how is the model
doing" across games and rungs. Neither answers the question an operator
actually asks after a bad night — *what did it do in this game, and what was
true at the moment it decided?* That question needs the decision and its
context side by side, and the context has to be read **as of the decision**,
never after it.

The as-of rule, and why it is the whole module
---------------------------------------------
Every context field here comes from the latest snapshot at or before
``decided_at``. Taking the newest snapshot for the market instead would be
trivially easier and would quietly attach a fourth-quarter score to a decision
made two hours before tip — the model would appear to have traded a 46-34 game
it never saw. That is lookahead, and on a page whose whole purpose is to judge
decisions it is the one error that cannot be allowed. `_context_sql` carries
the ``captured_at <= decided_at`` bound and `TradeContext.context_age_seconds`
reports how stale the reading was, so a sparse pregame join is visible rather
than assumed fresh.

What the score columns will actually show
----------------------------------------
Mostly "pregame", and that is the honest answer rather than a gap.

**The model is pregame-only.** It prices a game before tip and does not price
a running one, so its shadow orders are pregame by construction. Measured over
the full shadow run on 2026-08-17 — 11,283 orders, every one of them joined:

    decided while the market was live :     10   (0.09%)
    decided pregame                   : 11,273

and all ten live ones land on a single instant, 2026-07-31 23:34:06Z, the
first day of the run. So `score`, `margin`, `period` and `minutes_left` are
populated, correct, and nearly always pregame. They are kept — not dropped as
dead columns — because they are the columns an in-game strategy lights up with
no change here, and because "the model never traded inside a game" is itself
the finding a deep-dive page should make obvious at a glance.

Minutes left is an estimate
---------------------------
`market_snapshots` carries a period and **no game clock**, so time remaining is
interpolated from wall-clock since the period was first seen — wrong whenever
the clock stops, and labelled ``est.`` everywhere it is shown. The estimator is
`core.live_fv.minutes_remaining`, imported rather than reimplemented so this
page and the live strip cannot disagree about what quarter it is.

The outcome is conditional on a fill that never happened
--------------------------------------------------------
A shadow order is a limit order the system decided and never sent. Most of them
would have **rested** on the book (`would_rest`), and a resting limit fills only
if somebody crosses it. So `pnl_if_filled` is exactly what it says: the money
that bet would have made *had it filled at its limit*. It is not a return, it
is not what the strategy earned, and it must never be summed into anything that
calls itself performance — the backtest's fill model exists precisely because
this number needs one (`core/backtest/fills.py`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import text

from core.live_fv import minutes_remaining, parse_score

UTC = dt.timezone.utc

#: Timeline downsampling. A live game is sampled every 200ms across ~14
#: markets, so one game is tens of thousands of rows per market — more than a
#: browser should be handed and far more than an eye can read. One point per
#: bucket (the last reading in it) keeps the shape and bounds the payload.
DEFAULT_BUCKET_SECONDS = 30

#: Cap on timeline points, after bucketing. A 2.5h game at 30s is ~300.
MAX_TIMELINE_POINTS = 900


@dataclass(frozen=True)
class TradeContext:
    """The game, as of the instant the model decided. Never after it."""

    #: Venue score string, first team first ("46-34"), or None pregame.
    score: str | None
    #: Points, first team's frame — the frame the YES side is quoted in.
    margin: int | None
    period: str | None
    minutes_left: float | None
    minutes_left_is_estimate: bool
    is_live: bool
    #: How stale the snapshot behind this reading was, in seconds. Pregame
    #: polling is 15-60 min, so a large number here is normal, not a fault —
    #: but it has to be visible or the reading looks instantaneous.
    context_age_seconds: float | None
    note: str | None = None

    @property
    def is_pregame(self) -> bool:
        return not self.is_live


@dataclass(frozen=True)
class ShadowTrade:
    """One order the model decided and the system never sent."""

    shadow_order_id: int
    decided_at: dt.datetime
    market_slug: str
    human: str
    market_type: str | None
    line: float | None
    side: str
    limit_price: float
    quantity: float
    would_rest: bool
    binding_constraint: str | None

    model_fv: float | None
    market_bid: float | None
    market_ask: float | None
    edge_net: float | None

    #: Hours before tip-off. Negative means after it.
    hours_to_tipoff: float | None
    context: TradeContext

    #: 1 = the market settled YES, 0 = NO, None = not resolved yet.
    resolved_outcome: int | None

    @property
    def spread(self) -> float | None:
        if self.market_bid is None or self.market_ask is None:
            return None
        return self.market_ask - self.market_bid

    @property
    def bet_won(self) -> bool | None:
        """Shadow orders are always BUY on the market's YES side
        (`core/shadow_run.py`), so the bet wins exactly when it settles YES."""
        if self.resolved_outcome is None:
            return None
        return self.resolved_outcome == 1

    @property
    def pnl_if_filled(self) -> float | None:
        """Dollars this order would have made **had it filled at its limit**.

        Conditional, and the name says so. Most of these rest on the book and
        a resting limit fills only when someone crosses it; treating this as
        realised P&L would credit the strategy with every fill it never got.
        """
        if self.resolved_outcome is None:
            return None
        per_contract = (1.0 - self.limit_price) if self.bet_won else -self.limit_price
        return per_contract * self.quantity


@dataclass(frozen=True)
class TimelinePoint:
    """One downsampled reading of the game's own path, after the decisions."""

    at: dt.datetime
    score: str | None
    margin: int | None
    period: str | None
    bid: float | None
    ask: float | None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0


@dataclass(frozen=True)
class GameDetail:
    event_slug: str
    league: str
    label: str
    tipoff: dt.datetime | None
    final_score: str | None
    trades: list[ShadowTrade] = field(default_factory=list)
    #: The moneyline's path through the game. Context for the decisions, not
    #: an input to them — every point here is later than every decision.
    timeline: list[TimelinePoint] = field(default_factory=list)
    timeline_market: str | None = None

    @property
    def n_live_decisions(self) -> int:
        return sum(1 for t in self.trades if t.context.is_live)


# --------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------- #

#: Game state as of each decision. The ``captured_at <= decided_at`` bound is
#: the as-of rule and the reason this is a LATERAL rather than a join on the
#: newest row per market.
_TRADES_SQL = text("""
    SELECT so.id, so.decided_at, so.market_slug, so.sports_market_type, so.line,
           so.side, so.limit_price, so.quantity, so.would_rest,
           so.binding_constraint, so.model_probability, so.market_bid,
           so.market_ask, so.edge_net,
           p.resolved_outcome,
           snap.captured_at AS context_at, snap.is_live,
           snap.event_score, snap.event_period,
           tip.game_start_time
      FROM shadow_orders so
      LEFT JOIN predictions p ON p.id = so.prediction_id
      LEFT JOIN LATERAL (
            SELECT m.captured_at, m.is_live, m.event_score, m.event_period
              FROM market_snapshots m
             WHERE m.market_slug = so.market_slug
               AND m.captured_at <= so.decided_at
             ORDER BY m.captured_at DESC
             LIMIT 1
      ) snap ON TRUE
      LEFT JOIN LATERAL (
            SELECT m.game_start_time
              FROM market_snapshots m
             WHERE m.market_slug = so.market_slug
               AND m.game_start_time IS NOT NULL
             ORDER BY m.captured_at DESC
             LIMIT 1
      ) tip ON TRUE
     WHERE so.event_slug = :event_slug
     ORDER BY so.decided_at, so.market_slug
""")

#: When each period was first observed, so elapsed time inside it can be
#: estimated. One clock per game: every market in it shares these instants.
_PERIOD_STARTS_SQL = text("""
    SELECT event_period, min(captured_at) AS first_seen
      FROM market_snapshots
     WHERE event_slug = :event_slug
       AND is_live IS TRUE
       AND event_period IS NOT NULL
     GROUP BY event_period
""")

#: The game's own path, downsampled to one reading per bucket.
_TIMELINE_SQL = text("""
    SELECT DISTINCT ON (bucket)
           to_timestamp(floor(extract(epoch FROM captured_at) / :bucket)
                        * :bucket) AS bucket,
           captured_at, event_score, event_period, best_bid, best_ask
      FROM market_snapshots
     WHERE market_slug = :market_slug
       AND is_live IS TRUE
     ORDER BY bucket, captured_at DESC
""")

_FINAL_SCORE_SQL = text("""
    SELECT event_score
      FROM market_snapshots
     WHERE event_slug = :event_slug
       AND is_live IS TRUE
       AND event_score IS NOT NULL
     ORDER BY captured_at DESC
     LIMIT 1
""")

#: Games the model actually shadow-traded, newest first. Driven by
#: `shadow_orders` rather than by the snapshot stream: a game with no decision
#: in it has nothing for this page to show.
#: Era filtering (core/era.py) happens in the HAVING clause on the game's
#: LAST decision — a game belongs to the era it finished deciding in, so one
#: game's tape is never split across the archive boundary. Both bounds are
#: nullable: NULL disables that side of the filter, so the same statement
#: serves "everything" (both NULL), "PULSE era" (since set), and "archive"
#: (before set).
_GAMES_SQL = text("""
    SELECT so.event_slug,
           count(*) AS n_trades,
           min(so.decided_at) AS first_decision,
           max(so.decided_at) AS last_decision,
           count(p.resolved_outcome) AS n_resolved,
           max(ts.tipoff) AS tipoff
      FROM shadow_orders so
      LEFT JOIN predictions p ON p.id = so.prediction_id
      -- The game's own start, from our snapshots: predictions do not carry
      -- it (checked, not assumed — the first draft of this join aggregated a
      -- column that does not exist).
      LEFT JOIN (SELECT event_slug, max(game_start_time) AS tipoff
                   FROM market_snapshots
                  WHERE game_start_time IS NOT NULL
                  GROUP BY event_slug) ts ON ts.event_slug = so.event_slug
     WHERE so.event_slug IS NOT NULL
       AND so.event_slug LIKE :league_prefix
     GROUP BY so.event_slug
    HAVING (CAST(:since AS timestamptz) IS NULL OR max(so.decided_at) >= :since)
       AND (CAST(:before AS timestamptz) IS NULL OR max(so.decided_at) < :before)
     ORDER BY max(so.decided_at) DESC
     LIMIT :limit
""")


def _f(value) -> float | None:
    return None if value is None else float(value)


def list_games(session, *, league: str, limit: int = 60,
               since=None, before=None) -> list[dict]:
    """Games this league's model has shadow-traded, newest decision first.

    The league filter is a slug prefix on the event slug
    (``wnba-ny-chi-2026-08-18``), which is how the venue names events and how
    `core.team_mapping` already parses them. ``since``/``before`` are the era
    bounds — presentation filters, never measurement (see core/era.py).
    """
    rows = session.execute(
        _GAMES_SQL, {"league_prefix": f"{league}-%", "limit": limit,
                     "since": since, "before": before}
    ).all()
    return [
        {
            "event_slug": r.event_slug,
            "label": game_label(r.event_slug, league=league),
            "n_trades": r.n_trades,
            "n_resolved": r.n_resolved,
            "first_decision": r.first_decision,
            "last_decision": r.last_decision,
            #: The GAME's own start. The card dates itself by this, not by the
            #: first shadow trade — pregame trades land the night before, and
            #: a card wearing yesterday's date read as a played game with
            #: stuck trades ("GSV didn't play yesterday?", operator,
            #: 2026-08-19).
            "tipoff": r.tipoff.isoformat() if r.tipoff else None,
        }
        for r in rows
    ]


def game_label(event_slug: str | None, *, league: str) -> str:
    """``wnba-ny-chi-2026-08-18`` -> ``NY vs CHI``.

    Positional only. The slug's first team is the side the market is quoted
    from and **not** reliably the away team — Polymarket changed convention in
    the season's first week (see `core.team_mapping`) — so this deliberately
    reads "vs" rather than "@", which would assert a home/away it cannot know.
    """
    if not event_slug:
        return "—"
    rest = event_slug[len(league) + 1:] if event_slug.startswith(f"{league}-") else event_slug
    parts = rest.rsplit("-", 3)          # away, home, YYYY, MM-DD -> teams first
    teams = parts[0].split("-") if parts else []
    if len(teams) >= 2:
        return f"{teams[0].upper()} vs {teams[1].upper()}"
    return rest.upper()


def _context_for(
    row, *, period_starts: dict[str, dt.datetime]
) -> TradeContext:
    """Game state at one decision, from the as-of snapshot."""
    score = row.event_score
    period = row.event_period
    is_live = bool(row.is_live)

    margin = None
    pair = parse_score(score)
    if pair is not None:
        margin = pair[0] - pair[1]

    minutes_left = None
    is_estimate = False
    note = None
    if is_live and period:
        started = period_starts.get(period)
        seconds_in = (
            (row.decided_at - started).total_seconds() if started is not None else 0.0
        )
        clock = minutes_remaining(period, seconds_into_period=max(seconds_in, 0.0))
        minutes_left = clock.minutes_left
        is_estimate = clock.is_estimate
        note = clock.note

    age = None
    if row.context_at is not None:
        age = (row.decided_at - row.context_at).total_seconds()

    return TradeContext(
        score=score,
        margin=margin,
        period=period,
        minutes_left=minutes_left,
        minutes_left_is_estimate=is_estimate,
        is_live=is_live,
        context_age_seconds=age,
        note=note,
    )


def build_game_detail(
    session,
    event_slug: str,
    *,
    league: str,
    human_label,
    bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
    with_timeline: bool = True,
) -> GameDetail:
    """Every shadow trade in one game, with as-of context and outcome.

    ``human_label`` is injected (it lives in `core.api`) rather than imported,
    so this module stays free of the API layer and can be tested without it.
    """
    period_starts = {
        r.event_period: r.first_seen
        for r in session.execute(_PERIOD_STARTS_SQL, {"event_slug": event_slug}).all()
    }

    rows = session.execute(_TRADES_SQL, {"event_slug": event_slug}).all()

    trades: list[ShadowTrade] = []
    tipoff: dt.datetime | None = None
    for r in rows:
        if r.game_start_time is not None:
            tipoff = r.game_start_time
        hours = None
        if r.game_start_time is not None:
            hours = (r.game_start_time - r.decided_at).total_seconds() / 3600.0
        trades.append(
            ShadowTrade(
                shadow_order_id=r.id,
                decided_at=r.decided_at,
                market_slug=r.market_slug,
                human=human_label(r.market_slug, r.sports_market_type, _f(r.line)),
                market_type=r.sports_market_type,
                line=_f(r.line),
                side=r.side,
                limit_price=float(r.limit_price),
                quantity=float(r.quantity),
                would_rest=bool(r.would_rest),
                binding_constraint=r.binding_constraint,
                model_fv=_f(r.model_probability),
                market_bid=_f(r.market_bid),
                market_ask=_f(r.market_ask),
                edge_net=_f(r.edge_net),
                hours_to_tipoff=hours,
                context=_context_for(r, period_starts=period_starts),
                resolved_outcome=r.resolved_outcome,
            )
        )

    final_score = session.execute(
        _FINAL_SCORE_SQL, {"event_slug": event_slug}
    ).scalar()

    timeline: list[TimelinePoint] = []
    timeline_market = None
    if with_timeline:
        # The moneyline is the game's own price: one market, no line, directly
        # comparable to the score. Ladder rungs each price a different question.
        timeline_market = f"aec-{event_slug}"
        points = session.execute(
            _TIMELINE_SQL,
            {"market_slug": timeline_market, "bucket": bucket_seconds},
        ).all()
        for p in points[:MAX_TIMELINE_POINTS]:
            pair = parse_score(p.event_score)
            timeline.append(
                TimelinePoint(
                    at=p.captured_at,
                    score=p.event_score,
                    margin=None if pair is None else pair[0] - pair[1],
                    period=p.event_period,
                    bid=_f(p.best_bid),
                    ask=_f(p.best_ask),
                )
            )

    return GameDetail(
        event_slug=event_slug,
        league=league,
        label=game_label(event_slug, league=league),
        tipoff=tipoff,
        final_score=final_score,
        trades=trades,
        timeline=timeline,
        timeline_market=timeline_market if timeline else None,
    )
