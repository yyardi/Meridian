"""The MONEY scorer — the code behind +4.761pp, which was never committed.

**This is the gap ce found and it was mine.** The +6.880 / +4.761 / +10.857pp
figures were computed in ad-hoc shell heredocs and reported in messages; the
only committed scorer was `analysis/pulse_branch_scoring.py`, which is a BRIER
scorer ("Brier(market) − Brier(model)", line 81). Anyone auditing the ladder
found the Brier file, correctly concluded the arithmetic did not support a
money claim, and had no way to check the actual computation.

**The figures are money.** This file is that computation, committed so it can be
anchor-checked rather than taken on my word.

## The statistic

Per filled entry, in probability points == cents per contract at $1 notional:

    side == 'yes'  (bought YES at the bid)   pnl = settlement − limit_price
    side == 'no'   (sold  YES at the ask)    pnl = limit_price − settlement

`limit_price` is on the **YES scale for both sides** — verified: it equals
`market_bid` on 100.0% of yes entries and `market_ask` on 100.0% of no entries,
and correlates +0.995 with the YES mid on each arm. There is no squaring
anywhere; this is linear in the edge, which is the whole reason the money route
costs 58 games where the Brier route costs 15,400.

## Why the distinction is load-bearing

Brier is **quadratic** in edge, so edge resolution scales 1/G^(1/4) and 2.69pp
needs ~15,400 games. Money is **linear**, so it scales 1/G^(1/2) and the same
target needs ~182. **If these figures were Brier the ladder would collapse.**
They are not, and this file is the proof.

## Population and estimator, pinned

* `action == 'enter'` AND `filled_at.notna()` — 1,944 of 2,974. The withdrawn
  arm is excluded and must stay excluded: it never traded, so its P&L is a
  counterfactual at a price the market left.
* No dedupe. Every fill is a distinct trade with real money on it; deduping
  discards realised P&L. (This differs from the Brier scorer deliberately —
  there, repeated rows are one opinion logged many times.)
* `clustered_mean`: cluster-robust sandwich on per-row P&L, t at df = G−1,
  clusters are games. Row-weighted, so a 146-fill game contributes more money
  than a 1-fill game. Game-weighted is the defensible alternative and gives
  +2.451pp / 260 games; it is reported alongside.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

DECISIONS = "backups/exports/pulse_decisions_20260906T174104Z.csv.gz"
OUTCOMES = "backups/exports/resolved_outcomes_20260901T195202Z.csv"


def load() -> pd.DataFrame:
    d = pd.read_csv(DECISIONS)
    r = (pd.read_csv(OUTCOMES)[["market_slug", "settlement"]]
         .rename(columns={"settlement": "y"}).drop_duplicates("market_slug"))
    d = d.merge(r, on="market_slug", how="left")
    d["s"] = d.side.astype(str).str.lower()
    # MONEY, not Brier: a signed price difference, never a squared error.
    d["pnl"] = np.where(d.s.eq("yes"), d.y - d.limit_price, d.limit_price - d.y)
    return d[(d.action == "enter") & d.y.notna()].copy()


def score(frame: pd.DataFrame):
    c = clustered_mean({k: v.tolist() for k, v in frame.groupby("game_id").pnl})
    return c, (c.hi - c.lo) / 2


def main() -> int:
    E = load()
    F = E[E.filled_at.notna()]
    print("=== MONEY per filled contract (probability points = cents at $1) ===")
    print("    pnl = y − limit_price  (bought YES) | limit_price − y  (sold YES)")
    print("    no squaring anywhere — linear in edge, unlike Brier\n")
    for lbl, f in (("ALL entries (incl. never-traded)", E),
                   ("FILLED only  <- the figure", F),
                   ("WITHDRAWN (counterfactual, excluded)", E[E.filled_at.isna()])):
        c, hw = score(f)
        flag = "SPANS ZERO" if c.lo <= 0 <= c.hi else "excludes 0"
        print(f"  {lbl:38s} n {len(f):>5,} G {c.n_clusters:>2}  "
              f"{c.mean*100:+7.3f}pp [{c.lo*100:+7.3f}, {c.hi*100:+7.3f}]  "
              f"hw {hw*100:5.3f}  {flag}")

    c, hw = score(F)
    print(f"\n=== THE LADDER, G = {c.n_clusters} x (hw / target)^2 ===")
    for lbl, t in (("current point", abs(c.mean)), ("taker bar 2.69pp", 0.0269),
                   ("2.00pp", 0.02), ("1.00pp", 0.01)):
        print(f"  {lbl:>18} {c.n_clusters*(hw/t)**2:>8,.0f} games")

    g = F.groupby("game_id").pnl.mean()
    c2 = clustered_mean({k: [v] for k, v in g.items()})
    hw2 = (c2.hi - c2.lo) / 2
    print(f"\n  estimand alternative — GAME-WEIGHTED {c2.mean*100:+.3f}pp "
          f"-> {c2.n_clusters*(hw2/abs(c2.mean))**2:,.0f} games (4.5x)")

    print("\n=== SANITY: this is not Brier ===")
    F2 = F.copy()
    F2["mid"] = (F2.market_bid + F2.market_ask) / 2
    br = ((F2["mid"] - F2.y) ** 2 - (F2.fair_value - F2.y) ** 2).mean()
    print(f"  Brier(mkt) − Brier(model) on the same rows: {br:+.5f}  (dimensionless)")
    print(f"  money per contract:                         {c.mean:+.5f}  (price units)")
    print("  Different quantities, different units, different scaling laws.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
