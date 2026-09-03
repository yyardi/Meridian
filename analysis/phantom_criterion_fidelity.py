"""How well does the PHANTOM CRITERION hold against real resting orders?

WHY THIS IS A COMMITTED ARTIFACT AND NOT A SCRATCH SCRIPT
---------------------------------------------------------
The phantom finding (63.9% of v1's shadow fills are fills our own presence
would have prevented) rests on a MODEL of venue mechanics, not on an
observation:

    a resting bid at B forces the public best_bid >= B, so the mid cannot
    reach B while the ask stays above it.

The COUNT of fills satisfying `mid <= B while ask > B` is arithmetic on the
tape, and an independently written query reproduces it exactly. That
validates the implementation. It cannot validate the assumption, because
both queries share it. If the venue does not behave this way, both are
wrong together — and this is the part nobody measured.

This file is the only check we have on the assumption itself: real orders
that really rested, and whether the book ever did the impossible while they
were live.

THE UNIT MATTERS MORE THAN THE NUMBER, which is why both are reported here
and neither is reported alone. The same two events give:

    per-ORDER (order had >= 1 violating tick)   2/25    = 8.0%
    per-TICK  (individual violating observation) 2/36369 = 0.0055%

Per-order is the right unit for DATING AN ORDER'S DEATH — it answers "did
this order's window contain a glitch", which is what the liveness witness
needed and what the run-length calibration below is for. Per-tick is the
unit comparable to phantom classification, which is applied at individual
fill events. Quoting the per-order rate as the criterion's error rate
overstates it by three orders of magnitude, and in the conservative-looking
direction that survives review. It has already happened once.

DO NOT PUT A PERCENTAGE FROM THIS FILE NEXT TO 63.9%. Any number placed
there reads as a measured error rate on the phantom share, and none of
these are that. Three reasons, each sufficient on its own:

  1. Ticks are not independent — 36,369 of them inside 25 orders, and
     violations cluster within an order. The real uncertainty is governed
     by n=25, not n=36,369, so the tight per-tick CI is an illusion.
  2. The sample is CONDITIONED ON EXECUTION. These orders come from
     passive-execution trade activities, so every one of them filled.
     Orders that rested and never traded are structurally absent — and
     those are exactly where a stale or mis-modelled book is most likely.
  3. n=25, all BUY. This BOUNDS the instrument; it does not measure it.

The honest summary is qualitative: supportive and thin.

WHAT WOULD ACTUALLY SETTLE IT: the operator's resting-order probe. It is
the only instrument that can falsify the phantom finding. If real orders
sit at the touch while the mid crosses through them, 63.9% is wrong and
everything resting on it moves.
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _exports_dir():
    for base in [REPO, *Path(__file__).resolve().parents]:
        if (base / "backups/exports").is_dir():
            return base / "backups/exports"
    raise FileNotFoundError("backups/exports not found — run from the main "
                            "checkout, where the pinned exports live.")


EX = _exports_dir()
ACTIVITIES = EX / "venue_activities_20260826T040141Z.json"
OUR_INTENTS = {"ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_LONG",
               "ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_SHORT"}
R_GRID = (1, 2, 3, 5, 10, 20)


def violation_runs(ticks: pd.DataFrame) -> pd.DataFrame:
    """Lengths of consecutive violating ticks, per order.

    ticks: columns fid, viol (0/1), pre-sorted by (fid, captured_at).
    """
    runs = []
    for fid, g in ticks.groupby("fid", sort=False):
        cur = 0
        for x in g.viol.values:
            if x:
                cur += 1
            elif cur:
                runs.append((fid, cur))
                cur = 0
        if cur:
            runs.append((fid, cur))
    return pd.DataFrame(runs, columns=["fid", "len"])


def rates(ticks: pd.DataFrame) -> dict:
    """BOTH units, always together. A rate is a pair; returning only one
    discards the half the next reader will supply from their own question.
    """
    n_ord = ticks.fid.nunique()
    viol_ord = ticks.groupby("fid").viol.max().sum()
    return {
        "orders": int(n_ord),
        "ticks": int(len(ticks)),
        "orders_with_violation": int(viol_ord),
        "violating_ticks": int(ticks.viol.sum()),
        "per_order": float(viol_ord / n_ord) if n_ord else float("nan"),
        "per_tick": float(ticks.viol.mean()) if len(ticks) else float("nan"),
    }


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # THE UNIT CONFUSION, ENCODED. One order violates on 50 of its 100
    # ticks; nine orders never violate. Per-order says 10% of orders were
    # affected. Per-tick says 5% of observations were. Both true, three
    # orders of magnitude apart in the general case, and only one of them
    # is comparable to a per-fill classification.
    rows = []
    for fid in range(10):
        for i in range(100):
            rows.append((fid, 1 if (fid == 0 and i < 50) else 0))
    t = pd.DataFrame(rows, columns=["fid", "viol"])
    r = rates(t)
    check("per-order and per-tick are computed distinctly",
          abs(r["per_order"] - 0.10) < 1e-9 and abs(r["per_tick"] - 0.05) < 1e-9)
    check("neither rate can be derived from the other without the counts",
          r["orders"] == 10 and r["ticks"] == 1000
          and r["orders_with_violation"] == 1 and r["violating_ticks"] == 50)

    # run lengths: one run of 50, not 50 runs of 1
    runs = violation_runs(t)
    check("consecutive violations form ONE run, not many",
          len(runs) == 1 and int(runs.len.iloc[0]) == 50)

    # split runs are counted separately
    t2 = pd.DataFrame({"fid": [0] * 6, "viol": [1, 1, 0, 0, 1, 0]})
    r2 = violation_runs(t2)
    check("a gap splits a run", sorted(r2.len) == [1, 2])

    # a run that reaches the end of an order's window is still counted
    t3 = pd.DataFrame({"fid": [0] * 4, "viol": [0, 0, 1, 1]})
    check("a run open at the window's end is counted",
          len(violation_runs(t3)) == 1
          and int(violation_runs(t3).len.iloc[0]) == 2)
    return fails


def load_orders() -> pd.DataFrame:
    """Our real passive BUY orders, with their rest windows."""
    rows = []
    for page in json.load(open(ACTIVITIES))["pages"]:
        for a in page.get("activities") or []:
            if a.get("type") != "ACTIVITY_TYPE_TRADE":
                continue
            ex = (a.get("trade") or {}).get("passiveExecution")
            if not isinstance(ex, dict):
                continue
            o = ex.get("order") or {}
            if o.get("intent") not in OUR_INTENTS or o.get("side") != "ORDER_SIDE_BUY":
                continue
            px = (o.get("price") or {}).get("value")
            rows.append(dict(
                slug=o.get("marketSlug"), price=float(px) if px else None,
                ins=o.get("insertTime") or o.get("createTime"),
                tr=ex.get("transactTime") or o.get("lastTransactTime")))
    f = pd.DataFrame(rows).dropna(subset=["price"])
    for c in ("ins", "tr"):
        f[c] = pd.to_datetime(f[c], utc=True, format="mixed", errors="coerce")
    return f.dropna(subset=["ins", "tr"]).reset_index(drop=True)


def main() -> None:
    f = load_orders()
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    con.execute(f"""CREATE TEMP TABLE tk AS SELECT * FROM (
        SELECT market_slug, captured_at, best_bid
          FROM read_csv('{EX}/live_ticks_pulse_games_20260901T195202Z.csv.gz')
        UNION ALL SELECT column00, column05, column06
          FROM read_csv('{EX}/eval_market_snapshots.csv.gz', header=false)
        UNION ALL SELECT column00, column05, column06
          FROM read_csv('{EX}/delta_market_snapshots.csv.gz', header=false)
        UNION ALL SELECT market_slug, captured_at, best_bid
          FROM read_csv('{EX}/live_snapshots_since0820.csv.gz')
      ) WHERE best_bid IS NOT NULL""")
    con.register("f", f.reset_index(names="fid"))
    t = con.execute("""
      SELECT f.fid, t.captured_at, t.best_bid, f.price,
             CASE WHEN t.best_bid < f.price - 1e-9 THEN 1 ELSE 0 END AS viol
      FROM f JOIN tk t ON t.market_slug = f.slug
       AND t.captured_at >= f.ins AND t.captured_at <= f.tr
      ORDER BY f.fid, t.captured_at
    """).df()

    r = rates(t)
    print("=== CRITERION FIDELITY: real resting BUY orders vs the book ===")
    print(f"orders with tape in their rest window : {r['orders']}")
    print(f"ticks examined                        : {r['ticks']:,}")
    print(f"orders with >= 1 violating tick       : {r['orders_with_violation']}")
    print(f"violating ticks                       : {r['violating_ticks']}")
    print(f"\n  per-ORDER {r['orders_with_violation']}/{r['orders']} = "
          f"{r['per_order']:.3%}   <- unit for DATING AN ORDER'S DEATH")
    print(f"  per-TICK  {r['violating_ticks']}/{r['ticks']} = "
          f"{r['per_tick']:.4%}  <- unit comparable to per-fill classification")
    print("\n  Both describe the same events. Quoting the per-order rate as")
    print("  the criterion's error rate overstates it ~"
          f"{r['per_order']/r['per_tick']:.0f}x.")

    runs = violation_runs(t)
    print(f"\nviolating RUNS: {len(runs)} across "
          f"{runs.fid.nunique() if len(runs) else 0} orders")
    if len(runs):
        print(f"  run length: min {runs.len.min()} median "
              f"{runs.len.median():.0f} max {runs.len.max()}")
    print("\n=== RUN-LENGTH CALIBRATION (for the liveness witness only) ===")
    print(f"{'R (ticks)':>10s} {'orders with run >= R':>22s} {'FP/order':>10s}")
    for R in R_GRID:
        hit = runs[runs.len >= R].fid.nunique() if len(runs) else 0
        print(f"{R:>10d} {hit:>22d} {hit/r['orders']:>9.1%}")
    print("\nThese runs are SPURIOUS by construction: every tick occurred")
    print("while the order was nominally still resting, so any run >= R")
    print("would be a wrongly-dated death.")

    print("\n=== WHAT THIS DOES AND DOES NOT SUPPORT ===")
    print("Supports: the phantom criterion was not contradicted at the tick")
    print("  level by the real resting orders we can see.")
    print("Does NOT support: any error rate on the 63.9% phantom share.")
    print(f"  n={r['orders']} orders, all BUY, ALL OF WHICH FILLED (drawn from")
    print("  passive executions), ticks clustered within orders. This bounds")
    print("  the instrument; it does not measure the criterion.")
    print("Settles it: the operator's resting-order probe, which is the only")
    print("  instrument that can FALSIFY the phantom finding.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    main()
