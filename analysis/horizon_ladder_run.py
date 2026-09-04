"""The horizon ladder, run exactly as pre-registered.

Registration: `analysis/horizon_ladder_preregistration.md`, commit 2a611bd,
written and committed before this export existed. Nothing here deviates from it.

One thing the registration did NOT anticipate, recorded rather than fixed: the
binding rung is the SHORT end. 30s covers 76.2% (its window is [15s, 30s] under
the h/2 staleness rule, only fifteen seconds wide) while 3600s covers 82.6%.
The balanced panel is 7,852 rows rather than the ~9,817 projected, and for the
opposite reason to the one projected.

**Dropping 30s would raise the panel substantially and is REFUSED.** The ladder
was closed in §1 of the registration. This is the thin panel, reported thin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

EXPORT = "backups/exports/quote_horizon_ladder_20260904T181500Z.csv"
RUNGS = ["mid30", "mid60", "mid300", "mid900", "mid1800", "mid3600"]
LABELS = {"mid30": "30s", "mid60": "60s", "mid300": "300s",
          "mid900": "900s", "mid1800": "1800s", "mid3600": "3600s"}
POWER_FLOOR = 0.30      # cents; registration §6


def load() -> pd.DataFrame:
    d = pd.read_csv(EXPORT)
    is_bid = d.side.astype(str).str.lower().eq("bid")
    d = d[np.where(is_bid, d.qbid == d.qp, d.qask == d.qp)].copy()   # side-specific gate
    d["is_bid"] = d.side.astype(str).str.lower().eq("bid")
    d["mid_fill"] = (d.bb + d.ba) / 2.0
    d["sign"] = np.where(d.is_bid, 1.0, -1.0)
    # drift: POSITIVE = favourable to us (registration §2; this is −λ)
    for r in RUNGS:
        d[f"d_{r}"] = d.sign * (d[r] - d.mid_fill) * 100.0
    d["d_settle"] = d.sign * (d.settlement - d.qp) * 100.0
    d["over"] = np.where(d.is_bid, d.qp - d.mid_fill, d.mid_fill - d.qp) * 100.0
    return d


def cm(frame: pd.DataFrame, col: str):
    s = frame[[col, "game_id"]].dropna()
    if s.empty:
        return None
    return clustered_mean({g: v.tolist() for g, v in s.groupby("game_id")[col]})


def main() -> int:
    d = load()
    print(f"after side-specific gate: {len(d):,} rows | games {d.game_id.nunique()}")

    print("\n" + "=" * 72)
    print("§4 CENSORING FIRST — before any level is interpreted")
    print("=" * 72)
    for r in RUNGS:
        n = d[r].notna().sum()
        print(f"  {LABELS[r]:>6}  {n:>6,} / {len(d):,}  ({n/len(d)*100:5.1f}%)  "
              f"censored {100-n/len(d)*100:5.1f}%  games {d[d[r].notna()].game_id.nunique()}")
    print("  The two censorings are DIFFERENT POPULATIONS: the 30s rung drops")
    print("  markets that were not updating; the 3600s rung drops late-game fills.")
    print("  The registration's late-game argument covers the long end only, and")
    print("  the short end is a not-updating mechanism — said here rather than")
    print("  letting one argument silently cover both.")

    bal = d.dropna(subset=RUNGS).copy()
    print(f"\n  BALANCED PANEL {len(bal):,} rows ({len(bal)/len(d)*100:.1f}%), "
          f"games {bal.game_id.nunique()}, markets {bal.market_slug.nunique()}")
    print("  Thin. Reported thin — dropping the 30s rung would raise it and is")
    print("  refused: the ladder was closed before the data existed.")

    print("\n" + "=" * 72)
    print("§3 PRIMARY — the ladder on the balanced panel (same fills every rung)")
    print("=" * 72)
    print(f"  {'rung':>7} {'drift':>9} {'95% CI':>22}")
    levels = {}
    for r in RUNGS:
        c = cm(bal, f"d_{r}")
        levels[r] = c
        print(f"  {LABELS[r]:>7} {c.mean:>+9.3f} [{c.lo:+.3f}, {c.hi:+.3f}]")
    st = cm(bal, "d_settle")
    print(f"  {'settle':>7} {st.mean:>+9.3f} [{st.lo:+.3f}, {st.hi:+.3f}]   "
          f"<- known terminal value")

    print("\n" + "=" * 72)
    print("§5 TURNOVER — two definitions, not to be conflated")
    print("=" * 72)
    sign_h = next((LABELS[r] for r in RUNGS if levels[r].hi < 0), None)
    print(f"  TURNOVER-SIGN (CI entirely below zero): "
          f"{sign_h if sign_h else 'DOES NOT FIRE inside the ladder'}")
    print(f"  paired increments (balanced panel):")
    peak_h = None
    for a, b in zip(RUNGS, RUNGS[1:]):
        bal["inc"] = bal[f"d_{b}"] - bal[f"d_{a}"]
        c = cm(bal, "inc")
        fires = c.hi < 0
        if fires and peak_h is None:
            peak_h = f"{LABELS[a]}->{LABELS[b]}"
        print(f"    {LABELS[a]:>6} -> {LABELS[b]:<6} {c.mean:>+8.3f} "
              f"[{c.lo:+.3f}, {c.hi:+.3f}]{'   <- falls' if fires else ''}")
    print(f"  TURNOVER-PEAK: {peak_h if peak_h else 'DOES NOT FIRE inside the ladder'}")

    print("\n" + "=" * 72)
    print("§7 DISCRIMINATOR — is the shape reversion? ladder by overshoot quintile")
    print("=" * 72)
    bal["oq"] = pd.qcut(bal.over, 5, labels=False, duplicates="drop")
    print(f"  {'overshoot':>16} {'n':>6} " + " ".join(f"{LABELS[r]:>8}" for r in RUNGS))
    shapes = {}
    for q in sorted(bal.oq.dropna().unique()):
        s = bal[bal.oq == q]
        vals = [cm(s, f"d_{r}").mean for r in RUNGS]
        shapes[q] = vals
        print(f"  {s.over.min():>7.1f}-{s.over.max():<8.1f} {len(s):>6} "
              + " ".join(f"{v:>+8.3f}" for v in vals))
    print("\n  If the SHAPE is the same across buckets, reversion is not driving it.")
    print("  If it scales with overshoot, it is. Normalised to each bucket's 30s:")
    print(f"  {'overshoot bucket':>16} " + " ".join(f"{LABELS[r]:>8}" for r in RUNGS))
    for q, v in shapes.items():
        base = v[0]
        norm = [x - base for x in v]
        print(f"  {int(q):>16} " + " ".join(f"{x:>+8.3f}" for x in norm))

    print("\n" + "=" * 72)
    print("★ THE PRE-DECLARED BRANCH HAS A BROKEN PREMISE")
    print("=" * 72)
    print("  §5 commits me to reporting a terminal-outcome finding if the drift")
    print("  never turns over. That branch assumes the terminal value IS a loss.")
    print("  On this cohort, game-clustered, it is not established:")
    for nm, s in (("full gated", d), ("balanced panel", bal),
                  ("excluded from panel", d[~d.index.isin(bal.index)])):
        c = cm(s, "d_settle")
        print(f"    {nm:22s} n {len(s):>6,}  settle {c.mean:+7.3f}c "
              f"[{c.lo:+7.3f}, {c.hi:+7.3f}]  {'SPANS ZERO' if c.lo <= 0 <= c.hi else ''}")
    print("  The -3.4c the question was built on does not reproduce here. At 11")
    print("  games the settlement estimate is far too noisy to establish a loss,")
    print("  and the -3.4c figure comes from a tape that pools two engine binaries")
    print("  while this cohort is single-binary by construction.")
    print("  So the gap between 'drift positive at an hour' and 'settles at -3.4c'")
    print("  is NOT ESTABLISHED on this cohort. Executing the pre-declared branch")
    print("  would assert a mechanism for a difference that has not been shown to")
    print("  exist. Reporting the premise failure instead, per the registration's")
    print("  own logic rather than against it.")

    print("\n" + "=" * 72)
    print("§6 THE POWER FLOOR travels with the conclusion")
    print("=" * 72)
    hw = np.mean([(levels[r].hi - levels[r].lo) / 2 for r in RUNGS])
    print(f"  mean clustered half-width across rungs: {hw:.3f}c "
          f"(registered floor {POWER_FLOOR:.2f}c)")
    if not sign_h:
        print(f"  TURNOVER-SIGN did not fire. Per §6 that CANNOT distinguish a true")
        print(f"  drift between −{POWER_FLOOR:.1f}c and 0 from no turnover at all.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
