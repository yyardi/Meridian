"""The Bitcoin windows from Kalshi's side: settlement agreement, lead-lag, the reverse taker, the locked pair.

The live arms buy on the VENUE when Kalshi's same-window mid clears the venue's ask plus
fee. The operator also holds a Kalshi account, so three other trades are possible. This
reads them all off the same joint quote tape (`quotes` in the model's ledger: the venue's
touch and Kalshi's touch, read in the same 3-s arms tick):

1. **Do the two contracts settle alike?** Every settled window in the ledger is compared
   with Kalshi's own result for the window that closes at the same second. A locked pair
   is only locked if they never disagree.
2. **Who leads?** At every tick where the two mids differ by >= GAP, how much of the gap
   each venue closes over the next 30 and 60 s.
3. **The reverse taker:** buy on KALSHI when the venue's mid (two-sided, <= 3c wide)
   clears Kalshi's ask plus Kalshi's fee (0.07 p(1-p), up to the cent) by a margin; the
   first qualifying tick per window, one contract, held to the result.
4. **The locked pair:** YES on one venue and NO on the other, each at its ask plus its
   fee. It pays exactly $1 if the two settle alike, so any tick where the two costs sum
   below $1 is a riskless profit (sizes on Kalshi's side are not on the tape).

    python analysis/btc15/kalshi_side.py /path/to/polymarket-15m.sqlite
"""
from __future__ import annotations

import bisect
import datetime as dt
import math
import os
import sqlite3
import sys
from collections import defaultdict

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.btc15 import quant as Q  # noqa: E402
from core.btc15.harness import kalshi_mid_of  # noqa: E402
from core.fees import KALSHI_TAKER, POLYMARKET_TAKER  # noqa: E402  -- both constants of this period

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
START_S, MIN_LEAD_S, GAP = 30.0, 90.0, 0.03


def kfee(p: float) -> float:
    """Kalshi's quadratic taker fee (KXBTC15M: fee_multiplier 1), up to the cent."""
    return math.ceil(round(KALSHI_TAKER * p * (1 - p) * 100, 9)) / 100


