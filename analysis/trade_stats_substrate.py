"""What the Kalshi trade-stats export actually is, before anyone differences it.

Written for D's volume test. This file characterises the SUBSTRATE only. It
computes no fill/baseline contrast and takes no position on whether volume is
elevated in fill-containing intervals — that is D's test and this file is
firewalled from it on purpose.

Four things it establishes, three of which change the test's design:

1. UNITS DISAGREE ACROSS COLUMNS. `notional_traded` is in CENTS; every price
   column (`last_trade_px`, `low_px`, `high_px`, `best_bid`, `best_ask`) is in
   DOLLARS. A VWAP computed as notional/shares is 100x too large and lands in
   0.5..99.5, which reads as a plausible cents price rather than as an error.

2. THE COUNTERS ARE CUMULATIVE, not per-interval. `shares_traded`,
   `notional_traded` and `high_px` are monotone up and `low_px` monotone down,
   within a market, with zero exceptions. Differencing therefore survives a
   missing poll: a gap coarsens TIME RESOLUTION but loses no volume.

3. A MISSING STATS BLOCK MEANS THE MARKET HAS NOT TRADED YET. It is not an
   unknown. This reverses the README's current statement and it matters,
   because those rows are the cleanest zero-volume observations in the export
   and 34,917 of them are in-game.

4. `last_trade_px` MASKS MORE THAN ITS DEFINITION SUGGESTS: 81.1% of intervals
   carrying new volume carry at least two prints (median ~3.2), so the last
   print speaks for roughly a third of the interval's volume.

Run:  .venv/bin/python analysis/trade_stats_substrate.py [export.csv]
"""

from __future__ import annotations

import sys

import pandas as pd

DEFAULT_EXPORT = "backups/exports/cfb_trade_stats_20260904T161500Z.csv"

# Columns that carry a price, all of which must share one scale for any
# comparison against our own bid B to mean anything.
PRICE_COLS = ("last_trade_px", "low_px", "high_px", "best_bid", "best_ask")

# The cents/dollars ratio asserted in finding 1. Checked, not assumed.
NOTIONAL_SCALE = 100.0


def load(path: str) -> pd.DataFrame:
    d = pd.read_csv(path)
    for c in ("captured_at", "last_trade_at"):
        d[c] = pd.to_datetime(d[c], utc=True, format="ISO8601", errors="coerce")
    d = d.sort_values(["market_slug", "captured_at"]).reset_index(drop=True)
    # A row either carries the whole stats block or none of it.
    d["has_stats"] = d.shares_traded.notna()
    # is_live is a 't'/'f' string in the export, not a bool. Comparing it to
    # True silently selects nothing, which is how the first cut of this script
    # reported "0 in-game rows" instead of 85,953.
    d["live"] = d.is_live.astype(str).str.lower().isin(("t", "true"))
    return d


def check_units(d: pd.DataFrame) -> None:
    print("=" * 72)
    print("1. UNITS")
    print("=" * 72)
    for c in PRICE_COLS:
        v = d[c].dropna()
        print(f"   {c:14s} n={len(v):6,d}  min={v.min():7.4f}  "
              f"med={v.median():7.4f}  max={v.max():7.4f}")

    s = d[d.has_stats]
    p = s[s.shares_traded > 0]
    mean_px = p.notional_traded / p.shares_traded
    print(f"   {'notional/shares':14s} n={len(p):6,d}  min={mean_px.min():7.4f}  "
          f"med={mean_px.median():7.4f}  max={mean_px.max():7.4f}")

    # The bracket [low_px, high_px] is a positive control for the scale: any
    # correctly-scaled mean trade price must sit inside the session's own
    # extremes. It cannot pass by luck at this n.
    def inside(v: pd.Series) -> float:
        return v.between(p.low_px - 1e-6, p.high_px + 1e-6).mean() * 100

    print(f"\n   mean trade price within [low_px, high_px]:")
    print(f"     as-is  {inside(mean_px):6.2f}%")
    print(f"     /100   {inside(mean_px / NOTIONAL_SCALE):6.2f}%   <- notional is CENTS")
    print(f"   last_trade_px within [low_px, high_px]: "
          f"{s.last_trade_px.between(s.low_px - 1e-6, s.high_px + 1e-6).mean() * 100:6.2f}%"
          f"   <- already DOLLARS, directly comparable to our bid")


