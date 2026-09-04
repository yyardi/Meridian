"""The wide CFB board: a census of our own absence — 2026-09-04

    .venv/bin/python analysis/cfb_wide_band_census.py [--exports DIR]

DESCRIPTIVE. No verdict, no recommendation.

The question, from the manager: the CFB board is ~3x wider than WNBA
(board medians 11c vs 4c; CFB p75 = 30c), yet our real CFB fills sit at
a 1c median. We therefore have little read on the wide 65% of the board,
and every "touch-joining is dead" statement in the record is silently
scoped to the tight corner we sample. This counts what is actually
there.

★ THE HEADLINE, and it decides item 3 outright: THE WIDE BOARD IS
EXCLUDED BY OUR OWN GATE, NOT BY THE MARKET. `MAX_SPREAD = 0.15`
(core/quote/adverse_selection.py:137, core/quote/depth_signal.py:117)
refuses to quote once the spread exceeds 15c. Observed max spread at
quote is EXACTLY 0.15 in both leagues with ZERO fills above it, in
21,126 CFB and 17,339 WNBA fills. So above 15c this is not "we quoted
and nobody crossed to us" — it is "we are forbidden to quote", by a
constant. The board's median is 11c and its p75 is 30c (manager's
13.0M-row count), so the gate sits between the median and the third
quartile: MORE THAN A QUARTER of the CFB board is structurally
invisible to this system, and no amount of further trading will sample
it while the constant stands.

Below the gate the manager's prediction — near-zero real fills in wide
cells — is REFUTED: 1,044 real fills at >=5c across 11 games and 276
markets. The absence is not gradual; it is a wall at 15c.

★ THE SIZE OF THE BLIND SPOT, measured by the manager on 13.0M live
snapshot rows since 2026-08-18 (is_live, crossed books excluded):

    CFB   43.24% of rows above MAX_SPREAD   1,244/1,439 markets (86.4%)
    WNBA  10.22%                              559/696   markets (80.3%)

Both are ROW shares, so time-weighted — the right weighting for "what
fraction of quotable opportunity is refused", the wrong one for "how
many markets are affected", hence both columns.

★ THE HONEST SUMMARY, recorded here rather than left in a thread:
**The system is blind to 43.2% of the live CFB board by row, by policy
rather than by accident. Every "touch-joining is dead as a family"
statement is scoped to the other 56.8%. The visible evidence gives NO
reason to expect the blind region is better, and two monotone trends
suggest it is worse — but extrapolating a trend past a boundary is a
move this program has burned itself on, so the region remains
UNMEASURED, not measured-and-dismissed.** That last clause is load
bearing: "probably protecting us" is an inference from evidence that
stops at the boundary, and a future reader must not be told the
question was settled.

CAVEAT ON ONE OF THOSE TWO TRENDS, added after testing it: the
composition trend (real share falling with width) is largely FORCED by
the fill rule's geometry and is not independent evidence about flow —
see `analysis/composition_gradient_is_forced.py`. The settlement trend
stands. So the honest count is closer to one-and-a-half trends than
two, and the conclusion is unchanged in direction but weaker in
support than when it was first written.

WHAT THIS CENSUS CAN AND CANNOT SEE
-----------------------------------
The substrate is FILLS ONLY (`shadow_quote_fills`). It contains no
record of quotes that rested and never filled, so for any cell the
census cannot by itself separate:
  (a) we quoted there and nothing hit us  — a market fact, and
  (b) we never quoted there               — our own absence.
One lever recovers part of it: a PHANTOM fill is evidence that a quote
existed in that cell, since a phantom is a quote the touch had already
crossed. So phantom counts witness presence even where real fills are
absent. Above 15c both are zero and the gate explains why; below it,
phantoms confirm we were present in every band we report.

Resolving (a) vs (b) properly needs the rested-quote stream
(`quote_v2_observations`), which has no local export.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import MAX_SPREAD, clustered_mean  # noqa: E402

EXPORT_NAME = "quote_fills_classified_20260904T142200Z.csv"
BANDS = [("<=1c", 0, 1), ("2c", 2, 2), ("3-4c", 3, 4),
         ("5-9c", 5, 9), ("10-15c", 10, 15), (">15c (GATED)", 16, 999)]
PBANDS = [(-0.01, 0.20, "<20c"), (0.20, 0.35, "20-35c"),
          (0.35, 0.65, "35-65c"), (0.65, 0.80, "65-80c"), (0.80, 1.01, ">80c")]
COMPARISONS = {"n": 0}


def load(exports: Path) -> pd.DataFrame:
    d = pd.read_csv(exports / EXPORT_NAME).rename(columns={"pop": "population"})
    d["league"] = np.where(
        d.market_slug.str.contains("wnba", case=False), "WNBA", "CFB")
    d["s_c"] = (d.s_q * 100).round().astype(int)
    d["pnl_c"] = d.pnl * 100.0
    return d


def band_of(s: int) -> str:
    for lab, lo, hi in BANDS:
        if lo <= s <= hi:
            return lab
    return "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=REPO / "backups/exports")
    args = ap.parse_args()
    d = load(args.exports)
    c = d[d.league == "CFB"].copy()
    c["band"] = c.s_c.map(band_of)
    real = c[c.population == "real"]

    print("# The wide CFB board — a census of our own absence\n")
    print(f"Export `{EXPORT_NAME}` · CFB {len(c):,} settled fills · "
          f"{c.game_id.nunique()} games · real {len(real):,} / phantom "
          f"{(c.population=='phantom').sum():,}\n")

    print("## 0. The gate, which decides what this census means\n")
    print(f"Engine constant **MAX_SPREAD = {MAX_SPREAD}** — quoting is "
          f"refused above it. Observed max spread at quote: "
          f"**CFB {c.s_q.max():.2f}, WNBA {d[d.league=='WNBA'].s_q.max():.2f}**, "
          f"with **{(d.s_q > MAX_SPREAD).sum()} fills above the gate** in "
          f"{len(d):,}. Above 15c the absence is POLICY, not market "
          f"behaviour.\n")

    print("## 1. Counts by spread-at-quote band (counts before ratios)\n")
    print("| band | fills | real | phantom | real share | games | markets |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for lab, _lo, _hi in BANDS:
        g = c[c.band == lab]
        if not len(g):
            print(f"| {lab} | 0 | 0 | 0 | — | 0 | 0 |")
            continue
        nr = int((g.population == "real").sum())
        print(f"| {lab} | {len(g):,} | {nr:,} | {len(g)-nr:,} | "
              f"{nr/len(g)*100:.1f}% | {g.game_id.nunique()} | "
              f"{g.market_slug.nunique()} |")
    wide = real[real.s_c >= 5]
    print(f"\n**>=5c: {len(wide):,} real fills, {wide.game_id.nunique()} "
          f"games, {wide.market_slug.nunique()} markets** — the "
          f"near-zero prediction is refuted BELOW the gate. Real share "
          f"falls monotonically with width (48% at <=1c to ~20% at 5c+): "
          f"in wider cells most of what the simulator calls a fill is a "
          f"phantom.\n")

    print("## 2. Spread band x price band (ALL fills, then real)\n")
    for name, sub in (("ALL", c), ("REAL", real)):
        print(f"**{name}**\n")
        print("| band | " + " | ".join(p[2] for p in PBANDS) + " |")
        print("|---" * (len(PBANDS) + 1) + "|")
        for lab, _lo, _hi in BANDS:
            g = sub[sub.band == lab]
            cells = [str(int(((g.qp > lo) & (g.qp <= hi)).sum()))
                     for lo, hi, _n in PBANDS]
            print(f"| {lab} | " + " | ".join(cells) + " |")
        print()
    print("The 35-65c band that WAVE_STANDARD flags as never-sliced is in "
          "fact where most of our fills already are — it is well sampled "
          "on the SPREAD-tight side and empty only where the gate bites.\n")

    print("## 3. Settlement P&L by band, real fills, game-clustered\n")
    print("| band | fills | games | markets | mean | 95% CI | width |")
    print("|---|---:|---:|---:|---:|---|---:|")
    rows = [(lab, real[real.band == lab]) for lab, _l, _h in BANDS]
    rows.append(("WIDE >=5c", wide))
    rows.append((">=5c AND 35-65c", wide[wide.qp.between(0.35, 0.65)]))
    for lab, g in rows:
        if g.game_id.nunique() < 2:
            print(f"| {lab} | {len(g)} | {g.game_id.nunique()} | "
                  f"{g.market_slug.nunique()} | — | not computable | — |")
            continue
        cm = clustered_mean({k: list(v) for k, v in g.groupby("game_id").pnl_c})
        COMPARISONS["n"] += 1
        print(f"| {lab} | {len(g):,} | {g.game_id.nunique()} | "
              f"{g.market_slug.nunique()} | {cm.mean:+.2f}c | "
              f"[{cm.lo:+.2f}, {cm.hi:+.2f}] | {cm.hi-cm.lo:.2f}c |")
    print("\nEvery band shares the SAME 11 games, so these are not "
          "independent of each other or of the CFB aggregate; they are a "
          "decomposition, not replications. CI widths of 6-13c are the "
          "right order for settlement — the ~0.3c that would signal the "
          "capture identity appears nowhere.\n")

    print(f"---\n**Comparisons: {COMPARISONS['n']} game-clustered "
          f"intervals**, all on one 11-game sample; at 95% roughly one in "
          f"twenty would clear zero by chance, and nothing here is offered "
          f"as a finding about the market.\n")
    print("No in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
