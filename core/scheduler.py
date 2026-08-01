"""Daily job scheduler: stats, odds, predictions, resolution.

Runs alongside the recorder. The recorder has its own tight loop because
snapshots are unrecoverable; these jobs are all backfillable, so they run once
a day and simply retry tomorrow if they fail.

Never crashes the loop — same reasoning as the recorder. A scheduler that dies
unattended silently stops the prediction log from compounding.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time

import structlog

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc


def _safe(name: str, fn, **kwargs) -> None:
    try:
        fn(**kwargs)
        log.info("job_ok", job=name)
    except Exception as exc:
        log.error("job_failed", job=name, error=str(exc), exc_info=True)


def run_daily_jobs(season: int | None = None) -> None:
    """One pass of every daily job, in dependency order."""
    from core.feeds.espn_odds import ESPNOddsFetcher
    from core.feeds.espn_stats import ESPNStatsFetcher
    from core.predictions import PredictionLogger
    from core.resolution import ResolutionJob

    today = dt.datetime.now(UTC)
    season = season or today.year

    # 1. Yesterday's results first, so features are current before predicting.
    yesterday = (today - dt.timedelta(days=1)).strftime("%Y%m%d")
    _safe("stats", ESPNStatsFetcher().fetch_date, date_yyyymmdd=yesterday, season=season)
    _safe("stats_today", ESPNStatsFetcher().fetch_date,
          date_yyyymmdd=today.strftime("%Y%m%d"), season=season)

    # 1b. Box-score stats for yesterday's games (pace features need them).
    from core.feeds.espn_boxscores import backfill as boxscore_backfill
    _safe("boxscores", boxscore_backfill, start_season=season, end_season=season)

    # 2. Live sportsbook odds for the cross-market signal.
    _safe("odds", ESPNOddsFetcher().fetch_live)

    # 3. Predict against the newest snapshot.
    _safe("predictions", PredictionLogger().run)

    # 4. Resolve anything that has settled.
    _safe("resolution", ResolutionJob().run)


def run_forever(interval_hours: float = 6.0, odds_minutes: float = 20.0) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.format_exc_info,
                    structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    log.info("scheduler_started", interval_hours=interval_hours, odds_minutes=odds_minutes)
    last_full = 0.0
    while True:
        now = time.time()
        if now - last_full >= interval_hours * 3600:
            try:
                run_daily_jobs()
            except Exception as exc:
                log.error("cycle_failed", error=str(exc), exc_info=True)
            last_full = now
        else:
            # Fast leg: sportsbook lines only. The venue-gap signal is a
            # WINDOW — the book moves on news and the thin venue lags. A 6h
            # book cadence cannot see windows; 20 min can. The Polymarket leg
            # is already sampled every 15 min by the recorder.
            from core.feeds.espn_odds import ESPNOddsFetcher
            _safe("odds_fast", ESPNOddsFetcher().fetch_live)
        time.sleep(odds_minutes * 60)


def main() -> int:
    p = argparse.ArgumentParser(prog="meridian-scheduler")
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval-hours", type=float, default=6.0)
    args = p.parse_args()
    if args.once:
        logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
        structlog.configure(
            processors=[structlog.processors.add_log_level,
                        structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        )
        run_daily_jobs()
    else:
        run_forever(args.interval_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
