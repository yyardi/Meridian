"""The priority race: after a coinbase move, how long until the venue's book re-prices, could a
post at X ms be first at the new level, and what would first-in-queue fills there earn? SIZING ONLY.

The join arms stand at the BACK of the touch queue, which price-time priority makes the
adverse-only position: a last-in order fills when the whole level is swept and never on the
benign flow that hits the front (mm_replay.py: 27 of 74 fills a window were trade-throughs).
The position that could flip the sign is FIRST at a new level the instant spot moves, before
the market maker re-prices. From the tape, per coinbase move of >= X dollars within W ms
(one event per 5 s):

  (a) the delay from the coinbase quote to the first book message whose touch has moved a tick
      in the move's direction (the venue's stream is 10 Hz snapshots, so 100 ms resolution);
  (b) whether that first message moved BOTH sides or one -- a one-sided state is the only window
      in which a bid at the old ask does not cross resting offers; its duration;
  (c) the share of events where a post X ms after the coinbase quote precedes the re-price
      message (X = 50, 100, 200, 300 ms);
  (d) for events with a re-price: a one-contract order first in queue at the new level on the
      move's side (bid on an up-move, offer on a down-move) filled by the FIRST opposite print at
      that level before the next re-price; its 30/60-s markouts, with and without the rebate.

    python analysis/btc15/priority_race.py <microtape.sqlite> [--x 10] [--w-ms 250]
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


def pct(xs, q):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tape")
    ap.add_argument("--x", type=float, default=10.0)
    ap.add_argument("--w-ms", type=int, default=250)
    a = ap.parse_args(argv)
    m = sqlite3.connect(f"file:{a.tape}?mode=ro", uri=True)
    spot = m.execute("SELECT recv, (bid+ask)/2 FROM spot WHERE exchange='coinbase' ORDER BY recv").fetchall()
    st = [r[0] for r in spot]; sp = [r[1] for r in spot]
    books = m.execute("SELECT recv, slug, bid, ask, bid_size, ask_size FROM book_msgs WHERE bid IS NOT NULL AND ask IS NOT NULL ORDER BY recv").fetchall()
    bt = [b[0] for b in books]
    prints = m.execute("SELECT recv, slug, price, quantity, taker_intent, maker_intent FROM trades ORDER BY recv").fetchall()
    pt = [p[0] for p in prints]
    events = []
    last = -1e9
    for i in range(1, len(st)):
        if st[i] - last < 5.0:
            continue
        j = bisect.bisect_right(st, st[i] - a.w_ms / 1000) - 1
        if j < 0:
            continue
        mv = sp[i] - sp[j]
        if abs(mv) >= a.x:
            events.append((st[i], 1 if mv > 0 else -1, mv)); last = st[i]
    print(f"coinbase moves >= ${a.x:.0f} within {a.w_ms} ms: {len(events)} events; book messages {len(books)}")
    delays, one_sided, gap_dur, both_at_once, no_reprice = [], 0, [], 0, 0
    lead_share = {x: 0 for x in (50, 100, 200, 300)}
    fills = []
    for t0, d, mv in events:
        k = bisect.bisect_right(bt, t0) - 1
        if k < 0 or t0 - bt[k] > 2:
            continue
        slug, ob, oa = books[k][1], books[k][2], books[k][3]
        # first message after t0, same slug, with the touch moved a tick in the direction
        rep = None
        for idx in range(k + 1, min(k + 400, len(books))):
            b = books[idx]
            if b[1] != slug:
                break
            if b[0] - t0 > 30:
                break
            moved_bid = (b[2] >= ob + TICK - 1e-9) if d > 0 else (b[2] <= ob - TICK + 1e-9)
            moved_ask = (b[3] >= oa + TICK - 1e-9) if d > 0 else (b[3] <= oa - TICK + 1e-9)
            if moved_bid or moved_ask:
                rep = (idx, b, moved_bid, moved_ask)
                break
        if rep is None:
            no_reprice += 1
            continue
        idx, b, moved_bid, moved_ask = rep
        delay = b[0] - t0
        delays.append(delay)
        for x in lead_share:
            if delay > x / 1000:
                lead_share[x] += 1
        if moved_bid and moved_ask:
            both_at_once += 1
        else:
            one_sided += 1
            # how long until the other side follows
            for idx2 in range(idx + 1, min(idx + 400, len(books))):
                b2 = books[idx2]
                if b2[1] != slug or b2[0] - b[0] > 30:
                    break
                ok = (b2[2] >= ob + TICK - 1e-9 and b2[3] >= oa + TICK - 1e-9) if d > 0 else (b2[2] <= ob - TICK + 1e-9 and b2[3] <= oa - TICK + 1e-9)
                if ok:
                    gap_dur.append(b2[0] - b[0]); break
        # (d) first in queue at the new level on the move's side, from the re-price message on
        if d > 0:
            level = b[2]; side = "bid"                      # the new bid
        else:
            level = b[3]; side = "offer"                    # the new offer
        # until the next message whose touch on our side leaves the level
        end = None
        for idx2 in range(idx + 1, min(idx + 2000, len(books))):
            b2 = books[idx2]
            if b2[1] != slug:
                end = b2[0]; break
            if (side == "bid" and abs(b2[2] - level) > 1e-9) or (side == "offer" and abs(b2[3] - level) > 1e-9):
                end = b2[0]; break
        if end is None:
            continue
        lo = bisect.bisect_right(pt, b[0]); hi = bisect.bisect_left(pt, end)
        fill = None
        for pr in prints[lo:hi]:
            if pr[1] != slug or pr[2] is None:
                continue
            if side == "bid" and abs(pr[2] - level) < 0.005 and (pr[4] in HITS_BID or pr[5] == "ORDER_INTENT_BUY_LONG"):
                fill = pr; break
            if side == "offer" and abs(pr[2] - level) < 0.005 and (pr[4] in LIFTS_OFFER or pr[5] == "ORDER_INTENT_BUY_SHORT"):
                fill = pr; break
        if fill is None:
            fills.append((t0, side, level, None, None, None, end - b[0], 0.0, 0.0))
            continue
        # the flow that hit the level while it stood: the first print's size and the total on our side
        flow = sum(pr[3] or 0.0 for pr in prints[lo:hi] if pr[1] == slug and pr[2] is not None and abs(pr[2] - level) < 0.005
                   and ((side == "bid" and (pr[4] in HITS_BID or pr[5] == "ORDER_INTENT_BUY_LONG"))
                        or (side == "offer" and (pr[4] in LIFTS_OFFER or pr[5] == "ORDER_INTENT_BUY_SHORT"))))
        tf = fill[0]
        def mid_at(t):
            j = bisect.bisect_right(bt, t) - 1
            while j >= 0 and books[j][1] != slug:
                j -= 1
            return None if j < 0 else (books[j][2] + books[j][3]) / 2
        m30, m60 = mid_at(tf + 30), mid_at(tf + 60)
        val = (lambda mid: None if mid is None else ((mid - level) if side == "bid" else (level - mid)))
        fills.append((t0, side, level, val(m30), val(m60), REBATE * level * (1 - level), end - b[0], fill[3] or 0.0, flow))
    n = len(delays)
    print(f"\n(a) events with a re-price within 30 s: {n}; none within 30 s: {no_reprice}")
    print(f"    delay coinbase quote -> first re-priced book message: median {1000*pct(delays,.5):.0f} ms, p25 {1000*pct(delays,.25):.0f}, p75 {1000*pct(delays,.75):.0f}, p90 {1000*pct(delays,.9):.0f} ms")
    print(f"(b) re-price message moved both sides at once: {both_at_once}/{n}; one side first: {one_sided}/{n}"
          + (f"; the other side followed after median {1000*pct(gap_dur,.5):.0f} ms (p90 {1000*pct(gap_dur,.9):.0f}), {len(gap_dur)} measured" if gap_dur else ""))
    print("(c) share of events where a post X ms after the coinbase quote precedes the re-price message (an upper bound on being first):")
    for x, cnt in lead_share.items():
        print(f"    X={x:3d} ms: {cnt}/{n} = {cnt/n:.2f}" if n else "    n=0")
    filled = [f for f in fills if f[3] is not None]
    print(f"\n(d) first in queue at the new level on the move's side: {len(fills)} levels, {len(filled)} got an opposite print before the level moved "
          f"(level life median {1000*pct([f[6] for f in fills],.5):.0f} ms)")
    for h, idx in (("30 s", 3), ("60 s", 4)):
        xs = [f[idx] for f in filled if f[idx] is not None]
        if len(xs) > 1:
            mu = statistics.mean(xs); se = statistics.pstdev(xs) / math.sqrt(len(xs))
            reb = statistics.mean(f[5] for f in filled)
            print(f"    markout {h}: n={len(xs)} mean {100*mu:+.2f}c ± {100*se:.2f}; with the rebate {100*(mu+reb):+.2f}c")
    first_sz = [f[7] for f in filled]; flow = [f[8] for f in filled]
    if filled:
        print(f"    the first opposite print at the level: median {pct(first_sz,.5):.0f} contracts (p25 {pct(first_sz,.25):.0f}, p75 {pct(first_sz,.75):.0f}); "
              f"total opposite flow while the level stood: median {pct(flow,.5):.0f}, p75 {pct(flow,.75):.0f}, mean {statistics.mean(flow):.0f} contracts")
        per_window = len(filled) / max(1, len({round(f[0] // 900) for f in fills}))
        print(f"    ~{per_window:.1f} such fills per window at one contract; at the full first print's size the rebate-inclusive "
              f"markout is worth ~{100*statistics.mean(max(0.0, f[4] + f[5]) if f[4] is not None else 0 for f in filled) * pct(first_sz,.5)/100:.1f}c per event (median size)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
