"""Are the maker arms' fills toxic because spot moved first? The split the spot trigger is sized on.

The join arms re-price only on the venue's book messages. If spot leads the book by a few
hundred milliseconds (microtape_leadlag.py), our quotes stand at the old price for exactly the
interval in which informed flow hits them. This instrument reads, per maker fill:

  * the fill instant -- ``filled_ts`` from the decision's response (join arms, from 2026-09-30
    evening); older fills are reconstructed from the microtape: the last print at our price on
    our side inside the fill's second, or the book message that crossed us;
  * the largest coinbase move in the 250 / 500 / 1000 ms BEFORE that instant;
  * the fill's 30-s and 60-s markouts (ledger ``markouts``), in the side's own terms.

Then the markouts of fills preceded by a >= $X move against the rest, with n per bucket. If the
negative markouts sit in the spot-preceded bucket, pulling the quotes on a spot move removes
them and the rest is the spread; if they are everywhere, the spread is too thin for the venue.

SIZING INSTRUMENT, NOT A RESULT.

Registered before the first night's run (2026-09-30 17:25Z, with the Manager): the primary
read is X = $10 over the 500 ms before the fill instant (a ~2-sigma half-second move at
today's volatility: 1-min sd ~ $58, so 500-ms sd ~ $5) on the 60-s markout; 250 / 1000 ms and
the 30-s markout are secondary. Population: every fee-0 fill of touch_maker, touch_maker_k
(15m), touch_maker (1h) and kalshi_requote from 2026-09-30 17:18Z to 2026-10-01 12:00Z, read
once. The decision the read serves: a spot trigger for the makers (pull or re-centre both
quotes when coinbase moves >= $X within 250 ms, re-join after the book re-prices) is built
only if the spot-preceded bucket carries the negative markouts and the rest does not.

    python analysis/btc15/maker_fill_toxicity.py <dir with polymarket-15m-microtape.sqlite and the arm ledgers> [--horizon 15m]

The hourly bot tapes no spot (its sockets are off; spot is taped once, by the 15-minute bot),
so ``--horizon 1h`` reads spot from the 15-minute microtape in the same directory.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import glob
import json
import os
import sqlite3
import statistics

HITS_BID = ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")
LIFTS_OFFER = ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")


def fill_instant(m, r: dict, slug: str, side: str, yes_px: float, t_sec: float) -> tuple[float | None, str]:
    """(instant, how) for a fill: the response's filled_ts, else reconstructed from the tape."""
    if r.get("filled_ts"):
        return float(r["filled_ts"]), r.get("filled_by", "response")
    lo, hi = t_sec - 1.0, t_sec + 1.0
    if side == "YES":       # a YES bid at yes_px: filled by prints on the bid side, or the ask crossing below
        pr = m.execute("SELECT recv FROM trades WHERE slug=? AND recv BETWEEN ? AND ? AND ABS(price-?)<0.005 AND "
                       "(taker_intent IN (?,?) OR maker_intent='ORDER_INTENT_BUY_LONG') ORDER BY recv DESC LIMIT 1",
                       (slug, lo, hi, yes_px, *HITS_BID)).fetchone()
        bk = m.execute("SELECT recv FROM book_msgs WHERE slug=? AND recv BETWEEN ? AND ? AND ask IS NOT NULL AND ask <= ?-0.005 "
                       "ORDER BY recv LIMIT 1", (slug, lo, hi, yes_px)).fetchone()
    else:                   # a NO bid at 1-yes_px = a YES offer at yes_px
        pr = m.execute("SELECT recv FROM trades WHERE slug=? AND recv BETWEEN ? AND ? AND ABS(price-?)<0.005 AND "
                       "(taker_intent IN (?,?) OR maker_intent='ORDER_INTENT_BUY_SHORT') ORDER BY recv DESC LIMIT 1",
                       (slug, lo, hi, yes_px, *LIFTS_OFFER)).fetchone()
        bk = m.execute("SELECT recv FROM book_msgs WHERE slug=? AND recv BETWEEN ? AND ? AND bid IS NOT NULL AND bid >= ?+0.005 "
                       "ORDER BY recv LIMIT 1", (slug, lo, hi, yes_px)).fetchone()
    if bk:
        return bk[0], "through(tape)"
    if pr:
        return pr[0], "prints(tape)"
    return None, "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--horizon", default="15m")
    ap.add_argument("--exchange", default="coinbase")
    ap.add_argument("--x", type=float, default=10.0, help="spot move in USD that counts as 'spot moved first'")
    ap.add_argument("--spot-from", default=None, help="microtape to read spot from (default: the 15m one in root)")
    a = ap.parse_args(argv)
    m = sqlite3.connect(f"file:{os.path.join(a.root, f'polymarket-{a.horizon}-microtape.sqlite')}?mode=ro", uri=True)
    sm = sqlite3.connect(f"file:{a.spot_from or os.path.join(a.root, 'polymarket-15m-microtape.sqlite')}?mode=ro", uri=True)
    spot = sm.execute("SELECT recv, (bid+ask)/2 FROM spot WHERE exchange=? ORDER BY recv", (a.exchange,)).fetchall()
    st = [r[0] for r in spot]; sp = [r[1] for r in spot]

    def move_before(t: float, w_ms: int) -> float | None:
        """spot at t minus spot at t - w: each is the last quote at or before that instant (a quiet
        exchange has no row inside a short window; its last quote is still its price)."""
        i = bisect.bisect_right(st, t) - 1
        j = bisect.bisect_right(st, t - w_ms / 1000) - 1
        if i < 0 or j < 0 or t - st[i] > 5.0:
            return None
        return sp[i] - sp[j]

    rows = []
    for f in sorted(glob.glob(os.path.join(a.root, f"polymarket-{a.horizon}-arm-*.sqlite"))):
        name = os.path.basename(f).split("-arm-")[1].rsplit(".", 1)[0]
        c = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        spec = json.loads((c.execute("SELECT value FROM state WHERE key='arm_spec'").fetchone() or [None])[0] or "{}")
        if spec.get("kind") not in ("join", "requote", "maker"):
            continue
        for x in c.execute("SELECT f.id, f.ticker, f.side, f.price_u, f.filled_at, d.response FROM fills f "
                           "JOIN decisions d ON d.ticker=f.ticker WHERE f.fee_u = 0 ORDER BY f.id"):
            price = x["price_u"] / 10_000
            yes_px = price if x["side"] == "YES" else round(1 - price, 4)
            t_sec = dt.datetime.fromisoformat(x["filled_at"]).timestamp()
            try:
                r = json.loads(x["response"] or "{}")
            except ValueError:
                r = {}
            t, how = fill_instant(m, r, x["ticker"], x["side"], yes_px, t_sec)
            marks = {}
            for hz, yb, ya in c.execute("SELECT horizon_s, yes_bid, yes_ask FROM markouts WHERE fill_id=?", (x["id"],)):
                if yb is None or ya is None:
                    continue
                mid = (yb + ya) / 2
                marks[hz] = (mid if x["side"] == "YES" else 1 - mid) - price
            mv = {w: (None if t is None else move_before(t, w)) for w in (250, 500, 1000)}
            rows.append((name, x["id"], x["ticker"][-5:], x["side"], price, t, how, mv, marks))
    print(f"{len(rows)} maker fills; spot rows {len(spot)} ({a.exchange})")
    print("arm            fill window side price  instant(how)              dSpot 250/500/1000 ms   mark 30s   mark 60s")
    for name, fid, w, side, price, t, how, mv, marks in rows:
        f = lambda v: "   -  " if v is None else f"{v:+6.1f}"
        print(f"{name:14s} #{fid:<3d} {w} {side:3s} {price:.2f}  {('-' if t is None else f'{t:.3f}')} {how:14s} "
              f"{f(mv[250])} {f(mv[500])} {f(mv[1000])}   {('-' if 30 not in marks else f'{100*marks[30]:+5.1f}c'):>7s}  {('-' if 60 not in marks else f'{100*marks[60]:+5.1f}c'):>7s}")
    for hz in (30, 60):
        for w in (250, 500, 1000):
            pre, rest = [], []
            for name, fid, wdw, side, price, t, how, mv, marks in rows:
                if hz not in marks or mv[w] is None:
                    continue
                against = (mv[w] <= -a.x) if side == "YES" else (mv[w] >= a.x)      # spot moved AGAINST our side
                (pre if against else rest).append(marks[hz])
            def s(xs):
                if not xs: return "n=0"
                mu = statistics.mean(xs); sd = statistics.pstdev(xs) if len(xs) > 1 else 0
                return f"n={len(xs)} mean={100*mu:+.1f}c" + (f" t={mu/(sd/len(xs)**0.5):+.1f}" if sd else "")
            print(f"markout {hz:2d}s, spot moved >= ${a.x:.0f} against us within {w:4d} ms before the fill: {s(pre)} | the rest: {s(rest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
