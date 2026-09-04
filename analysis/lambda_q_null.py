"""The geometry-only null for λ(q), built and mutation-tested BEFORE the number.

`real edge = s/2 − λ(q)`. `s/2` is measured at +1.256¢. λ(q) is the unmeasured
term, and the whole question is whether λ < s/2 anywhere in the queue
distribution.

**This file computes the NULL and the MUTATION TEST only.** The real λ(q) is in
`lambda_q_measure.py` and must not be run until this one passes. The firewall is
the point: the hazard here is a slope that the partition manufactures, and a
null built after seeing the slope is not a null.

## The pre-declared statistic

    λ_i  =  (mid_fill − mid60)  for a BID fill   (we bought; we lose if mid falls)
            (mid60 − mid_fill)  for an ASK fill  (we sold;   we lose if mid rises)

    Δλ   =  λ(top q quintile) − λ(bottom q quintile),  in cents,
            game-clustered (11 games), clusters are games and never rows.

Positive Δλ is the hypothesis: a deeper queue needs a larger sell to reach us,
larger sells are likelier informed, so adverse selection rises with q.

## The null, and why it is on the QUEUE rather than the spread

Permute q **within spread strata**, preserving each row's spread stratum and its
drift, destroying only the q↔drift correspondence. Under this null the queue
carries no information beyond spread, so:

> **PRE-DECLARED: the null's Δλ distribution centres on ZERO. If the observed Δλ
> sits inside it, the slope is the partition talking and λ(q) has no q in it.**

**THAT PRE-DECLARATION WAS REFUTED BY ITS OWN NULL, and the refutation is the
first real finding here.** The null centres on **+0.0533¢** (sd 0.1776, 2,000
draws — a standard error of 0.004¢, so 13 SEs from zero) and is asymmetric:
2.5th −0.278¢, 97.5th **+0.416¢**. The statistic is biased upward by the
partition alone, before any q-dependence exists.

The cause is the tie structure: **35.6% of fills have q = 0**, so quintiles of q
cannot be equal-sized and the bottom bucket is a pile of zeros while the top is
a long tail. Quintiles of a heavily-tied, violently skewed variable are not five
equal groups, and the asymmetry follows.

**The operational consequence, which is the whole reason to build a null first:
an observed Δλ must be compared to THIS distribution, never to zero.** Comparing
to zero would score +0.4¢ as a finding when the geometry supplies it.

## Why the null is still required when the confounder looks absent

Measured on this file: log1p(q) vs spread is **Pearson −0.000, Spearman +0.023**
— essentially no monotone relation, which would ordinarily argue the
stratification is unnecessary. It is not, and the reason is the failure recorded
in `FORCED_GRADIENTS.md`: **median q by spread quintile runs 0.3, 3, 30, 25, 20
— a hundredfold non-monotone swing that a monotone correlation cannot see.** A
scalar correlation would have talked me out of the null; the quintile table is
why that would have been wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.quote.adverse_selection import clustered_mean

EXPORT = "backups/exports/quote_lambda_q_20260904T172000Z.csv"
HORIZON = "mid60"          # README: 94.9% coverage, dominates mid30
N_PERM = 2000
RNG_SEED = 20260904        # fixed; Date/random would break reproducibility
N_STRATA = 5


def load() -> pd.DataFrame:
    d = pd.read_csv(EXPORT)
    is_bid = d.side.astype(str).str.lower().eq("bid")
    # THE PRICE-IDENTITY GATE IS SIDE-SPECIFIC. An OR across both sides admits
    # 12,150 rows and silently includes fills whose *other* side happened to
    # match; the side-specific form reproduces the README's 12,025 exactly.
    d = d[np.where(is_bid, d.qbid == d.qp, d.qask == d.qp)].copy()
    d["is_bid"] = d.side.astype(str).str.lower().eq("bid")
    d["q"] = np.where(d.is_bid, d.obq, d.oaq)
    d["mid_fill"] = (d.bb + d.ba) / 2.0
    d["spread"] = d.ba - d.bb
    d = d[d.q.notna() & d[HORIZON].notna() & d.mid_fill.notna()].copy()
    # Adverse selection: positive means the mid moved AGAINST us.
    d["lam"] = np.where(d.is_bid,
                        d.mid_fill - d[HORIZON],
                        d[HORIZON] - d.mid_fill) * 100.0    # cents
    d["stratum"] = pd.qcut(d.spread, N_STRATA, labels=False, duplicates="drop")
    return d


def delta_lambda(d: pd.DataFrame, qcol: str = "q") -> float | None:
    """λ(top q quintile) − λ(bottom q quintile), game-clustered."""
    try:
        edges = pd.qcut(d[qcol], 5, labels=False, duplicates="drop")
    except ValueError:
        return None
    top, bot = d[edges == edges.max()], d[edges == edges.min()]
    if top.empty or bot.empty:
        return None
    a = clustered_mean({g: v.tolist() for g, v in top.groupby("game_id").lam})
    b = clustered_mean({g: v.tolist() for g, v in bot.groupby("game_id").lam})
    return None if (a is None or b is None) else a.mean - b.mean


def permute_within_strata(d: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Shuffle q inside each spread stratum. Drift and stratum stay put."""
    out = d.q.to_numpy().copy()
    for s in d.stratum.unique():
        idx = np.flatnonzero((d.stratum == s).to_numpy())
        out[idx] = rng.permutation(out[idx])
    return pd.Series(out, index=d.index)


