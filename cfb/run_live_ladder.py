"""Sample a live game's full ladder FROM THE VENUE, simultaneously, on a cadence.

    python cfb/run_live_ladder.py --prefix aec-nfl-det-buf-2026-09-17 --every 30 --minutes 120

This is the instrument that found STATUS 0bu. It is NOT the recorder tape:
market_snapshots stamps a whole sweep with one captured_at while fetching
rungs seconds apart, which under-measures a phenomenon that lives at seconds.
Here every rung is fetched with its own get_book inside a few seconds, so a
violation is two prices that coexisted.

PLACES NOTHING. It imports the venue client's read-only get_book and nothing
else; a test pins that. Output is one block per sample: timestamp, every rung,
and the fee-netted violations with edge x min(touch size). Sizes are TOUCH
sizes -- whether an order at them would fill is the one thing this cannot say.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import scan  # noqa: E402

LINE = re.compile(r"-(neg|pos)-(\d+)pt(\d)$")


def line_of(slug: str, winner_prefix: str) -> float | None:
    if slug.startswith(winner_prefix):
        return 0.0
    m = LINE.search(slug)
    if not m:
        return None
    return (-1.0 if m.group(1) == "neg" else 1.0) * (float(m.group(2)) + float(m.group(3)) / 10)


def slugs_for(prefix: str) -> list[str]:
    """The ladder's slugs from the recorder's own listing of this game."""
    from sqlalchemy import create_engine, text
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        rows = c.execute(text(
            "SELECT DISTINCT market_slug FROM market_snapshots "
            "WHERE captured_at >= now() - interval '2 days' AND market_slug LIKE :p "
            "AND sports_market_type IN ('football_team_full_game_winner','football_team_full_game_spread',"
            "'baseball_team_full_game_winner','baseball_team_full_game_spread')"),
            {"p": f"%{prefix}%"}).all()
    return sorted(r[0] for r in rows)


def sample(client, slugs: list[str], winner_prefix: str):
    rungs = {}
    t0 = time.time()
    for s in slugs:
        try:
            book, _ = client.get_book(s)
        except Exception as e:  # noqa: BLE001 -- one bad rung must not kill the sample
            print(f"  ERR {s} {str(e)[:60]}")
            continue
        md = book.market_data
        if not md.bids or not md.offers:
            continue
        k = line_of(s, winner_prefix)
        if k is None:
            continue
        rungs[k] = (float(md.bids[0].px.value), float(md.offers[0].px.value),
                    float(md.bids[0].qty), float(md.offers[0].qty))
    return rungs, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", required=True, help="e.g. aec-nfl-det-buf-2026-09-17 (winner slug)")
    ap.add_argument("--every", type=float, default=30.0, help="seconds between samples")
    ap.add_argument("--minutes", type=float, default=120.0)
    ap.add_argument("--max-size", type=float, default=1e12, help="no cap: venue depth is real (0bs)")
    a = ap.parse_args()
    from core.polymarket.client import PolymarketGatewayClient

    game_key = a.prefix.replace("aec-", "")
    slugs = slugs_for(game_key)
    print(f"live ladder  prefix={a.prefix}  rungs={len(slugs)}  every={a.every:g}s  for {a.minutes:g} min")
    end = time.time() + a.minutes * 60
    with PolymarketGatewayClient() as c:
        while time.time() < end:
            rungs, took = sample(c, slugs, a.prefix)
            now = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
            v = scan.scan_ladder(game_key, rungs, max_size=a.max_size)
            print(f"=== {now}Z  rungs {len(rungs)}  fetched in {took:.1f}s  violations {len(v)}")
            for x in sorted(v, key=lambda x: -x.dollars)[:8]:
                print(f"  ${x.dollars:9,.2f} = {x.edge*100:+5.2f}c x {x.size:9,.0f}  "
                      f"buy {x.high_line:+.1f}@{x.buy_price:.4f} sell {x.low_line:+.1f}@{x.sell_price:.4f}")
            sys.stdout.flush()
            time.sleep(max(0.0, a.every - took))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
