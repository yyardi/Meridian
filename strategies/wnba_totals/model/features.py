"""Point-in-time feature engineering for WNBA totals.

The one rule
------------
**Every feature is computed `as_of` a timestamp, from games strictly before
it.** `as_of` is keyword-only and has no default anywhere in this module, so
"current season stats" is not expressible. That is the point: lookahead bias is
silent and flattering — a model that accidentally sees the future produces an
excellent backtest that evaporates on live money.

Filtering happens in SQL (`game_date < as_of`), not via pandas `.shift()`
tricks. Explicit beats clever when the failure mode is a plausible-looking lie.

See docs/math/point-in-time.md.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from core.config import SEASON_TYPE_POSTSEASON, SEASON_TYPE_REGULAR
from core.storage import TeamGameLog
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig


@dataclass(frozen=True)
class LeagueAverages:
    """League-wide means, themselves `as_of`-correct."""

    points_scored: float
    points_allowed: float
    games: int

    @property
    def is_usable(self) -> bool:
        return self.games > 0


@dataclass(frozen=True)
class TeamFeatures:
    """Everything the model knows about one team at one instant."""

    team_id: str
    as_of: dt.datetime

    games_played: int = 0

    # Raw season means (shrunk toward league average).
    offense_ppg: float = 0.0
    defense_ppg_allowed: float = 0.0

    # Home/away splits.
    offense_ppg_home: float = 0.0
    offense_ppg_away: float = 0.0
    defense_ppg_allowed_home: float = 0.0
    defense_ppg_allowed_away: float = 0.0

    # Exponentially-decayed recent form.
    offense_ppg_recent: float = 0.0
    defense_ppg_allowed_recent: float = 0.0

    rest_days: float | None = None

    # Win-loss record — REGULAR SEASON ONLY.
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0
    pythagorean_win_pct: float = 0.5
    record_residual: float = 0.0

    sufficient_data: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MatchupFeatures:
    """Two teams plus properties of the specific game being predicted."""

    home: TeamFeatures
    away: TeamFeatures
    as_of: dt.datetime
    is_playoff_game: bool = False
    head_to_head_games: int = 0
    #: League mean points per team-game, as_of. 0.0 means "unknown", in which
    #: case the projection falls back to the legacy halved formula.
    league_points_per_team: float = 0.0

    @property
    def sufficient_data(self) -> bool:
        return self.home.sufficient_data and self.away.sufficient_data


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _shrink(team_mean: float, league_mean: float, n: int, k: float) -> float:
    """Shrink a team mean toward the league mean.

        adjusted = (n * team_mean + k * league_mean) / (n + k)

    With few games you get roughly the league average; with many, roughly the
    team's own mean. This is the posterior mean under a normal prior — the
    standard treatment — and it degrades gracefully instead of producing wild
    April projections from a 2-game sample.
    """
    if n <= 0:
        return league_mean
    return (n * team_mean + k * league_mean) / (n + k)


def _decayed_mean(values: list[float], half_life: float) -> float:
    """Exponentially weighted mean, most recent first.

    `values[0]` is the most recent game. Weight 2**(-i/half_life): a game
    `half_life` games ago counts half as much as the latest.
    """
    if not values:
        return 0.0
    if half_life <= 0:
        return values[0]
    weights = [2.0 ** (-i / half_life) for i in range(len(values))]
    total_w = sum(weights)
    return sum(v * w for v, w in zip(values, weights)) / total_w


def pythagorean_win_pct(points_for: float, points_against: float, exponent: float) -> float:
    """Expected win% from points alone: PF^k / (PF^k + PA^k).

    Returns exactly 0.5 when PF == PA, for any exponent.
    """
    if points_for <= 0 and points_against <= 0:
        return 0.5
    if points_for == points_against:
        return 0.5
    try:
        pf = math.pow(points_for, exponent)
        pa = math.pow(points_against, exponent)
    except OverflowError:
        # Extreme exponents on large totals; fall back to the ordering.
        return 1.0 if points_for > points_against else 0.0
    if pf + pa == 0:
        return 0.5
    return pf / (pf + pa)


# --------------------------------------------------------------------- #
# Queries — all filtered `game_date < as_of`
# --------------------------------------------------------------------- #


def _prior_games_stmt(*, as_of: dt.datetime, team_id: str | None = None,
                      regular_season_only: bool = False) -> Select:
    conditions = [
        TeamGameLog.game_date < as_of,       # <- the no-lookahead guarantee
        TeamGameLog.is_completed.is_(True),
    ]
    if team_id is not None:
        conditions.append(TeamGameLog.team_id == team_id)
    if regular_season_only:
        conditions.append(TeamGameLog.season_type == SEASON_TYPE_REGULAR)
    return select(TeamGameLog).where(and_(*conditions)).order_by(TeamGameLog.game_date.desc())


def league_averages(*, as_of: dt.datetime, session: Session, season: int | None = None) -> LeagueAverages:
    """League means over games before `as_of`.

    Restricted to the current season by default: a 2020 game average is not a
    sensible prior for a 2026 team.
    """
    stmt = _prior_games_stmt(as_of=as_of, regular_season_only=True)
    if season is not None:
        stmt = stmt.where(TeamGameLog.season == season)
    rows = session.scalars(stmt).all()
    if not rows:
        return LeagueAverages(points_scored=0.0, points_allowed=0.0, games=0)
    scored = [r.points_scored for r in rows if r.points_scored is not None]
    allowed = [r.points_allowed for r in rows if r.points_allowed is not None]
    if not scored:
        return LeagueAverages(points_scored=0.0, points_allowed=0.0, games=0)
    return LeagueAverages(
        points_scored=sum(scored) / len(scored),
        points_allowed=sum(allowed) / len(allowed),
        games=len(rows),
    )


def build_team_features(
    *,
    team_id: str,
    as_of: dt.datetime,
    session: Session,
    season: int | None = None,
    config: WNBATotalsConfig | None = None,
    league: LeagueAverages | None = None,
) -> TeamFeatures:
    """Build one team's features using ONLY games before `as_of`.

    `as_of` is keyword-only and has no default — there is deliberately no way
    to ask for "current" stats.
    """
    cfg = config or CONFIG
    league = league or league_averages(as_of=as_of, session=session, season=season)

    stmt = _prior_games_stmt(as_of=as_of, team_id=team_id)
    if season is not None:
        stmt = stmt.where(TeamGameLog.season == season)
    games = session.scalars(stmt).all()  # newest first

    notes: list[str] = []
    n = len(games)
    if n == 0:
        return TeamFeatures(
            team_id=team_id,
            as_of=as_of,
            offense_ppg=league.points_scored,
            defense_ppg_allowed=league.points_allowed,
            sufficient_data=False,
            notes=("no prior games",),
        )

    scored = [float(g.points_scored) for g in games if g.points_scored is not None]
    allowed = [float(g.points_allowed) for g in games if g.points_allowed is not None]

    raw_off = sum(scored) / len(scored) if scored else league.points_scored
    raw_def = sum(allowed) / len(allowed) if allowed else league.points_allowed

    home = [g for g in games if g.is_home]
    away = [g for g in games if not g.is_home]

    def _split_mean(rows, attr: str, fallback: float) -> float:
        vals = [float(getattr(r, attr)) for r in rows if getattr(r, attr) is not None]
        return sum(vals) / len(vals) if vals else fallback

    # Shrink every mean toward the league average.
    k = cfg.shrinkage_k
    lg_s, lg_a = league.points_scored, league.points_allowed
    if not league.is_usable:
        lg_s, lg_a = raw_off, raw_def

    offense = _shrink(raw_off, lg_s, n, k)
    defense = _shrink(raw_def, lg_a, n, k)

    off_home = _shrink(_split_mean(home, "points_scored", raw_off), lg_s, len(home), k)
    off_away = _shrink(_split_mean(away, "points_scored", raw_off), lg_s, len(away), k)
    def_home = _shrink(_split_mean(home, "points_allowed", raw_def), lg_a, len(home), k)
    def_away = _shrink(_split_mean(away, "points_allowed", raw_def), lg_a, len(away), k)

    # Recent form: exponentially decayed, newest first.
    off_recent = _shrink(
        _decayed_mean(scored, cfg.form_half_life_games), lg_s, n, k
    )
    def_recent = _shrink(
        _decayed_mean(allowed, cfg.form_half_life_games), lg_a, n, k
    )

    rest_days = None
    if games[0].game_date is not None:
        rest_days = (as_of - games[0].game_date).total_seconds() / 86400.0

    # ---- Record: REGULAR SEASON ONLY -------------------------------- #
    # Postseason is excluded because *regular-season* record is the feature,
    # even when predicting a playoff game. Preseason never reaches the table.
    reg = [g for g in games if g.season_type == SEASON_TYPE_REGULAR]
    wins = sum(
        1 for g in reg
        if g.points_scored is not None and g.points_allowed is not None
        and g.points_scored > g.points_allowed
    )
    losses = len(reg) - wins
    win_pct = wins / len(reg) if reg else 0.0

    pf = sum(float(g.points_scored) for g in reg if g.points_scored is not None)
    pa = sum(float(g.points_allowed) for g in reg if g.points_allowed is not None)
    pythag = pythagorean_win_pct(pf, pa, cfg.pythagorean_exponent)

    # The residual is the part of record that point differential CANNOT
    # explain — close-game execution. Shrunk toward 0 (the league-average
    # residual is 0 by construction) so a 3-game record cannot dominate.
    raw_residual = win_pct - pythag if reg else 0.0
    record_residual = _shrink(raw_residual, 0.0, len(reg), k)

    sufficient = n >= cfg.min_games_required
    if not sufficient:
        notes.append(f"only {n} prior games (need {cfg.min_games_required})")

    return TeamFeatures(
        team_id=team_id,
        as_of=as_of,
        games_played=n,
        offense_ppg=offense,
        defense_ppg_allowed=defense,
        offense_ppg_home=off_home,
        offense_ppg_away=off_away,
        defense_ppg_allowed_home=def_home,
        defense_ppg_allowed_away=def_away,
        offense_ppg_recent=off_recent,
        defense_ppg_allowed_recent=def_recent,
        rest_days=rest_days,
        wins=wins,
        losses=losses,
        win_pct=win_pct,
        pythagorean_win_pct=pythag,
        record_residual=record_residual,
        sufficient_data=sufficient,
        notes=tuple(notes),
    )


def head_to_head_count(
    *, team_a: str, team_b: str, as_of: dt.datetime, session: Session, season: int | None = None
) -> int:
    """Prior meetings between two teams before `as_of`."""
    stmt = _prior_games_stmt(as_of=as_of, team_id=team_a).where(
        TeamGameLog.opponent_id == team_b
    )
    if season is not None:
        stmt = stmt.where(TeamGameLog.season == season)
    return len(session.scalars(stmt).all())


def build_matchup_features(
    *,
    home_team_id: str,
    away_team_id: str,
    as_of: dt.datetime,
    session: Session,
    season: int | None = None,
    is_playoff_game: bool = False,
    config: WNBATotalsConfig | None = None,
) -> MatchupFeatures:
    """Both teams' features plus properties of the game being predicted."""
    cfg = config or CONFIG
    league = league_averages(as_of=as_of, session=session, season=season)

    home = build_team_features(
        team_id=home_team_id, as_of=as_of, session=session,
        season=season, config=cfg, league=league,
    )
    away = build_team_features(
        team_id=away_team_id, as_of=as_of, session=session,
        season=season, config=cfg, league=league,
    )
    h2h = head_to_head_count(
        team_a=home_team_id, team_b=away_team_id, as_of=as_of, session=session, season=season
    )
    return MatchupFeatures(
        home=home, away=away, as_of=as_of,
        is_playoff_game=is_playoff_game, head_to_head_games=h2h,
        league_points_per_team=league.points_scored if league.is_usable else 0.0,
    )


def is_playoff_season_type(season_type: int | None) -> bool:
    return season_type == SEASON_TYPE_POSTSEASON
