"""λ(q) measured — the adverse-selection term in `real edge = s/2 − λ(q)`.

Run `lambda_q_null.py` first; this file compares against that null, never
against zero, because the null does not sit at zero.

TWO DIFFERENT QUESTIONS, and only the second decides whether touch-joining
earns anything:

* **Does λ depend on q?**  Δλ = λ(top quintile) − λ(bottom quintile), against
  the permutation null. This is the queue-position story.
* **Is λ below s/2 = 1.256¢ anywhere?**  That is about the LEVEL of λ in each
  bucket, not the slope, and a flat λ is perfectly tradable if its level is low
  enough. A slope test cannot answer it and must not be reported as if it had.

Horizon is 60s throughout (README: 94.9% coverage; mid30 is 76.2% and its
shortfall is not random). Clusters are games, never rows — 11 of them, so the
intervals are honestly wide and `clustered_mean` takes df = G-1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.lambda_q_null import (N_PERM, RNG_SEED, delta_lambda, load,
                                    run_null)
from core.quote.adverse_selection import clustered_mean

#: Measured elsewhere, quoted here as the threshold λ must beat.
HALF_SPREAD_CENTS = 1.256


def cm(frame: pd.DataFrame):
    return clustered_mean({g: v.tolist() for g, v in frame.groupby("game_id").lam})


def main() -> int:
    d = load()
    print(f"n {len(d):,} | games {d.game_id.nunique()} | markets "
          f"{d.market_slug.nunique()} | horizon mid60\n")

    overall = cm(d)
    print("=" * 74)
    print("LEVEL — is λ below s/2 at all?")
    print("=" * 74)
    print(f"  λ overall  {overall.mean:+.3f}c  [{overall.lo:+.3f}, {overall.hi:+.3f}]"
          f"  (G={overall.n_clusters})")
    print(f"  s/2        {HALF_SPREAD_CENTS:+.3f}c")
    print(f"  edge = s/2 − λ = {HALF_SPREAD_CENTS - overall.mean:+.3f}c"
          f"   [{HALF_SPREAD_CENTS - overall.hi:+.3f}, "
          f"{HALF_SPREAD_CENTS - overall.lo:+.3f}]")

    print("\n" + "=" * 74)
    print("LEVEL BY QUEUE DEPTH — the question is the level in each bucket")
    print("=" * 74)
    d = d.copy()
    d["qb"] = pd.qcut(d.q, 5, labels=False, duplicates="drop")
    print(f"  {'bucket':>7} {'n':>6} {'q range':>16} {'λ (c)':>9} {'95% CI':>20} "
          f"{'edge = s/2−λ':>14}")
    for b in sorted(d.qb.dropna().unique()):
        s = d[d.qb == b]
        r = cm(s)
        if r is None:
            continue
        rng = f"{s.q.min():.0f}-{s.q.max():.0f}"
        edge = HALF_SPREAD_CENTS - r.mean
        print(f"  {int(b):>7} {len(s):>6} {rng:>16} {r.mean:>+9.3f} "
              f"[{r.lo:+.3f},{r.hi:+.3f}]".ljust(64) + f"{edge:>+10.3f}c")

    print("\n" + "=" * 74)
    print("SLOPE — Δλ against the null, NOT against zero")
    print("=" * 74)
    obs = delta_lambda(d)
    null = run_null(d, N_PERM, np.random.default_rng(RNG_SEED))
    lo, hi = np.percentile(null, [2.5, 97.5])
    inside = lo <= obs <= hi
    p = float((np.abs(null - null.mean()) >= abs(obs - null.mean())).mean())
    print(f"  observed Δλ      {obs:+.4f}c")
    print(f"  null             mean {null.mean():+.4f}c  95% [{lo:+.4f}, {hi:+.4f}]")
    print(f"  observed is {'INSIDE' if inside else 'OUTSIDE'} the null   "
          f"two-sided p = {p:.3f}")
    print(f"  vs zero it would look like {obs:+.4f}c — which is the comparison")
    print(f"  the null exists to forbid.")

    print("\n" + "=" * 74)
    print("★ THE TRIGGER — why the level above cannot be read as an edge")
    print("=" * 74)
    d["over"] = np.where(d.is_bid, d.qp - d.mid_fill, d.mid_fill - d.qp) * 100
    print(f"  mid past our price at the fill: {(d.over > 0).mean()*100:.1f}% of fills")
    print(f"  overshoot  mean {d.over.mean():+.3f}c   median {d.over.median():+.3f}c")
    print("  Rule A fires when the mid REACHES our quote, so mid_at_fill sits at a")
    print("  selected extreme BY CONSTRUCTION and later movement is reversion.")
    d["ob"] = pd.qcut(d.over, 5, labels=False, duplicates="drop")
    print(f"\n  {'overshoot':>18} {'n':>6} {'λ':>9} {'95% CI':>20}")
    for b in sorted(d.ob.dropna().unique()):
        s = d[d.ob == b]
        r = cm(s)
        if r:
            print(f"  {s.over.min():>8.1f}-{s.over.max():<9.1f} {len(s):>6} "
                  f"{r.mean:>+9.3f} [{r.lo:+.3f},{r.hi:+.3f}]")
    print("  λ tracks the trigger's own variable monotonically. That is the")
    print("  signature, not a coincidence.")
    print("\n  NOT A VALID CHECK, recorded because I ran it: regressing λ on the")
    print("  overshoot and reporting the residual mean gives +0.0000c, which is")
    print("  TAUTOLOGICAL — OLS residuals have mean zero by construction. The")
    print("  non-circular version is the smallest-overshoot bucket above, where")
    print("  selection is weakest and λ is still favourable.")
    strictly = (d.over > 1e-9).mean() * 100
    exactly = (d.over.abs() < 1e-9).mean() * 100
    print(f"  And there is NO UNSELECTED STRATUM: the mid is at-or-past our price")
    print(f"  on 100% of fills — strictly past on {strictly:.1f}%, exactly at it on")
    print(f"  {exactly:.1f}%. Even that exactly-at stratum required the mid to REACH")
    print(f"  our quote, so it is the weakest selection available and not a control.")
    z = d[d.over.abs() < 1e-9]
    r = cm(z)
    if r:
        print(f"  λ there: {r.mean:+.3f}c [{r.lo:+.3f}, {r.hi:+.3f}] on n={len(z):,} "
              f"— still favourable.")
    # `real <=> excess >= s/2` cannot clean this: it stratifies on the very
    # overshoot that drives the drift, so the "real" arm is the MORE selected one
    # (median overshoot 2.50c against the phantom arm's 1.00c), not the cleaner.
    d["real"] = d.over >= (d.spread * 100) / 2
    for lbl, s in (("real (excess>=s/2)", d[d.real]), ("phantom", d[~d.real])):
        rr = cm(s)
        if rr:
            print(f"  {lbl:20s} n {len(s):>6} λ {rr.mean:+.3f}c  median overshoot "
                  f"{s.over.median():.2f}c")

    print("\n" + "=" * 74)
    print("BY SIDE — the fill rule is side-asymmetric, so λ is reported per side")
    print("=" * 74)
    for lbl, s in (("bid (we bought)", d[d.is_bid]), ("ask (we sold)", d[~d.is_bid])):
        r = cm(s)
        if r:
            print(f"  {lbl:16s} n {len(s):>6}  λ {r.mean:+.3f}c "
                  f"[{r.lo:+.3f}, {r.hi:+.3f}]  edge {HALF_SPREAD_CENTS-r.mean:+.3f}c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
