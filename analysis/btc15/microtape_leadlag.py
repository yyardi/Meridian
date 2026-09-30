"""Does spot lead the venue's book at the resolution the arms act at? Read off the microtape.

SIZING INSTRUMENT, NOT A RESULT (operator rule 2026-09-30): this decides whether a
spot-driven taker arm is worth adding as a LIVE paper arm; nothing it prints is edge.

Measured on the once-a-second REST composite (Manager, 2026-09-30, 41 windows): the
composite did not lead either book -- corr(spot move over the prior 2 s, Poly's next mid
move) +0.034, and its own 2-s autocorrelation +0.207 said it smeared moves across seconds.
The microtape records spot at the exchanges' own cadence (Coinbase, Kraken sockets) and the
venue's book at every message, on one clock, so the same question can be asked at 100-500 ms:

  1. corr(spot move over the prior W ms before a book message, that message's mid move)
     for W in 100, 250, 500, 1000, 2000 ms -- lead if positive and larger at short W;
  2. of the book messages that arrive AFTER a spot move of >= $X within the prior W ms,
     the share whose PREVIOUS mid still showed the old price (a stale quote a taker could
     hit) and how far the mid then moved;
  3. the paper P&L of a taker who, L ms after a >= $X spot move, buys the side the move
     favours at the last displayed ask, marked at the venue mid H seconds later (spread +
     fee paid; the markout is the low-noise read).

    python analysis/btc15/microtape_leadlag.py <microtape.sqlite> [--since ISO] [--react-ms 300]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import math
import sqlite3
import statistics


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan"), n
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float("nan"), n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy), n


def fee(p: float, coef: float = 0.0695) -> float:
    return math.ceil(coef * p * (1 - p) * 100 - 1e-9) / 100


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--since", default=None)
    ap.add_argument("--react-ms", type=int, default=300)
    ap.add_argument("--exchange", default="coinbase")
    a = ap.parse_args(argv)
    c = sqlite3.connect(f"file:{a.path}?mode=ro", uri=True)
    since = dt.datetime.fromisoformat(a.since).timestamp() if a.since else 0.0
    spot = c.execute("SELECT recv, (bid+ask)/2 FROM spot WHERE exchange=? AND recv>? ORDER BY recv", (a.exchange, since)).fetchall()
    books = c.execute("SELECT recv, slug, bid, ask FROM book_msgs WHERE recv>? AND bid IS NOT NULL AND ask IS NOT NULL "
                      "ORDER BY recv", (since,)).fetchall()
    print(f"spot rows {len(spot)} ({a.exchange}), book messages {len(books)}")
    if not spot or not books:
        return 0
    st = [r[0] for r in spot]; sp = [r[1] for r in spot]

    def spot_at(t):
        i = bisect.bisect_right(st, t) - 1
        return sp[i] if i >= 0 else None

    # spot's own cadence
    g = sorted(b - a_ for a_, b in zip(st, st[1:]))
    print(f"spot gap median {1000*g[len(g)//2]:.0f} ms, p90 {1000*g[int(.9*len(g))]:.0f} ms")
    # 1. lead-lag at each window
    prev = {}
    rows = []                                   # (t, slug, mid, prev_mid, prev_t)
    for t, slug, bid, ask in books:
        mid = (bid + ask) / 2
        if slug in prev:
            rows.append((t, slug, mid, prev[slug][0], prev[slug][1]))
        prev[slug] = (mid, t)
    print("\nlead-lag: corr(spot move over the prior W ms, this book message's mid move)")
    for w in (100, 250, 500, 1000, 2000):
        xs, ys = [], []
        for t, slug, mid, pmid, pt in rows:
            s1, s0 = spot_at(t), spot_at(t - w / 1000)
            if s1 is None or s0 is None:
                continue
            xs.append(s1 - s0); ys.append(mid - pmid)
        r, n = _corr(xs, ys)
        print(f"  W={w:5d} ms  corr {r:+.3f}  n={n}")
    # contemporaneous / reverse: does the book lead spot? corr(mid move, spot move over the NEXT W ms)
    print("reverse: corr(this book message's mid move, spot move over the NEXT W ms)")
    for w in (250, 1000, 2000):
        xs, ys = [], []
        for t, slug, mid, pmid, pt in rows:
            s0, s1 = spot_at(t), spot_at(t + w / 1000)
            if s0 is None or s1 is None:
                continue
            xs.append(mid - pmid); ys.append(s1 - s0)
        r, n = _corr(xs, ys)
        print(f"  W={w:5d} ms  corr {r:+.3f}  n={n}")
    # 2 + 3. stale quotes after a spot jump, and a taker at reaction latency
    print(f"\nafter a spot move >= $X within the prior W ms, a taker {a.react_ms} ms later at the displayed ask, marked at the mid H s on")
    bt = [r[0] for r in books]
    for X in (10, 15, 25, 40):
        for W in (500, 1000):
            events = []                         # (t_event, direction)
            last_ev = -1e9
            for i in range(1, len(st)):
                if st[i] - last_ev < 5.0:       # one event per 5 s
                    continue
                s0 = spot_at(st[i] - W / 1000)
                if s0 is None:
                    continue
                d = sp[i] - s0
                if abs(d) >= X:
                    events.append((st[i], 1 if d > 0 else -1)); last_ev = st[i]
            pnl = {5: [], 30: []}
            stale = 0; judged = 0
            for te, direction in events:
                ta = te + a.react_ms / 1000
                j = bisect.bisect_right(bt, ta) - 1              # the book displayed at action time
                if j < 0 or ta - bt[j] > 30:
                    continue
                t0, slug, bid, ask = books[j]
                # was the displayed book already re-priced? compare to the book 1 s before the event
                k = bisect.bisect_right(bt, te - 1.0) - 1
                if k >= 0 and books[k][1] == slug:
                    judged += 1
                    old_mid = (books[k][2] + books[k][3]) / 2
                    if abs((bid + ask) / 2 - old_mid) < 0.005:
                        stale += 1
                price = ask if direction > 0 else 1 - bid           # buy YES on an up-move, NO on a down-move
                cost = price + fee(price)
                for H in pnl:
                    kk = bisect.bisect_right(bt, ta + H) - 1
                    if kk < 0 or books[kk][1] != slug or bt[kk] < ta:
                        continue
                    mid_h = (books[kk][2] + books[kk][3]) / 2
                    value = mid_h if direction > 0 else 1 - mid_h
                    pnl[H].append(value - cost)
            line = f"  X=${X:2d} W={W:4d}ms events {len(events):4d} displayed book unchanged since 1 s before the move: {stale}/{judged}"
            for H, xs in pnl.items():
                if len(xs) >= 2:
                    m = statistics.mean(xs); sd = statistics.pstdev(xs)
                    line += f" | H={H:2d}s n={len(xs)} mean {100*m:+.2f}c t={m/(sd/math.sqrt(len(xs))) if sd else float('nan'):+.2f}"
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
