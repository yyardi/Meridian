"""Walk-forward backtest engine.

This is the priority deliverable of the project: its job is to answer honestly
whether the model has an edge, *including when the answer is no*.

Structure of the loop
---------------------
Step through games in time order. For each one, features and the scoring
environment are computed ``as_of`` that game's tip-off, from games strictly
before it. There is no code path that can read the future — ``as_of`` is
mandatory everywhere in the feature layer, so lookahead is prevented
structurally rather than by discipline.

What the "market" is here
-------------------------
Polymarket US launched ~2026-03, so no multi-year venue history exists. The
historical backtest therefore prices against **ESPN sportsbook lines**, which
go back to 2020. That answers the first and more important question — *does
the projection beat a closing line?* — while the venue-specific question
(*is there edge on Polymarket's book?*) needs the recorder running forward.

Scope: **totals only**. Totals are the primary market and the only one where
we have a genuine open -> close pair, which is what CLV requires. Moneyline and
spread history carry a single snapshot per provider, so a closing line cannot
be separated from a current line, and fabricating one would corrupt the
headline metric.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.backtest.fills import (
    FillModel,
    american_to_price,
    pnl_for_contract,
    simulate_fill,
)
from core.backtest.metrics import BacktestMetrics, build_calibration
from core.config import SEASON_TYPE_POSTSEASON, SEASON_TYPE_REGULAR
from core.config_hash import compute_config_hash
from core.storage import SportsbookOdds, TeamGameLog
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.availability import (
    PlayerAvailabilityIndex,
    adjustment_from_projections,
)
from strategies.wnba_totals.model.fair_value import (
    MODEL_VERSION,
    estimate_totals_distribution,
    prob_over,
    project,
)
from strategies.wnba_totals.model.features import build_matchup_features

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Default price when a book's over/under juice is missing. -110 both sides.
DEFAULT_PRICE = american_to_price(-110)


@dataclass
class BetRecord:
    """One simulated bet, with everything needed to audit it later."""

    game_date: dt.datetime
    espn_game_id: str
    season: int
    season_type: int
    side: str                    # 'over' | 'under'
    entry_line: float
    closing_line: float | None
    projected_total: float
    model_probability: float
    entry_price: float
    edge: float
    contracts: float
    filled: bool
    fee: float
    actual_total: int | None
    won: bool | None
    pnl: float
    clv_points: float | None
    is_playoff: bool
    #: Points added to the projection for roster absences (0.0 when off).
    availability_delta: float = 0.0
    #: True when at least one rotation player was absent for either team.
    has_absence: bool = False
    #: Scoring-environment sigma used to price this bet. Stored so CLV can be
    #: converted from line points into probability terms after the fact —
    #: points are not comparable to an ROI, probabilities are.
    sigma: float = 0.0
    #: The two-sided vig-included prices quoted at entry, kept so the ledger
    #: can de-vig them rather than guess at the book's margin.
    over_price: float = 0.0
    under_price: float = 0.0


class SlopeTracker:
    """Expanding-window regression slope of (actual − line) on (proj − line).

    This is the winner's-curse correction: our measured incremental slope is
    ~0.4, meaning a raw model-vs-line gap is ~60% our own error. Estimated
    strictly from games BEFORE the current one (update after deciding), so the
    backtest cannot peek. Until `min_n` games it returns 1.0 — no shrinkage —
    which is the honest walk-forward behaviour, not a fitted constant.
    """

    def __init__(self, min_n: int = 100) -> None:
        self.min_n = min_n
        self.n = 0
        self.sx = self.sy = self.sxx = self.sxy = 0.0

    def add(self, x: float, y: float) -> None:
        self.n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.sxy += x * y

    def slope(self) -> float:
        if self.n < self.min_n:
            return 1.0
        den = self.n * self.sxx - self.sx * self.sx
        if den <= 0:
            return 1.0
        b = (self.n * self.sxy - self.sx * self.sy) / den
        return min(1.0, max(0.0, b))


@dataclass
class BacktestConfig:
    start_season: int = 2024
    end_season: int = 2026
    #: Minimum |projection - line| in points before betting. Small differences
    #: are inside model error.
    min_edge_points: float = 3.0
    stake_per_bet: float = 1.0        # flat stake; Kelly is a separate unit
    starting_bankroll: float = 100.0
    fill_model: FillModel = FillModel.REALISTIC
    seed: int = 42
    include_playoffs: bool = True
    #: Shrink the projection toward the line by the walk-forward incremental
    #: slope before betting. The statistically correct predictor of
    #: (actual − line) is slope × (proj − line), not the raw gap.
    shrink_to_market: bool = False
    #: Price probabilities from the SHRUNK projection even when selecting on
    #: the raw one. Selection on raw diff performs (54.1% hit); probability
    #: magnitudes from raw diff are overconfident (0.65 bucket realising
    #: 0.55). E[actual − line | raw_diff] = slope × raw_diff is the correct
    #: expectation to price from, and it uses no new information.
    calibrate_probabilities: bool = True
    #: Roster-availability adjustment. Three modes, and the distinction is the
    #: whole experiment:
    #:   "off"     — incumbent behaviour, the control arm.
    #:   "oracle"  — absence taken from the box score, i.e. with hindsight.
    #:               **NOT TRADABLE.** An upper bound on what roster awareness
    #:               could be worth, used to decide whether waiting a season
    #:               for point-in-time injury data is justified at all.
    #:   "report"  — absence from the point-in-time injury change log. Tradable,
    #:               but empty before the recorder's first run (2026-08-01), so
    #:               on history it is silently identical to "off".
    availability_mode: str = "off"
    #: Multiplier on the raw availability delta. 1.0 takes the minute-
    #: redistribution arithmetic at face value. That arithmetic has offsetting
    #: biases of unknown net sign (see availability.py), so this exists for the
    #: data to scale the term rather than for anyone to guess it.
    availability_beta: float = 1.0
    #: Sensitivity arm: book the unverified maker rebate (findings C7). Off by
    #: default — the venue has never paid one into this account.
    assume_maker_rebate: bool = False
    #: MEASURED adverse-selection concession in price units, overriding the
    #: fill model's stylised one (2026-08-07 fill re-exam). None keeps the
    #: model's default. Measured values: 0.021 pregame (ANCHOR's regime,
    #: 30 games), 0.047 in-game (13 games) — both E[-dmid | filled].
    adverse_selection_override: float | None = None


@dataclass
class BacktestResult:
    config: BacktestConfig
    model_version: str
    config_hash: str
    bets: list[BetRecord] = field(default_factory=list)
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    games_considered: int = 0
    games_no_odds: int = 0
    games_no_closing_line: int = 0
    games_insufficient_features: int = 0


def _game_rows(session: Session, start_season: int, end_season: int, include_playoffs: bool):
    """Completed games in time order, one row per game."""
    types = [SEASON_TYPE_REGULAR]
    if include_playoffs:
        types.append(SEASON_TYPE_POSTSEASON)
    return session.execute(
        select(
            TeamGameLog.espn_game_id,
            TeamGameLog.game_date,
            TeamGameLog.season,
            TeamGameLog.season_type,
            TeamGameLog.team_id,          # home
            TeamGameLog.opponent_id,      # away
            (TeamGameLog.points_scored + TeamGameLog.points_allowed).label("total"),
        )
        .where(TeamGameLog.is_home.is_(True))
        .where(TeamGameLog.is_completed.is_(True))
        .where(TeamGameLog.season >= start_season)
        .where(TeamGameLog.season <= end_season)
        .where(TeamGameLog.season_type.in_(types))
        # Secondary key: game_date ties are common (simultaneous tip-offs) and
        # Postgres returns ties in physical order, which changes when rows are
        # updated. A seeded backtest must not depend on heap layout.
        .order_by(TeamGameLog.game_date, TeamGameLog.espn_game_id)
    ).all()


#: Providers whose lines are set DURING the game. Including them is
#: catastrophic lookahead — an in-game total reflects the score so far.
#: `ESPN Bet - Live Odds` alone carries 502 "open" values and zero closes.
LIVE_PROVIDER_MARKER = "live"

#: A WNBA total moving more than this from open to close is not a real market
#: move — it is mismatched data. Real same-provider moves average ~0.3-0.6.
MAX_PLAUSIBLE_LINE_MOVE = 10.0


def _is_live_provider(name: str | None) -> bool:
    return LIVE_PROVIDER_MARKER in (name or "").lower()


def _odds_for_game(session: Session, espn_game_id: str) -> tuple[float | None, float | None, float, float]:
    """(entry_line, closing_line, over_price, under_price).

    Two correctness rules, both learned the hard way:

    1. **Exclude live-odds providers.** Their lines are set during the game.
    2. **Pair open and close from the SAME provider row.** Taking a median of
       opens across providers and a median of closes across a *different* set
       of providers compares unrelated numbers and fabricates line movement.

    Closing lines are used only where a genuine `close` object existed — never
    inferred, since CLV is the headline metric.
    """
    # COLUMNS, NOT ENTITIES — this is a memory bound, not a style choice.
    # `session.scalars(select(SportsbookOdds))` returns ORM instances, and the
    # identity map holds a strong reference to every one of them for the life
    # of the session. build() shares ONE session across all three fill models,
    # so a full traversal of sportsbook_odds was retained for the whole run and
    # released only when build() returned. That is what took the operator's
    # machine to ~9GB RSS and swap on 2026-08-18. Row tuples are not tracked,
    # so peak memory here is now one game's odds rather than the whole table.
    rows = [
        r for r in session.execute(
            select(
                SportsbookOdds.provider_name,
                SportsbookOdds.open_total,
                SportsbookOdds.close_total,
                SportsbookOdds.is_closing_line,
                SportsbookOdds.over_under,
                SportsbookOdds.over_odds,
                SportsbookOdds.under_odds,
            ).where(SportsbookOdds.espn_game_id == espn_game_id)
        ).all()
        if not _is_live_provider(r.provider_name)
    ]
    if not rows:
        return None, None, DEFAULT_PRICE, DEFAULT_PRICE

    # Prefer a single provider that has BOTH an open and a genuine close.
    paired = [
        r for r in rows
        if r.open_total is not None and r.close_total is not None and r.is_closing_line
    ]
    entry = closing = None
    if paired:
        paired.sort(key=lambda r: float(r.open_total))
        chosen = paired[len(paired) // 2]
        entry = float(chosen.open_total)
        closing = float(chosen.close_total)
        if abs(closing - entry) > MAX_PLAUSIBLE_LINE_MOVE:
            # Mismatched data rather than a real move; drop the pair.
            entry = closing = None

    if entry is None:
        consensus = [float(r.over_under) for r in rows if r.over_under is not None]
        if consensus:
            entry = sorted(consensus)[len(consensus) // 2]

    over_odds = [float(r.over_odds) for r in rows if r.over_odds is not None]
    under_odds = [float(r.under_odds) for r in rows if r.under_odds is not None]
    over_price = american_to_price(sorted(over_odds)[len(over_odds) // 2]) if over_odds else DEFAULT_PRICE
    under_price = american_to_price(sorted(under_odds)[len(under_odds) // 2]) if under_odds else DEFAULT_PRICE

    return entry, closing, over_price, under_price


def _availability_delta(
    *,
    index: PlayerAvailabilityIndex | None,
    mode: str,
    espn_game_id: str,
    home_id: str,
    away_id: str | None,
    as_of: dt.datetime,
) -> tuple[float, bool]:
    """Combined points adjustment for both teams' absences, and whether any.

    The sum of both teams' deltas is the adjustment to the *total*: a scorer
    out on either side lowers the expected combined score.
    """
    if mode == "off" or index is None or away_id is None:
        return 0.0, False
    if mode not in {"oracle", "report"}:
        raise ValueError(f"unknown availability_mode: {mode!r}")

    total = 0.0
    absence = False
    for team_id in (home_id, away_id):
        if mode == "oracle":
            absent = index.oracle_absent_ids(
                espn_game_id=espn_game_id, team_id=team_id, as_of=as_of
            )
        else:
            absent = index.absent_from_reports(team_id=team_id, as_of=as_of)
        if not absent:
            continue

        projections, n_games = index.projections(team_id=team_id, as_of=as_of)
        adj = adjustment_from_projections(
            team_id=team_id, as_of=as_of, projections=projections,
            n_games=n_games, absent_ids=absent,
        )
        if not adj.sufficient_data:
            continue
        total += adj.delta_points
        absence = absence or adj.has_absence
    return total, absence


def run_backtest(
    *,
    session: Session,
    config: BacktestConfig | None = None,
    model_config: WNBATotalsConfig | None = None,
) -> BacktestResult:
    """Walk forward through history, betting totals against the sportsbook line."""
    cfg = config or BacktestConfig()
    mcfg = model_config or CONFIG
    rng = random.Random(cfg.seed)   # seeded: results must be exactly replayable

    result = BacktestResult(
        config=cfg,
        model_version=MODEL_VERSION,
        config_hash=compute_config_hash(mcfg.as_dict()),
    )

    availability: PlayerAvailabilityIndex | None = None
    if cfg.availability_mode != "off":
        availability = PlayerAvailabilityIndex(
            session=session,
            start_season=cfg.start_season,
            end_season=cfg.end_season,
            half_life=mcfg.form_half_life_games,
        )
        if cfg.availability_mode == "report":
            availability.load_injury_log(session=session)

    bankroll = cfg.starting_bankroll
    equity = [bankroll]
    calib_pairs: list[tuple[float, int]] = []
    tracker = SlopeTracker()

    for game_id, game_date, season, season_type, home_id, away_id, actual_total in _game_rows(
        session, cfg.start_season, cfg.end_season, cfg.include_playoffs
    ):
        result.games_considered += 1

        entry_line, closing_line, over_price, under_price = _odds_for_game(session, game_id)
        if entry_line is None:
            result.games_no_odds += 1
            continue
        if closing_line is None:
            result.games_no_closing_line += 1

        # --- everything below is computed as_of tip-off, never later --- #
        features = build_matchup_features(
            home_team_id=home_id, away_team_id=away_id,
            as_of=game_date, session=session, season=season,
            is_playoff_game=(season_type == SEASON_TYPE_POSTSEASON),
            config=mcfg,
        )
        if not features.sufficient_data:
            result.games_insufficient_features += 1
            continue

        dist = estimate_totals_distribution(as_of=game_date, session=session, season=season)
        projection = project(features, config=mcfg, sigma=dist.sigma)

        avail_delta, has_absence = _availability_delta(
            index=availability, mode=cfg.availability_mode, espn_game_id=game_id,
            home_id=home_id, away_id=away_id, as_of=game_date,
        )
        projected_total = projection.projected_total + cfg.availability_beta * avail_delta

        raw_diff = projected_total - entry_line
        slope = tracker.slope()
        sel_diff = slope * raw_diff if cfg.shrink_to_market else raw_diff
        prob_diff = slope * raw_diff if cfg.calibrate_probabilities else sel_diff
        # Update AFTER using the slope, never before — no peeking at this game.
        if actual_total is not None:
            tracker.add(raw_diff, float(actual_total) - entry_line)
        if abs(sel_diff) < cfg.min_edge_points:
            continue

        side = "over" if sel_diff > 0 else "under"
        entry_price = over_price if side == "over" else under_price
        model_p = prob_over(entry_line + prob_diff, entry_line, dist.sigma)
        if side == "under":
            model_p = 1.0 - model_p
        edge = model_p - entry_price

        fill = simulate_fill(
            quoted_price=entry_price,
            contracts=cfg.stake_per_bet / max(entry_price, 1e-6),
            model=cfg.fill_model,
            rng_value=rng.random(),
            assume_rebate=cfg.assume_maker_rebate,
            adverse_selection_override=cfg.adverse_selection_override,
        )

        won = None
        pnl = 0.0
        if actual_total is not None:
            hit_over = actual_total > entry_line
            won = hit_over if side == "over" else (not hit_over)
            if fill.filled:
                pnl = pnl_for_contract(fill.price, won) * fill.contracts - fill.fee

        clv = None
        if closing_line is not None:
            # Positive CLV = the line moved toward our side after we bet.
            clv = (closing_line - entry_line) if side == "over" else (entry_line - closing_line)

        if fill.filled:
            bankroll += pnl
            equity.append(bankroll)
            result.metrics.n_filled += 1
            result.metrics.total_pnl += pnl
            result.metrics.total_staked += cfg.stake_per_bet
            result.metrics.total_fees += fill.fee
            if won is not None:
                result.metrics.n_resolved += 1
                result.metrics.n_wins += int(won)
                result.metrics.returns.append(pnl / cfg.stake_per_bet)
                result.metrics.edges.append(edge)
                result.metrics.realised.append(pnl / cfg.stake_per_bet)
                calib_pairs.append((model_p, int(won)))

        if clv is not None:
            result.metrics.clv_points.append(clv)
            result.metrics.n_with_closing_line += 1

        result.metrics.n_bets += 1
        result.bets.append(
            BetRecord(
                game_date=game_date, espn_game_id=game_id, season=season,
                season_type=season_type, side=side, entry_line=entry_line,
                closing_line=closing_line, projected_total=projected_total,
                model_probability=model_p, entry_price=fill.price, edge=edge,
                contracts=fill.contracts, filled=fill.filled, fee=fill.fee,
                actual_total=actual_total, won=won, pnl=pnl, clv_points=clv,
                is_playoff=(season_type == SEASON_TYPE_POSTSEASON),
                availability_delta=cfg.availability_beta * avail_delta,
                has_absence=has_absence,
                sigma=dist.sigma,
                over_price=over_price,
                under_price=under_price,
            )
        )

    result.metrics.equity_curve = equity
    result.metrics.calibration = build_calibration(calib_pairs)
    return result
