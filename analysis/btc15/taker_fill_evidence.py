"""Was a paper taker fill real? The microtape's prints and book messages around every fill.

A paper taker "fills" at the displayed ask the instant its rule fires. The sports ladder work
(STATUS 0cd) found that a displayed quote is often not there: prints go THROUGH the display
while it stands. With the microtape (2026-09-30) the same check exists for BTC. For each fill
in every arm ledger after the microtape began:

  * the book message the venue sent last before the fill instant (what was displayed) and the
    first after it (did the displayed level survive the next update?);
  * prints on the slug within +/- ``window`` seconds of the fill: any print AT the fill price on
    the taker's side (a BUY_LONG at the ask for a YES fill; a BUY_SHORT at the bid for a NO
    fill) is consistent with the quote having been there; a print through the display against
    us (a taker paying MORE than our displayed ask before our instant) says the display was
    stale; no print at all says nothing either way -- and is counted as such.

SIZING / AUDIT INSTRUMENT: it says which paper fills have print evidence, not what they earned.

    python analysis/btc15/taker_fill_evidence.py <artifacts/btc15 dir> [--horizon 15m] [--since ISO] [--window 5]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import glob
import os
import sqlite3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--horizon", default="15m")
    ap.add_argument("--since", default=None)
    ap.add_argument("--window", type=float, default=5.0)
    a = ap.parse_args(argv)
    mp = os.path.join(a.root, f"polymarket-{a.horizon}-microtape.sqlite")
    m = sqlite3.connect(f"file:{mp}?mode=ro", uri=True)
    first_recv = m.execute("SELECT MIN(recv) FROM book_msgs").fetchone()[0] or 0.0
    since = max(first_recv, dt.datetime.fromisoformat(a.since).timestamp() if a.since else 0.0)
    print(f"microtape from {dt.datetime.fromtimestamp(first_recv, dt.timezone.utc).isoformat(timespec='seconds')}; fills since "
          f"{dt.datetime.fromtimestamp(since, dt.timezone.utc).isoformat(timespec='seconds')}")
    tally = {"evidenced": 0, "stale": 0, "no_print": 0, "no_book_msg": 0}
    for f in sorted(glob.glob(os.path.join(a.root, f"polymarket-{a.horizon}-arm-*.sqlite"))):
        name = os.path.basename(f).split("-arm-")[1].rsplit(".", 1)[0]
        c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        fills = c.execute("SELECT f.id, f.ticker, f.side, f.price_u, f.fee_u, f.filled_at, f.book FROM fills f "
                          "ORDER BY f.id").fetchall()
        fills = [x for x in fills if dt.datetime.fromisoformat(x["filled_at"]).timestamp() >= since]
        if not fills:
            continue
        print(f"\n== {name}: {len(fills)} fills")
        for x in fills:
            t = dt.datetime.fromisoformat(x["filled_at"]).timestamp()
            slug = x["ticker"]
            price = x["price_u"] / 10_000
            yes_px = price if x["side"] == "YES" else round(1 - price, 4)      # in YES terms
            taker_fee = x["fee_u"] > 0
            books = m.execute("SELECT recv, bid, ask FROM book_msgs WHERE slug=? AND recv BETWEEN ? AND ? ORDER BY recv",
                              (slug, t - 30, t + 30)).fetchall()
            bt = [b[0] for b in books]
            i = bisect.bisect_right(bt, t) - 1
            before = books[i] if i >= 0 else None
            after = books[i + 1] if i + 1 < len(books) else None
            prints = m.execute("SELECT recv, price, quantity, taker_intent, maker_intent FROM trades WHERE slug=? AND recv BETWEEN ? AND ? "
                               "ORDER BY recv", (slug, t - a.window, t + a.window)).fetchall()
            if x["side"] == "YES":          # we paid the ask: evidence = someone else BUY_LONG at >= our price
                at = [p for p in prints if p[1] is not None and abs(p[1] - yes_px) < 0.005 and p[3] in ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")]
                through = [p for p in prints if p[1] is not None and p[1] > yes_px + 0.005 and p[0] < t and p[3] in ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")]
            else:                           # we paid 1 - bid: evidence = BUY_SHORT at <= that bid
                at = [p for p in prints if p[1] is not None and abs(p[1] - yes_px) < 0.005 and p[3] in ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")]
                through = [p for p in prints if p[1] is not None and p[1] < yes_px - 0.005 and p[0] < t and p[3] in ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")]
            if before is None:
                verdict = "no_book_msg"
            elif through and not at:
                verdict = "stale"
            elif at:
                verdict = "evidenced"
            else:
                verdict = "no_print"
            tally[verdict] += 1
            disp = f"{before[1]}/{before[2]} @-{t - before[0]:.1f}s" if before else "-"
            nxt = f"{after[1]}/{after[2]} @+{after[0] - t:.1f}s" if after else "-"
            print(f"  #{x['id']:4d} {x['filled_at'][11:19]} {x['side']} {price:.2f}{' taker' if taker_fee else ' maker'}  displayed {disp}  next {nxt}  "
                  f"prints±{a.window:.0f}s {len(prints)} at-price {len(at)} through-before {len(through)}  -> {verdict}")
    print("\ntotal:", tally)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
