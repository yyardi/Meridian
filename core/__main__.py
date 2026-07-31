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


def _status(gap_minutes: int = 90) -> int:
    """Freshness and gap report.

    On a laptop this is the important command. Snapshots cannot be backfilled,
    so the thing you need to know is not "is it running now" but "when did it
    stop, and for how long". Exit code is non-zero when stale, so this can be
    wired into a cron/alert.
    """
    import datetime as dt

    Session = get_sessionmaker(get_engine())
    with Session() as s:
        count, newest, oldest = s.execute(
            select(
                func.count(MarketSnapshot.id),
                func.max(MarketSnapshot.captured_at),
                func.min(MarketSnapshot.captured_at),
            )
        ).one()
        cycles = s.scalar(
            select(func.count(func.distinct(MarketSnapshot.captured_at)))
        )
        instants = s.scalars(
            select(func.distinct(MarketSnapshot.captured_at)).order_by(
                MarketSnapshot.captured_at
            )
        ).all()

    print(f"snapshots   : {count} across {cycles} cycles")
    print(f"first       : {oldest}")
    print(f"most recent : {newest}")

    if newest is None:
        print("STALE: no snapshots at all")
        return 1

    age_min = (dt.datetime.now(dt.timezone.utc) - newest).total_seconds() / 60
    print(f"age         : {age_min:.1f} min")

    # Gaps larger than expected mean lost, unrecoverable data.
    gaps = []
    for prev, nxt in zip(instants, instants[1:]):
        delta_min = (nxt - prev).total_seconds() / 60
        if delta_min > gap_minutes:
            gaps.append((prev, nxt, delta_min))

    if gaps:
        print(f"\n⚠️  {len(gaps)} gap(s) over {gap_minutes} min — data lost, not recoverable:")
        for prev, nxt, delta in gaps[-5:]:
            print(f"      {prev:%Y-%m-%d %H:%M} -> {nxt:%Y-%m-%d %H:%M}  ({delta/60:.1f}h)")
    else:
        print("gaps        : none")

    if age_min > gap_minutes:
        print(f"\nSTALE: no snapshot in {age_min:.0f} min. Is the recorder running?")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-recorder")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--status", action="store_true", help="print recorder freshness + gaps")
    parser.add_argument("--gap-minutes", type=int, default=90, help="gap threshold for --status")
    parser.add_argument("--json-logs", action="store_true", help="emit JSON logs")
    args = parser.parse_args()

    configure_logging(json_logs=args.json_logs)

    if args.status:
        return _status(args.gap_minutes)

    recorder = Recorder()
    if args.once:
        stats = recorder.run_once()
        return 0 if stats.snapshots_written or not stats.market_errors else 1
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
