"""Kalshi recorder entrypoint.

    python -m core.kalshi --once      # single cycle, useful for testing
    python -m core.kalshi             # run forever on the adaptive cadence
    python -m core.kalshi --gate      # where the sample stands vs the gate
    python -m core.kalshi --report    # the two pre-registered statistics
"""

from __future__ import annotations

import argparse

from core.__main__ import configure_logging
from core.kalshi.recorder import KalshiRecorder


def _gate() -> int:
    from core.kalshi.analysis import gate_status
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        status = gate_status(session)
    for key, value in status.items():
        print(f"{key:14}: {value}")
    return 0


def _report() -> int:
    """The founding-thesis numbers. Reads whichever DATABASE_URL points at —
    the full sample lives on the primary (see the analysis module docstring:
    the local mirror is a smaller, not wrong, sample)."""
    import json

    from core.kalshi.analysis import report
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    with Session() as session:
        print(json.dumps(report(session), indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-kalshi-recorder")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--gate", action="store_true", help="matched games vs the 10-game gate")
    parser.add_argument("--report", action="store_true",
                        help="the two pre-registered venue-gap statistics")
    parser.add_argument("--json-logs", action="store_true", help="emit JSON logs")
    args = parser.parse_args()

    configure_logging(json_logs=args.json_logs)

    if args.gate:
        return _gate()
    if args.report:
        return _report()

    recorder = KalshiRecorder()
    if args.once:
        stats = recorder.run_once()
        return 0 if not stats.errors else 1
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
