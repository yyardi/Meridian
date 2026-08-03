"""Refresh slow-moving fitted constants.

Right now there is exactly one: the winner's-curse slope, the fraction of a
model-vs-market disagreement that is real information rather than the model's
own error. Measured at ~0.16-0.23 on WNBA totals, which is to say a raw gap is
mostly noise.

It lives on the daily job rather than the 20-minute one because computing it
re-derives point-in-time features for every completed game — seconds against
local Postgres, minutes against Supabase. The prediction path reads the cached
row and only recomputes if none is fresh.

    python -m core.calibration
"""

from __future__ import annotations

import datetime as dt
import logging
import sys

import structlog

from core.storage import get_engine, get_sessionmaker
from strategies.wnba_totals.model.fair_value import estimate_market_slope, store_slope

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc


def refresh_market_slope(as_of: dt.datetime | None = None) -> float:
    """Recompute and store the totals market slope."""
    as_of = as_of or dt.datetime.now(UTC)
    Session = get_sessionmaker(get_engine())
    with Session() as session:
        slope = estimate_market_slope(as_of=as_of, session=session)
        store_slope(session=session, as_of=as_of, slope=slope)
    log.info("market_slope_refreshed", as_of=as_of.isoformat(), slope=round(slope, 4))
    return slope


def main() -> int:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
    refresh_market_slope()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
