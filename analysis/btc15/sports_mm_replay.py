"""Making at the touch, or one tick inside it, on the football in-play tapes -- sized with the arms'
queue model and the venue's rebate. SIZING ONLY (operator rule 2026-09-30).

Streams a slate directory's slate_books_<game>.jsonl / slate_trades_<game>.jsonl (the ladder
recorder's files: one row per MARKET_DATA update and per print, same fields as the BTC microtape).
For every slug with >= MIN_PRINTS prints, two one-contract policies, |pos| <= 1, inventory marked
at the slug's last mid, the venue's maker rebate (0.0125 x p x (1-p)) credited per fill:

  join     at the venue's touch on both sides, re-joined at the back of the queue (the size displayed
           at that level when we join) whenever the touch moves; filled by prints at our price on our
           side beyond the size ahead, or by a trade-through.
  improve  one tick inside the touch on both sides whenever the spread is >= 2 ticks (first in
           queue at a new level: filled by the FIRST opposite print at or through our price); else
           the same as join.

Per family (winner `aec-`, spread `asc-`) and policy: fills a slug-hour, net, net with the rebate,
adverse selection (mid 60 s after the fill), share of fills that were trade-throughs.

    python analysis/btc15/sports_mm_replay.py <slate dir> [--min-prints 50] [--games N]
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import glob
import json
import math
import os
import statistics

HITS_BID = ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")
LIFTS_OFFER = ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")
REBATE = 0.0125


def rebate_usd(price: float, qty: float) -> float:
    """The venue's maker rebate on one trade: 0.0125 x qty x p x (1-p), rounded to the nearest cent
    (banker's) AT THE TRADE (docs.polymarket.us/fees, 2026-09-25). A one-contract fill at 50c is
    $0.003 and rounds to nothing; the rebate exists only from a few contracts a fill."""
    x = REBATE * qty * price * (1 - price) * 100
    n = math.floor(x)
    frac = x - n
    if abs(frac - 0.5) < 1e-9:
        cents = n if n % 2 == 0 else n + 1
    else:
        cents = round(x)
    return cents / 100
MIN_PRINTS = 50


def ts(s: str) -> float:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def grid_of(books: list) -> float:
    """The slug's price increment, read off its own quotes: the finest decimal place any touch used
    (the winner market quotes 0.055 / 0.06 in its tails; the ladder rungs quote whole cents)."""
    fine = 0.01
    for (_t, bid, ask, _b, _a) in books:
        for px in (bid, ask):
            if px is None:
                continue
            if abs(px * 1000 - round(px * 1000)) < 1e-6 and abs(px * 100 - round(px * 100)) > 1e-6:
                return 0.005 if abs(px * 200 - round(px * 200)) < 1e-6 else 0.001
    return fine


STRICT = False      # --strict: a print AT our improved price means a resting order was there (an incumbent); only prints strictly through our price fill us


def replay(books: list, prints: list, policy: str, trace: int = 0) -> dict:
    """books: [(t, bid, ask, bs, as)], prints: [(t, price, qty, taker, maker)] for ONE slug."""
    pt = [p[0] for p in prints]
    quote = {"bid": None, "offer": None}
    pos = 0; cash = 0.0; fills = []; mids = []
    tick = grid_of(books)
    traced = 0
    for i, (t, bid, ask, bs, asz) in enumerate(books):
        if bid is None or ask is None or ask <= bid:
            quote = {"bid": None, "offer": None}
            continue
        mid = (bid + ask) / 2
        mids.append((t, mid))
        lo = bisect.bisect_right(pt, books[i - 1][0]) if i else 0
        hi = bisect.bisect_right(pt, t)
        for side in ("bid", "offer"):
            q = quote[side]
            if q is None:
                continue
            price, since, ahead, first = q
            hit = 0.0; last_print = None
            for (pr_t, px, qty, ti, mi) in prints[lo:hi]:
                if pr_t <= since or px is None or not qty:
                    continue
                at_ours = abs(px - price) < 1e-9
                if STRICT and first and at_ours:
                    continue                                  # someone rested at our price: that print was theirs
                if side == "bid" and px <= price + 1e-9 and (ti in HITS_BID or mi == "ORDER_INTENT_BUY_LONG"):
                    hit += qty; last_print = (px, qty, ti)
                elif side == "offer" and px >= price - 1e-9 and (ti in LIFTS_OFFER or mi == "ORDER_INTENT_BUY_SHORT"):
                    hit += qty; last_print = (px, qty, ti)
            through = (ask <= price - tick + 1e-9) if side == "bid" else (bid >= price + tick - 1e-9)
            filled = through or (hit > 0 if first else hit > ahead)
            if filled and abs(pos + (1 if side == "bid" else -1)) <= 1:
                if side == "bid":
                    pos += 1; cash -= price
                else:
                    pos -= 1; cash += price
                fills.append((t, side, price, mid, through, (last_print[1] if last_print else 0.0)))
                if traced < trace:
                    traced += 1
                    print(f"      fill {dt.datetime.fromtimestamp(t, dt.timezone.utc):%H:%M:%S.%f} {side:5s} @ {price:.3f}  book now {bid:.3f}/{ask:.3f}  "
                          f"{'THROUGH' if through else 'print ' + str(last_print)}  pos {pos:+d}  cash {cash:+.3f}")
                quote[side] = None
        # re-quote
        inside = policy == "improve" and (ask - bid) >= 2 * tick - 1e-9
        for side, px, sz in (("bid", bid, bs), ("offer", ask, asz)):
            want = (round(px + tick, 3) if side == "bid" else round(px - tick, 3)) if inside else px
            if want <= 0 or want >= 1:
                quote[side] = None
                continue
            if quote[side] is None or abs(quote[side][0] - want) > 1e-9:
                quote[side] = (want, t, 0.0 if inside else float(sz or 0.0), inside)
    if not mids:
        return {}
    last_mid = mids[-1][1]
    net = cash + pos * last_mid
    mt = [x[0] for x in mids]
    def mid_at(t):
        j = bisect.bisect_right(mt, t) - 1
        return mids[j][1] if j >= 0 else None
    spread = 0.0; adverse = 0.0; rebate = 0.0; capacity = 0.0; cap_fills = 0
    for (t, side, price, mid, through, qty) in fills:
        edge = (mid - price) if side == "bid" else (price - mid)
        spread += edge
        rebate += rebate_usd(price, 1.0)                      # one contract: rounds to zero below ~4 contracts
        m60 = mid_at(t + 60)
        a60 = ((m60 - mid) if side == "bid" else (mid - m60)) if m60 is not None else 0.0
        if m60 is not None:
            adverse += a60
        if not through and qty:
            # what the fill was worth at the taker's own size (capped at 100 contracts): edge to the mid,
            # the 60-s move, and the rebate, times the contracts that printed -- the capacity of the flow
            capacity += (edge + a60) * min(qty, 100.0) + rebate_usd(price, min(qty, 100.0))
            cap_fills += 1
    hours = max(1e-9, (mids[-1][0] - mids[0][0]) / 3600)
    widths = sorted(b[2] - b[1] for b in books if b[1] is not None and b[2] is not None and b[2] > b[1])
    return {"fills": len(fills), "through": sum(1 for f in fills if f[4]), "net": net, "net_rebate": net + rebate,
            "spread": spread, "adverse": adverse, "hours": hours, "rebate": rebate,
            "width_med": widths[len(widths) // 2] if widths else None, "mid_med": statistics.median(m_[1] for m_ in mids),
            "tick": tick, "capacity_usd": capacity, "cap_fills": cap_fills}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slate")
    ap.add_argument("--min-prints", type=int, default=MIN_PRINTS)
    ap.add_argument("--games", type=int, default=0)
    ap.add_argument("--top", type=int, default=0, help="also print the N best and worst slugs per family/policy")
    ap.add_argument("--trace", default=None, help="slug substring: print the first --trace-n fills of the improve policy")
    ap.add_argument("--trace-n", type=int, default=25)
    ap.add_argument("--dump", default=None, help="write per-slug rows as JSON lines here")
    ap.add_argument("--strict", action="store_true", help="credit an improved quote only with prints strictly through its price")
    a = ap.parse_args(argv)
    global STRICT
    STRICT = a.strict
    dump = open(a.dump, "w") if a.dump else None
    games = sorted(glob.glob(os.path.join(a.slate, "slate_trades_*.jsonl")))
    if a.games:
        games = games[:a.games]
    agg = collections.defaultdict(lambda: collections.defaultdict(list))
    n_slugs = 0
    for tf in games:
        game = os.path.basename(tf)[len("slate_trades_"):-len(".jsonl")]
        bf = os.path.join(a.slate, f"slate_books_{game}.jsonl")
        if not os.path.exists(bf):
            continue
        prints = collections.defaultdict(list)
        with open(tf) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                prints[r["slug"]].append((ts(r["recv"]), r.get("price"), r.get("quantity"), r.get("taker_intent"), r.get("maker_intent")))
        keep = {s for s, ps in prints.items() if len(ps) >= a.min_prints}
        if not keep:
            continue
        books = collections.defaultdict(list)
        with open(bf) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                s = r.get("slug")
                if s in keep:
                    books[s].append((ts(r["recv"]), r.get("bid"), r.get("ask"), r.get("bid_size"), r.get("ask_size")))
        for s in keep:
            if len(books[s]) < 100:
                continue
            fam = "winner" if s.startswith("aec-") else "spread" if s.startswith("asc-") else "other"
            ps = sorted(prints[s], key=lambda r: r[0]); bs = sorted(books[s], key=lambda r: r[0])
            for pol in ("join", "improve"):
                tr = a.trace_n if (a.trace and a.trace in s and pol == "improve") else 0
                if tr:
                    print(f"   trace {s} ({pol}): grid {grid_of(bs)}, {len(bs)} book msgs, {len(ps)} prints")
                r = replay(bs, ps, pol, trace=tr)
                if r:
                    r["slug"] = s; r["policy"] = pol; r["family"] = fam; r["slate"] = os.path.basename(a.slate.rstrip("/"))
                    agg[(fam, pol)]["rows"].append(r)
                    if dump:
                        dump.write(json.dumps(r) + "\n")
            n_slugs += 1
    print(f"slate {a.slate}: {len(games)} games read, {n_slugs} slugs with >= {a.min_prints} prints")
    print("family  policy   slugs  fills/slug-h  through%  net/slug-h   with rebate     spread/slug-h  adverse60/slug-h   (per ONE contract quoted both sides, |pos|<=1)")
    for (fam, pol), d in sorted(agg.items()):
        rows = d["rows"]; n = len(rows); H = sum(r["hours"] for r in rows)
        f = lambda k: 100 * sum(r[k] for r in rows) / H
        per = [r["net_rebate"] / r["hours"] for r in rows]
        se = 100 * statistics.pstdev(per) / math.sqrt(n) if n > 1 else float("nan")
        thr = sum(r["through"] for r in rows) / max(1, sum(r["fills"] for r in rows))
        med = 100 * statistics.median(per)
        print(f"{fam:7s} {pol:8s} {n:5d}  {sum(r['fills'] for r in rows)/H:11.1f}  {100*thr:6.0f}%  {f('net'):+9.1f}c  {f('net_rebate'):+9.1f}c ± {se:.1f} (median slug {med:+.1f}c)  {f('spread'):+9.1f}c  {f('adverse'):+9.1f}c")
        if a.top:
            ranked = sorted(rows, key=lambda r: r["net_rebate"] / r["hours"])
            for tag, sel in (("worst", ranked[:a.top]), ("best", ranked[-a.top:])):
                for r in sel:
                    print(f"      {tag:5s} {r['slug'][-40:]:40s} {r['hours']:4.1f}h fills {r['fills']:4d} thr {r['through']:3d} "
                          f"net+reb {100*r['net_rebate']/r['hours']:+7.1f}c/h spread {100*r['spread']/r['hours']:+6.1f} adv {100*r['adverse']/r['hours']:+6.1f} "
                          f"reb {100*r['rebate']/r['hours']:+5.1f} | width med {r['width_med']} mid med {r['mid_med']:.3f} tick {r['tick']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
