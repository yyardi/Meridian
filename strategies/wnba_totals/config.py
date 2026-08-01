"""Configuration for the WNBA totals strategy.

Every tunable the model depends on lives here, and the whole dict is hashed
into `predictions.config_hash` at prediction time. That is deliberate:
`model_version` is a hand-bumped constant and will eventually be forgotten,
whereas changing any value below necessarily changes the hash — so the backtest
can never silently blend two different models.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WNBATotalsConfig:
    # -- Recent-form decay ------------------------------------------------
    #: Half-life in games for the exponential form weighting. A game 5 games
    #: ago counts half as much as the most recent one. Decay rather than
    #: truncate: older games still carry signal, just less of it.
    form_half_life_games: float = field(
        default_factory=lambda: _env_float("WNBA_FORM_HALF_LIFE", 5.0)
    )

    # -- Small-sample shrinkage -------------------------------------------
    #: Prior weight, in games, for shrinking a team mean toward the league
    #: mean. With n games the team gets weight n/(n+k). k=5 means a 5-game
    #: sample is weighted 50/50 against the league average.
    shrinkage_k: float = field(default_factory=lambda: _env_float("WNBA_SHRINKAGE_K", 5.0))

    #: Below this many prior games the model declines to predict rather than
    #: emitting a confident bad number.
    min_games_required: int = field(
        default_factory=lambda: _env_int("WNBA_MIN_GAMES", 5)
    )

    # -- Pythagorean expectation ------------------------------------------
    #: Fitted on 2023-2025 WNBA data: 769 games, 37 team-seasons, RMSE 0.049
    #: win%. NOT the NBA's ~13.91 — that is materially wrong for this league.
    #: Ideally refit walk-forward rather than pinned; see docs.
    pythagorean_exponent: float = field(
        default_factory=lambda: _env_float("WNBA_PYTHAG_K", 11.09)
    )

    # -- Game total distribution ------------------------------------------
    #: Measured on 2023-2025 regular-season games: mean 164.0, sd 17.3.
    #: Used to convert a projected total into P(over line).
    total_sigma: float = field(default_factory=lambda: _env_float("WNBA_TOTAL_SIGMA", 17.3))

    # -- Record modifier ---------------------------------------------------
    #: Coefficient on the Pythagorean record residual, applied to the projected
    #: margin. MUST be fitted walk-forward, never hand-tuned — the residual is
    #: statistically indistinguishable from luck (observed sd 4.9 win-% pts vs
    #: a 7.9 binomial noise floor), so a fitted beta should collapse toward 0.
    #: The default of 0.0 means "no effect until the data earns it".
    record_beta: float = field(default_factory=lambda: _env_float("WNBA_RECORD_BETA", 0.0))

    #: Playoff down-weight for the record modifier. Regular-season record
    #: loses predictive value once seeding is locked and rotations tighten.
    playoff_record_weight: float = field(
        default_factory=lambda: _env_float("WNBA_PLAYOFF_WEIGHT", 0.25)
    )

    #: Clutch execution has no mechanism for moving a game's *combined* score,
    #: so the record modifier is applied to spread/moneyline only.
    apply_record_to_totals: bool = False

    #: Use home/away split scoring rather than overall means.
    #: A WNBA team plays ~22 home and ~22 away games, so each split is a small
    #: sample and the difference between them is mostly noise. Kept as a flag
    #: so the backtest can settle it rather than assumption.
    use_home_away_splits: bool = field(
        default_factory=lambda: _env_bool("WNBA_HOME_AWAY_SPLITS", True)
    )

    # -- Risk / sizing guardrails -----------------------------------------
    #: Kelly fraction. Quarter Kelly by default: full Kelly is growth-optimal
    #: ONLY if the edge estimate is exact, and ours is model-derived and
    #: currently uncalibrated (see docs/math/calibration-problem.md).
    kelly_fraction: float = field(default_factory=lambda: _env_float("WNBA_KELLY_FRAC", 0.25))

    #: Hard caps, applied AFTER Kelly so a model bug cannot produce a
    #: catastrophic bet. Percentages of bankroll.
    max_position_size_pct: float = field(
        default_factory=lambda: _env_float("WNBA_MAX_POS_PCT", 0.05)
    )
    max_game_exposure_pct: float = field(
        default_factory=lambda: _env_float("WNBA_MAX_GAME_PCT", 0.08)
    )
    max_daily_exposure_pct: float = field(
        default_factory=lambda: _env_float("WNBA_MAX_DAY_PCT", 0.20)
    )
    #: Below this, the edge is inside model error and not worth trading.
    min_edge_threshold: float = field(
        default_factory=lambda: _env_float("WNBA_MIN_EDGE", 0.03)
    )
    #: Stop trading entirely below this bankroll.
    min_bankroll: float = field(default_factory=lambda: _env_float("WNBA_MIN_BANKROLL", 10.0))
    #: Final absolute backstop, in dollars, regardless of everything above.
    max_position_dollars: float = field(
        default_factory=lambda: _env_float("WNBA_MAX_POS_DOLLARS", 5.0)
    )

    #: Assumed correlation between different market types on the SAME game
    #: (e.g. moneyline and total). Conservative fixed assumption, not fitted:
    #: ~250 games/season is not enough to estimate a covariance matrix
    #: reliably, and a bad estimate is more dangerous than an honest constant.
    same_game_correlation: float = field(
        default_factory=lambda: _env_float("WNBA_SAME_GAME_CORR", 0.5)
    )
    #: Same-side ladder rungs (Over 176.5 and Over 179.5) are nearly the same
    #: bet.
    same_side_ladder_correlation: float = field(
        default_factory=lambda: _env_float("WNBA_LADDER_CORR", 0.95)
    )

    def as_dict(self) -> dict:
        """Config snapshot for hashing into the prediction log."""
        return asdict(self)


CONFIG = WNBATotalsConfig()
