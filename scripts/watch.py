#!/usr/bin/env python
"""Live tail of the recorders. Ctrl-C to stop.

    .venv/bin/python scripts/watch.py          # 200ms tick recorder (local)
    .venv/bin/python scripts/watch.py --slow   # 15-min pregame recorder (Supabase)

Prints a new block every two seconds. During a game the tick view should be
moving constantly; if the timestamp stops advancing, recording has stopped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

from sqlalchemy import create_engine, text

LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

SQL = text("""
    select to_char(captured_at, 'HH24:MI:SS') t,
           market_slug, best_bid, best_ask, event_score, is_live
    from market_snapshots
    order by captured_at desc
    limit :n
""")

RATE = text("""
    select count(*), count(distinct event_slug)
    from market_snapshots
    where captured_at > now() - interval '60 seconds'
""")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--slow", action="store_true", help="watch Supabase instead of local ticks")
    p.add_argument("-n", type=int, default=12, help="rows to show")
    args = p.parse_args()

    if args.slow:
        from core.storage.base import app_database_url
        url, label = app_database_url(), "SUPABASE (pregame, ~15 min)"
    else:
        url, label = LOCAL_URL, "LOCAL (200ms ticks)"

    engine = create_engine(url)
    try:
        while True:
            with engine.connect() as c:
                rows = c.execute(SQL, {"n": args.n}).fetchall()
                n60, ev60 = c.execute(RATE).one()

            print("\033[2J\033[H", end="")  # clear screen, no shell, no TERM needed
            now = dt.datetime.now(dt.timezone.utc).astimezone().strftime("%H:%M:%S")
            print(f"\033[1m{label}\033[0m   {now}   "
                  f"\033[36m{n60} rows/min across {ev60} events\033[0m")
            print("-" * 96)
            print(f"{'time':<10}{'market':<46}{'bid':>7}{'ask':>7}  {'score':<10}live")
            for t, slug, bid, ask, score, live in rows:
                b = f"{float(bid):.2f}" if bid is not None else "  -"
                a = f"{float(ask):.2f}" if ask is not None else "  -"
                sc = score or ""
                print(f"{t:<10}{slug[:44]:<46}{b:>7}{a:>7}  {sc:<10}"
                      f"{'YES' if live else ''}")
            print("\nCtrl-C to stop")
            time.sleep(2)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
