"""Historical live win probability, and hypothesis #16.

Two things live here because they are one measurement used twice.

**The curve** — P(win | margin, minutes remaining), fitted from the 787
completed games in `team_game_logs` that carry quarter-by-quarter scores. This
is the first live model this project has had. Everything before it was pregame.

**Hypothesis #16** — *"in tight games the market prices the trailing team's
live win probability below the historical base rate."* Origin, 2026-08-06:
*"i took IND to win at 30% when they were down just 5 in a tight game...
cashed at 45."* The only hypothesis in the ledger with live money attached to
its origin, which is a reason to test it carefully rather than a reason to
believe it.

Read [pulse-hypotheses.md](../../docs/pulse-hypotheses.md) rows 15 and 16
first. Note what is already dead: #1, #3, #4 and #7 all FAILED gated tests on
2026-08-06. **The fade family is closed.** This is not a fade — it does not
claim the price overshoots and comes back; it claims the price sits at a level
the historical base rate disagrees with, at a moment when the base rate is
unusually well determined.


PRE-REGISTERED GATE — fixed before any number was computed
----------------------------------------------------------
Stated in the ledger row for #16 and copied here verbatim, 2026-08-07.

    PASS  requires ALL of:
      (1) mean (historical P - market-implied P) for the trailing team > 0.02
      (2) the 95% confidence interval on that mean, clustered by game,
          excludes zero
      (3) observations spread across >= 10 distinct games

    FAIL  if (3) is met but (1) or (2) is not.

    NO DATA  if (3) is not met. Zero observations is NOT a null result.

**Verdict language is used only if the gate is met.** Below 10 games the
report says NO DATA and states what is missing.

Note (1) and (2) are not redundant: a 2c mean with an interval spanning zero
is noise of the right size, and an interval excluding zero at a 0.5c mean is a
real effect too small to trade. Both have happened in this project.


Why period boundaries, and only period boundaries
-------------------------------------------------
`market_snapshots` carries `event_score` and `event_period` and **no game
clock**. Minutes remaining is therefore unknown at a general tick — which
would put an unmeasured error straight into the denominator of the curve.

At the instant `event_period` increments, the clock is 0 for the period that
just ended, so minutes remaining is *exactly* 30, 20 or 10. The comparison is
restricted to those three instants per game because they are the only ones
where the historical curve can be evaluated without guessing. This is a
constraint on the data, and it is the reason the sample is ~3 observations per
game rather than thousands.


Side conventions — measured, not assumed
----------------------------------------
This is the V14/V15 hazard and it decides the sign of every number below.

**`event_score` is `first_team-second_team`**, where "first team" is the team
named first in the market slug — the side the market is quoted from, which is
*not* necessarily the away team. **YES on a winner market = the first team
wins.**

Verified 2026-08-07 against all 12 finished games with both a final
`event_score` and a settled winner-market price: in **12 of 12**, the sign of
`A - B` agrees with whether YES settled near 1. Had `event_score` been
home-first while the slug was quoted away-first, roughly half would disagree.
See `docs/findings.md` V19.

So the market-implied probability for the **trailing** team is:

    trailing team is the first team   ->  P_market = mid
    trailing team is the second team  ->  P_market = 1 - mid

`test_win_curve.py` pins both branches. Getting this backwards inverts the
hypothesis into its own negation and every intermediate number still looks
plausible.

    python -m core.pulse.win_curve
    python -m core.pulse.win_curve --teams        # ungated per-team table
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from scipy import stats
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.quote.adverse_selection import clustered_mean
from core.storage import MarketSnapshot, TeamGameLog

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

# --------------------------------------------------------------------- #
# The game's shape. WNBA: four 10-minute quarters.
# --------------------------------------------------------------------- #

QUARTER_MINUTES = 10.0
REGULATION_MINUTES = 40.0

#: The three instants where minutes-remaining is exactly known.
#: (label, period that just ended, minutes remaining after it)
BOUNDARIES: tuple[tuple[str, str, float], ...] = (
    ("end Q1", "Q1", 30.0),
    ("half", "Q2", 20.0),
    ("end Q3", "Q3", 10.0),
)

#: Absolute-margin buckets. Pre-registered; #16 concerns trailing by 1-9, so
#: the first three are the ones the gate can see and 10+ is context.
BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("1-3", 1, 3),
    ("4-6", 4, 6),
    ("7-9", 7, 9),
    ("10+", 10, 10_000),
)

#: The rule of thumb this fit is reported against: sd of the remaining margin
#: swing is ~2.0 points per sqrt(minute).
RULE_OF_THUMB_SIGMA = 2.0

Z95 = 1.96

#: Median mid over this window before a period increment, rather than the
#: single last tick. 30s is `adverse_selection.DEFAULT_HORIZON_SECONDS`,
#: pre-registered there; reusing it avoids inventing a fourth constant. The
#: single-last-tick version is reported alongside as a robustness line.
MID_WINDOW_SECONDS = 30.0

# -- the gate --------------------------------------------------------- #
GATE_MIN_EDGE = 0.02
GATE_MIN_GAMES = 10


def wilson(wins: int, n: int) -> tuple[float, float, float] | None:
    """Wilson score interval for a rate. `(p, lo, hi)`.

    Wilson rather than the normal approximation: several cells below are in
    the tens, where the normal interval runs past 0 or 1 and reads as
    precision that is not there.
    """
    if n == 0:
        return None
    p = wins / n
    z2 = Z95 * Z95
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bucket_of(margin: int) -> str | None:
    """Bucket label for an absolute margin. None for a tied game."""
    m = abs(margin)
    if m == 0:
        return None
    for label, lo, hi in BUCKETS:
        if lo <= m <= hi:
            return label
    return None


# --------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class GameState:
    """One team's position at one period boundary of one completed game."""

    espn_game_id: str
    team: str
    opponent: str
    is_home: bool
    boundary: str            # 'end Q1' | 'half' | 'end Q3'
    minutes_left: float
    margin: int              # this team's points minus opponent's, so far
    won: bool

    @property
    def bucket(self) -> str | None:
        return bucket_of(self.margin)

    @property
    def is_trailing(self) -> bool:
        return self.margin < 0


