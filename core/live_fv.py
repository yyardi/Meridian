"""Live formula fair value for in-game moneylines. **Display only.**

What this is
------------
One number per live moneyline:

    P_live = Phi( (margin + pregame_edge * minutes_left / 40)
                  / (sigma * sqrt(minutes_left)) )

`sigma` is fitted in [`core/pulse/win_curve.py`](pulse/win_curve.py) from 787
completed games. `margin` and the period come from the tick stream. The
pregame edge comes from the v4 projection. It is rendered beside the market's
bid/ask on `/picks` so the two can be looked at together.

**It is not validated and nothing trades on it.** The one hypothesis this
formula has been pointed at — #16, trailing-team underpricing — passed its
pre-registered gate and then inverted under a confound check, which is exactly
why the strip carries the caption it does. A number on a screen acquires
authority just by being there; this one has not earned any.

What is deliberately absent
---------------------------
There is no code path from this module to `core/executor.py`, no order object,
no size, no ticket. It computes a float and hands it to a template. If that
ever needs to change, the gate is a passing out-of-sample measurement, not a
convenient import.

The honest bits
---------------
**Minutes remaining is an estimate, and is labelled one.** `market_snapshots`
carries `event_period` and **no game clock**. Within a period the strip
interpolates linearly on wall-clock time since the period was first seen,
which is wrong whenever the clock stops — timeouts, fouls, reviews — and a
WNBA quarter takes appreciably longer than 10 minutes of wall time. Only at a
period boundary is the figure exact, which is the same reason
`win_curve.py` only measures there. Every response carries
`minutes_left_is_estimate: true` and the UI prints "est.".

**Overtime is not regulation.** After Q4 the game runs in 5-minute periods,
the pregame edge is spent, and the curve's 40-minute denominator no longer
describes anything. OT is handled explicitly rather than by letting
`minutes_left` go negative and the square root go imaginary.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import structlog
from scipy import stats

from core.pulse.win_curve import (
    QUARTER_MINUTES,
    REGULATION_MINUTES,
    pregame_margin_from_price,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Fitted 2026-08-07 from 787 completed games; see docs/math/win-curve.md.
#: Hardcoded rather than recomputed per request: the fit walks every completed
#: game and this endpoint is polled continuously. Refresh it when the season's
#: history grows, and bump the note in the doc when you do.
DEFAULT_SIGMA = 2.628

#: Overtime periods are 5 minutes in the WNBA.
OT_MINUTES = 5.0

#: How far apart the model and the market must be before the gap is coloured.
#: Below this the difference is inside the noise the formula carries anyway.
GAP_HIGHLIGHT = 0.03

#: Period label -> (periods completed before it, its length in minutes).
_PERIOD_PLAN: dict[str, tuple[float, float]] = {
    "Q1": (0.0, QUARTER_MINUTES),
    "Q2": (QUARTER_MINUTES, QUARTER_MINUTES),
    "HT": (2 * QUARTER_MINUTES, 0.0),
    "Q3": (2 * QUARTER_MINUTES, QUARTER_MINUTES),
    "Q4": (3 * QUARTER_MINUTES, QUARTER_MINUTES),
}


@dataclass(frozen=True)
class LiveFV:
    """One live moneyline, model and market side by side."""

    event_slug: str
    market_slug: str
    label: str
    period: str
    score: str
    #: Margin in the FIRST team's frame, matching the YES side of the book.
    margin: int
    minutes_left: float
    minutes_left_is_estimate: bool
    pregame_price: float | None
    fair_value: float | None
    bid: float | None
    ask: float | None
    note: str | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2.0

    @property
    def gap(self) -> float | None:
        """fair value − market mid, in the YES (first team) frame."""
        m, fv = self.mid, self.fair_value
        return None if (m is None or fv is None) else fv - m

    @property
    def highlight(self) -> bool:
        g = self.gap
        return g is not None and abs(g) > GAP_HIGHLIGHT


@dataclass(frozen=True)
class Clock:
    """What we can say about the game clock, which is never much.

    `usable` is separate from `is_estimate` on purpose. Most of the strip runs
    on estimates and that is fine — they are labelled. `usable=False` is
    stronger: it means the estimate has degraded to the point where feeding it
    to the formula produces a *confident* number rather than an approximate
    one, and a confident wrong number on a trading screen is the failure this
    whole module is trying not to be.
    """

    minutes_left: float
    is_estimate: bool
    note: str | None = None
    usable: bool = True

    def __iter__(self):
        """Legacy 3-tuple unpacking, so callers reading (m, est, note) work."""
        return iter((self.minutes_left, self.is_estimate, self.note))


def minutes_remaining(
    period: str | None,
    *,
    seconds_into_period: float,
    ot_number: int = 0,
) -> Clock:
    """Estimated minutes left in regulation.

    Linear interpolation inside the period, because there is no clock in the
    data. Three edges are handled explicitly rather than by arithmetic
    accident:

    * **Period start** (`seconds_into_period == 0`) returns the exact figure —
      30, 20 or 10 — and `is_estimate=False`. This is the only moment the
      number is not a guess, and it is the moment `win_curve.py` measures at.
    * **Halftime** has no clock running at all, so it is 20 minutes exactly.
    * **Overtime** is past regulation. Minutes left is the OT clock, and the
      caller is told via the note that the regulation model no longer applies.

    Elapsed time is clamped to the period length: a quarter takes longer in
    wall-clock than 10 minutes (timeouts, fouls, reviews), and without the
    clamp a long Q4 would drive `minutes_left` negative and the square root
    imaginary.
    """
    if not period:
        return Clock(REGULATION_MINUTES, True, "no period reported", usable=False)

    p = period.upper()

    if p == "OT" or p.startswith("OT"):
        # Overtime is not the model's domain: the pregame edge has been spent
        # by definition (the teams are level), the period is 5 minutes rather
        # than 10, and the 40-minute denominator describes nothing. Suppressed
        # rather than approximated — printing a number under a note that says
        # the model does not apply just invites reading the number.
        elapsed = min(max(seconds_into_period, 0.0) / 60.0, OT_MINUTES)
        left = max(OT_MINUTES - elapsed, 0.0)
        return Clock(left, True,
                     "overtime: regulation model does not apply, pregame edge spent",
                     usable=False)

    if p in {"FT", "F", "FINAL"}:
        return Clock(0.0, False, "final", usable=False)

    if p == "HT":
        # Clock is stopped; the second half has not started.
        return Clock(REGULATION_MINUTES - 2 * QUARTER_MINUTES, False, "halftime")

    plan = _PERIOD_PLAN.get(p)
    if plan is None:
        return Clock(REGULATION_MINUTES, True,
                     f"unrecognised period {period!r}", usable=False)

    completed, length = plan
    raw_elapsed = max(seconds_into_period, 0.0) / 60.0
    elapsed = min(raw_elapsed, length)
    left = REGULATION_MINUTES - completed - elapsed
    exact = raw_elapsed == 0.0

    if raw_elapsed > length:
        # The period has run past its nominal length in wall-clock terms, which
        # is normal — a WNBA quarter takes 15-20 real minutes. The clamp keeps
        # `left` from going negative, but it also means the estimate has
        # SATURATED: the true remaining time is somewhere in [0, length] and we
        # cannot tell where.
        #
        # Reporting 0.0 here is what makes the formula collapse to a step
        # function and print FV 1.000 on a one-possession game. That is fake
        # certainty at exactly the moment the estimate is worst, so the caller
        # is told to suppress the number instead.
        return Clock(max(left, 0.0), True,
                     "clock estimate exhausted — no reliable FV", usable=False)

    return Clock(max(left, 0.0), not exact, None)


def fair_value(
    *,
    margin: int,
    minutes_left: float,
    pregame_price: float | None,
    sigma: float = DEFAULT_SIGMA,
) -> float | None:
    """P(first team wins), in the YES frame the book is quoted in.

    Returns None without a pregame price rather than defaulting to a coin
    flip. A 50/50 prior on a game between a 0.68 team and a 0.30 team is not a
    neutral assumption, it is a wrong one — and it is precisely the assumption
    that made hypothesis #16 look like a 6.8c edge before the confound check
    inverted it.
    """
    if pregame_price is None:
        return None
    if minutes_left <= 0:
        return 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)

    edge = pregame_margin_from_price(pregame_price, sigma)
    expected = margin + edge * (minutes_left / REGULATION_MINUTES)
    return float(stats.norm.cdf(expected / (sigma * math.sqrt(minutes_left))))


def parse_score(value: str | None) -> tuple[int, int] | None:
    """`"46-34"` -> `(46, 34)` = (first team, second team).

    The ordering is the venue's and it matches the market slug's first team —
    measured across 12 of 12 settled games, see `win_curve.py` and V19 in
    docs/findings.md. This is the frame the YES side is quoted in, so the
    margin computed from it is directly comparable to the book.
    """
    if not value or "-" not in value:
        return None
    try:
        a, b = value.split("-", 1)
        return int(a.strip()), int(b.strip())
    except ValueError:
        return None


# --------------------------------------------------------------------- #
# Assembling it from the tick stream
# --------------------------------------------------------------------- #


def build_live_fv(
    session, *, sigma: float = DEFAULT_SIGMA, within_hours: float = 6.0
) -> list[LiveFV]:
    """One row per currently-live moneyline.

    Reads only. No prediction is written, no order is built, nothing is sized.

    `within_hours` bounds on **`game_start_time`, not `captured_at`** — the
    same choice `core/board.py` documents. Bounding on when a row was last
    written would make a market vanish because its writer is slow rather than
    because its game is over. Widening it is how a past slate is inspected.
    """
    from sqlalchemy import text

    from core.api import _human_market  # label formatting lives with the UI

    rows = session.execute(text("""
        SELECT DISTINCT ON (market_slug)
               market_slug, event_slug, captured_at, event_period, event_score,
               best_bid, best_ask
        FROM market_snapshots
        WHERE sports_market_type = 'basketball_team_full_game_winner'
          AND is_live IS TRUE
          AND game_start_time >= now() - make_interval(hours => :hours)
        ORDER BY market_slug, captured_at DESC
    """), {"hours": int(within_hours)}).all()
    if not rows:
        return []

    slugs = [r.event_slug for r in rows]
    # When each live period was first observed, so elapsed time can be
    # interpolated. Taken per (event, period) rather than per market: every
    # market in a game shares one clock.
    starts = {
        (r.event_slug, r.event_period): r.first_seen
        for r in session.execute(text("""
            SELECT event_slug, event_period, min(captured_at) AS first_seen
            FROM market_snapshots
            WHERE is_live IS TRUE AND event_slug = ANY(:slugs)
              AND event_period IS NOT NULL
            GROUP BY event_slug, event_period
        """), {"slugs": slugs}).all()
    }
    pregame = {
        r.event_slug: (float(r.best_bid) + float(r.best_ask)) / 2.0
        for r in session.execute(text("""
            SELECT DISTINCT ON (event_slug) event_slug, best_bid, best_ask
            FROM market_snapshots
            WHERE sports_market_type = 'basketball_team_full_game_winner'
              AND is_live IS FALSE AND event_score = '0-0'
              AND best_bid IS NOT NULL AND best_ask IS NOT NULL
              AND best_ask > best_bid
              AND event_slug = ANY(:slugs)
            ORDER BY event_slug, captured_at DESC
        """), {"slugs": slugs}).all()
    }

    out: list[LiveFV] = []
    for r in rows:
        score = parse_score(r.event_score)
        if score is None:
            continue
        first_points, second_points = score
        margin = first_points - second_points

        started = starts.get((r.event_slug, r.event_period))
        seconds_in = (
            (r.captured_at - started).total_seconds() if started else 0.0
        )
        clock = minutes_remaining(r.event_period, seconds_into_period=seconds_in)
        minutes_left, is_estimate, note = (
            clock.minutes_left, clock.is_estimate, clock.note)

        pre = pregame.get(r.event_slug)
        # Suppressed rather than rendered as a step function: see `Clock`.
        # A blank cell is a worse-looking screen and a more honest one than
        # "1.000" on a three-point game.
        fv = (
            fair_value(margin=margin, minutes_left=minutes_left,
                       pregame_price=pre, sigma=sigma)
            if clock.usable else None
        )
        if pre is None:
            note = "; ".join(filter(None, [note, "no pregame quote — no fair value"]))

        out.append(LiveFV(
            event_slug=r.event_slug,
            market_slug=r.market_slug,
            label=_human_market(r.market_slug, "basketball_team_full_game_winner", None),
            period=r.event_period or "?",
            score=r.event_score or "?",
            margin=margin,
            minutes_left=minutes_left,
            minutes_left_is_estimate=is_estimate,
            pregame_price=pre,
            fair_value=fv,
            bid=float(r.best_bid) if r.best_bid is not None else None,
            ask=float(r.best_ask) if r.best_ask is not None else None,
            note=note or None,
        ))
    return sorted(out, key=lambda x: x.event_slug)


def as_dict(row: LiveFV) -> dict:
    """Serialise for the API. Note what is not here: no order, no size."""
    return {
        "event_slug": row.event_slug,
        "market_slug": row.market_slug,
        "label": row.label,
        "period": row.period,
        "score": row.score,
        "margin": row.margin,
        "minutes_left": round(row.minutes_left, 1),
        "minutes_left_is_estimate": row.minutes_left_is_estimate,
        "pregame_price": row.pregame_price,
        "fair_value": row.fair_value,
        "bid": row.bid,
        "ask": row.ask,
        "mid": row.mid,
        "gap": row.gap,
        "highlight": row.highlight,
        "note": row.note,
    }
