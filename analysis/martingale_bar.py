"""The settlement loss is what a fair market predicts. There is no anomaly.

B's objection — that our net position is CREATED by the price path, since a
resting bid only fills when the mid comes down to it — has a quantitative
consequence that closes the question it was raised about.

THE BAR IS NOT ZERO
-------------------
Under a fair market the mid at the fill instant IS the market's expectation of
settlement. So for a bid filled at price `qp` while the mid is `m`:

    E[settlement P&L] = E[settlement] - qp = m - qp = capture

and our fill rule only fires once the mid has come down to our price, so
`capture <= 0` ALWAYS. **A passive quoter using a mid-cross fill rule has
negative expected settlement P&L in a perfectly fair market**, equal to the
overshoot of the mid past its quote. That is the null, and it is not zero.

MEASURED, on the 13,651 real fills of the 24-game classified export,
game-clustered:

    league   rows    games   capture (the bar)      settlement observed      residual
    CFB      7,396      11   -3.88 [-4.76, -2.99]   -2.44 [-5.05, +0.17]   +1.44 [-1.54, +4.42]
    WNBA     6,255      13   -2.30 [-2.46, -2.14]   -3.38 [-4.75, -2.01]   -1.07 [-2.51, +0.37]
    ALL     13,651      24   -3.15 [-3.74, -2.57]   -2.87 [-4.27, -1.46]   +0.29 [-1.36, +1.94]

**The residual is indistinguishable from zero, in each league separately and
pooled.** The settlement loss is fully accounted for by the fill rule's own
geometry under fair pricing. No directional accident, no moment selection, no
toxic flow is required to explain it — and at this sample size none of them
is detectable on top of it.

WHY THIS IS NOT UN-RETIRING CAPTURE
-----------------------------------
Capture remains useless for RANKING boards or widths: it is an identity
(= -overshoot), so any cross-board comparison of it reports tick geometry
rather than economics, and any gradient read off it is forced. That ruling
stands.

Being an identity is exactly what makes it the correct NULL here. We are not
using it to measure a strategy's quality; we are using it as the arithmetic
prediction that fair pricing makes for settlement P&L, and then asking whether
the realised settlement departs from it. It does not.

WHAT THIS MEANS, AND IT IS WORSE NEWS THAN AN ACCIDENT
------------------------------------------------------
A directional accident reverses; geometry does not. This says the losing is
structural and predictable: a passive quoter that only trades when the market
comes to it, and holds to a binary settlement, collects the overshoot as a
loss every time, in a fair market, forever. It is the quantitative form of
"v1 is not a market maker; it is a passive position accumulator with slightly
better entry prices than mid".

It also explains the shape that prompted the question:
  - positive markout to 300s      — the mid mean-reverts slightly after a dip
  - loss entirely beyond 300s     — the overshoot is only realised at settlement
  - no informedness gradient      — no informed counterparty is involved

★ THE SCOPE LIMIT: THIS DESCRIBES ONLY THE FILLS THE MODEL CAN BOOK
-------------------------------------------------------------------
`core/quote/engine.py:203` books a fill ONLY when `mid <= bid_price` (or
`mid >= ask_price`). So capture <= 0 holds on every row **by construction of
the instrument**, not as a fact about the market. Verified on all 38,465:
capture > 0 on ZERO rows, in both populations (phantom mean -1.872c, real
mean -3.154c).

The case that makes a maker money — a seller crosses the spread and lifts our
resting bid while the ask is still ABOVE it, so we bought below fair value —
**produces no row at all.** It is absent, not misclassified: the engine never
books it. (Phantoms are not that case either; they also have `mid <= B`.)

And the classifier is misaligned in the same direction. `ask <= B` compares
the current ask against our quote price, which was the best bid when we
quoted — so it fires only when the market has fallen by at least the
quote-time spread. That is SUFFICIENT for a real fill and NOT NECESSARY: a
transient aggressive sell can hit a resting bid without the ask ever coming
down. Had the engine booked such a fill, this criterion would have labelled
it PHANTOM.

So "real" selects sustained moves THROUGH our price and misses aggressive
orders AT our price. Those are different economics — being run over by a move
versus providing liquidity to a transient seller — and only the first is in
this dataset.

**Consequence for how this result may be quoted.** It is not evidence that
touch-joining loses. It is evidence that the half of the distribution the fill
rule can see must lose, and that its size is the overshoot. Whether the unseen
half is rare or merely unobserved cannot be settled here.

UNMEASURABLE ON THIS SUBSTRATE — 2026-09-04
--------------------------------------------
The discriminating test needs the venue's record of what actually traded.
`market_trade_stats` is NFL-ONLY: zero markets shared with
`shadow_quote_fills` ever, its whole history is 09-03/09-04, and even there
`captured_at - last_trade_at` runs median 5,788s (1.6h), p90 3.4 days. **No
trade data exists for any WNBA or CFB market at any time in this database.**

So not one fill in this study has ever been checked against a real trade.
Everything here — the separation, the -3.4c, this bar — is inference from the
recorded BOOK. That is a limit of the substrate, not of the arithmetic, and no
arithmetic on this substrate can close it.

Indirect evidence that the unseen case is genuinely rare rather than merely
invisible: the queue data (A2) puts us first in queue on 1.2% of cycles under
the price-identity gate, median 28 contracts ahead. A transient one-lot sell
would usually be absorbed by the size in front of us.

WHAT IT DOES NOT SHOW
---------------------
The residual CI is +-1.6c. A real mechanism worth up to ~1.5c/fill would be
invisible here. "No anomaly detected at n=24 games" is not "no anomaly".

The bar assumes mid = E[settlement]. At a crossing instant the book is
one-sided, so the mid may itself be a biased estimate — which is a reason the
residual could be non-zero in either direction, not a reason to trust it more.

The bar is also estimator-dependent. Simulated under a true martingale
(`martingale_null_simulation.py`), the POOLED estimator used here scores ~0,
while the mean-of-per-market-means scores -0.9c to -1.6c. "The bar is zero"
is true for this aggregation and is not automatic.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402


def _exports_dir():
    for base in [REPO, *Path(__file__).resolve().parents]:
        if (base / "backups/exports").is_dir():
            return base / "backups/exports"
    raise FileNotFoundError("backups/exports not found — run from the main "
                            "checkout, where the pinned exports live.")


EXPORT = "quote_fills_classified_20260904T142200Z.csv"


def bar_and_residual(real: pd.DataFrame) -> pd.DataFrame:
    """capture (the fair-market prediction), settlement, and the gap."""
    out = []
    for label, g in list(real.groupby("lg")) + [("ALL", real)]:
        rows = {"lg": label, "rows": len(g), "games": g.game_id.nunique()}
        for name, col in (("capture", g.capture), ("settle", g.pnl),
                          ("residual", g.pnl - g.capture)):
            cm = clustered_mean({k: list(v)
                                 for k, v in col.groupby(g.game_id)})
            rows[name] = cm.mean * 100
            rows[f"{name}_lo"], rows[f"{name}_hi"] = cm.lo * 100, cm.hi * 100
        out.append(rows)
    return pd.DataFrame(out)


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # THE NULL IS NOT ZERO. A fair market with our fill rule loses the
    # overshoot: construct fills whose settlement equals the mid exactly
    # (a perfectly fair, perfectly realised market) and confirm the
    # settlement P&L equals capture and is NEGATIVE, not zero.
    n = 400
    rng = np.random.default_rng(11)
    mid = rng.uniform(0.30, 0.70, n)
    over = rng.uniform(0.005, 0.04, n)          # mid overshoots our price
    qp = mid + over                              # bid filled above the mid
    df = pd.DataFrame({"lg": "T", "game_id": np.repeat(np.arange(20), 20),
                       "side": "bid", "qp": qp, "mid": mid,
                       "pnl": mid - qp})         # settlement == mid: fair
    df["capture"] = df["mid"] - df.qp
    t = bar_and_residual(df)
    row = t[t.lg == "ALL"].iloc[0]
    check(f"a perfectly fair market still loses ({row.capture:+.2f}c)",
          row.capture < -0.4)
    check("and the residual against the bar is exactly zero",
          abs(row.residual) < 1e-9)

    # a market that settles ABOVE the mid leaves a positive residual --
    # so the statistic can detect a departure, it is not degenerate
    df2 = df.copy()
    df2["pnl"] = df2.pnl + 0.02
    r2 = bar_and_residual(df2)
    r2 = r2[r2.lg == "ALL"].iloc[0]
    check(f"an injected +2c edge is recovered ({r2.residual:+.2f}c)",
          abs(r2.residual - 2.0) < 1e-6)
    return fails


def main() -> None:
    ex = _exports_dir()
    c = pd.read_csv(ex / EXPORT)
    c["lg"] = np.where(c.market_slug.str.contains("-wnba-"), "WNBA", "CFB")
    r = c[c["pop"] == "real"].copy()
    r["mid"] = (r.bb + r.ba) / 2.0
    r["capture"] = np.where(r.side == "bid", r["mid"] - r.qp,
                            r.qp - r["mid"])

    print(f"substrate: {EXPORT}")
    print(f"  real fills {len(r):,}  games {r.game_id.nunique()}\n")
    print("Under a fair market the mid at fill IS E[settlement], so the")
    print("prediction for settlement P&L is CAPTURE, not zero.\n")
    t = bar_and_residual(r)
    print(f"{'':5s} {'rows':>7s} {'gm':>4s} {'capture (the bar)':>24s} "
          f"{'settlement observed':>24s} {'RESIDUAL':>24s}")
    for x in t.itertuples():
        f = (f"{x.capture:+.2f} [{x.capture_lo:+.2f},{x.capture_hi:+.2f}]",
             f"{x.settle:+.2f} [{x.settle_lo:+.2f},{x.settle_hi:+.2f}]",
             f"{x.residual:+.2f} [{x.residual_lo:+.2f},{x.residual_hi:+.2f}]")
        print(f"{x.lg:5s} {x.rows:>7,} {x.games:>4d} {f[0]:>24s} {f[1]:>24s} "
              f"{f[2]:>24s}")

    a = t[t.lg == "ALL"].iloc[0]
    spans = a.residual_lo <= 0 <= a.residual_hi
    print(f"\npooled residual spans zero: {bool(spans)}")
    print("-> the settlement loss is what fair pricing predicts for this fill")
    print("   rule. No accident, selection or toxicity is REQUIRED to explain")
    print(f"   it, and none worth less than ~{max(abs(a.residual_lo), abs(a.residual_hi)):.1f}c/fill would be")
    print("   detectable on top of it at 24 games.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    main()
