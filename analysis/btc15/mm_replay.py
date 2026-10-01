"""What continuous two-sided making earns on the venue, on the microtape, with the arms' queue model.

SIZING ONLY (operator rule 2026-09-30): the live answer is the A/B arms' ledgers.

A maker quotes one contract at the venue's touch on both sides, re-joining whenever the touch
moves (new place at the back of the queue: the size displayed at that level at that instant).
A side fills when the prints at its price on its side since it was placed exceed the size that
was ahead of it, or when the book trades through it. After a fill the maker keeps quoting (so
it can be long or short up to ``max_pos`` contracts); inventory is marked at the mid and
settled at the window's result. Optionally the spot trigger: when coinbase moves >= X within W
ms, the threatened side is pulled and re-joined after the book re-prices a tick that way or
after 2 s. Per window: fills, gross spread earned (half-spread per fill against the mid at the
fill), adverse selection (mid 60 s on minus mid at the fill, signed by the side), net, and net
with the venue's maker rebate credited (docs.polymarket.us/fees, effective 2026-09-25:
theta -0.0125, i.e. 0.0125 x p x (1-p) paid to the maker per contract; the ledgers book makers
at zero, so this is the only place the rebate appears).

    python analysis/btc15/mm_replay.py <microtape.sqlite> <ledger.sqlite> [--x 10] [--w-ms 250] [--max-pos 3]
"""
from __future__ import annotations

import argparse
import bisect
import collections
import math
import sqlite3
import statistics

HITS_BID = ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")
LIFTS_OFFER = ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")
TICK = 0.01


REBATE = 0.0125


