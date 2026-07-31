"""Recorder entrypoint.

    python -m core --once      # single cycle, useful for testing
    python -m core             # run forever on the adaptive cadence
    python -m core --status    # freshness check: is the recorder alive?
"""

from __future__ import annotations

import argparse
import logging
import sys

import structlog
from sqlalchemy import func, select

from core.recorder import Recorder
from core.storage import MarketSnapshot, get_engine, get_sessionmaker


def configure_logging(json_logs: bool = False) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    # httpx logs every request at INFO; at ~150 requests/cycle that buries the
    # cycle summary and the errors that actually matter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
            if json_logs
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def _status() -> int:
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        count, newest = s.execute(
            select(func.count(MarketSnapshot.id), func.max(MarketSnapshot.captured_at))
        ).one()
    print(f"snapshots: {count}")
    print(f"most recent: {newest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-recorder")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--status", action="store_true", help="print recorder freshness")
    parser.add_argument("--json-logs", action="store_true", help="emit JSON logs")
    args = parser.parse_args()

    configure_logging(json_logs=args.json_logs)

    if args.status:
        return _status()

    recorder = Recorder()
    if args.once:
        stats = recorder.run_once()
        return 0 if stats.snapshots_written or not stats.market_errors else 1
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
