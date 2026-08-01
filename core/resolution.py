"""Resolution job — attach ground truth to predictions.

Two independent sources, deliberately:

* **Polymarket settlement** is authoritative for how a market actually paid
  (free, unauthenticated): ``{"slug": ..., "settlement": 0|1}``.
* **ESPN final scores** give `actual_total` and act as a cross-check.

When they disagree we log loudly and write neither silently, because a
disagreement means either a data bug or a market-resolution edge case and both
are worth knowing about.

Joining the two systems is the hard part — see `core.team_mapping` for the
three verified hazards (different ID spaces, different abbreviations, different
timezones). A *wrong* join is worse than a missing one: it attaches the wrong
outcome to a prediction and silently corrupts the backtest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.config import SEASON_TYPE_PRESEASON
from core.polymarket.client import PolymarketGatewayClient
from core.storage import (
    MarketSnapshot,
    Prediction,
    ResolvedOutcome,
    TeamGameLog,
    get_engine,
    get_sessionmaker,
)
from core.team_mapping import (
    PREFIX_MONEYLINE,
    PREFIX_SPREAD,
    PREFIX_TOTAL,
    UnknownTeamError,
    parse_market_slug,
    resolve_orientation,
    utc_window,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


class ResolutionStats:
    def __init__(self) -> None:
        self.markets_seen = 0
        self.outcomes_written = 0
        self.predictions_updated = 0
        self.no_espn_match = 0
        self.ambiguous_match = 0
        self.not_settled = 0
        self.disagreements = 0
        self.errors = 0


def find_espn_game(
    *, session: Session, market_slug: str
) -> tuple[TeamGameLog, TeamGameLog] | None:
    """Match a Polymarket market to an ESPN game.

    Join key is the normalised team pair plus a UTC window around the slug's
    local date — never the date alone (evening games cross midnight UTC) and
    never the game id (different ID spaces).

    Returns (home_row, away_row) or None. Ambiguity returns None rather than a
    guess.
    """
    parsed = parse_market_slug(market_slug)
    if parsed is None:
        return None

    # Home/away from ESPN, never from slug order — see core.team_mapping.
    orientation = resolve_orientation(session=session, parsed=parsed)
    if orientation is None:
        return None

    home_row = session.scalar(
        select(TeamGameLog).where(
            and_(
                TeamGameLog.espn_game_id == orientation.espn_game_id,
                TeamGameLog.is_home.is_(True),
                TeamGameLog.is_completed.is_(True),
                TeamGameLog.season_type != SEASON_TYPE_PRESEASON,
            )
        )
    )
    if home_row is None:
        return None

    away_row = session.scalar(
        select(TeamGameLog).where(
            TeamGameLog.espn_game_id == home_row.espn_game_id,
            TeamGameLog.team_id == home_row.opponent_id,
        )
    )
    if away_row is None:
        return None
    return home_row, away_row


def implied_settlement(
    *, market_slug: str, home: TeamGameLog, away: TeamGameLog, line: float | None
) -> int | None:
    """What ESPN's final score implies this market should settle to.

    Used only as a cross-check against Polymarket's authoritative settlement.
    Polymarket quotes the away (first-in-slug) team's side.
    """
    parsed = parse_market_slug(market_slug)
    if parsed is None or home.points_scored is None or away.points_scored is None:
        return None

    home_pts = float(home.points_scored)
    away_pts = float(away.points_scored)

    # The market is quoted from the FIRST slug team's side; whether that team
    # is home or away is an ESPN fact, not a slug fact.
    quoted_is_home = home.team_abbrev == parsed.first_espn
    quoted_pts = home_pts if quoted_is_home else away_pts
    opponent_pts = away_pts if quoted_is_home else home_pts

    if parsed.market_type == PREFIX_TOTAL:
        if line is None:
            return None
        return 1 if (home_pts + away_pts) > line else 0

    if parsed.market_type == PREFIX_MONEYLINE:
        return 1 if quoted_pts > opponent_pts else 0

    if parsed.market_type == PREFIX_SPREAD:
        if line is None:
            return None
        # "quoted side covers +L"  <=>  quoted_margin + L > 0
        return 1 if (quoted_pts - opponent_pts) + line > 0 else 0

    return None


class ResolutionJob:
    def __init__(self, sessionmaker=None, client: PolymarketGatewayClient | None = None) -> None:
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self._client = client or PolymarketGatewayClient()

    def run(self, limit: int | None = None) -> ResolutionStats:
        """Resolve every predicted market that is not yet resolved."""
        stats = ResolutionStats()

        with self._Session() as session:
            unresolved = session.execute(
                select(
                    Prediction.market_slug,
                    func.max(Prediction.line),
                    func.max(Prediction.sports_market_type),
                )
                .where(Prediction.resolved_outcome.is_(None))
                .where(
                    Prediction.market_slug.notin_(
                        select(ResolvedOutcome.market_slug)
                    )
                )
                # Only ask about markets whose game has actually finished.
                # Without this the job fires a settlement request per unplayed
                # market every cycle and collects ~100 404s for nothing.
                .where(
                    Prediction.market_slug.in_(
                        select(MarketSnapshot.market_slug).where(
                            MarketSnapshot.game_start_time
                            < dt.datetime.now(UTC) - dt.timedelta(hours=3)
                        )
                    )
                )
                .group_by(Prediction.market_slug)
                .limit(limit)
            ).all()

            for market_slug, line, _mtype in unresolved:
                stats.markets_seen += 1
                try:
                    self._resolve_one(session, market_slug, line, stats)
                except UnknownTeamError as exc:
                    stats.errors += 1
                    log.warning("unknown_team", market=market_slug, error=str(exc))
                except Exception as exc:
                    stats.errors += 1
                    log.error(
                        "resolution_failed", market=market_slug,
                        error=str(exc), exc_info=True,
                    )
            session.commit()

            stats.predictions_updated = self._backfill_predictions(session)
            session.commit()

        log.info(
            "resolution_complete",
            markets=stats.markets_seen,
            outcomes_written=stats.outcomes_written,
            predictions_updated=stats.predictions_updated,
            no_espn_match=stats.no_espn_match,
            not_settled=stats.not_settled,
            disagreements=stats.disagreements,
            errors=stats.errors,
        )
        return stats

    def _resolve_one(
        self, session: Session, market_slug: str, line, stats: ResolutionStats
    ) -> None:
        # 1. Authoritative: Polymarket settlement.
        try:
            payload = self._client.get_settlement(market_slug)
        except Exception:
            stats.not_settled += 1
            return
        settlement = payload.get("settlement")
        if settlement is None:
            stats.not_settled += 1
            return
        settlement = int(settlement)

        # 2. Cross-check: ESPN final score.
        match = find_espn_game(session=session, market_slug=market_slug)
        actual_total = home_pts = away_pts = None
        if match is None:
            stats.no_espn_match += 1
        else:
            home, away = match
            home_pts = home.points_scored
            away_pts = away.points_scored
            if home_pts is not None and away_pts is not None:
                actual_total = int(home_pts) + int(away_pts)

            expected = implied_settlement(
                market_slug=market_slug, home=home, away=away,
                line=float(line) if line is not None else None,
            )
            if expected is not None and expected != settlement:
                # Never silently pick a side.
                stats.disagreements += 1
                log.warning(
                    "settlement_disagreement",
                    market=market_slug,
                    polymarket_settlement=settlement,
                    espn_implies=expected,
                    final_score=f"{away.team_abbrev} {away_pts} @ {home.team_abbrev} {home_pts}",
                    line=float(line) if line is not None else None,
                    hint="data bug or market-resolution edge case; investigate",
                )

        event_slug = session.scalar(
            select(MarketSnapshot.event_slug)
            .where(MarketSnapshot.market_slug == market_slug)
            .limit(1)
        )

        stmt = (
            pg_insert(ResolvedOutcome)
            .values(
                market_slug=market_slug,
                event_slug=event_slug,
                settlement=settlement,
                resolved_at=dt.datetime.now(UTC),
                final_score_home=int(home_pts) if home_pts is not None else None,
                final_score_away=int(away_pts) if away_pts is not None else None,
                actual_total=actual_total,
            )
            # Never overwrite a resolved outcome once written.
            .on_conflict_do_nothing(index_elements=["market_slug"])
            .returning(ResolvedOutcome.id)
        )
        if session.execute(stmt).scalar() is not None:
            stats.outcomes_written += 1

    @staticmethod
    def _backfill_predictions(session: Session) -> int:
        """Attach outcomes to predictions. Idempotent; never rewrites."""
        result = session.execute(
            update(Prediction)
            .where(Prediction.resolved_outcome.is_(None))
            .where(Prediction.market_slug == ResolvedOutcome.market_slug)
            .values(
                resolved_outcome=ResolvedOutcome.settlement,
                resolved_at=ResolvedOutcome.resolved_at,
                # "Correct" = the model leaned the same way the market settled.
                was_correct=(
                    (Prediction.model_probability > 0.5)
                    == (ResolvedOutcome.settlement == 1)
                ),
            )
        )
        return result.rowcount or 0


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
    parser = argparse.ArgumentParser(prog="meridian-resolution")
    parser.add_argument("--backfill", action="store_true", help="resolve pending predictions")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    _configure_logging()
    if not args.backfill:
        parser.error("--backfill is required")
    ResolutionJob().run(limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
