"""Kalshi's book in the last seconds: how much rests on the LOSER at the last tenths of a cent, per
window, from the microtape's kalshi_book (ten levels a side, every reader pass inside the last
120 s). SIZING ONLY.

The relay's partial average decides a window before its close; Kalshi's book stayed two-sided to
the last seconds at 0.002/0.003 on 2026-09-30 (the venue's was one-sided from ~10 s). A resting
YES bid at 0.002 on a window the average has decided DOWN is someone paying 0.2c for a sure
loser; selling it to them (buying NO at 0.998) earns 0.2c a contract at a fee of 0.07·0.998·0.002.
Whether that is worth anything is the SIZE resting there, which this prints: per window, at
tau = 10, 5, 3, 1 s before the close, the best bid on the losing side, its size, and the total
size within 1c of zero on that side; then the sum over windows of (size x price) -- the dollars
that flow would pay for sure losers per window, which bounds the take at any fee.

    python analysis/btc15/kalshi_last_seconds.py <artifacts dir> [--horizon 15m]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import statistics


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--horizon", default="15m")
    a = ap.parse_args(argv)
    m = sqlite3.connect(f"file:{os.path.join(a.root, f'polymarket-{a.horizon}-microtape.sqlite')}?mode=ro", uri=True)
    c = sqlite3.connect(f"file:{os.path.join(a.root, f'polymarket-{a.horizon}.sqlite')}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    if not m.execute("SELECT name FROM sqlite_master WHERE name='kalshi_book'").fetchone():
        print("no kalshi_book table yet (the depth tape runs from the restart that carries 53c5552)")
        return 0
    first = m.execute("SELECT MIN(recv) FROM kalshi_book").fetchone()[0]
    if first is None:
        print("kalshi_book is empty")
        return 0
    # windows: Kalshi tickers are not the venue's slugs; join by close time (both windows close at :00/:15/:30/:45)
    wins = [dict(r) for r in c.execute("SELECT * FROM windows WHERE result IN ('yes','no') AND close_ts > ? ORDER BY close_ts", (first,))]
    print(f"depth from {first:.0f}; settled windows since: {len(wins)}")
    print("window  result | tau: loser's best bid (size) | size within 1c | $ paid for losers")
    totals = {10: [], 5: [], 3: [], 1: []}
    for w in wins:
        cl, res = w["close_ts"], w["result"]
        loser = "yes" if res == "no" else "no"          # the side whose contracts settle at 0
        line = f"{w['ticker'][-5:]} {res:3s} |"
        for tau in (10, 5, 3, 1):
            t = cl - tau
            rec = m.execute("SELECT recv FROM kalshi_book WHERE recv <= ? AND recv > ? ORDER BY recv DESC LIMIT 1", (t, t - 3)).fetchone()
            if rec is None:
                line += f" {tau:2d}s: -          |"; totals[tau].append(None); continue
            rows = m.execute("SELECT price, size FROM kalshi_book WHERE recv=? AND side=? ORDER BY price DESC", (rec[0], loser)).fetchall()
            if not rows:
                line += f" {tau:2d}s: none       |"; totals[tau].append(0.0); continue
            best_p, best_s = rows[0]
            near = sum(s for p, s in rows if p <= 0.01)
            paid = sum(p * s for p, s in rows if p <= 0.01)
            totals[tau].append(paid)
            line += f" {tau:2d}s: {best_p:.3f} ({best_s:.0f}) | {near:.0f} | ${paid:.2f} |"
        print(line)
    print("\nper window, dollars resting on sure losers within 1c of zero (the most any taker could collect before fees):")
    for tau, xs in totals.items():
        ys = [x for x in xs if x is not None]
        if ys:
            print(f"  tau {tau:2d} s: n={len(ys)} median ${statistics.median(ys):.2f} mean ${statistics.mean(ys):.2f} max ${max(ys):.2f}  -> at 96 windows/day ~${96*statistics.mean(ys):.0f}/day gross")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
