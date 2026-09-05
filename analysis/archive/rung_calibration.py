"""Are far rungs priced above their settlement frequency? (favourite-longshot)

    .venv/bin/python analysis/rung_calibration.py [--selftest]
        [--ticks TICKS.csv.gz] [--resolved RESOLVED.csv]

PROVENANCE: this question fell out of a BUG. A flattening simulator that
leaned its ask unconditionally turned into "quote to get short" and printed
+$1,928 on a book whose baseline was −$212 (analysis/flattening_policy_sim.py,
fixed). The profit was an artifact of the wrong policy — but the mechanism it
exploited is an empirical claim about this venue that we have never tested:
on a ladder whose far rungs mostly expire worthless, are those rungs priced
ABOVE their realised settlement rate? That is the favourite-longshot bias,
among the most robust findings in sports betting markets, and it is
measurable on data we already own.

=======================================================================
THE PROHIBITION, WELDED TO THE QUESTION SO THEY CANNOT BE SEPARATED
=======================================================================
"SELL FAR RUNGS" IS THE SINGLE MOST RUIN-PRONE STRATEGY AVAILABLE TO US.
It has a positive mean and a catastrophic tail: a short at 0.03 collects
3c and can lose 97c, so one bad settlement erases hundreds of wins. Our
account is a $1,000 wallet with a STATED SURVIVAL CONDITION — precisely
the account that cannot survive one such settlement, and the measured
peak concurrent exposure (702 contracts, ~$702 arithmetic worst case at
unit size) says the book is already near its arithmetic capacity.

If this calibration comes back overpriced, the LEGITIMATE uses are:
  (a) OUR FV IS WRONG ABOUT TAILS and should be corrected — a modelling
      fix, not a position;
  (b) a QUOTING ADJUSTMENT on far rungs INSIDE an inventory-bounded book
      — skew the quote, never accumulate the exposure.
A NAKED SHORT-TAIL POSITION IS NOT A LEGITIMATE USE OF THIS FINDING, at
any measured edge, on this wallet. Nobody may cite this file's numbers in
support of one; the numbers and this paragraph travel together.
=======================================================================

METHOD: for each ladder market, take the mid at its FIRST two-sided LIVE
tick — early, before the game resolves the rung toward 0/1 — bucket by that
price, and compare the bucket's mean price against its realised settlement
rate. A well-calibrated board has price ≈ frequency on the diagonal;
favourite-longshot bias shows as realised BELOW price in the low buckets
(longshots overpriced) and realised ABOVE price in the high buckets
(favourites underpriced). Clustered by EVENT, since one game's rungs settle
together and are the opposite of independent.

IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING. One tape, 34 games.
**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

BANDS = [(0.0, .05), (.05, .15), (.15, .35), (.35, .65), (.65, .85),
         (.85, .95), (.95, 1.0)]


def band_of(p: float) -> str:
    for lo, hi in BANDS:
        if lo <= p < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "0.95-1.00"


def calibrate(mids: pd.DataFrame) -> pd.DataFrame:
    """mids: market_slug, event_slug, price, settlement -> per-band table."""
    m = mids.copy()
    m["band"] = m.price.map(band_of)
    rows = []
    for band, g in m.groupby("band"):
        vals = {e: list(v) for e, v in g.groupby("event_slug").settlement}
        cm = clustered_mean(vals)
        rows.append(dict(
            band=band, markets=len(g), events=g.event_slug.nunique(),
            mean_price=g.price.mean(), realised=g.settlement.mean(),
            gap=g.settlement.mean() - g.price.mean(),
            ci_lo=cm.lo if cm else float("nan"),
            ci_hi=cm.hi if cm else float("nan")))
    return pd.DataFrame(rows).sort_values("band")


def selftest() -> int:
    print("mutation test: the calibration instrument")
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    # A perfectly calibrated synthetic board: in the 0.00-0.05 band, 4% of
    # rungs settle 1 at a mean price of 0.04 -> gap ~0.
    rows = []
    for i in range(100):
        rows.append(dict(market_slug=f"m{i}", event_slug=f"e{i % 10}",
                         price=0.04, settlement=1 if i < 4 else 0))
    tab = calibrate(pd.DataFrame(rows))
    r = tab[tab.band == "0.00-0.05"].iloc[0]
    check("calibrated board reads gap ~0", abs(r.gap) < 1e-9)

    # Overpriced longshots: same 0.04 price, only 1% settle -> gap -0.03
    rows2 = [dict(market_slug=f"m{i}", event_slug=f"e{i % 10}", price=0.04,
                  settlement=1 if i < 1 else 0) for i in range(100)]
    r2 = calibrate(pd.DataFrame(rows2))
    r2 = r2[r2.band == "0.00-0.05"].iloc[0]
    check("overpriced longshots read a NEGATIVE gap (realised < price)",
          abs(r2.gap + 0.03) < 1e-9)

    check("bands are exhaustive and half-open",
          [band_of(x) for x in (0.0, .05, .5, .95, 1.0)]
          == ["0.00-0.05", "0.05-0.15", "0.35-0.65", "0.95-1.00",
              "0.95-1.00"])
    print(f"mutation test: "
          f"{'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=Path)
    ap.add_argument("--resolved", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.ticks is None or args.resolved is None:
        print("need --ticks and --resolved")
        return 2
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    mids = con.execute(f"""
        WITH first_tick AS (
          SELECT market_slug, any_value(event_slug) event_slug,
                 arg_min((best_bid + best_ask) / 2.0, captured_at) price
          FROM read_csv('{args.ticks}')
          WHERE is_live AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          GROUP BY market_slug
        ), res AS (
          SELECT market_slug, any_value(settlement) settlement
          FROM read_csv('{args.resolved}')
          WHERE settlement IS NOT NULL GROUP BY market_slug
        )
        SELECT f.*, r.settlement FROM first_tick f JOIN res r USING (market_slug)
    """).df()

    print("\n=== RUNG CALIBRATION — price vs realised settlement rate ===")
    print(f"markets: {len(mids)} across {mids.event_slug.nunique()} events "
          f"(price = mid at each rung's FIRST two-sided live tick)")
    tab = calibrate(mids)
    print(tab.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print("\ngap = realised − price. NEGATIVE in the low bands means "
          "longshots settle LESS often than their price implies, i.e. they "
          "are OVERPRICED — the favourite-longshot signature. CIs are on "
          "the realised rate, clustered by EVENT (one game's rungs settle "
          "together).")

    low = mids[mids.price < 0.15]
    if len(low):
        vals = {e: list(v) for e, v in low.groupby("event_slug").settlement}
        cm = clustered_mean(vals)
        print(f"\npooled low tail (<0.15): {len(low)} rungs, mean price "
              f"{low.price.mean():.4f}, realised "
              f"{low.settlement.mean():.4f}"
              + (f" [{cm.lo:.4f}, {cm.hi:.4f}] clustered, G={cm.n_clusters}"
                 if cm else ""))

    print("""
=======================================================================
READ THIS BEFORE CITING ANY NUMBER ABOVE
=======================================================================
Even if the low bands are overpriced, "SELL FAR RUNGS" REMAINS THE MOST
RUIN-PRONE STRATEGY AVAILABLE TO US: positive mean, catastrophic tail, on
a $1,000 wallet with a stated survival condition and a measured peak
exposure already near its arithmetic capacity. The legitimate uses are
(a) correcting our FV's tail behaviour, and (b) a quoting adjustment on
far rungs inside an inventory-bounded book. A naked short-tail position
is not one of them at any measured edge, and no number in this file may
be cited in support of one.

Confounds carried: the first-live-tick price is an opening mark, not a
closing line, so this measures the board AS FIRST QUOTED; a settled rung
is one that existed to be quoted (survivorship, though ladders are seeded
before tip); and 34 games is a small board with rungs correlated inside
each game, which is why every interval is event-clustered.
=======================================================================
No in-sample result justifies capital. The forward test is the evidence.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