def run(tape: str, ledger: str, x: float, w_ms: int, max_pos: int, trigger: bool, spot_from: str | None = None) -> dict:
    m = sqlite3.connect(f"file:{tape}?mode=ro", uri=True)
    c = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    sm = sqlite3.connect(f"file:{spot_from}?mode=ro", uri=True) if spot_from else m
    spot = sm.execute("SELECT recv, (bid+ask)/2 FROM spot WHERE exchange='coinbase' ORDER BY recv").fetchall()
    st = [r[0] for r in spot]; sp = [r[1] for r in spot]
    first = m.execute("SELECT MIN(recv) FROM book_msgs").fetchone()[0]
    windows = [dict(r) for r in c.execute("SELECT * FROM windows WHERE result IN ('yes','no') AND open_ts > ? ORDER BY close_ts", (first,))]
    out = collections.defaultdict(list)
    for w in windows:
        slug, res, cl = w["ticker"], w["result"], w["close_ts"]
        books = m.execute("SELECT recv, bid, ask, bid_size, ask_size FROM book_msgs WHERE slug=? AND recv < ? ORDER BY recv", (slug, cl - 90)).fetchall()
        prints = m.execute("SELECT recv, price, quantity, taker_intent, maker_intent FROM trades WHERE slug=? ORDER BY recv", (slug,)).fetchall()
        pt = [p[0] for p in prints]
        quote = {"bid": None, "offer": None}       # price, since, ahead
        pulled = {"bid": None, "offer": None}
        pos = 0; cash = 0.0; fills = []; mids = []
        pi = 0
        for i, (t, bid, ask, bs, asz) in enumerate(books):
            if bid is None or ask is None or ask - bid > 0.03:
                quote = {"bid": None, "offer": None}
                continue
            mid = (bid + ask) / 2
            mids.append((t, mid))
            # spot trigger
            if trigger and st:
                j = bisect.bisect_right(st, t) - 1; k = bisect.bisect_right(st, t - w_ms / 1000) - 1
                if j >= 0 and k >= 0 and t - st[j] <= 5:
                    mv = sp[j] - sp[k]
                    if abs(mv) >= x:
                        side = "offer" if mv > 0 else "bid"
                        if quote[side] is not None and pulled[side] is None:
                            pulled[side] = {"at": t, "dir": "up" if mv > 0 else "down", "mid": mid}
                            quote[side] = None
            for side in ("bid", "offer"):
                info = pulled[side]
                if info and ((info["dir"] == "up" and mid >= info["mid"] + TICK - 1e-9) or (info["dir"] == "down" and mid <= info["mid"] - TICK + 1e-9) or t - info["at"] >= 2.0):
                    pulled[side] = None
            # fills on what rests, using prints since the last book message
            lo = bisect.bisect_right(pt, books[i - 1][0]) if i else 0
            hi = bisect.bisect_right(pt, t)
            for side in ("bid", "offer"):
                q = quote[side]
                if q is None:
                    continue
                price, since, ahead = q
                hit = 0.0
                for (pr_t, px, qty, ti, mi) in prints[lo:hi]:
                    if pr_t <= since or px is None or not qty:
                        continue
                    if side == "bid" and px <= price + 1e-9 and (ti in HITS_BID or mi == "ORDER_INTENT_BUY_LONG"):
                        hit += qty
                    elif side == "offer" and px >= price - 1e-9 and (ti in LIFTS_OFFER or mi == "ORDER_INTENT_BUY_SHORT"):
                        hit += qty
                through = (ask <= price - TICK + 1e-9) if side == "bid" else (bid >= price + TICK - 1e-9)
                if (hit > ahead or through) and abs(pos + (1 if side == "bid" else -1)) <= max_pos:
                    if side == "bid":
                        pos += 1; cash -= price
                    else:
                        pos -= 1; cash += price
                    fills.append((t, side, price, mid, through))
                    quote[side] = None
            # re-join the touch
            for side, px, sz in (("bid", bid, bs), ("offer", ask, asz)):
                if pulled[side] is not None:
                    quote[side] = None
                    continue
                if quote[side] is None or quote[side][0] != px:
                    quote[side] = (px, t, float(sz or 0.0))
        # settle inventory at the result
        payoff = pos * (1.0 if res == "yes" else 0.0)
        net = cash + payoff
        # markouts
        mt = [x_[0] for x_ in mids]
        def mid_at(t):
            j = bisect.bisect_right(mt, t) - 1
            return mids[j][1] if j >= 0 else None
        spread_earned = 0.0; adverse60 = 0.0; n60 = 0; rebate = 0.0
        for (t, side, price, mid, through) in fills:
            spread_earned += (mid - price) if side == "bid" else (price - mid)
            rebate += REBATE * price * (1 - price)
            m60 = mid_at(t + 60)
            if m60 is not None:
                adverse60 += (m60 - mid) if side == "bid" else (mid - m60); n60 += 1
        out["fills"].append(len(fills)); out["through"].append(sum(1 for f in fills if f[4]))
        out["net"].append(net); out["spread"].append(spread_earned); out["adverse60"].append(adverse60)
        out["rebate"].append(rebate); out["net_rebate"].append(net + rebate)
        out["end_pos"].append(pos)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tape"); ap.add_argument("ledger")
    ap.add_argument("--x", type=float, default=10.0); ap.add_argument("--w-ms", type=int, default=250)
    ap.add_argument("--max-pos", type=int, default=3)
    ap.add_argument("--spot-from", default=None, help="microtape to read coinbase spot from (the hourly tape has none)")
    a = ap.parse_args(argv)
    for trig in (False, True):
        o = run(a.tape, a.ledger, a.x, a.w_ms, a.max_pos, trig, a.spot_from)
        n = len(o["net"])
        if not n:
            print("no windows"); return 0
        mean = lambda k: statistics.mean(o[k]); se = lambda k: statistics.pstdev(o[k]) / math.sqrt(n)
        print(f"{'WITH' if trig else 'without'} the spot trigger (${a.x:.0f}/{a.w_ms} ms), max |pos| {a.max_pos}, {n} windows:")
        print(f"  fills/window {mean('fills'):.1f} (through {mean('through'):.1f}); net/window {100*mean('net'):+.1f}c ± {100*se('net'):.1f} "
              f"(sum ${sum(o['net']):+.2f}); with the maker rebate {100*mean('net_rebate'):+.1f}c ± {100*se('net_rebate'):.1f} "
              f"(rebate {100*mean('rebate'):+.1f}c/window); spread earned/window {100*mean('spread'):+.1f}c; adverse 60-s/window {100*mean('adverse60'):+.1f}c; "
              f"mean |end position| {statistics.mean(abs(p) for p in o['end_pos']):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
