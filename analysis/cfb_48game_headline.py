"""The 48-game CFB headline — PRE-DECLARED before the pin exists.

Written 2026-09-05 while the classified pin is still being built. Every choice
below is fixed here, BEFORE the data can influence it. Revisions after the pin
lands must be appended with their reason, never edited in place.

WHAT IS BEING MEASURED, AND WHAT IT IS NOT
------------------------------------------
This is the settlement P&L of the fills OUR SIMULATOR BOOKS. It is not what
touch-joining earns. The fill rule books only `mid <= B`, so capture <= 0 on
every row by construction (verified: 0 of 38,465 on the previous pin), and the
profitable maker case — a seller crossing the spread to a resting bid while the
ask stays above — produces no row at all. **A 4.4x larger sample makes this a
much better measurement of the simulator's own losing half, and does not make
it a measurement of the strategy.** That sentence travels with the number.

PRIMARY
-------
Real population only (`pop == 'real'`), settlement basis, game-clustered via
`core/quote/adverse_selection.clustered_mean`, reported as
mean [lo, hi] with n in BOTH fills and games.

REPORTED SEPARATELY, NOT POOLED SILENTLY
----------------------------------------
  CFB (48 games)   the number the power work was about
  WNBA (13)        unchanged sample, different sport and engine era
  pooled (61)      reported third, after both parts

★ THE ENGINE SPLIT IS NOT AVAILABLE AS ASKED, and this was checked before the
pin landed. On the previous pin **9 of 24 games span BOTH engine commits**
(4529951a -> 63e7f1b8, deployed mid-slate at ~09-04 00:52Z). So:

  - splitting by GAME is impossible — the boundary runs through games;
  - splitting by FILL breaks the clustering, because one game's fills would sit
    in both arms and the arms would not be independent. That is the error this
    programme has made repeatedly and it is not available here either.

PRE-DECLARED HANDLING: **primary is POOLED across commits, stated as pooled.**
The sensitivity is a restriction to games lying ENTIRELY within one commit,
which preserves clustering. If the two differ materially the engine change is
confounded with time and the number must be reported as such.

★ THE PRICE FREEZE — pre-declared exclusion rule
------------------------------------------------
From ~17:39Z the venue stopped updating prices (mid step exactly 0.000000
across 602,119 observations, verified against the venue API, recorder faithful
8/8). Fills went 150/min -> 43 -> 1 -> 0 and recovered only partially (3 fills
in the 19:00 hour, 61 in the 20:00 hour).

  - the freeze window itself is structurally fill-free, so it self-excludes
    from a fill-based read and needs no rule;
  - **the PARTIAL-RECOVERY hours are a different regime** and are excluded from
    the primary, reported separately. A book that is updating 1/50th as often
    is not the board the rest of the sample describes.

The boundary is defined by the venue's own behaviour, not by the P&L: a fill is
in the recovery regime if its market's mid was frozen (zero step) for more than
`FREEZE_STALE_S` before it. Declared here so it cannot be tuned afterwards.

★ THE MAKER REBATE — both bases, and the sign is known in advance
-----------------------------------------------------------------
Verified: −0.0125 x p x (1−p), no maker fee, base tier, all participants.
Worth about +0.283c/fill, 22.6% of the gross half-spread. `assume_rebate=False`
is still on disk pending an operator decision.

Both bases are reported. This is a KNOWN, FAVOURABLE correction of known size —
it cannot rescue a negative result by surprise, and reporting only the
rebate-inclusive basis would flatter. Primary is stated on the basis the code
currently runs (`assume_rebate=False`), with the rebate-inclusive figure beside
it.

DECISION RULE, fixed now
------------------------
| outcome | reading |
|---|---|
| CFB interval excludes zero, negative | the simulator's booked population loses, now measured. Says nothing about the unbooked half |
| CFB interval excludes zero, positive | would be the first positive result; check the rebate basis and the freeze exclusion before it travels |
| CFB interval spans zero | 48 games still insufficient; report the half-width against the 2.61c at 11 games and against C's 0.68c projection |

**The projection is itself a pre-registered check**: C projected 103 games ->
0.68c half-width. We have 48. If the realised half-width is far from the
interpolation, the projection's model was wrong and that is worth knowing
independently of the P&L.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402

FREEZE_STALE_S = 120.0          # declared; not usable on a pin without ticks
FREEZE_START = pd.Timestamp("2026-09-05 17:39", tz="UTC")   # venue price freeze
REBATE_RATE = 0.0125            # |rebate| = 0.0125 * p * (1-p)


def _exports_dir():
    for base in [REPO, *Path(__file__).resolve().parents]:
        if (base / "backups/exports").is_dir():
            return base / "backups/exports"
    raise FileNotFoundError("backups/exports not found — run from the main "
                            "checkout, where the pinned exports live.")


def league(slug: pd.Series) -> pd.Series:
    return np.where(slug.str.contains("-wnba-"), "WNBA",
                    np.where(slug.str.contains("-cfb-"), "CFB", "other"))


def rebate_per_fill(price: pd.Series) -> pd.Series:
    """Maker rebate credited per contract: 0.0125 * p * (1-p), always >= 0."""
    return REBATE_RATE * price * (1.0 - price)


def report(df: pd.DataFrame, label: str, col: str = "pnl") -> None:
    if not len(df):
        print(f"  {label:34s} (empty)")
        return
    cm = clustered_mean({k: list(v) for k, v in df.groupby("game_id")[col]})
    ci = f"{cm.mean*100:+.3f}c [{cm.lo*100:+.3f}, {cm.hi*100:+.3f}]"
    half = (cm.hi - cm.lo) / 2 * 100
    print(f"  {label:34s} {len(df):>7,} fills {df.game_id.nunique():>3d} games "
          f"{ci:>30s}  half-width {half:.3f}c")


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # the rebate is a CREDIT, largest at p=0.5, zero at the boundaries
    r = rebate_per_fill(pd.Series([0.01, 0.5, 0.99]))
    check("rebate is non-negative everywhere", bool((r >= 0).all()))
    check(f"rebate peaks at p=0.5 ({r.iloc[1]*100:.3f}c)",
          r.iloc[1] > r.iloc[0] and r.iloc[1] > r.iloc[2])
    check("rebate at p=0.5 is 0.3125c",
          abs(r.iloc[1] - 0.003125) < 1e-12)

    # a game spanning two commits must NOT be splittable by game
    d = pd.DataFrame({"game_id": ["g1", "g1", "g2"],
                      "engine_commit": ["a", "b", "a"]})
    spans = d.groupby("game_id").engine_commit.nunique()
    check("a straddling game is detected, so 'split by engine' is refused",
          int((spans > 1).sum()) == 1)
    return fails


def main(path: Path) -> None:
    d = pd.read_csv(path, parse_dates=["filled_at"], low_memory=False)
    d["lg"] = league(d.market_slug)
    print(f"pin: {path.name}")
    print(f"  rows {len(d):,}  games {d.game_id.nunique()}  "
          f"window {d.filled_at.min()} -> {d.filled_at.max()}")
    print(f"  by league: "
          f"{d.groupby('lg').game_id.nunique().to_dict()} games")

    if "engine_commit" in d:
        spans = d.groupby("game_id").engine_commit.nunique()
        print(f"  engine commits: {d.engine_commit.nunique()}; "
              f"games straddling a commit boundary: {int((spans > 1).sum())}"
              f" of {len(spans)}  -> primary is POOLED, stated as pooled")

    real = d[d["pop"] == "real"].copy()

    # PRE-DECLARED FREEZE EXCLUSION, applied rather than described. The venue
    # stopped updating prices from ~17:39Z on 2026-09-05; the window itself is
    # structurally fill-free and the partial-recovery hours are a different
    # regime. This pin carries only the book AT each fill, not a tick series,
    # so the identifier used is the wall-clock boundary — stated because it is
    # cruder than the mid-staleness rule declared in the docstring.
    n_before = len(real)
    frozen = real.filled_at >= FREEZE_START
    real = real[~frozen].copy()
    print(f"\nfreeze exclusion (>= {FREEZE_START}): removed "
          f"{int(frozen.sum())} real fills of {n_before:,} "
          f"({frozen.mean():.3%}) — the window is fill-free, as expected")

    real["pnl_rebate"] = real.pnl + rebate_per_fill(real.qp)

    cfb_all = d[d.lg == "CFB"].game_id.nunique()
    cfb_real = real[real.lg == "CFB"].game_id.nunique()
    print(f"CFB games in the pin: {cfb_all}; with at least one REAL fill: "
          f"{cfb_real}. The headline's game count is the latter.")

    print("\n=== PRIMARY — real fills, settlement, game-clustered "
          "(assume_rebate=False, as the code runs) ===")
    for lg in ("CFB", "WNBA"):
        report(real[real.lg == lg], lg)
    report(real, "pooled")

    print("\n=== SAME, rebate-inclusive (known, favourable, +0.283c/fill) ===")
    for lg in ("CFB", "WNBA"):
        report(real[real.lg == lg], lg, col="pnl_rebate")
    report(real, "pooled", col="pnl_rebate")

    print("\n=== SENSITIVITY — games entirely within one engine commit ===")
    if "engine_commit" in d:
        spans = d.groupby("game_id").engine_commit.nunique()
        clean = set(spans[spans == 1].index)
        for lg in ("CFB", "WNBA"):
            report(real[(real.lg == lg) & real.game_id.isin(clean)],
                   f"{lg} single-commit games")

    print("\n=== PER-GAME SIGN COUNT (this regime only) ===")
    for lg in ("CFB", "WNBA"):
        g = real[real.lg == lg]
        if not len(g):
            continue
        tot = g.groupby("game_id").pnl.sum()
        print(f"  {lg:5s} {int((tot < 0).sum())} of {len(tot)} games lose "
              f"({(tot < 0).mean():.0%})")

    print("\nWHAT THIS IS: the settlement P&L of the fills the SIMULATOR books.")
    print("The fill rule books only mid <= B, so the profitable maker case")
    print("produces no row at all. A larger sample measures the booked losing")
    print("half more precisely; it does not measure what touch-joining earns.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    ex = _exports_dir()
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    p = Path(arg) if arg else sorted(ex.glob("quote_fills_classified_*.csv"))[-1]
    main(p)
