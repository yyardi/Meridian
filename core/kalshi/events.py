"""Entrypoint for the Kalshi non-sports recorder.

    python -m core.kalshi.events --once     # one sweep of the allowlist
    python -m core.kalshi.events            # run forever

The allowlist is `KALSHI_SERIES` (comma-separated); unset means the eight
pre-registered targets in `core.kalshi.events_shape.DEFAULT_SERIES`. It is
printed on every start, because "recorded nothing" and "was pointed at
nothing" have to be distinguishable from the log alone.
"""

from __future__ import annotations

import argparse

from core.__main__ import configure_logging
from core.kalshi.events_recorder import KalshiEventsRecorder


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-kalshi-events-recorder")
    parser.add_argument("--once", action="store_true", help="run a single sweep and exit")
    parser.add_argument("--json-logs", action="store_true", help="emit JSON logs")
    args = parser.parse_args()
    configure_logging(json_logs=args.json_logs)

    recorder = KalshiEventsRecorder()
    if args.once:
        return 0 if not recorder.run_once().errors else 1
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
