"""Pregame trade-tape sweeper — records the VOLUME TRAJECTORY of a board.

Why this exists
---------------
The venue's trade tape (`marketData.stats`) rides free in every book response,
and the live recorder now persists it — but the live recorder only polls books
during games. That leaves the pregame board unrecorded, and the pregame board
is where the program's central question lives:

**A market showing zero volume seven days out is indistinguishable from a dead
market UNLESS you watch it fill.** "Never trades" and "fills up in the last
hours" have opposite implications for whether a maker can ever be filled
there, and the only thing that separates them is the T-7 → T-0 trajectory.
That curve exists only if it is sampled AS IT GROWS; no later query recovers
it, because the venue exposes a cumulative counter and no history (V31).

Measured motivation (2026-09-02, one NFL game at T-7): the moneyline had
traded $919k while **14 of 18 market types had never traded at all**, quoting
19–32¢ wide. If those wide books stay empty through kickoff, there is no cell
for a maker to stand in — liquidity where it is too tight to earn, width where
nothing trades. That is a finding worth having before size is committed, and
this sweeper is what makes it observable.

Deliberately cheap and boring
-----------------------------
Stats only: no depth rows, no snapshots, one book call per market on a slow
cadence (default hourly). It writes `market_trade_stats` rows keyed by
`market_slug` with a NULL `snapshot_id` — standalone by design, so it shares
the consumers' table without depending on the recorders' write path.

Read-only against the public gateway. No credentials, no order path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import time

import structlog

from core.config import RECORDER
from core.polymarket import PolymarketGatewayClient
from core.storage import MarketTradeStat, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc

#: Hourly by default. The counters are CUMULATIVE, so cadence only bounds the
#: resolution of the growth curve — an hour is ample to tell a market that
#: fills late from one that never fills, and it keeps the request budget
#: negligible beside the recorders that share this IP.
DEFAULT_INTERVAL_SECONDS = 3600.0


def sweep_once(client, Session, *, league: str) -> tuple[int, int]:
    """One pass over the league board. Returns (markets_polled, rows_written)."""
    parsed, _raw = client.get_league_events(league=league)
    slugs = [m.slug for e in parsed.events for m in e.markets if m.slug]
    rows: list[dict] = []
    polled = 0
    for slug in slugs:
        try:
            book, _ = client.get_book(slug)
        except Exception as exc:                       # one bad market must
            log.warning("stats_book_failed",          # not end the sweep
                        market_slug=slug, error=str(exc)[:200])
            continue
        polled += 1
        data = book.market_data
        st = None if data is None else data.stats
        if st is None:
            continue
        v = lambda q: q.value if q is not None else None      # noqa: E731
        rows.append({
            "snapshot_id": None,
            "market_slug": slug,
            "captured_at": dt.datetime.now(UTC),
            "last_trade_px": v(st.last_trade_px),
            "last_trade_qty": st.last_trade_qty,
            "last_trade_at": st.last_trade_at,
            "shares_traded": st.shares_traded,
            "notional_traded": v(st.notional_traded),
            "open_interest": st.open_interest,
            "high_px": v(st.high_px),
            "low_px": v(st.low_px),
        })

    if rows:
        with Session() as session:
            session.execute(MarketTradeStat.__table__.insert(), rows)
            session.commit()
    return polled, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS,
                    help="seconds between sweeps (default 3600)")
    ap.add_argument("--once", action="store_true", help="one sweep, then exit")
    args = ap.parse_args()

    league = RECORDER.league_slug
    client = PolymarketGatewayClient(RECORDER)
    Session = get_sessionmaker(get_engine())
    log.info("stats_sweeper_started", league=league, interval_s=args.interval)

    while True:
        started = time.monotonic()
        try:
            polled, written = sweep_once(client, Session, league=league)
            log.info("stats_sweep", league=league, markets=polled,
                     rows=written, duration_s=round(time.monotonic() - started, 1))
        except Exception as exc:                       # a sweep must never
            log.error("stats_sweep_failed",           # kill the process
                      league=league, error=str(exc)[:300])
        if args.once:
            return 0
        time.sleep(max(1.0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
