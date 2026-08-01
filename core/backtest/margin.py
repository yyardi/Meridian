"""Walk-forward backtest for spread and moneyline (winner) markets.

No new algorithm: the same projection that prices totals also produces a
projected margin (home − away), and spreads/winners are priced off the margin
distribution. What was missing is validation — these markets were being
predicted and shadow-traded with no evidence behind them.

Honesty constraints, stated up front:

* **No CLV.** ESPN history carries one spread/moneyline snapshot per provider,
  with no open/close pair. Hit rate and ROI only — and those converge slowly.
* **Sign convention is verified, not assumed.** ESPN's `spread` is the home
  handicap (negative = home favoured). `validate_spread_convention` checks
  this against moneyline favourites across the whole dataset and the backtest
  refuses to run if agreement is poor — a wrong sign would silently invert
  every result.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.backtest.engine import DEFAULT_PRICE, _is_live_provider
from core.backtest.fills import FillModel, american_to_price, pnl_for_contract, simulate_fill
from core.backtest.metrics import build_calibration, sample_size_verdict
from core.config import SEASON_TYPE_POSTSEASON, SEASON_TYPE_REGULAR
from core.feeds.odds_math import two_sided_no_vig
from core.storage import SportsbookOdds, TeamGameLog
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.fair_value import (
    MARGIN_SIGMA_RATIO,
    estimate_totals_distribution,
    prob_home_win,
    project,
)
from strategies.wnba_totals.model.features import build_matchup_features


def home_covers(home_margin: float, home_spread: float) -> bool | None:
    """Did the home side cover its handicap?  None = push.

    `home_spread` follows ESPN's convention: negative = home favoured.
    Home -4.5 covers iff home wins by more than 4.5, i.e. margin + spread > 0.
    """
    value = home_margin + home_spread
    if value == 0:
        return None
    return value > 0


@dataclass
class MarginOdds:
    home_spread: float | None
    home_ml: float | None
    away_ml: float | None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[len(values) // 2]


def odds_for_game(session: Session, espn_game_id: str) -> MarginOdds:
    """Consensus spread and moneylines, live-odds providers excluded."""
    rows = [
        r for r in session.scalars(
            select(SportsbookOdds).where(SportsbookOdds.espn_game_id == espn_game_id)
        ).all()
        if not _is_live_provider(r.provider_name)
    ]
    return MarginOdds(
        home_spread=_median([float(r.spread) for r in rows if r.spread is not None]),
        home_ml=_median([float(r.home_moneyline) for r in rows if r.home_moneyline is not None]),
        away_ml=_median([float(r.away_moneyline) for r in rows if r.away_moneyline is not None]),
    )


def validate_spread_convention(session: Session, start_season: int, end_season: int) -> tuple[int, int]:
    """(agree, total): does sign(spread) match the moneyline favourite?

    Home favoured => negative home spread AND home implied probability > away.
    """
    agree = total = 0
    for gid in session.scalars(
        select(TeamGameLog.espn_game_id)
        .where(TeamGameLog.season >= start_season, TeamGameLog.season <= end_season)
        .distinct()
    ).all():
        o = odds_for_game(session, gid)
        if o.home_spread is None or o.home_ml is None or o.away_ml is None:
            continue
        if abs(o.home_spread) < 1.0:      # near pick'em: sign is noise
            continue
        p_home, p_away = two_sided_no_vig(o.home_ml, o.away_ml)
        if p_home is None:
            continue
        total += 1
        if (o.home_spread < 0) == (p_home > 0.5):
            agree += 1
    return agree, total


@dataclass
class MarginBacktestConfig:
    start_season: int = 2024
    end_season: int = 2026
    spread_threshold_points: float = 3.0
    winner_prob_threshold: float = 0.05
    stake_per_bet: float = 1.0
    fill_model: FillModel = FillModel.REALISTIC
    seed: int = 42
    include_playoffs: bool = True


@dataclass
class MarginResult:
    config: MarginBacktestConfig
    convention_agree: int = 0
    convention_total: int = 0
    games_considered: int = 0
    games_no_odds: int = 0

    spread_bets: int = 0
    spread_filled: int = 0
    spread_wins: int = 0
    spread_resolved: int = 0
    spread_pnl: float = 0.0
    spread_staked: float = 0.0

    winner_bets: int = 0
    winner_filled: int = 0
    winner_wins: int = 0
    winner_resolved: int = 0
    winner_pnl: float = 0.0
    winner_staked: float = 0.0
    winner_calib_pairs: list[tuple[float, int]] = field(default_factory=list)

    realized_margins: list[float] = field(default_factory=list)
    assumed_margin_sigma: float = 0.0


class SpreadConventionError(RuntimeError):
    """Raised when the data disagrees with the assumed sign convention."""


def run_margin_backtest(
    *,
    session: Session,
    config: MarginBacktestConfig | None = None,
    model_config: WNBATotalsConfig | None = None,
) -> MarginResult:
    cfg = config or MarginBacktestConfig()
    mcfg = model_config or CONFIG
    rng = random.Random(cfg.seed)
    result = MarginResult(config=cfg)

    # A wrong sign convention silently inverts every result; verify first.
    agree, total = validate_spread_convention(session, cfg.start_season, cfg.end_season)
    result.convention_agree, result.convention_total = agree, total
    if total >= 50 and agree / total < 0.9:
        raise SpreadConventionError(
            f"spread sign convention agreement is only {agree}/{total} — "
            "refusing to produce inverted results"
        )

    types = [SEASON_TYPE_REGULAR] + ([SEASON_TYPE_POSTSEASON] if cfg.include_playoffs else [])
    games = session.execute(
        select(
            TeamGameLog.espn_game_id, TeamGameLog.game_date, TeamGameLog.season,
            TeamGameLog.season_type, TeamGameLog.team_id, TeamGameLog.opponent_id,
            TeamGameLog.points_scored, TeamGameLog.points_allowed,
        )
        .where(TeamGameLog.is_home.is_(True))
        .where(TeamGameLog.is_completed.is_(True))
        .where(TeamGameLog.season >= cfg.start_season)
        .where(TeamGameLog.season <= cfg.end_season)
        .where(TeamGameLog.season_type.in_(types))
        .order_by(TeamGameLog.game_date)
    ).all()

    for gid, gdate, season, stype, home_id, away_id, hpts, apts in games:
        result.games_considered += 1
        if hpts is None or apts is None:
            continue
        actual_margin = float(hpts) - float(apts)

        odds = odds_for_game(session, gid)
        if odds.home_spread is None and odds.home_ml is None:
            result.games_no_odds += 1
            continue

        features = build_matchup_features(
            home_team_id=home_id, away_team_id=away_id, as_of=gdate,
            session=session, season=season,
            is_playoff_game=(stype == SEASON_TYPE_POSTSEASON), config=mcfg,
        )
        if not features.sufficient_data:
            continue

        dist = estimate_totals_distribution(as_of=gdate, session=session, season=season)
        projection = project(features, config=mcfg, sigma=dist.sigma)
        sigma_margin = dist.sigma * MARGIN_SIGMA_RATIO
        result.assumed_margin_sigma = sigma_margin
        result.realized_margins.append(actual_margin)

        # ---- spread ------------------------------------------------- #
        if odds.home_spread is not None:
            market_margin = -odds.home_spread
            diff = projection.projected_margin - market_margin
            if abs(diff) >= cfg.spread_threshold_points:
                bet_home = diff > 0
                covered = home_covers(actual_margin, odds.home_spread)
                if covered is not None:
                    won = covered if bet_home else (not covered)
                    fill = simulate_fill(
                        quoted_price=DEFAULT_PRICE,
                        contracts=cfg.stake_per_bet / DEFAULT_PRICE,
                        model=cfg.fill_model, rng_value=rng.random(),
                    )
                    result.spread_bets += 1
                    if fill.filled:
                        pnl = pnl_for_contract(fill.price, won) * fill.contracts - fill.fee
                        result.spread_filled += 1
                        result.spread_resolved += 1
                        result.spread_wins += int(won)
                        result.spread_pnl += pnl
                        result.spread_staked += cfg.stake_per_bet

        # ---- winner ------------------------------------------------- #
        if odds.home_ml is not None and odds.away_ml is not None:
            p_home_market, _ = two_sided_no_vig(odds.home_ml, odds.away_ml)
            if p_home_market is not None:
                p_home_model = prob_home_win(projection.projected_margin, sigma_margin)
                gap = p_home_model - float(p_home_market)
                if abs(gap) >= cfg.winner_prob_threshold:
                    bet_home = gap > 0
                    # Entry price is the vig-INCLUDED probability of the chosen
                    # side — that is what the book actually charges.
                    entry = american_to_price(odds.home_ml if bet_home else odds.away_ml)
                    won = (actual_margin > 0) if bet_home else (actual_margin < 0)
                    fill = simulate_fill(
                        quoted_price=entry,
                        contracts=cfg.stake_per_bet / max(entry, 1e-6),
                        model=cfg.fill_model, rng_value=rng.random(),
                    )
                    result.winner_bets += 1
                    if fill.filled:
                        pnl = pnl_for_contract(fill.price, won) * fill.contracts - fill.fee
                        result.winner_filled += 1
                        result.winner_resolved += 1
                        result.winner_wins += int(won)
                        result.winner_pnl += pnl
                        result.winner_staked += cfg.stake_per_bet
                        side_p = p_home_model if bet_home else 1.0 - p_home_model
                        result.winner_calib_pairs.append((side_p, int(won)))

    return result


def format_margin_report(r: MarginResult) -> str:
    import statistics as st

    out: list[str] = []
    add = out.append
    add("SPREAD + MONEYLINE BACKTEST (same projection as totals — margin view)")
    add("=" * 78)
    add(f"seasons {r.config.start_season}-{r.config.end_season} · "
        f"{r.config.fill_model.value} fills · spread threshold "
        f"{r.config.spread_threshold_points} pts · winner threshold "
        f"{r.config.winner_prob_threshold:.0%}")
    add("")
    add(f"  sign convention check : {r.convention_agree}/{r.convention_total} agree "
        f"({(r.convention_agree / r.convention_total * 100) if r.convention_total else 0:.1f}%)")
    add("  NO CLV IS POSSIBLE for these markets: ESPN history has no open/close")
    add("  pair for spreads or moneylines. Hit rate and ROI only — both are")
    add("  noise-dominated at these sample sizes.")
    add("")

    def block(name, bets, filled, wins, resolved, pnl, staked):
        add(name)
        add("-" * 78)
        add(f"  bets {bets} · filled {filled}")
        if resolved:
            hit = wins / resolved
            se = (hit * (1 - hit) / resolved) ** 0.5
            add(f"  hit rate : {hit:.3f} ± {se:.3f}   ({wins}/{resolved})")
            add(f"  ROI      : {pnl / staked:+.2%}" if staked else "  ROI: n/a")
            add(f"  breakeven at -110 pricing is 0.524")
        else:
            add("  nothing resolved")
        add("")

    block("SPREAD", r.spread_bets, r.spread_filled, r.spread_wins,
          r.spread_resolved, r.spread_pnl, r.spread_staked)
    block("MONEYLINE", r.winner_bets, r.winner_filled, r.winner_wins,
          r.winner_resolved, r.winner_pnl, r.winner_staked)

    if r.winner_calib_pairs:
        add("MONEYLINE CALIBRATION (model's chosen-side probability)")
        add("-" * 78)
        for b in build_calibration(r.winner_calib_pairs):
            if b.n >= 5:
                add(f"  predicted {b.predicted:.2f} -> realised "
                    f"{b.realised:.2f}  (n={b.n})")
        add("")

    if r.realized_margins:
        sd = st.pstdev(r.realized_margins)
        mean = st.mean(r.realized_margins)
        add("MARGIN DISTRIBUTION CHECK")
        add("-" * 78)
        add(f"  realised home margin : mean {mean:+.1f} (home-court advantage), sd {sd:.1f}")
        add(f"  model's assumed sigma_margin : {r.assumed_margin_sigma:.1f} "
            f"(= {MARGIN_SIGMA_RATIO} × sigma_total)")
        if r.assumed_margin_sigma and abs(sd - r.assumed_margin_sigma) > 2.5:
            add(f"  ⚠️  assumed sigma is off by {abs(sd - r.assumed_margin_sigma):.1f} — "
                "winner probabilities are mis-scaled; fix MARGIN_SIGMA_RATIO")
        add("")

    n = r.spread_bets + r.winner_bets
    add("VERDICT")
    add("-" * 78)
    for line in sample_size_verdict(n).split(". "):
        if line.strip():
            add(f"  {line.strip().rstrip('.')}.")
    return "\n".join(out)
