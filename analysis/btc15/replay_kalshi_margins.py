"""Replay the Kalshi-anchored taker at every margin on the joint quote tape.

The live arms (core/btc15/arms.py) trade one margin each. The harness also tapes,
every arms tick (3 s), the venue's touch and Kalshi's same-window touch
(`quotes` in the model's ledger). This replays the SAME rule the live taker runs --
core.btc15.quant.edge on Kalshi's mid (core.btc15.harness.kalshi_mid_of: two-sided,
<= 3c wide), the first tick per window between open + 30 s and close - 90 s whose
expected value beats the margin, one contract at the ask plus the venue's taker fee,
held to the venue's result -- at margins 1c ... 10c.

Choosing a margin on the same trades that score it would flatter the winner, so the
tape is split by day: margins are ranked on the earlier days and the chosen one is
read on the later days.

    python analysis/btc15/replay_kalshi_margins.py /path/to/polymarket-15m.sqlite [--split 0.5]
"""
from __future__ import annotations

import math
import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.btc15 import quant as Q  # noqa: E402
from core.btc15.harness import kalshi_mid_of  # noqa: E402
from core.fees import POLYMARKET_TAKER  # noqa: E402  -- the period's coefficient; the tape starts 2026-09-29

START_S, MIN_LEAD_S = 30.0, 90.0
MARGINS = [m / 100 for m in range(1, 11)]


def load(path: str):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    wins = {r["ticker"]: dict(r) for r in c.execute(
        "SELECT ticker, open_ts, close_ts, result FROM windows WHERE result IN ('yes','no')")}
    ticks = defaultdict(list)
    for r in c.execute("SELECT * FROM quotes ORDER BY t"):
        if r["ticker"] in wins:
            ticks[r["ticker"]].append(dict(r))
    return wins, ticks


def replay(wins: dict, ticks: dict, margin: float) -> list[tuple[float, int, float]]:
    """(pnl, day, cost) per window traded at this margin."""
    out = []
    for tk, rows in ticks.items():
        w = wins[tk]
        y = 1.0 if w["result"] == "yes" else 0.0
        for r in rows:
            if not (w["open_ts"] + START_S <= r["t"] < w["close_ts"] - MIN_LEAD_S):
                continue
            p = kalshi_mid_of({"yes_bid": r["kalshi_bid"], "yes_ask": r["kalshi_ask"]})
            if p is None:
                continue
            side, ev, price = Q.edge(p, r["yes_ask"], r["yes_bid"], POLYMARKET_TAKER)
            if side is None or ev <= margin:
                continue
            fee = Q.fee(price, POLYMARKET_TAKER)
            pnl = (y if side == "YES" else 1 - y) - price - fee
            out.append((pnl, int(w["open_ts"] // 86400), price + fee))
            break
    return out


def stats(tr):
    n = len(tr)
    if n < 2:
        return n, float("nan"), float("nan"), float("nan")
    xs = [x[0] for x in tr]
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return n, m, sd, m / (sd / math.sqrt(n)) if sd else float("nan")


def main() -> int:
    path = sys.argv[1]
    split = float(sys.argv[sys.argv.index("--split") + 1]) if "--split" in sys.argv else 0.5
    wins, ticks = load(path)
    days = sorted({int(wins[t]["open_ts"] // 86400) for t in ticks})
    print(f"tape: {sum(len(v) for v in ticks.values()):,} ticks over {len(ticks)} settled windows, {len(days)} days")
    if len(days) < 2:
        print("one day of tape: margins are printed, no split is possible yet")
    cut = days[max(1, int(len(days) * split))] if len(days) >= 2 else None
    print(f"\n{'margin':>7} {'all: n':>7} {'mean':>8} {'t':>6}   {'early: n':>9} {'mean':>8} {'t':>6}   {'late: n':>8} {'mean':>8} {'t':>6}")
    ranked = []
    for m in MARGINS:
        tr = replay(wins, ticks, m)
        a = stats(tr)
        e = stats([x for x in tr if cut is None or x[1] < cut])
        l = stats([x for x in tr if cut is not None and x[1] >= cut])
        ranked.append((e[3] if e[0] >= 20 else float("-inf"), m, l))
        print(f"{m*100:>6.0f}c {a[0]:>7} {a[1]*100:>7.2f}c {a[3]:>6.2f}   {e[0]:>9} {e[1]*100:>7.2f}c {e[3]:>6.2f}   "
              f"{l[0]:>8} {l[1]*100:>7.2f}c {l[3]:>6.2f}")
    if cut is not None:
        best = max(ranked)
        if best[0] != float("-inf"):
            n, mean, _, t = best[2]
            print(f"\nchosen on the early days: {best[1]*100:.0f}c -> late days, read once: n={n} mean={mean*100:+.2f}c t={t:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
