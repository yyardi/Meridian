"""Does PULSE beat the price it is betting against?

Not assigned — it follows from meridian-ce's architectural finding that
`predictions.features` carries eight keys and none of them is score, clock or
possession. If PULSE is a pregame model quoted against a live market, the
comparison everyone has been waiting for can be run on the export already in
hand, and it must be cut by horizon rather than pooled.

All comparisons are game-clustered (`clustered_mean`, clusters are games,
df = G−1). v4 only — the README forbids pooling model versions.

## ★ 1. PULSE DOES NOT BEAT THE MARKET

    Brier(market) − Brier(model) = −0.00700  [−0.01222, −0.00178]   G = 83
    Brier(model)  0.19683      Brier(market) 0.18983

Negative means the market is better, and the interval excludes zero. By horizon
to resolution, the market wins wherever there is power:

    2.5–6h      −0.00569 [−0.0109, −0.0005]   MARKET
    6–24h       −0.00423 [−0.0073, −0.0012]   MARKET
    1–3 days    −0.00954 [−0.0170, −0.0020]   MARKET
    3+ days     +0.00311 [−0.0163, +0.0225]   tie (thinnest market, widest CI)

## ★ 2. THERE ARE NO IN-GAME PREDICTIONS AT ALL

Hours from prediction to resolution: **p5 = 7.7**, median 27.7. Nothing below
2.5 hours in any quantity. So the architecture finding is confirmed from the
data side rather than from the schema alone: **PULSE never predicts during a
game.** The "stale pregame model against a live market" concern is real in
principle and simply does not arise here, because PULSE is not quoted live.

This also closes the sigma question for good. A per-observation σ should track
remaining game uncertainty; PULSE has no in-game observations for it to track.

## ★ 3. THE ENTRY GATE DOES REAL WORK, AND NOT THE WORK YOU WOULD EXPECT

    actionable   n 96,027 (52.3%)   diff −0.00353 [−0.00616, −0.00090]
    declined     n 87,511 (47.7%)   diff −0.01080 [−0.01987, −0.00173]
    paired within game (actionable − declined)
                                    +0.00816 [−0.00000, +0.01633]   BORDERLINE

The gate declines the model's **largest** disagreements — mean |edge| 0.0715 on
declined against 0.0360 on actionable — and those are exactly where the model
is worst. **A big model-vs-market gap is evidence of a stale model, not of an
edge**, and the gate is already acting on that.

The paired interval's lower bound sits at −0.00000, so this is borderline and
is reported as borderline. It is the first measurement of the declined branch,
which was structurally invisible before this export.

## The trap this file walks around

`is_actionable` is a **'t'/'f' string**, not a boolean. Comparing it to `True`
selects nothing and returns a clean empty result — the same shape as the
`is_live` trap on the QUOTE tape.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

EXPORT = "backups/exports/pulse_predictions_20260904T183000Z.csv.gz"
HORIZONS = [(0, 2.5, "in-game / <2.5h"), (2.5, 6, "2.5-6h"), (6, 24, "6-24h"),
            (24, 72, "1-3 days"), (72, 1e9, "3+ days out")]


def load() -> pd.DataFrame:
    d = pd.read_csv(EXPORT)
    d = d[d.model_version == "v4"].copy()
    for c in ("predicted_at", "resolved_at"):
        d[c] = pd.to_datetime(d[c], utc=True, format="ISO8601", errors="coerce")
    d["h_to_res"] = (d.resolved_at - d.predicted_at).dt.total_seconds() / 3600.0
    # 't'/'f' STRING, not a boolean — comparing to True selects nothing.
    d["act"] = d.is_actionable.astype(str).str.lower().isin(("true", "t", "1"))
    d["b_model"] = (d.model_probability - d.settlement) ** 2
    d["b_mkt"] = (d.market_mid - d.settlement) ** 2
    d["b_diff"] = d.b_mkt - d.b_model          # positive = model beats market
    return d


def cm(frame: pd.DataFrame, col: str):
    return clustered_mean({k: v.tolist() for k, v in frame.groupby("game_id")[col]})


def verdict(r) -> str:
    return "MODEL" if r.lo > 0 else ("MARKET" if r.hi < 0 else "tie")


def main() -> int:
    d = load()
    print(f"v4: {len(d):,} rows | {d.game_id.nunique()} games | "
          f"{d.market_slug.nunique()} markets\n")

    r = cm(d, "b_diff")
    print("=" * 72)
    print("1. DOES PULSE BEAT THE PRICE IT IS BETTING AGAINST?")
    print("=" * 72)
    print(f"  Brier(model) {cm(d,'b_model').mean:.5f}   "
          f"Brier(market) {cm(d,'b_mkt').mean:.5f}")
    print(f"  difference   {r.mean:+.5f} [{r.lo:+.5f}, {r.hi:+.5f}]  G={r.n_clusters}"
          f"   -> {verdict(r)}")

    print("\n  by horizon to resolution (pooling mixes different comparisons):")
    h = d[d.h_to_res.notna() & (d.h_to_res >= 0)]
    print(f"  {'bucket':>18} {'n':>7} {'G':>4} {'diff':>10} {'95% CI':>22}")
    for lo, hi, lbl in HORIZONS:
        s = h[(h.h_to_res >= lo) & (h.h_to_res < hi)]
        if len(s) < 200:
            print(f"  {lbl:>18} {len(s):>7,}   -- too few rows to report --")
            continue
        rr = cm(s, "b_diff")
        print(f"  {lbl:>18} {len(s):>7,} {s.game_id.nunique():>4} {rr.mean:>+10.5f} "
              f"[{rr.lo:+.4f}, {rr.hi:+.4f}] {verdict(rr)}")

    print("\n" + "=" * 72)
    print("2. THERE ARE NO IN-GAME PREDICTIONS")
    print("=" * 72)
    q = h.h_to_res.quantile([.01, .05, .5, .95])
    print(f"  hours to resolution: p1 {q[.01]:.1f}  p5 {q[.05]:.1f}  "
          f"median {q[.5]:.1f}  p95 {q[.95]:.1f}")
    print(f"  rows under 2.5h: {(h.h_to_res < 2.5).sum():,} "
          f"({(h.h_to_res < 2.5).mean()*100:.2f}%)")
    print("  PULSE is a pregame model and is never quoted live, so there is no")
    print("  in-game state for a per-observation sigma to track. That closes the")
    print("  sigma question rather than deferring it to a better export.")

    print("\n" + "=" * 72)
    print("3. THE ENTRY GATE — and it declines the LARGEST edges")
    print("=" * 72)
    for lbl, s in (("actionable", d[d.act]), ("declined", d[~d.act])):
        rr = cm(s, "b_diff")
        print(f"  {lbl:11s} n {len(s):>7,} ({len(s)/len(d)*100:4.1f}%)  "
              f"diff {rr.mean:+.5f} [{rr.lo:+.5f}, {rr.hi:+.5f}]  "
              f"mean |edge| {s.edge.abs().mean():.4f}")
    p = d.groupby(["game_id", "act"]).b_diff.mean().unstack().dropna()
    if {True, False} <= set(p.columns):
        diff = p[True] - p[False]
        rr = clustered_mean({g: [v] for g, v in diff.items()})
        print(f"  paired within game (actionable − declined) {rr.mean:+.5f} "
              f"[{rr.lo:+.5f}, {rr.hi:+.5f}]  G={rr.n_clusters}")
        print(f"  -> {'gate selects better' if rr.lo > 0 else 'BORDERLINE — lower bound at zero' if abs(rr.lo) < 1e-4 else 'indistinguishable from random selection'}")
    print("  A large model-vs-market gap is evidence of a stale model, not of an")
    print("  edge — and the gate is already acting on that.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
