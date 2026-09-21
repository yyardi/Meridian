#!/usr/bin/env python3
"""Today's slate at update resolution, gated on how fresh BOTH legs are.

Incremental. The first version rescanned the whole ladder on every update,
which is O(rungs^2) per message: 1.1 GB of tape across 48 games is ~5M
updates x 780 pairs and it does not finish. A crossing can only newly appear
when one of its legs moves, so an update to rung k is checked against the
other rungs only -- O(rungs), a 40x cut on the same arithmetic.

The arithmetic IS the same: buy the higher line at its ask, sell the lower at
its bid, edge = sell - buy - fee(buy) - fee(sell), size = min of the two
quoted sides. Copied from core.ladder.scan and checked against it on a
fixture, because a threshold is only comparable to numbers computed with the
identical expression.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import datetime as dt

sys.path.insert(0, "/app" if os.path.isdir("/app/core") else
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder.scan import DEFAULT_FEE_RATE, MAX_PLAUSIBLE_EDGE, fee  # noqa: E402

GATES = (2.0, 5.0, 15.0, 60.0, 300.0, 1e18)
FLOOR = 25.0
RATE = DEFAULT_FEE_RATE   # the constant at scan time: slate_books_*.jsonl rows carry no fee coefficient (core/ladder/stream_episodes.py)


def _epoch(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def line_of(slug):
    if slug.startswith("aec-"):
        return 0.0
    t = slug.rsplit("-", 2)
    if len(t) < 3 or t[-2] not in ("neg", "pos"):
        return None
    try:
        v = float(t[-1].replace("pt", "."))
    except ValueError:
        return None
    return -v if t[-2] == "neg" else v


def scan_file(path):
    game = os.path.basename(path)[len("slate_books_"):-len(".jsonl")]
    bid, ask, bsz, asz, seen = {}, {}, {}, {}, {}
    res = {g: {"n": 0, "floor": 0, "best": 0.0, "sum": 0.0, "inst": 0} for g in GATES}
    updates = 0
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        k = line_of(d.get("slug", ""))
        b, a = d.get("bid"), d.get("ask")
        r = _epoch(d.get("recv"))
        if k is None or b is None or a is None or r is None:
            continue
        if bid.get(k) == b and ask.get(k) == a:
            seen[k] = r
            continue
        bid[k], ask[k], seen[k] = b, a, r
        bsz[k], asz[k] = d.get("bid_size") or 0.0, d.get("ask_size") or 0.0
        updates += 1
        if len(bid) < 2:
            continue
        hits = []                      # (edge, dollars, age)
        ak, fak = ask[k], fee(ask[k], RATE)
        bk, fbk = bid[k], fee(bid[k], RATE)
        for j, bj in bid.items():
            if j == k:
                continue
            if j < k:                  # k is the HIGHER line: buy k, sell j
                e = bj - ak - fak - fee(bj, RATE)
                if 0.0 < e <= MAX_PLAUSIBLE_EDGE:
                    hits.append((e, e * min(asz[k], bsz[j]), r - min(seen[j], seen[k])))
            else:                      # k is the LOWER line: buy j, sell k
                aj = ask[j]
                e = bk - aj - fbk - fee(aj, RATE)
                if 0.0 < e <= MAX_PLAUSIBLE_EDGE:
                    hits.append((e, e * min(asz[j], bsz[k]), r - min(seen[j], seen[k])))
        if not hits:
            continue
        for g in GATES:
            sub = [h for h in hits if h[2] <= g]
            if not sub:
                continue
            o = res[g]
            o["inst"] += 1
            o["n"] += len(sub)
            best = max(h[1] for h in sub)
            o["sum"] += best           # best per instant, never the sum over pairs
            o["best"] = max(o["best"], best)
            o["floor"] += sum(1 for h in sub if h[1] >= FLOOR)
    return {"game": game, "updates": updates, "gates": res}


def main(dirs):
    files = []
    for d in dirs:
        files += sorted(glob.glob(os.path.join(d, "slate_books_*.jsonl")))
    per = []
    for i, f in enumerate(files, 1):
        per.append(scan_file(f))
        print(f"  ... {i}/{len(files)} {per[-1]['game']}  {per[-1]['updates']:,} updates",
              flush=True)
    per = [p for p in per if p["updates"]]
    print(f"\n{len(per)} games, {sum(p['updates'] for p in per):,} book updates\n")
    print("BOTH LEGS QUOTED WITHIN ...  (the older leg's age at the crossing)")
    print(f"  {'gate':>7}{'instants':>11}{'pairs':>10}{'>=$25':>9}{'games':>7}"
          f"{'sum of bests':>15}{'biggest':>12}")
    for g in GATES:
        lab = "any" if g > 1e17 else f"{g:.0f}s"
        n = sum(p["gates"][g]["n"] for p in per)
        it = sum(p["gates"][g]["inst"] for p in per)
        fl = sum(p["gates"][g]["floor"] for p in per)
        s = sum(p["gates"][g]["sum"] for p in per)
        b = max([p["gates"][g]["best"] for p in per], default=0.0)
        gm = sum(1 for p in per if p["gates"][g]["inst"])
        print(f"  {lab:>7}{it:>11,}{n:>10,}{fl:>9,}{gm:>7}{s:>15,.0f}{b:>12,.0f}")
    print("\nPER GAME, 2s gate vs no gate")
    print(f"  {'game':<34}{'updates':>10}{'2s':>7}{'2s>=$25':>9}{'any':>10}{'any>=$25':>10}")
    per.sort(key=lambda p: -p["gates"][2.0]["inst"])
    for p in per[:20]:
        g2, ga = p["gates"][2.0], p["gates"][1e18]
        print(f"  {p['game']:<34}{p['updates']:>10,}{g2['inst']:>7,}{g2['floor']:>9,}"
              f"{ga['inst']:>10,}{ga['floor']:>10,}")
    if len(per) > 20:
        print(f"  ... {len(per)-20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
