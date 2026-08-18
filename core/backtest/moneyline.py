"""Walk-forward backtest for the MONEYLINE and SPREAD. Money-at-price only.

    python -m core.backtest.moneyline
    python -m core.backtest.moneyline --start 2024 --end 2026 --min-edge 0.03

Why this is a separate module from `engine.py`
----------------------------------------------
Not scope creep — a different metric set. `engine.py` is totals, and its
headline is **CLV**, which needs an entry line and a genuinely different
closing line. Totals have that: ESPN's historical rows carry `open_total` and
`close_total` as two columns on the same row (818 of them).

**Moneyline and spread have no such pair, and this was measured rather than
assumed.** On the live primary, 2026-08-18:

* 1,697 games carry a moneyline, and the multiple rows per game are **different
  sportsbooks** — 6.92 providers on average, up to 16 — not a time series.
* Within a single provider, only 51 game-provider pairs show any moneyline
  variation at all.
* Every odds row was captured **after** the game finished (median ~4 years
  after); `captured_at` is backfill time, not observation time.
* So the 1,192 games where `home_moneyline` "changed" are cross-provider
  *disagreement*, not market *movement*. That check cannot tell the two apart,
  and reading it as movement is the mistake this module exists downstream of.

Fabricating a close — taking another book's number, or the consensus, as "the
close" — would put a corrupted CLV in the same column as the totals engine's
real one. So **CLV is reported as unavailable here, not as a number.** The
venue-specific version of the question is answerable forward, from the 200ms
Polymarket archive, and belongs in the in-game replay rather than here.

What IS measured
----------------
Money-at-price, the C11 frame: buy at the book's de-vigged price, settle 0/1,
ROI over dollars staked. Win rate is reported only beside its stake-weighted
entry cost, because on a portfolio of mixed prices a bare hit rate is a
category error.

Uncertainty is **game-clustered** (C4). A game contributes at most one
moneyline bet and one spread bet, and those two are the same disagreement seen
twice — a projected margin that is wrong for the moneyline is wrong for the
spread. Treating them as independent would understate the interval by roughly
√2 on exactly the games that matter most.

Assumptions, stated because they are load-bearing
-------------------------------------------------
* **Spread juice is assumed −110/−110.** `sportsbook_odds` has `over_odds` and
  `under_odds` for totals but no spread-price columns, so the standard two-way
  price is used. Real spread juice varies a little; a systematically wrong
  assumption here would bias spread ROI, and it is the first thing to check if
  spread numbers look surprising.
* **Live providers are excluded**, reusing `engine._is_live_provider`. A line
  set during the game reflects the score so far, and including one is
  catastrophic lookahead rather than a small bias.
* Prices are de-vigged proportionally (`devig_two_sided`), so the model is
  compared against the book's *belief*, not against the book's margin.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import logging
import math
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.backtest.engine import _is_live_provider, _game_rows
from core.backtest.exp_devigged_clv import devig_two_sided
from core.backtest.fills import (
    american_to_price,
    fee_per_contract,
    pnl_for_contract,
)
from core.config import SEASON_TYPE_POSTSEASON, SEASON_TYPE_REGULAR
from core.storage import SportsbookOdds, TeamGameLog
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.fair_value import (
    MARGIN_SIGMA_RATIO,
    MODEL_VERSION,
    estimate_totals_distribution,
    prob_cover,
    prob_home_win,
    project,
)
from strategies.wnba_totals.model.features import build_matchup_features

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

MARKET_ML = "moneyline"
MARKET_SPREAD = "spread"

#: Standard two-way juice, used for the spread because the odds table carries
#: no spread-price columns. See the module docstring.
DEFAULT_TWO_WAY_ODDS = -110.0

#: Why CLV is absent, carried in the result so a reader never has to guess
#: whether it was forgotten.
CLV_UNAVAILABLE = (
    "no open->close pair exists for moneyline or spread: the odds history "
    "carries one consensus value per game per provider (6.92 providers on "
    "average), every row backfilled after the game finished. Cross-provider "
    "disagreement is not market movement. Fabricating a close would corrupt "
    "the metric, so it is omitted rather than estimated."
)


@dataclass
class MarketBet:
    """One simulated bet, with everything needed to audit it."""

    espn_game_id: str
    game_date: dt.datetime
    season: int
    market: str                 # 'moneyline' | 'spread'
    side: str                   # 'home' | 'away'
    line: float | None          # spread line; None for the moneyline
    model_probability: float
    book_probability: float     # de-vigged
    entry_price: float          # what a contract costs
    edge: float                 # model - book, in probability
    won: bool
    pnl: float                  # per contract, excluding fees
    fee: float


@dataclass
class MarketSummary:
    market: str
    bets: list[MarketBet] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.bets)

    @property
    def games(self) -> int:
        return len({b.espn_game_id for b in self.bets})

    @property
    def staked(self) -> float:
        return sum(b.entry_price for b in self.bets)

    @property
    def pnl(self) -> float:
        return sum(b.pnl for b in self.bets)

    @property
    def fees(self) -> float:
        return sum(b.fee for b in self.bets)

    @property
    def roi(self) -> float | None:
        return None if self.staked == 0 else self.pnl / self.staked

    @property
    def hit_rate(self) -> float | None:
        return None if not self.bets else sum(1 for b in self.bets if b.won) / len(self.bets)

    @property
    def entry_cost(self) -> float | None:
        """Stake-weighted average price — the breakeven the hit rate must beat.

        Reported next to `hit_rate` always. A 45% hit rate on 0.42 entries is
        profit; the same number alone reads as failure (C11).
        """
        return None if not self.bets else self.staked / len(self.bets)

    def roi_interval(self, *, resamples: int = 4000, seed: int = 42
                     ) -> tuple[float, float] | None:
        """Game-clustered bootstrap CI on ROI. Resamples GAMES, not bets."""
        if self.games < 2:
            return None
        by_game: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for b in self.bets:
            by_game[b.espn_game_id][0] += b.pnl
            by_game[b.espn_game_id][1] += b.entry_price
        keys = sorted(by_game)
        rng = random.Random(seed)
        out = []
        for _ in range(resamples):
            pnl = staked = 0.0
            for _ in keys:
                k = rng.choice(keys)
                pnl += by_game[k][0]
                staked += by_game[k][1]
            if staked > 0:
                out.append(pnl / staked)
        if len(out) < 2:
            return None
        out.sort()
        return out[int(0.025 * len(out))], out[int(0.975 * len(out))]

    def as_dict(self) -> dict:
        ci = self.roi_interval()
        return {
            "market": self.market,
            "bets": self.n,
            "games": self.games,
            "staked": round(self.staked, 2),
            "pnl": round(self.pnl, 2),
            "roi": None if self.roi is None else round(self.roi, 4),
            "roi_ci95_game_clustered": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
            "roi_ci_crosses_zero": None if ci is None else bool(ci[0] < 0 < ci[1]),
            "hit_rate": None if self.hit_rate is None else round(self.hit_rate, 4),
            "entry_cost_stake_weighted": (
                None if self.entry_cost is None else round(self.entry_cost, 4)
            ),
            "fees_as_reported": round(self.fees, 2),
            "mean_clv": None,
            "clv_unavailable_because": CLV_UNAVAILABLE,
        }


@dataclass
class MoneylineConfig:
    start_season: int = 2024
    end_season: int = 2026
    #: Minimum |model − book| in probability before betting. The totals engine
    #: gates on POINTS; a binary win-probability market has no points, and
    #: reusing a points threshold here is the miscalibration this backtest was
    #: asked to test for.
    min_edge: float = 0.03
    include_playoffs: bool = True
    markets: tuple[str, ...] = (MARKET_ML, MARKET_SPREAD)
    seed: int = 42


@dataclass
class MoneylineResult:
    config: MoneylineConfig
    model_version: str
    summaries: dict[str, MarketSummary] = field(default_factory=dict)
    games_considered: int = 0
    games_no_odds: int = 0
    games_insufficient_features: int = 0

    def as_dict(self) -> dict:
        return {
            "model_version": self.model_version,
            "config": dataclasses.asdict(self.config),
            "games_considered": self.games_considered,
            "games_no_odds": self.games_no_odds,
            "games_insufficient_features": self.games_insufficient_features,
            "markets": [s.as_dict() for s in self.summaries.values()],
        }


def _ml_and_spread_for_game(
    session: Session, espn_game_id: str
) -> tuple[float | None, float | None, float | None]:
    """(de-vigged P(home) from the moneyline, home spread line, spread price).

    Live providers are excluded — a line set during the game reflects the score
    so far. Consensus is the median across the remaining books.
    """
    rows = [
        r for r in session.execute(
            select(
                SportsbookOdds.provider_name,
                SportsbookOdds.home_moneyline,
                SportsbookOdds.away_moneyline,
                SportsbookOdds.spread,
            ).where(SportsbookOdds.espn_game_id == espn_game_id)
        ).all()
        if not _is_live_provider(r.provider_name)
    ]
    if not rows:
        return None, None, None

    p_home = None
    pairs = [
        (float(r.home_moneyline), float(r.away_moneyline))
        for r in rows
        if r.home_moneyline is not None and r.away_moneyline is not None
    ]
    if pairs:
        probs = []
        for home_odds, away_odds in pairs:
            devigged = devig_two_sided(
                american_to_price(home_odds), american_to_price(away_odds)
            )
            if devigged is not None:
                probs.append(devigged[0])
        if probs:
            p_home = sorted(probs)[len(probs) // 2]

    spreads = [float(r.spread) for r in rows if r.spread is not None]
    spread_line = sorted(spreads)[len(spreads) // 2] if spreads else None
    spread_price = american_to_price(DEFAULT_TWO_WAY_ODDS)
    return p_home, spread_line, spread_price


def run_backtest(
    *,
    session: Session,
    config: MoneylineConfig | None = None,
    model_config: WNBATotalsConfig | None = None,
) -> MoneylineResult:
    """Walk forward, pricing the moneyline and spread against the book."""
    cfg = config or MoneylineConfig()
    mcfg = model_config or CONFIG

    result = MoneylineResult(config=cfg, model_version=MODEL_VERSION)
    for market in cfg.markets:
        result.summaries[market] = MarketSummary(market=market)

    for row in _game_rows(session, cfg.start_season, cfg.end_season, cfg.include_playoffs):
        result.games_considered += 1
        as_of = row.game_date

        features = build_matchup_features(
            session=session, home_team_id=row.team_id, away_team_id=row.opponent_id,
            as_of=as_of, config=mcfg,
        )
        if features is None or not features.sufficient_data:
            result.games_insufficient_features += 1
            continue

        dist = estimate_totals_distribution(
            as_of=as_of, session=session, season=row.season
        )
        projection = project(features, config=mcfg, sigma=dist.sigma)
        if projection is None:
            result.games_insufficient_features += 1
            continue

        p_home_book, spread_line, spread_price = _ml_and_spread_for_game(
            session, row.espn_game_id
        )
        if p_home_book is None and spread_line is None:
            result.games_no_odds += 1
            continue

        home_pts, away_pts = _final_scores(session, row.espn_game_id)
        if home_pts is None or away_pts is None:
            continue
        margin = home_pts - away_pts
        sigma_margin = projection.sigma * MARGIN_SIGMA_RATIO

        if MARKET_ML in cfg.markets and p_home_book is not None:
            p_model = prob_home_win(projection.projected_margin, sigma_margin)
            bet = _maybe_bet(
                row=row, market=MARKET_ML, line=None,
                p_model_home=p_model, p_book_home=p_home_book,
                price_home=p_home_book, price_away=1.0 - p_home_book,
                home_won=margin > 0, min_edge=cfg.min_edge,
            )
            if bet is not None:
                result.summaries[MARKET_ML].bets.append(bet)

        if MARKET_SPREAD in cfg.markets and spread_line is not None:
            # SIGN, and it is the whole bet. `sportsbook_odds.spread` is the
            # home HANDICAP — negative when home is favoured (mean -1.82 against
            # a mean home margin of +1.55, corr -0.49 over 1,642 games). But
            # `prob_cover` is documented as P(home margin > line), i.e. it wants
            # the number the margin must EXCEED. Those are negatives of each
            # other.
            #
            # Passing the handicap straight through prices P(margin > -5) — the
            # chance home loses by fewer than 5 — while settlement scores
            # `margin + spread > 0`, i.e. margin > +5. The model then bets the
            # opposite side of the one it is graded on, every time, and the
            # result looks like a confident measured loss rather than a bug.
            # First draft of this module did exactly that and reported spread
            # ROI -7.27% with a CI excluding zero.
            cover_threshold = -spread_line
            p_model = prob_cover(
                projection.projected_margin, cover_threshold, sigma_margin
            )
            devigged = devig_two_sided(spread_price, spread_price)
            p_book = devigged[0] if devigged else 0.5
            bet = _maybe_bet(
                row=row, market=MARKET_SPREAD, line=spread_line,
                p_model_home=p_model, p_book_home=p_book,
                price_home=spread_price, price_away=spread_price,
                home_won=(margin + spread_line) > 0, min_edge=cfg.min_edge,
            )
            if bet is not None:
                result.summaries[MARKET_SPREAD].bets.append(bet)

    return result


def _final_scores(session: Session, espn_game_id: str) -> tuple[int | None, int | None]:
    row = session.execute(
        select(TeamGameLog.points_scored, TeamGameLog.points_allowed)
        .where(TeamGameLog.espn_game_id == espn_game_id)
        .where(TeamGameLog.is_home.is_(True))
    ).first()
    return (row.points_scored, row.points_allowed) if row else (None, None)


def _maybe_bet(
    *, row, market: str, line: float | None,
    p_model_home: float, p_book_home: float,
    price_home: float, price_away: float,
    home_won: bool, min_edge: float,
) -> MarketBet | None:
    """Take the side the model likes, if it likes it by more than `min_edge`.

    Edge is in PROBABILITY, not points. Both sides are considered: refusing to
    bet the away side would silently halve the sample and bias the result
    toward whatever the home-field term happens to do.
    """
    edge_home = p_model_home - p_book_home
    edge_away = (1.0 - p_model_home) - (1.0 - p_book_home)
    side, edge, price, model_p, book_p, won = (
        ("home", edge_home, price_home, p_model_home, p_book_home, home_won)
        if edge_home >= edge_away
        else ("away", edge_away, price_away, 1.0 - p_model_home,
              1.0 - p_book_home, not home_won)
    )
    if edge < min_edge or not (0.0 < price < 1.0):
        return None
    return MarketBet(
        espn_game_id=row.espn_game_id, game_date=row.game_date, season=row.season,
        market=market, side=side, line=line,
        model_probability=model_p, book_probability=book_p,
        entry_price=price, edge=edge, won=won,
        pnl=pnl_for_contract(price, won),
        fee=fee_per_contract(price, is_maker=False),
    )