def load_history(session: Session) -> list[GameState]:
    """Every (team, boundary) state from completed games with quarter scores.

    Both sides of each game are emitted. That is deliberate and it is what
    makes the league table exactly symmetric — P(win | lead k) and
    P(win | trail k) are the same games seen from opposite ends, so they sum
    to 1 by construction rather than by luck. It also means the **games**, not
    the rows, are the sample: 787 games produce 4,722 states.
    """
    rows = session.scalars(
        select(TeamGameLog).where(
            TeamGameLog.is_completed.is_(True),
            TeamGameLog.q1.is_not(None),
            TeamGameLog.q2.is_not(None),
            TeamGameLog.q3.is_not(None),
        )
    ).all()

    by_game: dict[str, list[TeamGameLog]] = defaultdict(list)
    for r in rows:
        by_game[r.espn_game_id].append(r)

    out: list[GameState] = []
    for game_id, sides in by_game.items():
        if len(sides) != 2:
            # A half-recorded game cannot produce a margin. Skipped, counted
            # by the caller rather than silently dropped.
            continue
        for team, opp in ((sides[0], sides[1]), (sides[1], sides[0])):
            if team.points_scored is None or team.points_allowed is None:
                continue
            if team.points_scored == team.points_allowed:
                continue  # no ties in basketball; a tie here is bad data
            won = team.points_scored > team.points_allowed
            cum_team = 0
            cum_opp = 0
            for label, period, minutes_left in BOUNDARIES:
                idx = {"Q1": "q1", "Q2": "q2", "Q3": "q3"}[period]
                tq, oq = getattr(team, idx), getattr(opp, idx)
                if tq is None or oq is None:
                    break
                cum_team += tq
                cum_opp += oq
                out.append(GameState(
                    espn_game_id=game_id,
                    team=team.team_abbrev or "?",
                    opponent=team.opponent_abbrev or "?",
                    is_home=bool(team.is_home),
                    boundary=label,
                    minutes_left=minutes_left,
                    margin=cum_team - cum_opp,
                    won=won,
                ))
    return out


# --------------------------------------------------------------------- #
# The league curve
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Cell:
    boundary: str
    bucket: str
    trailing: bool
    n: int
    wins: int

    @property
    def rate(self) -> float:
        return self.wins / self.n if self.n else float("nan")

    @property
    def ci(self) -> tuple[float, float, float] | None:
        return wilson(self.wins, self.n)


def build_cells(states: list[GameState]) -> dict[tuple[str, str, bool], Cell]:
    counts: dict[tuple[str, str, bool], list[int]] = defaultdict(lambda: [0, 0])
    for s in states:
        b = s.bucket
        if b is None:
            continue
        key = (s.boundary, b, s.is_trailing)
        counts[key][0] += 1
        counts[key][1] += int(s.won)
    return {
        k: Cell(boundary=k[0], bucket=k[1], trailing=k[2], n=v[0], wins=v[1])
        for k, v in counts.items()
    }


@dataclass(frozen=True)
class SigmaFit:
    """The per-sqrt-minute margin sigma implied by the empirical curve."""

    sigma: float
    n_points: int
    r_squared: float
    #: (minutes_left, mean margin, empirical P, implied sigma) per cell used.
    points: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def vs_rule_of_thumb(self) -> float:
        return self.sigma / RULE_OF_THUMB_SIGMA


