"""Live fair value for in-game TOTALS rungs. **Display only.**

Companion to [`core/live_fv.py`](live_fv.py), which does the same for
moneylines. Same rules: no gate, no order path, `UNVALIDATED` on the label.

Why totals and not something else
---------------------------------
The hand-trade audit found exactly one measured-positive pocket in the user's
own trading — **live totals, +9.4% over n=31, descriptive**. What was missing
there was not a button but a number: a live fair value to hold a price against.
This is that number. Its validation is the user looking at it against a real
game, not a gate.

The model
---------
Start from the v4 **pregame** projection, then update it by how far actual
scoring has diverged from what that projection expected by now:

    expected_so_far = pregame_mu * share(elapsed)
    surprise        = total_so_far - expected_so_far
    projected_final = pregame_mu + b(elapsed) * surprise
    P(Over line)    = 1 - Phi((line - projected_final) / sigma(elapsed))

**Never extrapolate raw pace.** `total_so_far * 40/elapsed` implies a 320-point
game from 12-12 after three minutes. The surprise form cannot do that: it moves
the projection by a *fraction* of the divergence and keeps the pregame anchor.


Two numbers in the original skeleton were wrong, and both are fixed here
------------------------------------------------------------------------
Fitted 2026-08-07 from the same 787 completed games as
[win-curve.md](../docs/math/win-curve.md), by regressing final total on the
cumulative total at each period boundary.

**1. The 1.32 coefficient is a Q1 number, not a constant.** It reproduces
exactly at Q1 (fitted **1.318** against the project's long-standing 1.32,
which is a useful check that this fit is the same one), but it decays:

    end Q1   b = 1.318
    half     b = 1.208
    end Q3   b = 1.128
    final    b = 1.000  (everything is banked; nothing is left to inform)

That shape is forced, not fitted-in: a point already scored is worth 1.0 on the
final by arithmetic, plus whatever it says about the scoring still to come. As
the game runs out the second term goes to zero. Using 1.32 at the half would
over-weight the surprise by ~9%, and at end-Q3 by ~17%.

**2. The win curve's sigmas are MARGIN sigmas and do not apply to totals.**
2.98 / 2.77 / 2.40 describe P(win | margin) — the distribution of the score
*difference*. Totals are a different quantity: the model's own pregame total
sigma is ~19 where the full-game margin sd is ~16.6. Fitting the totals
analogue properly gives residual sd of the final total:

    end Q1   15.88     (2.899 per sqrt-minute-remaining)
    half     13.03     (2.914)
    end Q3    9.67     (3.059)

Note the direction. Per sqrt-minute the margin sigma **decays** through the
game (2.98 -> 2.40) while the totals sigma is **flat to slightly rising**
(2.90 -> 3.06). Borrowing the margin numbers would have understated remaining
totals uncertainty by ~27% at end-Q3 — overconfidence at exactly the point in a
game where someone would act on the number.

So this module uses **fitted totals residual sd directly**, per period, rather
than imposing a sqrt-t law on top of a borrowed constant. The sqrt-t column
above is printed only to show that it does not hold.

**3. Quarters are near-uniform, and the shares are measured anyway.** Share of
regulation scoring: Q1 0.2541, Q2 0.2481, Q3 0.2544, Q4 0.2434. Close enough to
25% that `elapsed/40` would have been defensible; using the measured cumulative
shares is free and removes a known ~1-point bias at end-Q3.

The anchor
----------
`pregame_mu` is v4's own projected total, recovered by fitting a normal to the
**model's** pregame probability ladder for that game
([`fit_ladder`](../strategies/wnba_totals/model/curve_fit.py), the method in
[ladder-curve-fit.md](../docs/math/ladder-curve-fit.md)).

Inverting a single rung with an assumed sigma does **not** work and was tried
first: the recovered projection drifts 3.99 points across the ladder in every
game, because the stored probabilities carry v4's post-shrinkage effective
sigma (~20.75 measured) rather than the config's 19. Fitting the whole ladder
recovers both parameters and gives r^2 = 1.000 on every game.

Frames
------
**YES = OVER** on a totals market (V14, verified across 490 settled markets).
So `P(Over line)` is directly the YES-side price and compares to the book
without conversion. An UNDER position is `1 - FV`, which is what
`core/ev_guard.py` does in the position's own cost frame.

Overtime
--------
Suppressed. A regulation projection cannot price a game that is still adding
points past 40 minutes, and the surprise coefficient is defined on regulation
scoring. Same treatment as the moneyline strip.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass

import structlog
from scipy import stats

from core.live_fv import REGULATION_MINUTES, Clock, minutes_remaining, parse_score

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Fitted 2026-08-07 on 787 completed games with quarter scores.
#:
#: (elapsed_minutes, cumulative share of regulation scoring, surprise
#:  coefficient b, residual sd of the final total)
#:
#: The endpoints are not fitted, they are forced: at elapsed 0 nothing has been
#: observed so the projection is the pregame one and its sd is the pregame
#: total sd; at elapsed 40 every point is banked so b = 1 and nothing is left
#: to be uncertain about.
TOTALS_ANCHORS: tuple[tuple[float, float, float, float], ...] = (
    (0.0,  0.0000, 1.318, 19.00),
    (10.0, 0.2541, 1.318, 15.88),
    (20.0, 0.5022, 1.208, 13.03),
    (30.0, 0.7566, 1.128,  9.67),
    (40.0, 1.0000, 1.000,  0.00),
)

#: How far apart FV and the market must be before the gap is coloured. Same as
#: the moneyline strip, for the same reason: below this the difference is
#: inside the noise the formula carries anyway.
GAP_HIGHLIGHT = 0.03

#: A rung this far outside the band is not quotable and its "gap" is noise.
MIN_MID, MAX_MID = 0.02, 0.98


def _interp(elapsed: float, index: int) -> float:
    """Linear interpolation of an anchor column against elapsed minutes."""
    e = min(max(elapsed, 0.0), REGULATION_MINUTES)
    for (e0, *c0), (e1, *c1) in zip(TOTALS_ANCHORS, TOTALS_ANCHORS[1:]):
        if e0 <= e <= e1:
            if e1 == e0:
                return c0[index]
            w = (e - e0) / (e1 - e0)
            return c0[index] * (1.0 - w) + c1[index] * w
    return TOTALS_ANCHORS[-1][index + 1]


def expected_share(elapsed_minutes: float) -> float:
    """Fraction of a game's regulation scoring expected by `elapsed`."""
    return _interp(elapsed_minutes, 0)


