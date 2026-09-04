"""Phantom drift by width: the fourth forced gradient — 2026-09-04

    .venv/bin/python analysis/phantom_drift_geometry_null.py [--exports DIR]

The manager flagged, rather than reported, a beautiful-looking result:
phantom DRIFT rises monotonically with width, +0.969 → +3.385c at 300s
across the registered bands, intervals separating cleanly. Drift is
algebraically clean — the quote price cancels, so no s, no qp, no
threshold appears in the statistic. It therefore escapes the trap that
killed composition.

**It does not escape the trap that killed capture, because the
POPULATION is selected by a spread-dependent rule even though the
statistic is not.** A phantom is a fill where the mid reached our
resting price but the opposite touch did not follow. Our price sits
roughly s/2 below the mid, so **in a wider market the mid must travel
FURTHER to reach us at all.** If excursions revert by some fraction of
their size, drift scales with the excursion, and the excursion scales
with the spread — a gradient with no flow story in it.

THE TEST, on data that needs no markout: if the gradient is excursion
scaling, then drift/excursion should be CONSTANT across width bands
while both grow. Excursion is computable from the fills export alone —
`m_q` (mid at quote) minus `mid_at_fill`, signed to our side.

    band        n       mean excursion   drift@300s   ratio
    <=1.5c      6,401   1.87c            0.969c       0.52
    1.5-2.5c    4,647   2.55c            1.006c       0.39
    2.5-3.5c    3,614   3.24c            1.701c       0.53
    3.5-5.5c    5,002   4.37c            2.613c       0.60
    >5.5c       5,150   6.77c            3.385c       0.50

**Excursion grows 3.6x, drift grows 3.5x, and the ratio is flat at ~0.5
with no trend. corr(excursion, drift) = 0.973 across bands.** The mid
gives back about half of whatever excursion brought it to our price,
and it does so at the SAME rate in every width band. The width gradient
in drift is the width gradient in required excursion. **Fourth forced
gradient.**

THE CONTRAST THAT MAKES IT MORE THAN A COINCIDENCE. Run the identical
test on REAL fills, whose drift the manager measured as non-monotonic:

    band        mean excursion   drift@30s   ratio
    <=1.5c      3.07c            0.294c      0.10
    1.5-2.5c    4.41c            0.747c      0.17
    2.5-3.5c    4.71c            0.836c      0.18
    3.5-5.5c    5.91c            0.219c      0.04
    >5.5c       9.26c            1.022c      0.11

Ratio varies 4.5x with no pattern; corr 0.557. **The geometry explains
phantoms tightly and real fills poorly** — which is what the mechanism
predicts, since a phantom IS a pure excursion-and-revert with no
counterparty, while a real fill had someone cross to us.

LIMITS, stated. (1) This compares five BAND-LEVEL points: my excursion
figures against the manager's published drift figures. Five aggregate
points can produce a high correlation by chance; the constant RATIO
across a 3.6x range is the stronger evidence, but the decisive test is
a per-fill regression of drift on excursion within band, which needs
the per-fill markout data this session does not hold. (2) The two
populations are quoted at different horizons (300s phantom, 30s real),
so their ratios are NOT comparable to each other — each is internally
consistent only. (3) Nothing here is a claim about flow.

THE STANDING NOTE THIS EARNS, in the manager's words: *any statistic
cut by spread, on a population selected by a spread-dependent rule, is
guilty until proven innocent* — even when the statistic itself is
algebraically clean of spread.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

EXPORT_NAME = "quote_fills_classified_20260904T142200Z.csv"
LABS = ["<=1.5c", "1.5-2.5c", "2.5-3.5c", "3.5-5.5c", ">5.5c"]
#: published in docs/math/markout-measured.md (4a2cb1b); quoted, not recomputed
MGR_DRIFT = {
    "phantom": {"<=1.5c": 0.969, "1.5-2.5c": 1.006, "2.5-3.5c": 1.701,
                "3.5-5.5c": 2.613, ">5.5c": 3.385},          # 300s
    "real": {"<=1.5c": 0.294, "1.5-2.5c": 0.747, "2.5-3.5c": 0.836,
             "3.5-5.5c": 0.219, ">5.5c": 1.022},             # 30s
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=REPO / "backups/exports")
    d = pd.read_csv(ap.parse_args().exports / EXPORT_NAME).rename(
        columns={"pop": "population"})
    d["mid_f"] = (d.bb + d.ba) / 2
    d["excursion"] = np.where(d.side == "bid", d.m_q - d.mid_f,
                              d.mid_f - d.m_q)
    d["wb"] = pd.cut(d.s_q * 100, [-1, 1.5, 2.5, 3.5, 5.5, 999], labels=LABS)

    print("# Phantom drift by width — is it excursion scaling?\n")
    for pop, horizon in (("phantom", "300s"), ("real", "30s")):
        print(f"## {pop} fills (manager's drift at {horizon})\n")
        print("| band | n | mean excursion | drift | ratio |")
        print("|---|---:|---:|---:|---:|")
        ex, dr = [], []
        for b in LABS:
            g = d[(d.population == pop) & (d.wb == b)]
            if not len(g):
                continue
            e = g.excursion.mean() * 100
            r = MGR_DRIFT[pop][b]
            ex.append(e)
            dr.append(r)
            print(f"| {b} | {len(g):,} | {e:.2f}c | {r:.3f}c | {r/e:.2f} |")
        ex, dr = np.array(ex), np.array(dr)
        rat = dr / ex
        print(f"\ncorr(excursion, drift) = **{np.corrcoef(ex, dr)[0,1]:.3f}**; "
              f"ratio {rat.min():.2f}–{rat.max():.2f} "
              f"({'FLAT — pure scaling' if rat.max()/rat.min() < 2 else 'VARIES — not a clean scaling law'})"
              f"; excursion grows {ex.max()/ex.min():.1f}x, drift "
              f"{dr.max()/dr.min():.1f}x.\n")
    print("Five band-level points; the constant ratio across a wide "
          "excursion range is the evidence, not the correlation. The "
          "decisive per-fill regression needs markout data not held here.\n")
    print("No in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
