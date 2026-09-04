"""Were the vanished bids CONSUMED or CANCELLED? The direct volume test.

Runs the design pinned in docs/math/volume-test-predeclaration.md (+ Amendment
1). Nothing here may deviate from that document; if it must, the document gets
another appended amendment with its reason.

THE QUESTION. In the phantom-bid population the queue beneath our quote
vanished. Consumed (sellers traded through — a real resting order would likely
have filled, the case the fill rule cannot book) or cancelled (quotes pulled,
no trade, a true phantom)?

WHAT IS PRE-DECLARED AND MUST NOT DRIFT:
  unit       the real poll interval (Amendment 1a), NOT a synthetic grid
  N          402 treatment cells expected, clustered in 11 games
  baseline   same-market cells matched on bid-fall magnitude, game phase,
             and interval duration (Amendment 1b)
  B          best_bid at interval start, identically in BOTH arms
  primary    last_trade_at inside the interval AND last_trade_px <= B
  secondary  shares_traded delta > 0, reported beside the primary, never alone
  asymmetry  a positive is strong; a null may be reported ONLY as "not
             detectable at this cadence", never as "no consumption occurred"
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


TRADES = "cfb_trade_stats_20260904T161500Z.csv"
FILLS = "quote_fills_classified_20260904T142200Z.csv"

FALL_BINS = [-np.inf, 0.0000001, 0.01, 0.02, 0.04, np.inf]
DUR_BINS = [0, 180, 260, 400, np.inf]


def build_intervals(d: pd.DataFrame) -> pd.DataFrame:
    """Consecutive STATS-BEARING polls per market. NULL blocks are skipped,
    never read as zero volume — the skip is why duration must be matched."""
    s = d[d.shares_traded.notna()].sort_values(
        ["market_slug", "captured_at"]).copy()
    g = s.groupby("market_slug")
    s["t0"] = g.captured_at.shift(1)
    s["sh0"] = g.shares_traded.shift(1)
    s["bb0"] = g.best_bid.shift(1)
    iv = s[s.t0.notna()].copy()
    iv["dur"] = (iv.captured_at - iv.t0).dt.total_seconds()
    iv["dsh"] = iv.shares_traded - iv.sh0
    iv["bid_fall"] = iv.bb0 - iv.best_bid           # positive = bid fell
    iv["B"] = iv.bb0                                # pinned: touch at start
    iv["print_inside"] = ((iv.last_trade_at > iv.t0)
                          & (iv.last_trade_at <= iv.captured_at))
    iv["print_at_or_below_B"] = iv.print_inside & (
        iv.last_trade_px <= iv.B + 1e-9)
    return iv


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    t = pd.Timestamp("2026-09-04T00:00:00Z")
    d = pd.DataFrame({
        "market_slug": ["m"] * 4,
        "captured_at": [t, t + pd.Timedelta(seconds=200),
                        t + pd.Timedelta(seconds=400),
                        t + pd.Timedelta(seconds=600)],
        "shares_traded": [100.0, np.nan, 150.0, 150.0],
        "best_bid": [0.50, 0.49, 0.47, 0.47],
        "last_trade_px": [0.60, np.nan, 0.48, 0.99],
        "last_trade_at": [t - pd.Timedelta(seconds=50), pd.NaT,
                          t + pd.Timedelta(seconds=300),
                          t - pd.Timedelta(seconds=10)],
    })
    iv = build_intervals(d)
    # the NULL row is skipped, so the surviving interval spans 400s not 200s
    check("a NULL stats block is skipped, not read as zero volume",
          len(iv) == 2 and abs(iv.dur.iloc[0] - 400.0) < 1e-9)
    check("delta is taken across the skip (150-100=50), not against NULL",
          abs(iv.dsh.iloc[0] - 50.0) < 1e-9)
    # print at 0.48 <= B=0.50 and inside (0s, 400s] -> counts
    check("a print inside the interval at/below B counts",
          bool(iv.print_at_or_below_B.iloc[0]))
    # last interval: print is BEFORE t0, so must not count even though px high
    check("a print predating the interval never counts",
          not bool(iv.print_inside.iloc[1]))

    # a print inside but ABOVE B must not count for the primary
    d2 = d.copy()
    d2.loc[2, "last_trade_px"] = 0.90
    iv2 = build_intervals(d2)
    check("a print inside but ABOVE B fails the primary",
          bool(iv2.print_inside.iloc[0])
          and not bool(iv2.print_at_or_below_B.iloc[0]))
    return fails


def main() -> None:
    ex = _exports_dir()
    d = pd.read_csv(ex / TRADES, parse_dates=["captured_at", "last_trade_at"])
    iv = build_intervals(d)

    c = pd.read_csv(ex / FILLS, parse_dates=["filled_at"])
    c = c[(~c.market_slug.str.contains("-wnba-")) & (c.regime == "ingame")]
    c = c[(c["pop"] == "phantom") & (c.side == "bid")].copy()
    c["ask_q"] = c.m_q + c.s_q / 2
    fills = c[(c.ba - c.ask_q).abs() <= 0.01]
    print(f"ask-unmoved phantom BID fills: {len(fills):,} "
          f"in {fills.game_id.nunique()} games")

    # assign each fill to its containing poll interval
    iv = iv.sort_values(["market_slug", "captured_at"]).reset_index(drop=True)
    iv["ivid"] = np.arange(len(iv))
    hit = set()
    by_mkt = {m: g for m, g in iv.groupby("market_slug", sort=False)}
    for m, fg in fills.groupby("market_slug", sort=False):
        g = by_mkt.get(m)
        if g is None:
            continue
        idx = np.searchsorted(g.captured_at.values, fg.filled_at.values,
                              side="left")
        for i, ft in zip(idx, fg.filled_at.values):
            if i < len(g) and ft > g.t0.values[i]:
                hit.add(int(g.ivid.values[i]))
    iv["treat"] = iv.ivid.isin(hit)

    print(f"treatment cells: {int(iv.treat.sum()):,} "
          f"(pre-declared expectation ~402)")
    print(f"candidate control cells (same markets): "
          f"{int((~iv.treat & iv.market_slug.isin(fills.market_slug)).sum()):,}")

    # strata: bid-fall magnitude x duration x game phase, within market
    pool = iv[iv.market_slug.isin(fills.market_slug)].copy()
    pool["fall_b"] = pd.cut(pool.bid_fall, FALL_BINS, labels=False)
    pool["dur_b"] = pd.cut(pool.dur, DUR_BINS, labels=False)
    ph = pool.groupby("game_id").captured_at
    lo, hi = ph.transform("min"), ph.transform("max")
    frac = (pool.captured_at - lo) / (hi - lo).replace(pd.Timedelta(0),
                                                       pd.Timedelta(seconds=1))
    pool["phase_b"] = np.clip((frac * 3).astype(int), 0, 2)
    keys = ["market_slug", "fall_b", "dur_b", "phase_b"]

    strata = pool.groupby(keys, dropna=False).treat.agg(["sum", "count"])
    usable = strata[(strata["sum"] > 0) & (strata["count"] > strata["sum"])]
    pool = pool.merge(usable.reset_index()[keys], on=keys, how="inner")
    t_arm, c_arm = pool[pool.treat], pool[~pool.treat]
    print(f"\nafter exact matching on market x bid-fall x duration x phase:")
    print(f"  usable strata {len(usable):,}   treatment {len(t_arm):,}   "
          f"control {len(c_arm):,}   games {pool.game_id.nunique()}")
    if not len(t_arm) or not len(c_arm):
        print("  no matched comparison possible — reporting nothing further")
        return

    print("\n=== BALANCE, POOLED (this is NOT the estimator — see below) ===")
    for col, lab in (("bid_fall", "bid fall"), ("dur", "duration s")):
        print(f"  {lab:12s} treat median {t_arm[col].median():>8.3f}   "
              f"control median {c_arm[col].median():>8.3f}")
    print("  Pooled arms differ in stratum COMPOSITION, so pooled rates are")
    print("  confounded by it. Matching means comparing WITHIN stratum; the")
    print("  estimator below does that and the pooled figures are diagnostic.")

    print("\n=== COUNTS BEFORE RATIOS ===")
    for name, arm in (("treatment", t_arm), ("control", c_arm)):
        print(f"  {name:10s} n={len(arm):>6,}  "
              f"print_at_or_below_B={int(arm.print_at_or_below_B.sum()):>5,}  "
              f"any_volume={int((arm.dsh > 0).sum()):>6,}")

    # STRATIFIED estimator: each treatment cell is compared against its OWN
    # stratum's control rate, so stratum composition cannot leak in. Game
    # clustering is applied to the per-cell excesses.
    pool["vol"] = (pool.dsh > 0).astype(float)
    pool["prim"] = pool.print_at_or_below_B.astype(float)
    print("\n=== RESULT — stratified, game-clustered (11 games) ===")
    for lab, col in (("PRIMARY   print at/below B inside interval", "prim"),
                     ("SECONDARY any positive volume delta", "vol")):
        ctrl_rate = (pool[~pool.treat].groupby(keys)[col].mean()
                     .rename("cr").reset_index())
        t = pool[pool.treat].merge(ctrl_rate, on=keys, how="inner")
        t["excess"] = t[col] - t.cr
        cm = clustered_mean({k: list(v) for k, v in t.groupby("game_id").excess})
        tr = clustered_mean({k: list(v) for k, v in t.groupby("game_id")[col]})
        print(f"  {lab}")
        print(f"    treatment {tr.mean:>7.2%}   matched-control expectation "
              f"{t.cr.mean():>7.2%}")
        print(f"    EXCESS {cm.mean:+.2%} [{cm.lo:+.2%}, {cm.hi:+.2%}]"
              f"   {'spans zero' if cm.lo <= 0 <= cm.hi else 'excludes zero'}")

    print("\nREADING RULE, pre-declared: a positive is strong evidence of")
    print("consumption; a flat result means NOT DETECTABLE AT THIS CADENCE and")
    print("must never be reported as 'no consumption occurred'. last_trade_px")
    print("sees only the last print before each poll, so this under-counts.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    main()