def surprise_coefficient(elapsed_minutes: float) -> float:
    """How much of a point of over/under-scoring carries to the final."""
    return _interp(elapsed_minutes, 1)


def remaining_sigma(elapsed_minutes: float) -> float:
    """Residual sd of the final total, given what has been scored."""
    return _interp(elapsed_minutes, 2)


def project_total(
    *, pregame_mu: float, total_so_far: int, elapsed_minutes: float
) -> float:
    """The updated projection for the final total.

    Anchored on the pregame projection and moved by a *fraction* of the
    divergence from it — never by extrapolating the observed rate.
    """
    expected = pregame_mu * expected_share(elapsed_minutes)
    surprise = total_so_far - expected
    return pregame_mu + surprise_coefficient(elapsed_minutes) * surprise


def over_probability(
    *, projected_total: float, line: float, sigma: float
) -> float:
    """P(final total > line). This is the YES side (V14: YES = OVER).

    At sigma 0 the game is over and the answer is a step function rather than
    a division by zero.
    """
    if sigma <= 0:
        return 1.0 if projected_total > line else (0.0 if projected_total < line else 0.5)
    return float(1.0 - stats.norm.cdf((line - projected_total) / sigma))


# --------------------------------------------------------------------- #
# Assembling it
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class TotalsFV:
    """One live totals rung, model and market side by side."""

    event_slug: str
    market_slug: str
    label: str
    line: float
    period: str
    score: str
    total_so_far: int
    elapsed_minutes: float
    minutes_left: float
    minutes_left_is_estimate: bool
    pregame_mu: float | None
    projected_total: float | None
    sigma: float | None
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
        """fair value − market mid, both YES/OVER frame."""
        m, fv = self.mid, self.fair_value
        return None if (m is None or fv is None) else fv - m

    @property
    def highlight(self) -> bool:
        g = self.gap
        return g is not None and abs(g) > GAP_HIGHLIGHT


