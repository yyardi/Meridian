"""Prediction logger — the system's own dataset.

Every fair value the model emits is written here with the live market price and
a timestamp; the resolution job fills in the outcome later. That log **is** the
long-run dataset, and it compounds daily.

The question it exists to answer, at any moment:

    "How would every prediction I have ever made have performed?"

Two rules that make that answerable rather than merely plausible:

* **Log everything, not just actionable predictions.** No-edge predictions are
  the control group. Without them you cannot distinguish a skilled model from
  selective memory. `is_actionable` is a flag, not a filter.
* **Append-only.** A prediction's model price is never rewritten. Only the
  resolution fields are filled in later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.storage import MarketSnapshot, Prediction, get_engine, get_sessionmaker
from core.feeds.espn_client import ESPNClient
from core.team_mapping import (
    UnknownTeamError,
    orient_for_slug,
    orientation_from_scoreboard,
    parse_market_slug,
)
from strategies.wnba_totals.config import CONFIG, WNBATotalsConfig
from strategies.wnba_totals.model.fair_value import (
    MARKET_SPREAD,
    MARKET_TOTAL,
    MARKET_WINNER,
    MODEL_VERSION,
    STRATEGY,
    Projection,
    estimate_totals_distribution,
    predict_market,
    project,
    to_decimal,
)
from strategies.wnba_totals.model.features import build_matchup_features

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


class PredictionStats:
    def __init__(self) -> None:
        self.markets_seen = 0
        self.predictions_written = 0
        self.skipped_unparseable = 0
        self.skipped_insufficient = 0
        self.skipped_unknown_team = 0
        self.errors = 0


def _espn_team_id(session: Session, abbrev: str, season: int) -> str | None:
    """Resolve an ESPN abbreviation to its team id for a season."""
    from core.storage import TeamGameLog

    return session.scalar(
        select(TeamGameLog.team_id)
        .where(TeamGameLog.team_abbrev == abbrev)
        .where(TeamGameLog.season == season)
        .limit(1)
    )


class PredictionLogger:
    def __init__(self, sessionmaker=None, config: WNBATotalsConfig | None = None) -> None:
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self.config = config or CONFIG

    def latest_snapshot_time(self, session: Session) -> dt.datetime | None:
        return session.scalar(select(func.max(MarketSnapshot.captured_at)))

    def run(self, as_of: dt.datetime | None = None) -> PredictionStats:
        """Predict every market in the most recent snapshot."""
        stats = PredictionStats()

        with self._Session() as session:
            snapshot_time = self.latest_snapshot_time(session)
            if snapshot_time is None:
                log.warning("no_snapshots", hint="run the recorder first")
                return stats

            as_of = as_of or snapshot_time
            season = as_of.year

            markets = session.scalars(
                select(MarketSnapshot).where(MarketSnapshot.captured_at == snapshot_time)
            ).all()

            dist = estimate_totals_distribution(as_of=as_of, session=session, season=season)
            log.info(
                "totals_distribution",
                mean=round(dist.mean, 1),
                sigma=round(dist.sigma, 1),
                season_games=dist.n_current_season,
                shrunk=dist.shrunk_toward_history,
            )

            # Home/away comes from ESPN, never from the slug: Polymarket's slug
            # order is inconsistent (18 of 285 closed markets put the HOME team
            # first), and trusting it would silently invert spread/moneyline
            # predictions. See core.team_mapping.
            dates = sorted({
                p.local_date
                for p in (parse_market_slug(m.market_slug) for m in markets)
                if p is not None
            })
            span = []
            for d in dates:
                span.extend([d, d + dt.timedelta(days=1)])
            orientation_map = orientation_from_scoreboard(
                espn_client=ESPNClient(), dates=sorted(set(span))
            )
            log.info("orientation_map_built", games=len(orientation_map))

            # One projection per event, reused across that event's ~18 markets.
            projections: dict[str, tuple[Projection, object]] = {}
            rows: list[Prediction] = []

            for snap in markets:
                stats.markets_seen += 1
                try:
                    row = self._predict_one(
                        session=session, snap=snap, as_of=as_of, season=season,
                        sigma=dist.sigma, projections=projections, stats=stats,
                        orientation_map=orientation_map,
                    )
                except UnknownTeamError as exc:
                    stats.skipped_unknown_team += 1
                    log.warning("unknown_team", market=snap.market_slug, error=str(exc))
                    continue
                except Exception as exc:
                    stats.errors += 1
                    log.error(
                        "prediction_failed", market=snap.market_slug,
                        error=str(exc), exc_info=True,
                    )
                    continue
                if row is not None:
                    rows.append(row)

            session.add_all(rows)
            session.commit()
            stats.predictions_written = len(rows)

        log.info(
            "prediction_run_complete",
            markets=stats.markets_seen,
            written=stats.predictions_written,
            skipped_insufficient=stats.skipped_insufficient,
            skipped_unparseable=stats.skipped_unparseable,
            skipped_unknown_team=stats.skipped_unknown_team,
            errors=stats.errors,
        )
        return stats

    def _predict_one(
        self, *, session: Session, snap: MarketSnapshot, as_of: dt.datetime,
        season: int, sigma: float, projections: dict, stats: PredictionStats,
        orientation_map: dict,
    ) -> Prediction | None:
        parsed = parse_market_slug(snap.market_slug)
        if parsed is None:
            stats.skipped_unparseable += 1
            return None

        orientation = orient_for_slug(parsed, orientation_map)
        if orientation is None:
            stats.skipped_unknown_team += 1
            return None

        event_key = f"{orientation.espn_game_id}"
        if event_key not in projections:
            home_id = _espn_team_id(session, orientation.home_abbrev, season)
            away_id = _espn_team_id(session, orientation.away_abbrev, season)
            if home_id is None or away_id is None:
                stats.skipped_unknown_team += 1
                return None

            features = build_matchup_features(
                home_team_id=home_id, away_team_id=away_id,
                as_of=as_of, session=session, season=season,
                is_playoff_game=False,   # regular season; playoffs flagged by season_type
                config=self.config,
            )
            projections[event_key] = (
                project(features, config=self.config, sigma=sigma),
                features,
            )

        projection, features = projections[event_key]

        line = float(snap.line) if snap.line is not None else None
        bid = float(snap.best_bid) if snap.best_bid is not None else None
        ask = float(snap.best_ask) if snap.best_ask is not None else None

        mtype = snap.sports_market_type
        # The market is quoted from the FIRST slug team's perspective; whether
        # that team is home or away comes from ESPN, not the slug.
        quoted_side_is_home = orientation.first_is_home

        if mtype == MARKET_SPREAD:
            # "cover +L" for the quoted side means its margin > -L
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_SPREAD,
                line=-line if line is not None else None,
                market_bid=bid, market_ask=ask,
                config=self.config, is_home_side=quoted_side_is_home,
            )
        elif mtype == MARKET_WINNER:
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_WINNER,
                line=None, market_bid=bid, market_ask=ask,
                config=self.config, is_home_side=quoted_side_is_home,
            )
        elif mtype == MARKET_TOTAL:
            pred = predict_market(
                features=features, projection=projection,
                market_slug=snap.market_slug, sports_market_type=MARKET_TOTAL,
                line=line, market_bid=bid, market_ask=ask,
                config=self.config, is_over_side=True,
            )
        else:
            return None

        if pred is None:
            stats.skipped_insufficient += 1
            return None

        return Prediction(
            predicted_at=as_of,
            model_version=pred.model_version,
            strategy=STRATEGY,
            market_slug=pred.market_slug,
            event_slug=snap.event_slug,
            game_id=snap.game_id,
            sports_market_type=pred.sports_market_type,
            line=snap.line,
            model_probability=to_decimal(pred.model_probability),
            model_fair_value=to_decimal(pred.model_fair_value),
            market_bid=to_decimal(pred.market_bid),
            market_ask=to_decimal(pred.market_ask),
            market_mid=to_decimal(pred.market_mid),
            edge=to_decimal(pred.edge, "0.000001"),
            features=pred.features,
            model_config_snapshot=pred.model_config_snapshot,
            config_hash=pred.config_hash,
            is_actionable=pred.is_actionable,
            reduced_confidence=pred.reduced_confidence,
            confidence_notes=pred.confidence_notes,
        )


def _configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-predictions")
    parser.add_argument("--run", action="store_true", help="predict the latest snapshot")
    args = parser.parse_args()

    _configure_logging()
    if not args.run:
        parser.error("--run is required")
    PredictionLogger().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
