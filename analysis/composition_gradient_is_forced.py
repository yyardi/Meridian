"""Is the real/phantom composition gradient a mechanism instrument? — 2026-09-04

    .venv/bin/python analysis/composition_gradient_is_forced.py [--exports DIR]

The proposal: real share falls 48% -> 20% as the spread widens; measured on
COUNTS rather than money, so it should carry tight intervals and replicate
across leagues if informed flow is the cause. That would be the first
mechanism evidence not routed through a P&L.

★ IT DOES NOT WORK, AND THE REASON IS THE SAME SPECIES THAT KILLED CAPTURE.
The classification rule, recovered from the export and verified exact:

    real  <=>  excess >= s/2        (100.0% agreement, 38,465 fills)

where `excess` is how far the mid overshot our resting price. A resting bid
at B is only reachable by a real seller if the ASK came down to B, i.e. the
mid must travel an EXTRA s/2 past the fill trigger. **The spread is on both
sides of the statistic**: widen the market and the bar rises mechanically,
with no change in anybody's behaviour.

The geometry-only null makes this concrete — hold each league's excess
distribution FIXED at its pooled shape and move ONLY the threshold:

| band | CFB actual | CFB geometry-only | WNBA actual | WNBA geometry-only |
|---|---:|---:|---:|---:|
| <=1c | 99.2% | 81.8% | 100.0% | 78.6% |
| 2c | 38.9% | 62.6% | 39.7% | 56.4% |
| 3-4c | 34.3% | 48.2% | 41.0% | 37.9% |
| 5-9c | 23.0% | 29.7% | 17.4% | 16.3% |
| 10-15c | 11.2% | 15.2% | 5.8% | 3.9% |

A null with NO flow story reproduces a strong monotone decline on both
boards. So **a cross-league replication of "real share falls with width" is
FORCED**: both boards share one fill rule, so both must show it. Per the
central document's own asymmetry ruling this is the width-gradient trap in a
new costume, not the phantom-rate case — the phantom RATE is a property of
the simulator and replicating it confirms the mechanism; a phantom GRADIENT
in spread is the simulator's algebra restated.

There is a second mechanical channel, so this is not merely a threshold
artefact: our own quote placement depends on the spread through the
post-only clamp (`max(A-k, bid+tick)`), so the excess distribution is also
partly set by s via our policy rather than by flow.

The <=1c band is the cleanest illustration: real share 99-100% because the
bar is 0.5c and a 1c tick almost always clears it. Nobody would read that as
"informed flow avoids tight markets."

WHAT SURVIVES. The counts themselves, the gate, and settlement P&L by band
(settlement has no s on both sides) remain usable — see
`analysis/cfb_wide_band_census.py`. What does not survive is using
composition as evidence ABOUT FLOW.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

EXPORT_NAME = "quote_fills_classified_20260904T142200Z.csv"
BANDS = ["<=1c", "2c", "3-4c", "5-9c", "10-15c"]
COMPARISONS = {"n": 0}


def load(exports: Path) -> pd.DataFrame:
    d = pd.read_csv(exports / EXPORT_NAME).rename(columns={"pop": "population"})
    d["league"] = np.where(
        d.market_slug.str.contains("wnba", case=False), "WNBA", "CFB")
    d["mid_f"] = (d.bb + d.ba) / 2
    d["s_f"] = d.ba - d.bb
    d["excess"] = np.where(d.side == "bid", d.qp - d.mid_f, d.mid_f - d.qp)
    d["real01"] = (d.population == "real").astype(float)
    d["sb"] = pd.cut((d.s_f * 100).round(), [-1, 1, 2, 4, 9, 15],
                     labels=BANDS)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=REPO / "backups/exports")
    d = load(ap.parse_args().exports)

    print("# The composition gradient is forced, not evidence about flow\n")
    exact = (((d.excess >= d.s_f / 2 - 1e-9)) == (d.real01 == 1)).mean()
    print(f"**Classification rule recovered and verified: real <=> excess >= "
          f"s/2 — {exact*100:.1f}% agreement on {len(d):,} fills.** The "
          f"spread sits on both sides of the statistic.\n")

    print("## Composition by width, both boards, game-clustered\n")
    print("| league | band | fills | games | real share | 95% CI (clustered) "
          "| geometry-only null |")
    print("|---|---|---:|---:|---:|---|---:|")
    for lg in ("CFB", "WNBA"):
        pool = d[d.league == lg].excess.to_numpy()
        for b in BANDS:
            g = d[(d.league == lg) & (d.sb == b)]
            if not len(g):
                continue
            cm = clustered_mean(
                {k: list(v) for k, v in g.groupby("game_id").real01})
            COMPARISONS["n"] += 1
            thr = np.sort(g.s_f.to_numpy() / 2)
            pred = float(np.mean([(pool >= t - 1e-9).mean() for t in thr]))
            print(f"| {lg} | {b} | {len(g):,} | {g.game_id.nunique()} | "
                  f"{cm.mean*100:.1f}% | [{cm.lo*100:.1f}, {cm.hi*100:.1f}] "
                  f"| {pred*100:.1f}% |")

    print("\n## Are the two boards' width bands the same unit? NO — say it\n")
    for lg in ("CFB", "WNBA"):
        s = d[d.league == lg].s_f * 100
        print(f"* **{lg}** fills: median spread at fill {s.median():.0f}c "
              f"(p75 {s.quantile(.75):.0f}c). ")
    print("\nSo a '5-9c' band sits ABOVE WNBA's median and near/below CFB's "
          "board median (11c on the live board). The same label is a "
          "different position in each board's own distribution, and any "
          "cross-league comparison of that band compares unlike regions. "
          "This alone would blunt a replication claim even if the statistic "
          "were sound.\n")

    print(f"---\n**Comparisons: {COMPARISONS['n']} game-clustered intervals** "
          f"across two leagues sharing 24 games total.\n")
    print("No in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