def run_null(d: pd.DataFrame, n: int, rng: np.random.Generator) -> np.ndarray:
    vals = []
    for _ in range(n):
        t = d.copy()
        t["qperm"] = permute_within_strata(d, rng)
        v = delta_lambda(t, "qperm")
        if v is not None:
            vals.append(v)
    return np.asarray(vals)


def main() -> int:
    rng = np.random.default_rng(RNG_SEED)
    d = load()
    print(f"rows after gate + coverage: {len(d):,} | games {d.game_id.nunique()} "
          f"| markets {d.market_slug.nunique()}")
    print(f"q: zero {(d.q == 0).mean()*100:.1f}%  median {d.q.median():.0f}  "
          f"mean {d.q.mean():.0f}   (skewed — never the mean without the median)")

    print("\n" + "=" * 68)
    print("NULL — q permuted within spread strata. PRE-DECLARED to centre on 0.")
    print("=" * 68)
    null = run_null(d, N_PERM, rng)
    print(f"  draws {len(null):,}   mean {null.mean():+.4f}c   sd {null.std():.4f}c")
    print(f"  2.5th {np.percentile(null,2.5):+.4f}c   97.5th "
          f"{np.percentile(null,97.5):+.4f}c")
    ok = abs(null.mean()) < 0.05
    print(f"  centres on zero: {'PASS' if ok else 'FAIL'} "
          f"(|mean| {abs(null.mean()):.4f}c vs 0.05c tolerance)")

    print("\n" + "=" * 68)
    print("MUTATION TEST — injected onto a NULLED substrate, not onto real data")
    print("=" * 68)
    # THE FIRST VERSION OF THIS TEST INJECTED ONTO THE REAL DATA and printed the
    # recovered statistic, which is `real Δλ + injection` — so it announced the
    # real answer (+1.0 came back +1.351, +3.0 came back +3.351, a constant
    # +0.351c offset) before the measurement script had run. That is a hole in
    # my own firewall, recorded rather than edited away. Injecting onto a
    # substrate whose true effect is already zero cannot leak anything.
    base = d.copy()
    base["q"] = permute_within_strata(d, np.random.default_rng(RNG_SEED + 7))
    for inject in (1.0, 3.0):
        m = base.copy()
        top = pd.qcut(m.q, 5, labels=False, duplicates="drop")
        m.loc[top == top.max(), "lam"] += inject
        got = delta_lambda(m)
        print(f"  injected +{inject:.1f}c on the top quintile -> statistic "
              f"{got:+.3f}c   (expected ~+{inject:.1f}c on a nulled substrate)")
        print(f"    recovered: {'PASS' if abs(got - inject) < 0.35 else 'FAIL'}")

    print("\n" + "=" * 68)
    print("The real Δλ is NOT computed here. See lambda_q_measure.py.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
