#!/usr/bin/env python3
"""Hypothetical P&L for every ticket the desk wrote on one date, held to
settlement, priced off the venue's own final score.

    python slate_pnl.py 2026-09-20

Nothing was placed; this is the settlement arithmetic on the tickets that
were WRITTEN, against the scores that HAPPENED. Three sizings, because the
executor re-writes a standing crossing every cycle and 153 tickets on
2026-09-18 were 38 opportunities:

    A  every ticket, one contract          -- what the file literally says
    B  one per distinct pair, one contract -- the honest opportunity count
    C  one per distinct pair, full quoted size -- if displayed size fills

Split by which detector wrote the ticket (REST poll vs stream), since on
2026-09-19 the REST book ran a median 62 s stale and its crossings were
mostly artifacts while the stream's fresh ones were real but few.

The margin is (first team - second team) in slug order, read from the last
`event_score` the recorder saw for the winner market. That orientation was
verified on 2026-09-19 against Miami's SETTLED ladder (bid 0.99 at -10.5,
ask 0.01 at -13.5 => margin in (10.5, 13.5), and event_score said 33-20).
A game whose last period is not FT is reported but flagged, never silently
scored on a live score.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, "/app" if os.path.isdir("/app/core") else
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text  # noqa: E402
from core.ladder.live import _engine  # noqa: E402

SQL = """
SELECT DISTINCT ON (market_slug) market_slug, event_score, event_period
FROM market_snapshots
WHERE captured_at >= date_trunc('month', now()) AND captured_at >= now() - interval '2 days'
  AND market_slug = ANY(:slugs) AND event_score IS NOT NULL
ORDER BY market_slug, captured_at DESC
"""


def finals(games: list[str]) -> dict[str, tuple[int, bool]]:
    """game -> (margin, is_final). Margin = first team - second team."""
    slugs = ["aec-" + g for g in games]
    out = {}
    with _engine(None).connect() as c:
        for slug, score, period in c.execute(text(SQL), {"slugs": slugs}).all():
            m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(score or ""))
            if not m:
                continue
            out[slug[4:]] = (int(m.group(1)) - int(m.group(2)), str(period or "").upper() == "FT")
    return out


def main(date: str) -> int:
    tix = []
    for p in sorted(glob.glob(f"/out/ladder_intents_aec-*-{date}.jsonl")):
        for ln in open(p, encoding="utf-8"):
            if ln.strip():
                t = json.loads(ln)
                if "leg1" in t and "leg2" in t:
                    tix.append(t)
    if not tix:
        print(f"no tickets dated {date}")
        return 0
    games = sorted({t["game"] for t in tix})
    fin = finals(games)
    print(f"HYPOTHETICAL P&L, tickets dated {date}, held to settlement. NOTHING WAS PLACED.\n")
    print(f"  {'game':<28}{'margin':>8}{'final':>7}{'tickets':>9}")
    for g in games:
        m = fin.get(g)
        print(f"  {g:<28}{(m[0] if m else '?'):>8}{('yes' if m and m[1] else 'NO'):>7}"
              f"{sum(1 for t in tix if t['game'] == g):>9}")
    scored = [t for t in tix if t["game"] in fin]
    if len(scored) < len(tix):
        print(f"\n  {len(tix) - len(scored)} tickets on games with no recorded score are EXCLUDED below.")
    nonfinal = {g for g, (_, f) in fin.items() if not f}
    if nonfinal:
        print(f"  games scored on a NON-FINAL board score (treat as provisional): {sorted(nonfinal)}")

    def settle(t):
        m = fin[t["game"]][0]
        hi, lo = float(t["leg1"]["market_line"]), float(t["leg2"]["market_line"])
        pay = (1.0 if m + hi > 0 else 0.0) + (1.0 if m + lo < 0 else 0.0)
        cost = float(t["leg1"]["price"]) + float(t["leg2"]["price"])
        return pay, cost, float(t.get("displayed_size") or 0.0)

    def show(label, rows, size_of):
        if not rows:
            print(f"  {label:<46} (none)"); return
        cost = pay = 0.0; dbl = 0
        for t in rows:
            p, c, s = settle(t); n = size_of(s)
            cost += c * n; pay += p * n; dbl += p > 1.5
        print(f"  {label:<46} n={len(rows):>4}  in ${cost:>11,.2f}  out ${pay:>11,.2f}"
              f"  profit ${pay - cost:>10,.2f}  {((pay / cost - 1) * 100 if cost else 0):>5.1f}%  doubled {dbl}")

    for src_label, src in (("REST (the desk's poll)", None), ("STREAM (fresh legs only)", "stream")):
        rows = [t for t in scored if (t.get("source") == "stream") == (src == "stream")]
        best = {}
        for t in rows:
            k = (t["game"], t["leg1"]["market_line"], t["leg2"]["market_line"])
            if k not in best or (t.get("displayed_size") or 0) > (best[k].get("displayed_size") or 0):
                best[k] = t
        uniq = list(best.values())
        print(f"\n{src_label}")
        show("A  every ticket, 1 contract", rows, lambda s: 1.0)
        show("B  one per distinct pair, 1 contract", uniq, lambda s: 1.0)
        show("C  one per distinct pair, FULL quoted size", uniq, lambda s: s)
    print("\n  The ONE untested assumption under every row: that displayed size fills at the quoted price.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-09-20"))
