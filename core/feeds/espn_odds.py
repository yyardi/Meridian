"""ESPN sportsbook odds feed — live and historical.

Serves two purposes:

1. **Cross-market gap signal.** Sportsbooks carry far more WNBA volume than
   Polymarket US, so where the two disagree the book is more likely right.
2. **CLV benchmark.** Closing lines are what the backtest measures predictions
   against.

Two endpoints, and the difference is easy to get wrong:

* ``site.api.espn.com/.../scoreboard`` carries odds for *upcoming* games only —
  odds are stripped from past games.
* ``sports.core.api.espn.com/.../odds`` retains odds for past games, including
  open/close.

.. warning::
   The **live** scoreboard nests its current prices under keys literally named
   ``close`` (e.g. ``total.over.close.line``) even for games that have not been
   played. Trusting that name would mark upcoming games as closing lines and
   corrupt the CLV benchmark — the backtest's primary metric. Live mode
   therefore *never* sets ``is_closing_line``; only the historical path does,
   and only from a genuine ``close`` object on the core API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.feeds.espn_client import ESPNClient, ESPNNotFound
from core.feeds.espn_schemas import ScoreboardResponse
from core.feeds.odds_math import consensus, parse_american, parse_line, plausible_total
from core.storage import SportsbookOdds, TeamGameLog, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc


def _nested(payload: Any, *keys: str) -> Any:
    """Walk a nested dict, returning None on any missing/non-dict level."""
    cur = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


class OddsStats:
    def __init__(self) -> None:
        self.games_seen = 0
        self.rows_written = 0
        self.games_without_odds = 0
        self.with_closing_line = 0
        self.errors = 0


class ESPNOddsFetcher:
    def __init__(self, client: ESPNClient | None = None, sessionmaker=None) -> None:
        self._client = client or ESPNClient()
        self._Session = sessionmaker or get_sessionmaker(get_engine())

    # ---------------------------------------------------------------- #
    # Parsing
    # ---------------------------------------------------------------- #

    @staticmethod
    def parse_historical_item(
        item: dict[str, Any],
        espn_game_id: str,
        captured_at: dt.datetime,
        game_date: dt.datetime | None,
        game_is_final: bool,
    ) -> dict[str, Any]:
        """One provider's odds from the core API.

        `open`/`close` exist for 2024+ only; earlier seasons carry top-level
        consensus across many books but no open/close split.
        """
        provider = _nested(item, "provider", "name") or "unknown"

        # `overUnder` is reliably the line; use it as the reference against
        # which candidate open/close totals are sanity-checked.
        over_under = parse_line(item.get("overUnder"))

        # ESPN overloads close.total.american: the *line* for 2024+, the *odds*
        # for earlier seasons. plausible_total() rejects the latter — without
        # it, juice like -115 lands in close_total and the row gets flagged as
        # a closing line, corrupting CLV.
        open_total = plausible_total(
            parse_line(_nested(item, "open", "total", "american")), over_under
        )
        close_total = plausible_total(
            parse_line(_nested(item, "close", "total", "american")), over_under
        )

        # A closing line is only real if the game is over AND ESPN gave a
        # genuine, plausible close total. Never inferred.
        is_closing = bool(close_total is not None and game_is_final)

        home_ml = _nested(item, "homeTeamOdds", "moneyLine")
        away_ml = _nested(item, "awayTeamOdds", "moneyLine")
        if home_ml is None:
            home_ml = _nested(item, "homeTeamOdds", "close", "moneyLine", "american")
        if away_ml is None:
            away_ml = _nested(item, "awayTeamOdds", "close", "moneyLine", "american")

        return {
            "espn_game_id": espn_game_id,
            "game_date": game_date,
            "provider_name": provider,
            "captured_at": captured_at,
            "spread": parse_line(item.get("spread")),
            "over_under": over_under,
            "over_odds": parse_american(item.get("overOdds")),
            "under_odds": parse_american(item.get("underOdds")),
            "home_moneyline": parse_american(home_ml),
            "away_moneyline": parse_american(away_ml),
            "open_total": open_total,
            "close_total": close_total,
            "is_closing_line": is_closing,
            "raw": item,
        }

    @staticmethod
    def parse_live_odds(
        odds_entry: dict[str, Any],
        espn_game_id: str,
        captured_at: dt.datetime,
        game_date: dt.datetime | None,
    ) -> dict[str, Any]:
        """One provider's odds from the live scoreboard.

        `is_closing_line` is always False here — see the module warning.
        """
        provider = _nested(odds_entry, "provider", "name") or "unknown"

        home_ml = _nested(odds_entry, "moneyline", "home", "close", "odds")
        away_ml = _nested(odds_entry, "moneyline", "away", "close", "odds")
        if home_ml is None:
            home_ml = _nested(odds_entry, "homeTeamOdds", "moneyLine")
        if away_ml is None:
            away_ml = _nested(odds_entry, "awayTeamOdds", "moneyLine")

        over_odds = _nested(odds_entry, "total", "over", "close", "odds")
        under_odds = _nested(odds_entry, "total", "under", "close", "odds")

        over_under = odds_entry.get("overUnder")
        if over_under is None:
            over_under = _nested(odds_entry, "total", "over", "close", "line")

        return {
            "espn_game_id": espn_game_id,
            "game_date": game_date,
            "provider_name": provider,
            "captured_at": captured_at,
            "spread": parse_line(odds_entry.get("spread")),
            "over_under": parse_line(over_under),
            "over_odds": parse_american(over_odds),
            "under_odds": parse_american(under_odds),
            "home_moneyline": parse_american(home_ml),
            "away_moneyline": parse_american(away_ml),
            "open_total": None,
            "close_total": None,
            "is_closing_line": False,  # never, for an unplayed game
            "raw": odds_entry,
        }

    # ---------------------------------------------------------------- #
    # Persistence
    # ---------------------------------------------------------------- #

    def _persist(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        written = 0
        with self._Session() as session:
            for row in rows:
                stmt = (
                    pg_insert(SportsbookOdds)
                    .values(**row)
                    .on_conflict_do_nothing(constraint="uq_odds_game_provider_time")
                    .returning(SportsbookOdds.id)
                )
                if session.execute(stmt).scalar() is not None:
                    written += 1
            session.commit()
        return written

    # ---------------------------------------------------------------- #
    # Modes
    # ---------------------------------------------------------------- #

    def fetch_live(self, date_yyyymmdd: str | None = None) -> OddsStats:
        stats = OddsStats()
        captured_at = dt.datetime.now(UTC)
        date_str = date_yyyymmdd or captured_at.strftime("%Y%m%d")

        try:
            payload = self._client.get_scoreboard(date_str)
            board = ScoreboardResponse.model_validate(payload)
        except Exception as exc:
            log.error("scoreboard_failed", date=date_str, error=str(exc))
            stats.errors += 1
            return stats

        raw_events = {str(e.get("id")): e for e in payload.get("events", [])}

        rows: list[dict] = []
        for event in board.events:
            stats.games_seen += 1
            raw_comp = _nested(raw_events.get(event.id, {}), "competitions") or []
            odds_list = (raw_comp[0].get("odds") if raw_comp else None) or []
            if not odds_list:
                stats.games_without_odds += 1
                continue
            for entry in odds_list:
                try:
                    rows.append(
                        self.parse_live_odds(entry, event.id, captured_at, event.date)
                    )
                except Exception as exc:
                    stats.errors += 1
                    log.warning("live_odds_parse_failed", game=event.id, error=str(exc))

        stats.rows_written = self._persist(rows)
        log.info(
            "live_odds_complete",
            date=date_str,
            games=stats.games_seen,
            rows=stats.rows_written,
            without_odds=stats.games_without_odds,
        )
        return stats

    def fetch_historical_game(
        self,
        espn_game_id: str,
        game_date: dt.datetime | None = None,
        game_is_final: bool = True,
        captured_at: dt.datetime | None = None,
        stats: OddsStats | None = None,
    ) -> int:
        stats = stats or OddsStats()
        captured_at = captured_at or dt.datetime.now(UTC)
        try:
            payload = self._client.get_event_odds(espn_game_id)
        except ESPNNotFound:
            stats.games_without_odds += 1
            return 0
        except Exception as exc:
            stats.errors += 1
            log.warning("historical_odds_failed", game=espn_game_id, error=str(exc))
            return 0

        items = payload.get("items") or []
        if not items:
            stats.games_without_odds += 1
            return 0

        rows = []
        for item in items:
            try:
                row = self.parse_historical_item(
                    item, espn_game_id, captured_at, game_date, game_is_final
                )
                if row["is_closing_line"]:
                    stats.with_closing_line += 1
                rows.append(row)
            except Exception as exc:
                stats.errors += 1
                log.warning("historical_parse_failed", game=espn_game_id, error=str(exc))

        written = self._persist(rows)
        stats.rows_written += written
        return written

    def fetch_historical_season(self, season: int) -> OddsStats:
        """Fetch odds for every completed game we already have a log for."""
        stats = OddsStats()
        with self._Session() as session:
            games = session.execute(
                select(
                    TeamGameLog.espn_game_id,
                    TeamGameLog.game_date,
                ).where(TeamGameLog.season == season).distinct()
            ).all()

        captured_at = dt.datetime.now(UTC)
        for game_id, game_date in games:
            stats.games_seen += 1
            self.fetch_historical_game(
                game_id,
                game_date=game_date,
                game_is_final=True,
                captured_at=captured_at,
                stats=stats,
            )
            if stats.games_seen % 50 == 0:
                log.info(
                    "historical_progress",
                    season=season,
                    games=stats.games_seen,
                    total=len(games),
                    rows=stats.rows_written,
                )

        log.info(
            "historical_season_complete",
            season=season,
            games=stats.games_seen,
            rows=stats.rows_written,
            with_closing_line=stats.with_closing_line,
            without_odds=stats.games_without_odds,
            errors=stats.errors,
        )
        return stats

    # ---------------------------------------------------------------- #
    # Consensus
    # ---------------------------------------------------------------- #

    def consensus_for_game(self, espn_game_id: str) -> dict[str, Decimal | None]:
        """Median line across all providers for one game."""
        with self._Session() as session:
            rows = session.scalars(
                select(SportsbookOdds).where(SportsbookOdds.espn_game_id == espn_game_id)
            ).all()
        return {
            "providers": Decimal(len(rows)),
            "over_under": consensus([r.over_under for r in rows]),
            "spread": consensus([r.spread for r in rows]),
            "home_moneyline": consensus([r.home_moneyline for r in rows]),
            "away_moneyline": consensus([r.away_moneyline for r in rows]),
        }


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
    parser = argparse.ArgumentParser(prog="espn-odds")
    parser.add_argument("--live", action="store_true", help="poll today's scoreboard")
    parser.add_argument("--date", type=str, help="YYYYMMDD for --live")
    parser.add_argument("--historical", action="store_true", help="backfill historical odds")
    parser.add_argument("--season", type=int, help="season for --historical")
    parser.add_argument("--game", type=str, help="single ESPN game id for --historical")
    args = parser.parse_args()

    _configure_logging()
    fetcher = ESPNOddsFetcher()

    if args.live:
        fetcher.fetch_live(args.date)
    elif args.historical:
        if args.game:
            n = fetcher.fetch_historical_game(args.game)
            print(f"wrote {n} provider rows for game {args.game}")
        elif args.season:
            fetcher.fetch_historical_season(args.season)
        else:
            parser.error("--historical requires --season or --game")
    else:
        parser.error("one of --live or --historical is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
