"""One-shot historical backfill: game logs, sportsbook odds, Polymarket settlements.

Why this unit matters
---------------------
The project originally assumed the recorder running forward was the only data
source, implying months before any meaningful backtest. That is half true:
Polymarket US launched ~2026-03, so no multi-year *venue* history can exist —
but ESPN carries ~6 seasons of free sportsbook lines. That splits one question
into two:

* *Does the fair-value model beat a closing line?*  -> answerable **now**
* *Does an edge exist on this venue?*               -> needs the recorder

This unit unlocks the first.

Resumability
------------
Every write is an idempotent upsert (``ON CONFLICT DO NOTHING``), so "resume"
is simply "skip what is already present". That is more robust than a progress
cursor, which can itself go stale or lie after a partial write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from dataclasses import dataclass

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.feeds.espn_odds import ESPNOddsFetcher
from core.feeds.espn_stats import ESPNStatsFetcher
from core.polymarket.client import PolymarketGatewayClient
from core.storage import (
    ResolvedOutcome,
    SportsbookOdds,
    TeamGameLog,
    get_engine,
    get_sessionmaker,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Polymarket tag id for the WNBA.
WNBA_TAG_ID = 94

#: Plausible bounds for a real WNBA regular-season game total. All-Star games
#: run ~250 and would wreck a model fit. In practice they never reach the
#: database — we fetch schedules per franchise, and "Team Wilson" is not a
#: franchise — but the check is cheap insurance against another exhibition
#: format appearing later.
MIN_PLAUSIBLE_GAME_TOTAL = 100
MAX_PLAUSIBLE_GAME_TOTAL = 260


@dataclass
class SeasonCoverage:
    season: int
    regular: int = 0
    postseason: int = 0
    with_odds: int = 0
    with_closing_line: int = 0
    median_providers: float = 0.0
    suspicious_totals: int = 0


class Backfill:
    def __init__(self, sessionmaker=None) -> None:
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self._stats = ESPNStatsFetcher(sessionmaker=self._Session)
        self._odds = ESPNOddsFetcher(sessionmaker=self._Session)

    # ---------------------------------------------------------------- #
    # 1. Team game logs
    # ---------------------------------------------------------------- #

    def backfill_game_logs(self, start: int, end: int, dry_run: bool = False) -> None:
        if dry_run:
            log.info("dry_run_game_logs", seasons=f"{start}-{end}", teams_per_season=15)
            return
        self._stats.fetch_backfill(start, end)

    # ---------------------------------------------------------------- #
    # 2. Sportsbook odds (skips games already covered -> resumable)
    # ---------------------------------------------------------------- #

    def backfill_odds(self, start: int, end: int, dry_run: bool = False) -> None:
        for season in range(start, end + 1):
            with self._Session() as session:
                todo = session.execute(
                    select(TeamGameLog.espn_game_id, TeamGameLog.game_date)
                    .where(TeamGameLog.season == season)
                    .where(
                        TeamGameLog.espn_game_id.notin_(
                            select(SportsbookOdds.espn_game_id).distinct()
                        )
                    )
                    .distinct()
                ).all()

            if dry_run:
                log.info("dry_run_odds", season=season, games_to_fetch=len(todo))
                continue
            if not todo:
                log.info("odds_already_complete", season=season)
                continue

            log.info("odds_season_start", season=season, games_to_fetch=len(todo))
            captured_at = dt.datetime.now(UTC)
            for i, (game_id, game_date) in enumerate(todo, 1):
                self._odds.fetch_historical_game(
                    game_id, game_date=game_date, game_is_final=True, captured_at=captured_at
                )
                if i % 50 == 0:
                    log.info("odds_progress", season=season, done=i, total=len(todo))

    # ---------------------------------------------------------------- #
    # 3. Polymarket settlements
    # ---------------------------------------------------------------- #

    def backfill_settlements(self, dry_run: bool = False, page_size: int = 100) -> int:
        """Fetch resolution labels for closed WNBA markets.

        Free and unauthenticated. Only 2026 exists — the venue launched
        ~2026-03.
        """
        written = 0
        with PolymarketGatewayClient() as client, self._Session() as session:
            existing = set(session.scalars(select(ResolvedOutcome.market_slug)).all())

            offset = 0
            while True:
                try:
                    page = client._get(
                        "/v1/markets",
                        params={
                            "tagIds": WNBA_TAG_ID,
                            "closed": "true",
                            "limit": page_size,
                            "offset": offset,
                        },
                    )
                except Exception as exc:
                    log.error("settlement_page_failed", offset=offset, error=str(exc))
                    break

                markets = page.get("markets") or []
                if not markets:
                    break

                for market in markets:
                    slug = market.get("slug")
                    if not slug or slug in existing:
                        continue
                    if dry_run:
                        written += 1
                        continue
                    try:
                        payload = client.get_settlement(slug)
                    except Exception as exc:
                        # A market may be closed but not yet settled.
                        log.warning("settlement_failed", slug=slug, error=str(exc))
                        continue

                    settlement = payload.get("settlement")
                    if settlement is None:
                        continue

                    stmt = (
                        pg_insert(ResolvedOutcome)
                        .values(
                            market_slug=slug,
                            event_slug=market.get("eventSlug"),
                            game_id=str(market["gameId"]) if market.get("gameId") else None,
                            settlement=int(settlement),
                            resolved_at=dt.datetime.now(UTC),
                        )
                        .on_conflict_do_nothing(index_elements=["market_slug"])
                        .returning(ResolvedOutcome.id)
                    )
                    if session.execute(stmt).scalar() is not None:
                        written += 1

                session.commit()
                offset += page_size
                log.info("settlement_progress", offset=offset, written=written)

        log.info("settlements_complete", written=written, dry_run=dry_run)
        return written

    # ---------------------------------------------------------------- #
    # Coverage report
    # ---------------------------------------------------------------- #

    def coverage(self, start: int, end: int) -> list[SeasonCoverage]:
        out: list[SeasonCoverage] = []
        with self._Session() as session:
            for season in range(start, end + 1):
                cov = SeasonCoverage(season=season)

                rows = session.execute(
                    select(
                        TeamGameLog.espn_game_id,
                        TeamGameLog.season_type,
                        func.max(TeamGameLog.points_scored + TeamGameLog.points_allowed),
                    )
                    .where(TeamGameLog.season == season)
                    .group_by(TeamGameLog.espn_game_id, TeamGameLog.season_type)
                ).all()

                game_ids = set()
                for game_id, season_type, total in rows:
                    game_ids.add(game_id)
                    if season_type == 2:
                        cov.regular += 1
                    elif season_type == 3:
                        cov.postseason += 1
                    if total is not None and not (
                        MIN_PLAUSIBLE_GAME_TOTAL <= total <= MAX_PLAUSIBLE_GAME_TOTAL
                    ):
                        cov.suspicious_totals += 1

                if game_ids:
                    cov.with_odds = session.scalar(
                        select(func.count(func.distinct(SportsbookOdds.espn_game_id))).where(
                            SportsbookOdds.espn_game_id.in_(game_ids)
                        )
                    ) or 0
                    cov.with_closing_line = session.scalar(
                        select(func.count(func.distinct(SportsbookOdds.espn_game_id)))
                        .where(SportsbookOdds.espn_game_id.in_(game_ids))
                        .where(SportsbookOdds.is_closing_line.is_(True))
                    ) or 0
                    per_game = session.execute(
                        select(func.count(SportsbookOdds.id))
                        .where(SportsbookOdds.espn_game_id.in_(game_ids))
                        .group_by(SportsbookOdds.espn_game_id)
                    ).scalars().all()
                    if per_game:
                        srt = sorted(per_game)
                        cov.median_providers = float(srt[len(srt) // 2])

                out.append(cov)
        return out

    def print_coverage(self, start: int, end: int) -> None:
        rows = self.coverage(start, end)

        print()
        print("COVERAGE REPORT")
        print("=" * 88)
        print(
            f"{'Season':<8}{'Reg':>6}{'Post':>6}{'Games':>7}"
            f"{'WithOdds':>10}{'TrueClose':>11}{'Providers':>11}{'Suspect':>9}"
        )
        print("-" * 88)

        t_reg = t_post = t_odds = t_close = 0
        for c in rows:
            games = c.regular + c.postseason
            t_reg += c.regular
            t_post += c.postseason
            t_odds += c.with_odds
            t_close += c.with_closing_line
            print(
                f"{c.season:<8}{c.regular:>6}{c.postseason:>6}{games:>7}"
                f"{c.with_odds:>10}{c.with_closing_line:>11}"
                f"{c.median_providers:>11.0f}{c.suspicious_totals:>9}"
            )

        total_games = t_reg + t_post
        pct = (t_close / total_games * 100) if total_games else 0.0
        print("-" * 88)
        print(
            f"{'TOTAL':<8}{t_reg:>6}{t_post:>6}{total_games:>7}{t_odds:>10}{t_close:>11}"
        )
        print()
        print(f"  {t_reg} regular + {t_post} postseason games")
        print(f"  {pct:.1f}% have a TRUE closing line and are usable for CLV")
        print()

        # State the limits plainly rather than letting the reader assume.
        no_clv = [str(c.season) for c in rows if c.regular and c.with_closing_line == 0]
        if no_clv:
            print(f"  ⚠️  No closing lines at all in: {', '.join(no_clv)}")
            print("      Those seasons carry multi-book consensus only. CLV cannot be")
            print("      computed there and the backtest must exclude them from CLV.")
        thin = [c for c in rows if 0 < c.postseason <= 24]
        if thin:
            print(
                f"  ⚠️  Postseason cohorts are tiny ({min(c.postseason for c in thin)}"
                f"-{max(c.postseason for c in thin)} games/season)."
            )
            print("      No playoff-specific conclusion is statistically supportable.")
        print()

    # ---------------------------------------------------------------- #

    def run_all(self, start: int, end: int, dry_run: bool = False) -> None:
        log.info("backfill_start", seasons=f"{start}-{end}", dry_run=dry_run)
        self.backfill_game_logs(start, end, dry_run)
        self.backfill_odds(start, end, dry_run)
        self.backfill_settlements(dry_run)
        self.print_coverage(start, end)


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
    parser = argparse.ArgumentParser(prog="meridian-backfill")
    parser.add_argument("--start", type=int, default=2020)
    parser.add_argument("--end", type=int, default=2026)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--coverage-only", action="store_true", help="just print coverage")
    parser.add_argument("--settlements-only", action="store_true")
    args = parser.parse_args()

    _configure_logging()
    bf = Backfill()

    if args.coverage_only:
        bf.print_coverage(args.start, args.end)
    elif args.settlements_only:
        bf.backfill_settlements(args.dry_run)
    else:
        bf.run_all(args.start, args.end, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