def pregame_totals_anchor(session) -> dict[str, float]:
    """v4's pregame projected total per game, from its own probability ladder.

    Fitted rather than inverted from one rung — see the module docstring for
    why a single-rung inversion drifts 3.99 points across the ladder.
    """
    from sqlalchemy import text

    from strategies.wnba_totals.model.curve_fit import fit_ladder

    # DISTINCT ON per market, NOT `predicted_at = max(predicted_at)`.
    #
    # That global-max shape is the exact bug `core/board.py` was written to
    # kill, and it bites harder here: once a game tips off, the prediction
    # logger stops pricing it (live markets are unpriceable pregame), so the
    # game falls out of the newest run — and the anchor would disappear at
    # precisely the moment the live FV needs it. Taking each market's own most
    # recent prediction keeps the pregame number available all game.
    rows = session.execute(text("""
        SELECT DISTINCT ON (market_slug) event_slug, market_slug, line,
               model_probability
        FROM predictions
        WHERE sports_market_type = 'basketball_team_full_game_total'
          AND line IS NOT NULL AND model_probability IS NOT NULL
        ORDER BY market_slug, predicted_at DESC
    """)).all()

    ladders: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        ladders[r.event_slug].append((float(r.line), float(r.model_probability)))

    out: dict[str, float] = {}
    for event_slug, points in ladders.items():
        fit = fit_ladder(sorted(points))
        if fit.ok and fit.implied_mean is not None:
            out[event_slug] = float(fit.implied_mean)
    return out


def build_live_totals_fv(session, *, within_hours: float = 6.0) -> list[TotalsFV]:
    """One row per live totals rung. Reads only; builds no order."""
    from sqlalchemy import text

    from core.api import _human_market

    rows = session.execute(text("""
        SELECT DISTINCT ON (market_slug)
               market_slug, event_slug, captured_at, event_period, event_score,
               line, best_bid, best_ask
        FROM market_snapshots
        WHERE sports_market_type = 'basketball_team_full_game_total'
          AND is_live IS TRUE
          AND line IS NOT NULL
          AND game_start_time >= now() - make_interval(hours => :hours)
        ORDER BY market_slug, captured_at DESC
    """), {"hours": int(within_hours)}).all()
    if not rows:
        return []

    slugs = list({r.event_slug for r in rows})
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
    anchors = pregame_totals_anchor(session)

    out: list[TotalsFV] = []
    for r in rows:
        score = parse_score(r.event_score)
        if score is None:
            continue
        total_so_far = score[0] + score[1]

        started = starts.get((r.event_slug, r.event_period))
        seconds_in = (r.captured_at - started).total_seconds() if started else 0.0
        clock: Clock = minutes_remaining(r.event_period, seconds_into_period=seconds_in)
        elapsed = REGULATION_MINUTES - clock.minutes_left

        mu = anchors.get(r.event_slug)
        note = clock.note
        projected = sigma = fv = None
        if mu is None:
            note = "; ".join(filter(None, [note, "no v4 pregame ladder — no anchor"]))
        elif clock.usable:
            projected = project_total(pregame_mu=mu, total_so_far=total_so_far,
                                      elapsed_minutes=elapsed)
            sigma = remaining_sigma(elapsed)
            fv = over_probability(projected_total=projected,
                                  line=float(r.line), sigma=sigma)

        out.append(TotalsFV(
            event_slug=r.event_slug, market_slug=r.market_slug,
            label=_human_market(r.market_slug, "basketball_team_full_game_total",
                                float(r.line)),
            line=float(r.line), period=r.event_period or "?",
            score=r.event_score or "?", total_so_far=total_so_far,
            elapsed_minutes=elapsed, minutes_left=clock.minutes_left,
            minutes_left_is_estimate=clock.is_estimate,
            pregame_mu=mu, projected_total=projected, sigma=sigma, fair_value=fv,
            bid=float(r.best_bid) if r.best_bid is not None else None,
            ask=float(r.best_ask) if r.best_ask is not None else None,
            note=note or None,
        ))
    return sorted(out, key=lambda x: (x.event_slug, x.line))


def as_dict(row: TotalsFV) -> dict:
    """Serialise for the API. No order, no size — same as the ML strip."""
    return {
        "event_slug": row.event_slug,
        "market_slug": row.market_slug,
        "label": row.label,
        "line": row.line,
        "period": row.period,
        "score": row.score,
        "total_so_far": row.total_so_far,
        "minutes_left": round(row.minutes_left, 1),
        "minutes_left_is_estimate": row.minutes_left_is_estimate,
        "pregame_mu": None if row.pregame_mu is None else round(row.pregame_mu, 1),
        "projected_total": (None if row.projected_total is None
                            else round(row.projected_total, 1)),
        "sigma": None if row.sigma is None else round(row.sigma, 2),
        "fair_value": row.fair_value,
        "bid": row.bid,
        "ask": row.ask,
        "mid": row.mid,
        "gap": row.gap,
        "highlight": row.highlight,
        "note": row.note,
    }