def fit_sigma(states: list[GameState]) -> SigmaFit | None:
    r"""Fit sigma in P(win) = Phi(margin / (sigma * sqrt(minutes_left))).

    Inverting, :math:`\Phi^{-1}(P) = \frac{m}{\sigma\sqrt{t}}`, which is a
    line through the origin in :math:`m/\sqrt{t}` with slope :math:`1/\sigma`.
    So this is a no-intercept least squares, weighted by cell count — the
    10+ bucket at end Q3 holds far more games than trailing-by-1-3 does, and
    an unweighted fit would let the thinnest cells set the slope.

    Cells at P=0 or P=1 are dropped: `Phi^{-1}` is infinite there and they
    carry no usable information about the scale.
    """
    # Group by (boundary, exact margin) so the regressor is a real margin
    # rather than a bucket midpoint.
    groups: dict[tuple[float, int], list[int]] = defaultdict(lambda: [0, 0])
    for s in states:
        if s.margin == 0:
            continue
        g = groups[(s.minutes_left, s.margin)]
        g[0] += 1
        g[1] += int(s.won)

    xs: list[float] = []
    ys: list[float] = []
    ws: list[float] = []
    points: list[tuple[float, float, float, float]] = []
    for (minutes_left, margin), (n, wins) in sorted(groups.items()):
        p = wins / n
        if p <= 0.0 or p >= 1.0:
            continue
        x = margin / math.sqrt(minutes_left)
        y = float(stats.norm.ppf(p))
        xs.append(x)
        ys.append(y)
        ws.append(float(n))
        points.append((minutes_left, float(margin), p, margin / (math.sqrt(minutes_left) * y)))

    if len(xs) < 3:
        return None

    # Weighted no-intercept least squares: slope = sum(w x y) / sum(w x^2).
    sxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))
    sxx = sum(w * x * x for w, x in zip(ws, xs))
    if sxx == 0:
        return None
    slope = sxy / sxx
    if slope <= 0:
        return None
    sigma = 1.0 / slope

    ss_res = sum(w * (y - slope * x) ** 2 for w, x, y in zip(ws, xs, ys))
    ss_tot = sum(w * y * y for w, y in zip(ws, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")

    return SigmaFit(sigma=sigma, n_points=len(xs), r_squared=r2, points=points)


def pregame_margin_from_price(price: float, sigma: float) -> float:
    """Invert a pregame moneyline price into an expected full-game margin.

    :math:`p = \\Phi(E / (\\sigma\\sqrt{40}))`, so
    :math:`E = \\sigma\\sqrt{40}\\,\\Phi^{-1}(p)`. Clamped away from 0 and 1,
    where the inverse is infinite and a 1c quote would imply a 40-point
    favourite.
    """
    p = min(max(price, 0.01), 0.99)
    return sigma * math.sqrt(REGULATION_MINUTES) * float(stats.norm.ppf(p))


def anchored_probability(
    margin: float, minutes_left: float, sigma: float, pregame_price: float
) -> float:
    """P(win) for a team, starting from what the market thought pregame.

    This is the league curve with the origin moved: instead of assuming two
    equal teams, it carries the pregame price forward, decayed by how much of
    the game is left.

        P = Phi( (margin + E * minutes_left / 40) / (sigma * sqrt(minutes_left)) )

    where `E` is the pregame expected margin implied by `pregame_price`.

    **This is the confound check for hypothesis #16, and it is not optional.**
    The empirical cells are team-blind: they say a team trailing by 1 at the
    half wins 42% of the time, averaged over every team that has ever trailed
    by 1. The market knows *which* team it is. Measured on this sample, the
    largest apparent edges are all games where the trailing side was a heavy
    pregame underdog (LA at 0.085, TOR at 0.125), so a team-blind base rate
    will call the price wrong precisely when the price is most right.

    It is also the formula the live FV strip renders (`core/live_fv.py`).
    """
    e = pregame_margin_from_price(pregame_price, sigma)
    expected = margin + e * (minutes_left / REGULATION_MINUTES)
    if minutes_left <= 0:
        return 1.0 if expected > 0 else (0.0 if expected < 0 else 0.5)
    return float(stats.norm.cdf(expected / (sigma * math.sqrt(minutes_left))))


def curve_probability(margin: float, minutes_left: float, sigma: float) -> float:
    """P(win) for a team `margin` points up with `minutes_left` to play.

    At `minutes_left == 0` the game is decided, so the step function is the
    honest answer rather than a division by zero.
    """
    if minutes_left <= 0:
        return 1.0 if margin > 0 else (0.0 if margin < 0 else 0.5)
    return float(stats.norm.cdf(margin / (sigma * math.sqrt(minutes_left))))


# --------------------------------------------------------------------- #
# Per-team deviation — ledger #15, UNGATED
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class TeamDeviation:
    team: str
    n: int
    observed: float          # actual win rate across its states
    expected: float          # league curve's prediction for the same states
    raw: float               # observed - expected
    shrunk: float            # raw pulled toward 0 by the shrinkage weight
    weight: float            # how much of `raw` survived
    win_rate: float          # the team's overall win rate in this sample
    expected_strength: float # expectation once team strength is anchored out
    raw_strength: float      # observed - expected_strength
    shrunk_strength: float   # ... shrunk


def team_deviations(
    states: list[GameState], sigma: float, *, prior_strength: float = 200.0
) -> list[TeamDeviation]:
    """Per-team departure from the league curve, shrunk toward zero.

    **This is reported ungated and should be read as a diagnostic, not a
    finding.** Two reasons, both in ledger row #15 and both load-bearing:

    1. Thirteen teams with a few dozen blown-lead events each is not enough to
       separate a trait from noise. The shrinkage weight `n / (n + k)` with
       `k = 200` states is what stops a team with 40 observations reading as a
       10-point effect. `k` is not fitted — it is roughly the number of states
       one full season of one team produces, so a team needs about a season
       before its own record outweighs the league's.
    2. Even a real trait is not tradable unless the *price* fails to know it.
       The market watches the same games. This measures the trait, which is
       the easy half.

    **Two expectation columns, and the second is the one to read.** The
    league curve is team-blind, so `raw` against it is dominated by how good
    the team is, not by how it holds leads: a team that wins 74% of its games
    beats a 50/50-anchored curve in every state, leading or trailing, and the
    column just reproduces the standings. `raw_strength` anchors the curve on
    the team's own win rate first — the same correction the hypothesis-16
    confound check applies — so what is left is departure from *its own*
    baseline, which is what ledger #15 actually asks.

    The strength anchor is the team's win rate over this same sample, so it is
    in-sample and biased toward zero. It is a diagnostic, not a fit.
    """
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for s in states:
        if s.margin == 0:
            continue
        a = agg[s.team]
        a[0] += 1.0
        a[1] += float(s.won)
        a[2] += curve_probability(s.margin, s.minutes_left, sigma)

    # A team's win rate over distinct games, not over states: three boundaries
    # of one game are one win, counted once.
    games: dict[str, dict[str, bool]] = defaultdict(dict)
    for s in states:
        games[s.team][s.espn_game_id] = s.won
    win_rate = {
        team: (sum(v.values()) / len(v) if v else 0.5) for team, v in games.items()
    }

    anchored: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for s in states:
        if s.margin == 0:
            continue
        a = anchored[s.team]
        a[0] += 1.0
        a[1] += anchored_probability(
            s.margin, s.minutes_left, sigma, win_rate.get(s.team, 0.5))

    out: list[TeamDeviation] = []
    for team, (n, wins, exp) in agg.items():
        if n == 0:
            continue
        observed = wins / n
        expected = exp / n
        raw = observed - expected
        weight = n / (n + prior_strength)
        an_n, an_sum = anchored[team]
        expected_strength = an_sum / an_n if an_n else expected
        raw_strength = observed - expected_strength
        out.append(TeamDeviation(
            team=team, n=int(n), observed=observed, expected=expected,
            raw=raw, shrunk=raw * weight, weight=weight,
            win_rate=win_rate.get(team, 0.5),
            expected_strength=expected_strength,
            raw_strength=raw_strength,
            shrunk_strength=raw_strength * weight,
        ))
    return sorted(out, key=lambda d: d.shrunk_strength)


# --------------------------------------------------------------------- #
# Hypothesis #16 — the live comparison
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class BoundaryQuote:
    """The market's last word before a period ended."""

    event_slug: str
    boundary: str
    minutes_left: float
    #: Score as the venue reports it: first team, second team.
    first_points: int
    second_points: int
    mid_window: float        # median mid over the final MID_WINDOW_SECONDS
    mid_last: float          # the single last two-sided quote
    spread: float
    n_ticks: int

    @property
    def first_is_trailing(self) -> bool:
        return self.first_points < self.second_points

    @property
    def trailing_margin(self) -> int:
        """Negative: how far the trailing team is behind."""
        return -abs(self.first_points - self.second_points)

    def market_p_trailing(self, *, use_window: bool = True) -> float:
        """Market-implied win probability for the TRAILING team.

        The mid is quoted on the YES side, and YES = the first team wins
        (see the module docstring, and V19 in docs/findings.md). So the
        trailing team's implied probability is the mid itself only when the
        first team is the one trailing, and `1 - mid` otherwise.

        Inverting this branch turns the hypothesis into its own negation while
        every intermediate number stays in [0, 1]. `test_win_curve.py` pins
        both directions.
        """
        mid = self.mid_window if use_window else self.mid_last
        return mid if self.first_is_trailing else 1.0 - mid


def load_boundary_quotes(session: Session) -> tuple[list[BoundaryQuote], dict[str, int]]:
    """The last moneyline quote before each period increment, per game.

    Returns the quotes and a tally of why candidates were dropped, because
    "no observations" and "every observation was unusable" call for different
    responses and the difference must not be invisible.
    """
    skips: dict[str, int] = defaultdict(int)

    rows = session.execute(text("""
        SELECT event_slug, market_slug, captured_at, event_period, event_score,
               best_bid, best_ask
        FROM market_snapshots
        WHERE sports_market_type = 'basketball_team_full_game_winner'
          AND is_live IS TRUE
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND event_score IS NOT NULL
          AND event_period IS NOT NULL
        ORDER BY event_slug, captured_at
    """)).all()

    by_game: dict[str, list] = defaultdict(list)
    for r in rows:
        by_game[r.event_slug].append(r)

    out: list[BoundaryQuote] = []
    for event_slug, ticks in by_game.items():
        # Walk forward and cut where the period label changes.
        for label, period, minutes_left in BOUNDARIES:
            in_period = [t for t in ticks if t.event_period == period]
            if not in_period:
                skips[f"no ticks in {period}"] += 1
                continue
            last = in_period[-1]

            # Everything after this instant must be a *later* period, or the
            # label is not a boundary at all — it is a gap in the stream.
            after = [t for t in ticks if t.captured_at > last.captured_at]
            if not after:
                skips[f"{period} never incremented (game ended or stream cut)"] += 1
                continue

            score = _parse_score(last.event_score)
            if score is None:
                skips["unparseable score at the boundary"] += 1
                continue
            first_points, second_points = score
            if first_points == second_points:
                skips["tied at the boundary (no trailing team)"] += 1
                continue

            window = [
                t for t in in_period
                if (last.captured_at - t.captured_at).total_seconds() <= MID_WINDOW_SECONDS
                and float(t.best_ask) > float(t.best_bid)
            ]
            if not window:
                skips["no two-sided quote in the final 30s"] += 1
                continue

            mids = sorted((float(t.best_bid) + float(t.best_ask)) / 2.0 for t in window)
            mid_window = mids[len(mids) // 2]
            mid_last = (float(last.best_bid) + float(last.best_ask)) / 2.0
            spread = float(last.best_ask) - float(last.best_bid)

            out.append(BoundaryQuote(
                event_slug=event_slug, boundary=label, minutes_left=minutes_left,
                first_points=first_points, second_points=second_points,
                mid_window=mid_window, mid_last=mid_last, spread=spread,
                n_ticks=len(window),
            ))
    return out, dict(skips)


def load_pregame_prices(session: Session) -> dict[str, float]:
    """Last two-sided winner-market mid per game while the score was still 0-0.

    YES frame, i.e. the probability of the *first* team winning. Used only for
    the anchored diagnostic; the gated comparison never touches it.
    """
    rows = session.execute(text("""
        SELECT DISTINCT ON (event_slug) event_slug, best_bid, best_ask
        FROM market_snapshots
        WHERE sports_market_type = 'basketball_team_full_game_winner'
          AND is_live IS FALSE
          AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND best_ask > best_bid
          AND event_score = '0-0'
        ORDER BY event_slug, captured_at DESC
    """)).all()
    return {
        r.event_slug: (float(r.best_bid) + float(r.best_ask)) / 2.0
        for r in rows
    }


def compare_anchored(
    quotes: list[BoundaryQuote],
    *,
    sigma: float,
    pregame: dict[str, float],
) -> list[Comparison]:
    """The confound check: base rate anchored on the pregame price.

    Games with no pregame quote are dropped rather than defaulted to 0.5 —
    defaulting would silently reinstate exactly the team-blindness this is
    built to remove.
    """
    out: list[Comparison] = []
    for q in quotes:
        margin = q.trailing_margin
        if not (-9 <= margin <= -1):
            continue
        pre_first = pregame.get(q.event_slug)
        if pre_first is None:
            continue
        # Work in the first team's frame, then convert to the trailing team's.
        margin_first = q.first_points - q.second_points
        p_first = anchored_probability(margin_first, q.minutes_left, sigma, pre_first)
        hist = p_first if q.first_is_trailing else 1.0 - p_first
        out.append(Comparison(
            quote=q, historical_p=hist, market_p=q.market_p_trailing(),
        ))
    return out


def _parse_score(value: str | None) -> tuple[int, int] | None:
    """`"46-34"` -> `(46, 34)` = (first team, second team). Else None."""
    if not value or "-" not in value:
        return None
    try:
        a, b = value.split("-", 1)
        return int(a.strip()), int(b.strip())
    except ValueError:
        return None


@dataclass(frozen=True)
class Comparison:
    """One boundary: what history says versus what the market charged."""

    quote: BoundaryQuote
    historical_p: float
    market_p: float

    @property
    def edge(self) -> float:
        """historical - market, for the trailing team. Positive = underpriced."""
        return self.historical_p - self.market_p


def empirical_probability(
    cells: dict[tuple[str, str, bool], Cell], boundary: str, margin: int
) -> float | None:
    """The observed base rate for this state, straight from the 787 games.

    **This is what the gate uses**, rather than the fitted curve, because
    "historical P" in the hypothesis means the rate that actually happened.
    The parametric curve is a smoothing of these cells and it visibly does not
    fit one sigma to all three boundaries (2.98 / 2.77 / 2.40 — see the sigma
    section of the report). Feeding that misfit into the comparison would
    charge the market for the model's shape error.

    The choice was made on the Part 1 misfit, before the hypothesis-16
    aggregate was computed; the fitted-curve version is reported alongside so
    the decision is visible rather than buried.
    """
    bucket = bucket_of(margin)
    if bucket is None:
        return None
    cell = cells.get((boundary, bucket, margin < 0))
    if cell is None or cell.n == 0:
        return None
    return cell.rate


def compare(
    quotes: list[BoundaryQuote],
    *,
    cells: dict[tuple[str, str, bool], Cell] | None = None,
    sigma: float | None = None,
    use_window: bool = True,
) -> list[Comparison]:
    """Trailing-by-1-to-9 states only, per the pre-registered hypothesis.

    Pass `cells` for the empirical base rate (the gated version) or `sigma`
    for the fitted curve (the robustness line). Exactly one is required.
    """
    if (cells is None) == (sigma is None):
        raise ValueError("pass exactly one of cells= (empirical) or sigma= (fitted)")

    out: list[Comparison] = []
    for q in quotes:
        margin = q.trailing_margin
        if not (-9 <= margin <= -1):
            continue
        if cells is not None:
            hist = empirical_probability(cells, q.boundary, margin)
            if hist is None:
                continue
        else:
            hist = curve_probability(margin, q.minutes_left, sigma)
        out.append(Comparison(
            quote=q,
            historical_p=hist,
            market_p=q.market_p_trailing(use_window=use_window),
        ))
    return out


# --------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------- #


@dataclass
class Study:
    states: list[GameState]
    cells: dict[tuple[str, str, bool], Cell]
    sigma: SigmaFit | None
    quotes: list[BoundaryQuote]
    skips: dict[str, int]
    #: Gated: historical P is the empirical base rate from the 787 games.
    comparisons: list[Comparison]
    #: Robustness: same, but the single last tick instead of the 30s median.
    comparisons_last_tick: list[Comparison]
    #: Robustness: historical P from the fitted sqrt-time curve instead.
    comparisons_fitted: list[Comparison]
    #: Confound check: base rate anchored on the pregame price. UNGATED, and
    #: the number that decides whether a PASS is tradable.
    comparisons_anchored: list[Comparison]
    deviations: list[TeamDeviation]
    #: Pregame YES-frame mid per game, for display in the observation table.
    pregame: dict[str, float] = field(default_factory=dict)

    @property
    def n_history_games(self) -> int:
        return len({s.espn_game_id for s in self.states})


def run_study(session: Session) -> Study:
    states = load_history(session)
    cells = build_cells(states)
    fit = fit_sigma(states)
    sigma = fit.sigma if fit else RULE_OF_THUMB_SIGMA
    quotes, skips = load_boundary_quotes(session)
    pregame = load_pregame_prices(session)
    return Study(
        states=states,
        cells=cells,
        sigma=fit,
        quotes=quotes,
        skips=skips,
        comparisons=compare(quotes, cells=cells, use_window=True),
        comparisons_last_tick=compare(quotes, cells=cells, use_window=False),
        comparisons_fitted=compare(quotes, sigma=sigma, use_window=True),
        comparisons_anchored=compare_anchored(
            quotes, sigma=sigma, pregame=pregame),
        deviations=team_deviations(states, sigma),
        pregame=pregame,
    )


def format_report(study: Study, *, show_teams: bool = False) -> str:
    out: list[str] = []
    add = out.append
    fit = study.sigma
    sigma = fit.sigma if fit else RULE_OF_THUMB_SIGMA

    add("LIVE WIN CURVE + HYPOTHESIS 16 — trailing-team ML underpricing")
    add("=" * 78)
    add(f"history                        : {study.n_history_games} completed games, "
        f"{len(study.states):,} team-states")
    add(f"boundaries                     : " + ", ".join(
        f"{lbl} ({m:.0f} min left)" for lbl, _, m in BOUNDARIES))
    add("")

    # ---- Part 1a: the league curve ---- #
    add("PART 1 — historical P(win | margin, period), league level")
    add("-" * 78)
    add("  Both sides of every game are counted, so lead and trail cells are the")
    add("  same games seen from opposite ends and sum to 1 by construction.")
    add("")
    add(f"  {'boundary':<9}{'bucket':>8}{'':>3}{'LEADING':>26}{'':>4}{'TRAILING':>26}")
    add(f"  {'':<9}{'':>8}{'':>3}{'n':>6}{'P(win)':>8}{'95% Wilson':>12}"
        f"{'':>4}{'n':>6}{'P(win)':>8}{'95% Wilson':>12}")
    for label, _, _ in BOUNDARIES:
        for bucket, _, _ in BUCKETS:
            lead = study.cells.get((label, bucket, False))
            trail = study.cells.get((label, bucket, True))
            def fmt(c: Cell | None) -> str:
                if c is None or c.n == 0:
                    return f"{'—':>6}{'—':>8}{'—':>12}"
                p, lo, hi = c.ci
                return f"{c.n:>6}{p:>8.3f}{f'[{lo:.3f},{hi:.3f}]':>12}"
            add(f"  {label:<9}{bucket:>8}{'':>3}{fmt(lead)}{'':>4}{fmt(trail)}")
    add("")

    # ---- Part 1b: sigma ---- #
    add("PART 1 — implied per-sqrt-minute sigma")
    add("-" * 78)
    if fit is None:
        add("  Not fitted — too few usable cells.")
    else:
        add(f"  model                        : P(win) = Phi( margin / (sigma * sqrt(minutes_left)) )")
        add(f"  fitted sigma                 : {fit.sigma:.3f} points per sqrt(minute)")
        add(f"  rule of thumb                : {RULE_OF_THUMB_SIGMA:.2f}")
        add(f"  ratio                        : {fit.vs_rule_of_thumb:.2f}x")
        add(f"  weighted R^2 (no intercept)  : {fit.r_squared:.3f} over "
            f"{fit.n_points} (boundary, margin) cells")
        add("")
        add("  Implied sigma by boundary, as a check that one sqrt(t) scale fits")
        add("  all three (if it drifts, the sqrt-time model is the wrong shape):")
        by_boundary: dict[float, list[float]] = defaultdict(list)
        for minutes_left, margin, p, implied in fit.points:
            if math.isfinite(implied) and implied > 0:
                by_boundary[minutes_left].append(implied)
        for label, _, minutes_left in BOUNDARIES:
            vals = sorted(by_boundary.get(minutes_left, []))
            if not vals:
                add(f"    {label:<8} —")
                continue
            med = vals[len(vals) // 2]
            add(f"    {label:<8} median implied sigma {med:5.2f}  (n={len(vals)} margins)")
        add("")
        add(f"  Total-game margin sd this implies: "
            f"{fit.sigma * math.sqrt(REGULATION_MINUTES):.1f} points over 40 minutes.")
    add("")

    # ---- Part 1c: per-team, ungated ---- #
    if show_teams:
        add("PART 1 — per-team deviation from the league curve (UNGATED, ledger #15)")
        add("-" * 78)
        add("  Diagnostic only. Shrunk by n/(n+200): a team needs about a season of")
        add("  states before its own record outweighs the league's. And a real trait")
        add("  is not tradable unless the PRICE fails to know it — the market watches")
        add("  the same games. This measures the easy half.")
        add("")
        add("  READ THE RIGHT-HAND COLUMNS. `vs league` compares each team to a")
        add("  team-blind curve, so it mostly reproduces the standings: a team that")
        add("  wins 74% of its games beats a 50/50 curve in every state, leading or")
        add("  trailing. `vs own strength` anchors the curve on the team's own win")
        add("  rate first, so what is left is departure from ITS OWN baseline —")
        add("  which is what 'holds leads badly' actually means.")
        add("")
        add(f"  {'team':<5}{'n':>5}{'win%':>7}{'obs':>7}"
            f"{'  |':>3}{'exp':>7}{'raw':>8}{'shrunk':>8}"
            f"{'  |':>3}{'exp':>7}{'raw':>8}{'shrunk':>8}")
        add(f"  {'':<5}{'':>5}{'':>7}{'':>7}{'  |':>3}{'--- vs league ---':>23}"
            f"{'  |':>3}{'- vs own strength -':>23}")
        for d in study.deviations:
            add(f"  {d.team:<5}{d.n:>5}{d.win_rate:>7.3f}{d.observed:>7.3f}"
                f"{'  |':>3}{d.expected:>7.3f}{d.raw:>+8.3f}{d.shrunk:>+8.3f}"
                f"{'  |':>3}{d.expected_strength:>7.3f}{d.raw_strength:>+8.3f}"
                f"{d.shrunk_strength:>+8.3f}")
        add("")
        if study.deviations:
            worst = study.deviations[0]
            best = study.deviations[-1]
            widest_league = max(abs(d.shrunk) for d in study.deviations)
            widest_strength = max(abs(d.shrunk_strength) for d in study.deviations)
            add(f"  Widest deviation, vs league       : "
                f"{widest_league * 100:.1f}c of win probability")
            add(f"  Widest deviation, vs own strength : "
                f"{widest_strength * 100:.1f}c  <- the honest number")
            add(f"  Extremes after strength control   : {worst.team} "
                f"{worst.shrunk_strength:+.3f} to {best.team} "
                f"{best.shrunk_strength:+.3f}")
            add("")
            add("  The strength anchor is each team's win rate over this same sample,")
            add("  so it is in-sample and biased toward zero. A deviation that is")
            add("  small here is small; one that is large would still need an")
            add("  out-of-sample test before it meant anything.")
        add("")

    # ---- Part 2: hypothesis 16 ---- #
    add("HYPOTHESIS 16 — is the trailing team underpriced?")
    add("-" * 78)
    add(f"  PRE-REGISTERED GATE (from the ledger row, fixed 2026-08-07)")
    add(f"    PASS requires mean (historical P - market P) > {GATE_MIN_EDGE:.2f},")
    add(f"    95% CI clustered by game excluding zero, across >= {GATE_MIN_GAMES} games.")
    add("")
    add(f"  boundary quotes recovered    : {len(study.quotes)} across "
        f"{len({q.event_slug for q in study.quotes})} games")
    add(f"  trailing by 1-9 (the sample) : {len(study.comparisons)} across "
        f"{len({c.quote.event_slug for c in study.comparisons})} games")
    if study.skips:
        add("  candidates dropped:")
        for reason, n in sorted(study.skips.items(), key=lambda kv: -kv[1]):
            add(f"    {reason:<52}: {n}")
    add("")

    if not study.comparisons:
        add("  VERDICT: NO DATA — no trailing-by-1-to-9 state was observed at any")
        add("  period boundary. Not a null result: the hypothesis was never tested.")
        return "\n".join(out)

    anchored_by_key = {
        (c.quote.event_slug, c.quote.boundary): c for c in study.comparisons_anchored
    }
    add("  Every observation")
    add("  `pre` is the trailing team's PREGAME price. `edge` is gated; `anch` is")
    add("  the same edge once the base rate starts from `pre` instead of 50/50.")
    add(f"  {'game':<24}{'boundary':<8}{'score':>8}{'marg':>6}{'pre':>7}"
        f"{'hist':>7}{'mkt':>7}{'edge':>8}{'anch':>8}")
    for c in sorted(study.comparisons, key=lambda x: (x.quote.event_slug, x.quote.boundary)):
        q = c.quote
        a = anchored_by_key.get((q.event_slug, q.boundary))
        pre = "—"
        if a is not None:
            # Back out the trailing team's pregame price for display.
            pre_first = study.pregame.get(q.event_slug)
            if pre_first is not None:
                p = pre_first if q.first_is_trailing else 1.0 - pre_first
                pre = f"{p:.3f}"
        add(f"  {q.event_slug.replace('wnba-', ''):<24}{q.boundary:<8}"
            f"{f'{q.first_points}-{q.second_points}':>8}{q.trailing_margin:>6}"
            f"{pre:>7}{c.historical_p:>7.3f}{c.market_p:>7.3f}{c.edge:>+8.3f}"
            f"{(f'{a.edge:+.3f}' if a else '—'):>8}")
    add("")

    by_game: dict[str, list[float]] = defaultdict(list)
    for c in study.comparisons:
        by_game[c.quote.event_slug].append(c.edge)
    edges = [x for v in by_game.values() for x in v]
    mean = sum(edges) / len(edges)
    cl = clustered_mean(by_game)
    n_games = len(by_game)

    add("  Result")
    add(f"    mean edge (historical - market) : {mean:+.4f}  ({mean * 100:+.2f}c)")
    if cl is not None:
        add(f"    95% CI, clustered by game       : [{cl.lo:+.4f}, {cl.hi:+.4f}]  "
            f"(G={cl.n_clusters}, df={cl.n_clusters - 1})")
    else:
        add("    95% CI, clustered by game       : n/a — fewer than 2 games")
    # Robustness: the single-last-tick mid instead of the 30s median.
    lt_by_game: dict[str, list[float]] = defaultdict(list)
    for c in study.comparisons_last_tick:
        lt_by_game[c.quote.event_slug].append(c.edge)
    lt = [x for v in lt_by_game.values() for x in v]
    if lt:
        lt_cl = clustered_mean(lt_by_game)
        lt_ci = f"[{lt_cl.lo:+.4f}, {lt_cl.hi:+.4f}]" if lt_cl else "n/a"
        add(f"    same, single last tick instead  : {sum(lt) / len(lt):+.4f}  {lt_ci}")
    fx_by_game: dict[str, list[float]] = defaultdict(list)
    for c in study.comparisons_fitted:
        fx_by_game[c.quote.event_slug].append(c.edge)
    fx = [x for v in fx_by_game.values() for x in v]
    if fx:
        fx_cl = clustered_mean(fx_by_game)
        fx_ci = f"[{fx_cl.lo:+.4f}, {fx_cl.hi:+.4f}]" if fx_cl else "n/a"
        add(f"    same, fitted curve not cells    : {sum(fx) / len(fx):+.4f}  {fx_ci}")
    add("    (The gate uses the empirical cells. The fitted-curve line is shown")
    add("     because the sqrt-time model does not hold one sigma across all")
    add("     three boundaries; if the two rows disagree, that misfit is why.)")
    add(f"    mean spread at the boundary     : "
        f"{sum(c.quote.spread for c in study.comparisons) / len(study.comparisons):.4f}")
    add("")

    # -- the confound check ---------------------------------------- #
    an_by_game: dict[str, list[float]] = defaultdict(list)
    for c in study.comparisons_anchored:
        an_by_game[c.quote.event_slug].append(c.edge)
    an = [x for v in an_by_game.values() for x in v]
    an_cl = clustered_mean(an_by_game) if an else None
    an_mean = sum(an) / len(an) if an else None

    add("  CONFOUND CHECK — base rate anchored on the pregame price (UNGATED)")
    if an_mean is None:
        add("    n/a — no pregame quote recovered for any game in the sample.")
    else:
        an_ci = f"[{an_cl.lo:+.4f}, {an_cl.hi:+.4f}]" if an_cl else "n/a"
        add(f"    mean edge, pregame-anchored    : {an_mean:+.4f}  "
            f"({an_mean * 100:+.2f}c)")
        add(f"    95% CI, clustered by game      : {an_ci}  "
            f"(n={len(an)}, G={len(an_by_game)})")
        add("")
        add("    The gated number compares the market against a base rate that does")
        add("    not know which teams are playing. This row moves the base rate's")
        add("    origin to the pregame price and asks the same question again. If")
        add("    the effect is the market pricing team strength that the league")
        add("    curve ignores, it lands near zero — or past it.")
    add("")

    add("  VERDICT")
    if n_games < GATE_MIN_GAMES:
        add(f"    NO DATA — {len(edges)} observations across {n_games} games, against")
        add(f"    a pre-registered minimum of {GATE_MIN_GAMES} games.")
        add(f"    Needs {GATE_MIN_GAMES - n_games} more games. This is NOT a null result:")
        add("    the comparison is built and will accrue.")
    elif cl is None:
        add("    NO DATA — too few clusters to form an interval.")
    elif mean > GATE_MIN_EDGE and cl.lo > 0:
        add(f"    PASS on the pre-registered terms — trailing teams price "
            f"{mean * 100:+.2f}c below")
        add(f"    the league base rate, 95% CI [{cl.lo:+.4f}, {cl.hi:+.4f}], "
            f"over {n_games} games.")
        # A PASS must never be readable without the confound beside it.
        if an_mean is not None and an_cl is not None and an_cl.hi < 0:
            add("")
            add("    *** AND IT IS NOT TRADABLE. ***")
            add(f"    Anchored on the pregame price the same states give "
                f"{an_mean * 100:+.2f}c,")
            add(f"    CI [{an_cl.lo:+.4f}, {an_cl.hi:+.4f}] — entirely BELOW zero. The sign")
            add("    flips. The gap is the league base rate not knowing which team is")
            add("    trailing, and the market does know: the largest apparent edges are")
            add("    all games where the trailing side was already a heavy pregame")
            add("    underdog. Buying it would be selling a correct price to a base")
            add("    rate that has never heard of the teams.")
            add("")
            add("    The gate is met and the gate was the wrong question. It compared a")
            add("    team-blind base rate against a team-aware price, so it could only")
            add("    ever have measured how often good teams trail bad ones. Recorded")
            add("    as PASS because that is what was pre-registered; recorded as")
            add("    NOT TRADABLE because that is what the number means.")
        elif an_mean is not None and an_cl is not None and an_cl.lo > 0:
            add("")
            add(f"    Survives the confound check: pregame-anchored {an_mean * 100:+.2f}c,")
            add(f"    CI [{an_cl.lo:+.4f}, {an_cl.hi:+.4f}], still above zero.")
            add("    Next step is out-of-sample games, not size.")
        else:
            add("")
            add("    The confound check does not resolve either way at this sample.")
            add("    Do not size on this until it does.")
    elif mean <= GATE_MIN_EDGE and cl.lo > 0:
        add(f"    FAIL — the effect is real but too small: {mean * 100:+.2f}c against a")
        add(f"    {GATE_MIN_EDGE * 100:.0f}c bar, CI [{cl.lo:+.4f}, {cl.hi:+.4f}].")
        add("    A confirmed phenomenon and not a trade.")
    else:
        add(f"    FAIL — mean {mean:+.4f} ({mean * 100:+.2f}c), 95% CI "
            f"[{cl.lo:+.4f}, {cl.hi:+.4f}]")
        add(f"    over {n_games} games. The interval does not exclude zero.")
    add("")
    add("  Caveats that survive any verdict:")
    add("    * The historical curve is a league base rate. It does not know who is")
    add("      playing, who is injured, or who is in foul trouble — the market does.")
    add("      A gap is only an edge if the curve's ignorance is not the reason for it.")
    add("    * Three observations per game maximum, and they are not independent")
    add("      within a game: the same lead often persists across two boundaries.")
    add("      Clustering by game is what keeps that from inflating the interval.")
    return "\n".join(out)


def main() -> int:
    from core.storage import get_engine, get_sessionmaker

    parser = argparse.ArgumentParser(prog="meridian-win-curve")
    parser.add_argument("--teams", action="store_true",
                        help="also print the ungated per-team deviation table")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.WARNING)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        study = run_study(session)
    print(format_report(study, show_teams=args.teams))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