def kalshi_results(t0: float, t1: float) -> dict[float, tuple[str, float | None]]:
    """close_ts -> (result, expiration_value) for every settled KXBTC15M market closing in [t0, t1]."""
    out, cursor = {}, None
    h = httpx.Client(timeout=20, headers={"User-Agent": "meridian-kalshi-side/1"})
    for _ in range(20):
        params = {"series_ticker": "KXBTC15M", "status": "settled", "min_close_ts": int(t0) - 60,
                  "max_close_ts": int(t1) + 60, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        d = h.get(f"{KALSHI}/markets", params=params).json()
        for m in d.get("markets") or []:
            ct = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp()
            try:
                ev = float(m.get("expiration_value") or "nan")
            except ValueError:
                ev = None
            out[ct] = (m.get("result"), ev)
        cursor = d.get("cursor")
        if not cursor:
            break
    return out


def mean_t(xs):
    n = len(xs)
    if n < 2:
        return n, float("nan"), float("nan")
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return n, m, m / (sd / math.sqrt(n)) if sd else float("nan")


def main(path: str) -> int:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    wins = {r["ticker"]: dict(r) for r in c.execute(
        "SELECT ticker, open_ts, close_ts, result, expiration_value FROM windows WHERE result IN ('yes','no')")}

    # 1. settlement agreement
    t0 = min(w["close_ts"] for w in wins.values())
    t1 = max(w["close_ts"] for w in wins.values())
    kr = kalshi_results(t0, t1)
    agree = disagree = missing = 0
    close_calls = []
    for w in wins.values():
        k = kr.get(w["close_ts"])
        if not k or k[0] not in ("yes", "no"):
            missing += 1
            continue
        if k[0] == w["result"]:
            agree += 1
        else:
            disagree += 1
            close_calls.append((w["ticker"], w["result"], k))
    print(f"1. settlement: {agree} agree, {disagree} disagree, {missing} not found on Kalshi "
          f"(venue windows closing {dt.datetime.fromtimestamp(t0, dt.timezone.utc):%m-%d %H:%MZ} .. "
          f"{dt.datetime.fromtimestamp(t1, dt.timezone.utc):%m-%d %H:%MZ})")
    for x in close_calls[:10]:
        print("   disagree:", x)

    # the tape, per settled window
    tape = defaultdict(list)
    for r in c.execute("SELECT * FROM quotes ORDER BY t"):
        if r["ticker"] in wins:
            tape[r["ticker"]].append(dict(r))

    def vmid(r):
        b, a = r["yes_bid"], r["yes_ask"]
        return None if b is None or a is None or a - b > 0.0301 or not 0 < b < a < 1 else (a + b) / 2

    def kmid(r):
        return kalshi_mid_of({"yes_bid": r["kalshi_bid"], "yes_ask": r["kalshi_ask"]})

    # 2. lead-lag: of a >= GAP disagreement, how much does each side close over the next 30 / 60 s
    for hz in (30, 60):
        closed_v, closed_k, n = [], [], 0
        for tk, rows in tape.items():
            ts = [r["t"] for r in rows]
            for r in rows:
                v, k = vmid(r), kmid(r)
                if v is None or k is None or abs(v - k) < GAP:
                    continue
                j = bisect.bisect_left(ts, r["t"] + hz)
                if j >= len(rows) or rows[j]["t"] - (r["t"] + hz) > 6:
                    continue
                v2, k2 = vmid(rows[j]), kmid(rows[j])
                if v2 is None or k2 is None:
                    continue
                gap = k - v                                    # signed: + means Kalshi is above the venue
                closed_v.append((v2 - v) / gap)               # share of the gap the VENUE moved toward Kalshi
                closed_k.append((k - k2) / gap)               # share Kalshi moved toward the venue
                n += 1
        if n:
            print(f"2. lead-lag, {hz} s after a gap >= {GAP*100:.0f}c: {n} ticks; the venue closes "
                  f"{sum(closed_v)/n:.0%} of the gap, Kalshi {sum(closed_k)/n:.0%}")

    # 3. the reverse taker, and 3b. the live rule on the same tape for comparison
    print("3. first qualifying tick per window, one contract, held to the venue's result:")
    for label, fn in (("buy on KALSHI off the venue's mid", "rev"), ("buy on the VENUE off Kalshi's mid (live rule)", "fwd")):
        for margin in (0.02, 0.04):
            pnl = []
            for tk, rows in tape.items():
                w = wins[tk]
                y = 1.0 if w["result"] == "yes" else 0.0
                for r in rows:
                    if not (w["open_ts"] + START_S <= r["t"] < w["close_ts"] - MIN_LEAD_S):
                        continue
                    if fn == "rev":
                        p = vmid(r)
                        kb, ka = r["kalshi_bid"], r["kalshi_ask"]
                        if p is None or kb is None or ka is None:
                            continue
                        ev_y = p - ka - kfee(ka)
                        ev_n = kb - p - kfee(1 - kb)
                        side, ev = ("YES", ev_y) if ev_y >= ev_n else ("NO", ev_n)
                        price = ka if side == "YES" else 1 - kb
                        cost = price + kfee(price)
                    else:
                        p = kmid(r)
                        if p is None:
                            continue
                        side, ev, price = Q.edge(p, r["yes_ask"], r["yes_bid"], POLYMARKET_TAKER)
                        if side is None:
                            continue
                        cost = price + Q.fee(price, POLYMARKET_TAKER)
                    if ev <= margin:
                        continue
                    pnl.append((y if side == "YES" else 1 - y) - cost)
                    break
            n, m, t = mean_t(pnl)
            print(f"   {label:46s} margin {margin*100:.0f}c: {n:3d} trades, mean {m*100:+6.2f}c, t {t:+.2f}")

    # 4. the locked pair
    best, ticks, locked = [], 0, defaultdict(float)
    for tk, rows in tape.items():
        for r in rows:
            va, vb, ka, kb = r["yes_ask"], r["yes_bid"], r["kalshi_ask"], r["kalshi_bid"]
            if None in (va, vb, ka, kb):
                continue
            ticks += 1
            # YES on the venue + NO on Kalshi; YES on Kalshi + NO on the venue
            a = va + Q.fee(va, POLYMARKET_TAKER) + (1 - kb) + kfee(1 - kb)
            b = ka + kfee(ka) + (1 - vb) + Q.fee(1 - vb, POLYMARKET_TAKER)
            edge = 1 - min(a, b)
            best.append(edge)
            if edge > 0:
                locked[tk] = max(locked[tk], edge)
    best.sort()
    q = lambda f: best[min(len(best) - 1, int(f * len(best)))]
    print(f"4. locked pair: {ticks} ticks; profit per pair after both fees: median {q(.5)*100:+.1f}c, "
          f"p90 {q(.9)*100:+.1f}c, p99 {q(.99)*100:+.1f}c, max {best[-1]*100:+.1f}c; "
          f"ticks above $0: {sum(1 for e in best if e > 0)}; windows with one: {len(locked)} of {len(tape)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
