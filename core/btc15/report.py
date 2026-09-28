"""The BTC15 scorecard.

    python -m core.btc15.report [--db /data/btc15.sqlite] [--mode paper]

Prints what the ledger holds: windows seen and decided, the model against the
market's mid and a random walk (Brier, hit rate), the allocation's P&L and
drawdown, how decisions ended, the proxy index's error against Kalshi's
official closing value, and the last ten calls.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics

from core.btc15.ledger import UNIT, Ledger


def report(led: Ledger, mode: str) -> str:
    c = led._conn
    out = []
    n_windows = c.execute("SELECT count(*) FROM windows").fetchone()[0]
    n_final = c.execute("SELECT count(*) FROM windows WHERE result IN ('yes','no')").fetchone()[0]
    statuses = collections.Counter(r[0].split(":")[0] for r in c.execute("SELECT status FROM decisions").fetchall())
    out.append(f"windows seen {n_windows}, finalized {n_final}; decisions by outcome: {dict(statuses)}")
    ex = led.experience(mode, n=10, n_lessons=0)
    rec = ex["your_record"]
    out.append(f"model: {rec['windows_scored']} scored windows, hit rate {rec['hit_rate']}, Brier {rec['brier_you']} "
               f"vs market mid {rec['brier_market_mid']} vs random walk {rec['brier_random_walk']}")
    a = led.account(mode)
    out.append(f"{mode} allocation (epoch {a['epoch']}): {a['settled']} settled, {a['wins']} won, "
               f"P&L ${a['realized_u'] / UNIT:+.4f}, peak ${a['peak_u'] / UNIT:+.4f}, drawdown ${a['drawdown_u'] / UNIT:.4f} of $10, "
               f"{a['open']} open (${a['open_cost_u'] / UNIT:.4f} at risk); halted: {led.halted(mode)}")
    errs = [r[0] - r[1] for r in c.execute(
        "SELECT proxy_close, expiration_value FROM windows WHERE proxy_close IS NOT NULL AND expiration_value IS NOT NULL")]
    if errs:
        out.append(f"proxy vs official closing BRTI average: n {len(errs)}, mean ${statistics.fmean(errs):+.2f}, "
                   f"median |err| ${statistics.median(abs(e) for e in errs):.2f}, max |err| ${max(abs(e) for e in errs):.2f}")
    lat = [r[0] for r in c.execute("SELECT latency_s FROM decisions WHERE latency_s IS NOT NULL")]
    if lat:
        out.append(f"model latency: median {statistics.median(lat):.1f} s, max {max(lat):.1f} s")
    out.append("last calls:")
    for r in ex["recent_calls_newest_first"]:
        out.append("  " + json.dumps(r))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/data/btc15.sqlite")
    ap.add_argument("--mode", default="paper")
    a = ap.parse_args(argv)
    print(report(Ledger(a.db), a.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
