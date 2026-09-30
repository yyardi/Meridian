"""Kalshi's BRTI relay against our composite and against the official settlement. Read-only.

Once the relay records (microtape ``brti``), three questions, each with n:
  1. relay value vs the composite (ledger ``ticks``) at the same second: mean and sd of the
     difference in USD, and the relay's own cadence (gap between ticks; expected ~1 s);
  2. the relay's ``last_60s_15m`` at each window's close vs the venue's ``expiration_value``:
     if the relay carries the settlement quantity, this difference is ~0 to the cent;
  3. the relay's ``avg_60s`` at each window's open vs the venue's ``strike``: the same check on
     the price to beat.
The status file's brti.sign_path and last_error say whether the handshake worked at all.

    python analysis/btc15/brti_relay_check.py <artifacts/btc15 dir> [--horizon 15m]
"""
from __future__ import annotations

import argparse
import bisect
import os
import sqlite3
import statistics


def _stats(xs, unit="$"):
    if not xs:
        return "n=0"
    return (f"n={len(xs)} mean={statistics.mean(xs):+.2f}{unit} sd={statistics.pstdev(xs):.2f} "
            f"median|x|={statistics.median(abs(x) for x in xs):.2f} max|x|={max(abs(x) for x in xs):.2f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--horizon", default="15m")
    a = ap.parse_args(argv)
    m = sqlite3.connect(f"file:{os.path.join(a.root, f'polymarket-{a.horizon}-microtape.sqlite')}?mode=ro", uri=True)
    c = sqlite3.connect(f"file:{os.path.join(a.root, f'polymarket-{a.horizon}.sqlite')}?mode=ro", uri=True)
    if not m.execute("SELECT name FROM sqlite_master WHERE name='brti'").fetchone():
        print("no brti table: this microtape was written before the relay existed, or the relay never ran")
        return 0
    brti = m.execute("SELECT recv, source_ts_ms, value, avg_60s, last_60s_15m FROM brti ORDER BY recv").fetchall()
    print(f"brti ticks: {len(brti)}")
    if not brti:
        print("the relay recorded nothing: read status brti.sign_path / last_error")
        return 0
    bt = [r[0] for r in brti]
    gaps = sorted(b - a_ for a_, b in zip(bt, bt[1:]))
    if gaps:
        print(f"relay cadence: median {gaps[len(gaps)//2]:.2f} s, p90 {gaps[int(.9*len(gaps))]:.2f} s, max {gaps[-1]:.1f} s")
    lag = [r[0] - r[1] / 1000 for r in brti if r[1]]
    if lag:
        print(f"receive minus CF calculation time: median {statistics.median(lag):.2f} s, p90 {sorted(lag)[int(.9*len(lag))]:.2f} s")
    # 1. against the composite at the same second
    ticks = c.execute("SELECT t, px FROM ticks WHERE t >= ? ORDER BY t", (bt[0] - 2,)).fetchall()
    tt = [r[0] for r in ticks]
    diffs = []
    for recv, _ts, value, _a, _l in brti:
        i = bisect.bisect_right(tt, recv) - 1
        if i >= 0 and recv - tt[i] <= 1.5:
            diffs.append(ticks[i][1] - value)
    print("composite minus relay value, same second:", _stats(diffs))
    # 2 + 3. against the venue's settlement fields
    win = c.execute("SELECT ticker, open_ts, close_ts, strike, expiration_value, proxy_open, proxy_close FROM windows "
                    "WHERE close_ts >= ? AND expiration_value IS NOT NULL ORDER BY close_ts", (bt[0],)).fetchall()
    d_close, d_open, d_proxy = [], [], []
    for tk, o, cl, strike, exp, po, pc in win:
        i = bisect.bisect_right(bt, cl + 1.5) - 1                   # the last relay tick at or just after the close
        if i >= 0 and abs(bt[i] - cl) <= 3 and brti[i][4] is not None:
            d_close.append(brti[i][4] - exp)
        j = bisect.bisect_right(bt, o + 1.5) - 1
        if j >= 0 and abs(bt[j] - o) <= 3 and brti[j][3] is not None and strike is not None:
            d_open.append(brti[j][3] - strike)
        if pc is not None:
            d_proxy.append(pc - exp)
    print("relay last_60s_15m at close minus expiration_value:", _stats(d_close))
    print("relay avg_60s at open minus strike:", _stats(d_open))
    print("our proxy_close minus expiration_value, same windows:", _stats(d_proxy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