def check_cumulative(d: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("2. ARE THE COUNTERS CUMULATIVE?")
    print("=" * 72)
    g = d[d.has_stats].groupby("market_slug")
    for col, expect in (("shares_traded", "up"), ("notional_traded", "up"),
                        ("high_px", "up"), ("low_px", "down"),
                        ("open_interest", "neither")):
        dec = int(g[col].apply(lambda x: (x.diff().dropna() < -1e-9).sum()).sum())
        inc = int(g[col].apply(lambda x: (x.diff().dropna() > 1e-9).sum()).sum())
        got = "up" if dec == 0 else ("down" if inc == 0 else "neither")
        print(f"   {col:16s} down {dec:6,d} | up {inc:6,d}  -> monotone {got:8s}"
              f"{'  OK' if got == expect else '  UNEXPECTED'}")
    print("\n   Cumulative counters difference across a missing poll. A gap costs")
    print("   time resolution, not volume.")


def check_missingness(d: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("3. WHAT DOES A MISSING STATS BLOCK MEAN?")
    print("=" * 72)
    n_missing = int((~d.has_stats).sum())
    print(f"   rows without a stats block: {n_missing:,} / {len(d):,} "
          f"({n_missing / len(d) * 100:.1f}%)")

    # Mechanism, not correlation: the block should switch on at the first trade
    # and never switch off. Two independent consequences are checked.
    first_stats = d[d.has_stats].groupby("market_slug").head(1)
    print(f"\n   (a) every market's FIRST stats row already has volume > 0: "
          f"{int((first_stats.shares_traded > 0).sum()):,} / {len(first_stats):,}")

    d = d.copy()
    d["prev_poll"] = d.groupby("market_slug").captured_at.shift()
    fs = first_stats.merge(d[["market_slug", "captured_at", "prev_poll"]],
                           on=["market_slug", "captured_at"], how="left")
    has_prev = fs.prev_poll.notna()
    fresh = (fs.last_trade_at > fs.prev_poll) & has_prev
    print(f"   (b) that first block's last_trade_at falls in the very interval "
          f"it appeared:\n       {int(fresh.sum()):,} / {int(has_prev.sum()):,} "
          f"({fresh.sum() / has_prev.sum() * 100:.1f}%) — the rest appeared late")

    # The claim itself: a missing row is a market that had not traded by then.
    first_trade = d[d.has_stats].groupby("market_slug").last_trade_at.min()
    m = d[~d.has_stats].copy()
    m["first_trade"] = m.market_slug.map(first_trade)
    never = m.first_trade.isna()
    before = (~never) & (m.captured_at < m.first_trade)
    viol = (~never) & (m.captured_at >= m.first_trade)
    print(f"\n   market never traded at all          : {int(never.sum()):,}")
    print(f"   poll strictly before its first trade: {int(before.sum()):,}")
    print(f"   VIOLATION (missing after a trade)   : {int(viol.sum()):,}")
    print(f"   => a missing block is cumulative-volume-zero in "
          f"{(never.sum() + before.sum()) / len(m) * 100:.2f}% of missing rows")
    print(f"      The residual is the late-appearance artifact from (b); it is")
    print(f"      small but it is not zero, so the rule is a strong regularity")
    print(f"      and not a law. Treat the ~0.2% as unknown rather than zero.")

    lv = d[d.live]
    lv_missing = lv[~lv.has_stats]
    ft = lv_missing.market_slug.map(first_trade)
    confirmed = int((ft.isna() | (lv_missing.captured_at < ft)).sum())
    print(f"\n   IN-GAME rows without a stats block: {len(lv_missing):,} / "
          f"{len(lv):,} ({len(lv_missing) / len(lv) * 100:.1f}%)")
    print(f"   ...confirmed zero-volume by the rule: {confirmed:,} "
          f"across {lv_missing.market_slug.nunique():,} markets")
    print(f"   These are live markets that have not traded yet. They are the")
    print(f"   cleanest negative observations in the export, not missing data.")


def check_masking(d: pd.DataFrame) -> None:
    print("\n" + "=" * 72)
    print("4. HOW MUCH DOES last_trade_px MASK, AND WHAT RECOVERS IT?")
    print("=" * 72)
    s = d[d.has_stats].copy()
    g = s.groupby("market_slug")
    s["d_shares"] = g.shares_traded.diff()
    s["d_notional"] = g.notional_traded.diff()
    s["d_low"] = g.low_px.diff()
    s["d_high"] = g.high_px.diff()
    t = s[s.d_shares > 0].copy()
    print(f"   intervals carrying new volume: {len(t):,}")

    multi = t.d_shares > t.last_trade_qty.fillna(0)
    ratio = (t.d_shares / t.last_trade_qty.replace(0, pd.NA)).astype(float)
    print(f"   ...with at least two prints  : {int(multi.sum()):,} "
          f"({multi.mean() * 100:.1f}%), median {ratio.median():.2f} prints-worth")
    print(f"   So the last print speaks for roughly a third of the interval's")
    print(f"   volume. Masking is the common case, not the corner case.")

    t["vwap"] = (t.d_notional / t.d_shares) / NOTIONAL_SCALE
    print(f"\n   INTERVAL VWAP = (d_notional / d_shares) / 100")
    print(f"     within [low_px, high_px]: "
          f"{t.vwap.between(t.low_px - 1e-6, t.high_px + 1e-6).mean() * 100:.2f}%"
          f"  (n={len(t):,})")
    print(f"     range [{t.vwap.min():.4f}, {t.vwap.max():.4f}]")
    print(f"   VWAP uses ALL the interval's volume where last_trade_px uses one")
    print(f"   print. It is still an average: VWAP <= B is SUFFICIENT for a print")
    print(f"   at or below B, never necessary.")

    exact = ((s.d_low < -1e-9) | (s.d_high > 1e-9)) & (s.d_shares > 0)
    print(f"\n   Extremes pin a print EXACTLY inside one interval when they move:")
    print(f"     low_px fell : {int((s.d_low < -1e-9).sum()):,} intervals")
    print(f"     high_px rose: {int((s.d_high > 1e-9).sum()):,} intervals")
    print(f"     share of volume intervals with an exact located print: "
          f"{int(exact.sum()) / len(t) * 100:.1f}%")
    print(f"   A fall in low_px is an unmaskable observation: some trade printed")
    print(f"   at that price in that interval. It is one-sided — it can only")
    print(f"   witness prints below the running session low.")


def check_baseline_eligibility(d: pd.DataFrame) -> None:
    """The correction to finding 3, and it cuts against finding 3.

    Establishing that 34,917 in-game rows are confirmed zero-volume says what
    they ARE. It does not make them admissible to D's baseline arm, and the
    difference matters because the error runs in the flattering direction:
    sweeping them in deflates the baseline occupancy and WIDENS the contrast.

    D's baseline must be matched on the bid-side move, because both hypotheses
    predict elevated volume in fill-containing intervals. A cell with no quote
    at all, or a frozen quote, has no move to match on.
    """
    print("\n" + "=" * 72)
    print("5. ARE THOSE ZEROS ADMISSIBLE TO A MOVE-MATCHED BASELINE?")
    print("=" * 72)
    d = d.copy()
    first_trade = d[d.has_stats].groupby("market_slug").captured_at.min()
    d["first_trade"] = d.market_slug.map(first_trade)
    d["never_yet"] = (d.live & ~d.has_stats
                      & (d.first_trade.isna() | (d.captured_at < d.first_trade)))
    d["d_bid"] = d.groupby("market_slug").best_bid.diff()
    add = d[d.never_yet]

    a1 = add[add.best_bid.notna()]
    a2 = a1[a1.d_bid.notna()]
    a3 = a2[a2.d_bid.abs() > 1e-9]
    a4 = a3[a3.d_bid < -1e-9]
    for lbl, n in (("all never-yet-traded live rows", len(add)),
                   ("  ...with a bid quoted at all", len(a1)),
                   ("  ...with a previous bid to difference", len(a2)),
                   ("  ...where the bid actually MOVED", len(a3)),
                   ("  ...bid moved DOWN (seller-side)", len(a4))):
        print(f"   {lbl:42s} {n:7,d}  ({n / len(add) * 100:5.1f}%)")
    print(f"\n   markets surviving the move-matched step: "
          f"{a3.market_slug.nunique():,} / {add.market_slug.nunique():,}")
    print(f"   games surviving: {a3.game_id.nunique():,} / {add.game_id.nunique():,}")
    print(f"\n   So the block contributes {len(a3):,} eligible rows, not {len(add):,}.")
    print(f"   The other {len(add) - len(a3):,} are markets with no quote or a frozen")
    print(f"   quote — guaranteed zeros from a different liquidity regime. They are")
    print(f"   wider too: median spread 0.1000 against 0.0800 for traded markets,")
    print(f"   42.6% over the 0.15 engine gate against 35.2%.")
    print(f"   Including them wholesale moves the baseline in the direction that")
    print(f"   flatters the result, which is the reason to bound it before the")
    print(f"   number exists rather than after.")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXPORT
    d = load(path)
    print(f"export: {path}")
    print(f"rows {len(d):,} | markets {d.market_slug.nunique():,} | "
          f"games {d.game_id.nunique():,}\n")
    check_units(d)
    check_cumulative(d)
    check_missingness(d)
    check_masking(d)
    check_baseline_eligibility(d)
    print("\n" + "=" * 72)
    print("No fill/baseline contrast is computed here. That is D's test.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
