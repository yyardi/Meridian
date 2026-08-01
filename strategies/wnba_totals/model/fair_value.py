"""Fair-value projection for WNBA totals, spreads and moneylines.

Deliberately simple. A WNBA season is ~250-300 games league-wide; complex
models memorise datasets that small. This linear baseline is what any future
model must beat *out-of-sample* before its complexity is justified.

Purity contract
---------------
No network calls, no ``datetime.now()``, no database writes. Time enters as
``as_of``. Same inputs always produce the same output, because the walk-forward
backtest must replay exactly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from scipy.stats import norm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import SEASON_TYPE_REGULAR
from core.config_hash import compute_config_hash
from core.storage import TeamGameLog
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.features import MatchupFeatures, TeamFeatures

#: Bump on any logic change. NOTE: this alone does not protect the prediction
#: log — it is hand-maintained and will eventually be forgotten. `config_hash`
#: is derived from the config actually used and cannot be forgotten.
MODEL_VERSION = "v2"

STRATEGY = "wnba_totals"

MARKET_TOTAL = "basketball_team_full_game_total"
MARKET_SPREAD = "basketball_team_full_game_spread"
MARKET_WINNER = "basketball_team_full_game_winner"


@dataclass(frozen=True)
class Projection:
    """Scoreline projection for one matchup."""

    projected_home: float
    projected_away: float
    projected_total: float
    projected_margin: float          # home - away, AFTER the record modifier
    baseline_margin: float           # before the record modifier
    record_adjustment: float
    sigma: float
    is_playoff_game: bool
    reduced_confidence: bool
    confidence_notes: str | None


@dataclass(frozen=True)
class MarketPrediction:
    """A fair value for one market, ready to persist."""

    market_slug: str
    sports_market_type: str
    line: float | None
    model_probability: float
    model_fair_value: float
    market_bid: float | None = None
    market_ask: float | None = None
    market_mid: float | None = None
    edge: float | None = None
    model_version: str = MODEL_VERSION
    strategy: str = STRATEGY
    config_hash: str = ""
    model_config_snapshot: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    reduced_confidence: bool = False
    confidence_notes: str | None = None
    is_actionable: bool = False


# --------------------------------------------------------------------- #
# Sigma estimation
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class TotalsDistribution:
    """Estimated scoring environment: mean and sigma of game totals."""

    mean: float
    sigma: float
    n_games: int
    n_current_season: int
    shrunk_toward_history: bool


def _totals_before(
    *, as_of: dt.datetime, session: Session, min_season: int, max_season: int | None = None
) -> list[float]:
    """Deduplicated game totals for completed regular-season games before `as_of`.

    Deduplicates on ``espn_game_id``: ``team_game_logs`` holds two rows per
    game, and naively aggregating both counts every game twice.
    """
    stmt = (
        select(
            TeamGameLog.espn_game_id,
            func.max(TeamGameLog.points_scored + TeamGameLog.points_allowed),
        )
        .where(TeamGameLog.game_date < as_of)          # no lookahead
        .where(TeamGameLog.is_completed.is_(True))
        .where(TeamGameLog.season_type == SEASON_TYPE_REGULAR)
        .where(TeamGameLog.season >= min_season)
        .group_by(TeamGameLog.espn_game_id)
    )
    if max_season is not None:
        stmt = stmt.where(TeamGameLog.season <= max_season)
    return [float(t) for _, t in session.execute(stmt).all() if t is not None]


def _mean_sd(values: list[float]) -> tuple[float, float]:
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, var**0.5


def estimate_totals_distribution(
    *,
    as_of: dt.datetime,
    session: Session,
    season: int | None = None,
    history_seasons: int = 3,
    prior_games: float = 60.0,
) -> TotalsDistribution:
    """Estimate the CURRENT scoring environment, shrunk toward recent history.

    Why current-season-first
    ------------------------
    The WNBA scoring environment is not stationary. Measured from our own data:

        2020-2025   mean 161-166   sigma 16.5-17.7   (stable)
        2026        mean 174.4     sigma 21.7        (a different game)

    A multi-season estimate would project 2026 totals roughly ten points low —
    a systematic mispricing on every totals market. Worse, it would look fine
    in a multi-year backtest while losing money live, because the error is
    invisible when averaged across regimes.

    So: use the current season, and shrink toward recent history only while the
    current-season sample is small (early April). Same shrinkage logic as team
    features, and it is point-in-time correct because every query filters
    ``game_date < as_of``.
    """
    season = season if season is not None else as_of.year

    current = _totals_before(
        as_of=as_of, session=session, min_season=season, max_season=season
    )
    history = _totals_before(
        as_of=as_of, session=session,
        min_season=season - history_seasons, max_season=season - 1,
    )

    n_cur = len(current)

    # Neither sample usable -> fall back to the configured default.
    if n_cur < 2 and len(history) < 2:
        return TotalsDistribution(0.0, CONFIG.total_sigma, n_cur, n_cur, False)

    if n_cur < 2:
        h_mean, h_sd = _mean_sd(history)
        return TotalsDistribution(h_mean, h_sd, len(history), n_cur, True)

    c_mean, c_sd = _mean_sd(current)
    if len(history) < 2:
        return TotalsDistribution(c_mean, c_sd, n_cur, n_cur, False)

    h_mean, h_sd = _mean_sd(history)

    # Shrink toward history with weight n/(n + prior_games). With ~60 games of
    # prior weight, the current season dominates by midseason but early-April
    # noise cannot swing the estimate.
    w = n_cur / (n_cur + prior_games)
    mean = w * c_mean + (1 - w) * h_mean
    sigma = w * c_sd + (1 - w) * h_sd

    return TotalsDistribution(
        mean=mean,
        sigma=sigma,
        n_games=n_cur + len(history),
        n_current_season=n_cur,
        shrunk_toward_history=w < 0.9,
    )


def estimate_total_sigma(
    *, as_of: dt.datetime, session: Session, seasons: int = 3
) -> tuple[float, float, int]:
    """Backwards-compatible wrapper returning (mean, sigma, n_games)."""
    d = estimate_totals_distribution(
        as_of=as_of, session=session, history_seasons=seasons
    )
    return d.mean, d.sigma, d.n_games


# --------------------------------------------------------------------- #
# Projection
# --------------------------------------------------------------------- #


def project(
    features: MatchupFeatures,
    *,
    config: WNBATotalsConfig | None = None,
    sigma: float | None = None,
) -> Projection:
    """Project a scoreline from matchup features.

    Baseline:
        projected_home = (home.offense + away.defense_allowed) / 2

    Then the record residual modifies the *margin* only (spread + moneyline).
    """
    cfg = config or CONFIG
    home, away = features.home, features.away

    # Home/away splits, if they are earning their keep. Each split is ~22
    # games, so the home-minus-away difference is mostly sampling noise; the
    # backtest decides via cfg.use_home_away_splits.
    if cfg.use_home_away_splits:
        home_off = home.offense_ppg_home or home.offense_ppg
        away_off = away.offense_ppg_away or away.offense_ppg
        home_def = home.defense_ppg_allowed_home or home.defense_ppg_allowed
        away_def = away.defense_ppg_allowed_away or away.defense_ppg_allowed
    else:
        home_off, away_off = home.offense_ppg, away.offense_ppg
        home_def, away_def = home.defense_ppg_allowed, away.defense_ppg_allowed

    projected_home = (home_off + away_def) / 2.0
    projected_away = (away_off + home_def) / 2.0

    projected_total = projected_home + projected_away
    baseline_margin = projected_home - projected_away

    # ---- Record modifier: margin only, never the total ------------- #
    # Clutch execution shifts who wins a close game; it has no mechanism for
    # moving the COMBINED score. Applying it to totals would add pure noise to
    # the primary market.
    playoff_weight = cfg.playoff_record_weight if features.is_playoff_game else 1.0
    record_edge = home.record_residual - away.record_residual
    record_adjustment = cfg.record_beta * record_edge * playoff_weight
    projected_margin = baseline_margin + record_adjustment

    notes: list[str] = []
    reduced = False
    if features.is_playoff_game:
        reduced = True
        notes.append(
            f"playoff game: regular-season record down-weighted to "
            f"{cfg.playoff_record_weight:g}x"
        )
    if not features.sufficient_data:
        reduced = True
        for side, f in (("home", home), ("away", away)):
            if not f.sufficient_data:
                notes.append(f"{side}: {'; '.join(f.notes) or 'insufficient data'}")

    return Projection(
        projected_home=projected_home,
        projected_away=projected_away,
        projected_total=projected_total,
        projected_margin=projected_margin,
        baseline_margin=baseline_margin,
        record_adjustment=record_adjustment,
        sigma=sigma if sigma is not None else cfg.total_sigma,
        is_playoff_game=features.is_playoff_game,
        reduced_confidence=reduced,
        confidence_notes="; ".join(notes) if notes else None,
    )


# --------------------------------------------------------------------- #
# Market probabilities
# --------------------------------------------------------------------- #


def prob_over(projected_total: float, line: float, sigma: float) -> float:
    """P(total > line) under Normal(projected_total, sigma^2)."""
    if sigma <= 0:
        return 0.5
    return float(1.0 - norm.cdf(line, loc=projected_total, scale=sigma))


def prob_cover(projected_margin: float, line: float, sigma_margin: float) -> float:
    """P(home margin > line).

    Margin sigma is smaller than total sigma: the two teams' scores are
    positively correlated (pace is shared), so their difference varies less
    than their sum. Approximated as a fraction of total sigma.
    """
    if sigma_margin <= 0:
        return 0.5
    return float(1.0 - norm.cdf(line, loc=projected_margin, scale=sigma_margin))


def prob_home_win(projected_margin: float, sigma_margin: float) -> float:
    """P(home wins) = P(margin > 0)."""
    return prob_cover(projected_margin, 0.0, sigma_margin)


#: Margin sigma as a fraction of total sigma. Team scores are positively
#: correlated through shared pace, so the difference is less variable than the
#: sum. 0.75 is a conventional starting approximation; the backtest should
#: revisit it against realised margins.
MARGIN_SIGMA_RATIO = 0.75


# --------------------------------------------------------------------- #
# Prediction assembly
# --------------------------------------------------------------------- #


def _features_snapshot(f: MatchupFeatures) -> dict:
    """Serialisable record of the inputs, for reproducibility."""

    def side(t: TeamFeatures) -> dict:
        return {
            "team_id": t.team_id,
            "games_played": t.games_played,
            "offense_ppg": round(t.offense_ppg, 4),
            "defense_ppg_allowed": round(t.defense_ppg_allowed, 4),
            "offense_ppg_home": round(t.offense_ppg_home, 4),
            "offense_ppg_away": round(t.offense_ppg_away, 4),
            "defense_ppg_allowed_home": round(t.defense_ppg_allowed_home, 4),
            "defense_ppg_allowed_away": round(t.defense_ppg_allowed_away, 4),
            "offense_ppg_recent": round(t.offense_ppg_recent, 4),
            "defense_ppg_allowed_recent": round(t.defense_ppg_allowed_recent, 4),
            "rest_days": t.rest_days,
            "wins": t.wins,
            "losses": t.losses,
            "win_pct": round(t.win_pct, 4),
            "pythagorean_win_pct": round(t.pythagorean_win_pct, 4),
            "record_residual": round(t.record_residual, 6),
            "sufficient_data": t.sufficient_data,
        }

    return {
        "as_of": f.as_of.isoformat(),
        "home": side(f.home),
        "away": side(f.away),
        "is_playoff_game": f.is_playoff_game,
        "head_to_head_games": f.head_to_head_games,
    }


def predict_market(
    *,
    features: MatchupFeatures,
    projection: Projection,
    market_slug: str,
    sports_market_type: str,
    line: float | None,
    market_bid: float | None = None,
    market_ask: float | None = None,
    config: WNBATotalsConfig | None = None,
    is_over_side: bool = True,
    is_home_side: bool = True,
) -> MarketPrediction | None:
    """Fair value for one market. Returns None when data is too thin.

    Refusing is deliberate: emitting a confident number from a 2-game sample is
    worse than emitting nothing, because it looks identical to a real signal.
    """
    cfg = config or CONFIG
    if not features.sufficient_data:
        return None

    sigma_margin = projection.sigma * MARGIN_SIGMA_RATIO

    if sports_market_type == MARKET_TOTAL:
        if line is None:
            return None
        p = prob_over(projection.projected_total, line, projection.sigma)
        if not is_over_side:
            p = 1.0 - p
    elif sports_market_type == MARKET_SPREAD:
        if line is None:
            return None
        # Polymarket spread markets are quoted from a team's perspective; the
        # caller states which side via is_home_side.
        margin = projection.projected_margin if is_home_side else -projection.projected_margin
        p = prob_cover(margin, line, sigma_margin)
    elif sports_market_type == MARKET_WINNER:
        p = prob_home_win(projection.projected_margin, sigma_margin)
        if not is_home_side:
            p = 1.0 - p
    else:
        return None

    p = min(max(p, 1e-6), 1.0 - 1e-6)

    mid = None
    if market_bid is not None and market_ask is not None:
        mid = (market_bid + market_ask) / 2.0
    edge = (p - mid) if mid is not None else None

    cfg_dict = cfg.as_dict()
    return MarketPrediction(
        market_slug=market_slug,
        sports_market_type=sports_market_type,
        line=line,
        model_probability=p,
        model_fair_value=p,
        market_bid=market_bid,
        market_ask=market_ask,
        market_mid=mid,
        edge=edge,
        config_hash=compute_config_hash(cfg_dict),
        model_config_snapshot=cfg_dict,
        features=_features_snapshot(features),
        reduced_confidence=projection.reduced_confidence,
        confidence_notes=projection.confidence_notes,
        is_actionable=bool(edge is not None and abs(edge) > 0.0),
    )


def to_decimal(value: float | None, places: str = "0.0001") -> Decimal | None:
    """Convert a model float to an exact Decimal for storage."""
    if value is None:
        return None
    return Decimal(str(round(value, 6))).quantize(Decimal(places))
