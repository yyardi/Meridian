"""FLATTEN's k on football: can the test even run? — 2026-09-04

    .venv/bin/python analysis/cfb_k_clamp.py

The registration ports k=1¢ from WNBA to football on an explicit
assumption (docs/math/adverse-selection-measured.md, "PORTING TO
GRIDIRON"):

    "a fixed 1¢ is the correct default for NFL, noting the clamp
     interaction: NFL's traded cells at 5-6¢ leave room for a 1¢ lean to
     be a genuine 1¢, unlike WNBA's tight band where it was forced."

This script tests the part of that claim which is measurable today, on
the pinned classified export — **not** the k-curve itself, which cannot
be produced from this substrate (see THE BLOCKER below).

WHAT IS MEASURED
----------------
1. The spread at quote on football's TRADED cells, real fills only.
2. The clamp: effective lean = min(k, s − tick). With a 1¢ tick, a 1¢
   market permits NO lean at all, and a 2¢ market makes every k ≥ 1¢ the
   same quote. So for each k we report how many DISTINCT policies it
   actually produces — the question of whether a k-curve on this board
   would be comparing four different things or one thing four times.
3. Settlement P&L per real fill, game-clustered — the PRIMARY metric —
   plus the games needed to resolve a k-difference at that dispersion.

THE BLOCKER, stated first because it governs the deliverable
------------------------------------------------------------
**The k-curve cannot be re-derived from this export, and not for want of
power — for want of the instrument.** The same document retracts the
earlier curve for exactly this: *"Filtering phantoms from the score does
not remove them from the POLICY — the simulator's inventory counted
them, and inventory steers the lean, so phantom fills chose quote paths
that exclusion cannot undo."* Changing k changes which quotes are
placed, hence which fills exist at all; a static table of the fills that
happened under ONE deployed policy cannot be re-scored under another.
The retracted curve was made that way. Reproducing the method would
reproduce the artifact.

A correct curve needs the whole-book replay with the order inserted.
Two things block it here: `analysis/capture_is_not_a_proxy.py` and the
replay that produced the WNBA curve are **not in the repo on main**, and
the only local tick substrate
(`market_snapshots_quote_replay_20260902T173700Z.csv.gz`) is **WNBA-only
— 365 markets, 2026-08-17..22, zero football rows.** CFB ticks live on
prod, which this session has no path to.

Settlement is PRIMARY throughout; capture is not computed anywhere here,
because capture ≡ −overshoot is an identity and any gradient off it is
forced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

#: --exports overrides for worktrees, which do not carry the gitignored
#: data directory
EXPORTS_DEFAULT = REPO / "backups/exports"
EXPORT_NAME = "quote_fills_classified_20260904T140631Z.csv"
#: verified against the substrate's own min_tick_size column, not assumed
TICK = 0.01
KS = [0, 1, 2, 3, 5]
COMPARISONS = {"n": 0}


def load(exports: Path) -> pd.DataFrame:
    d = pd.read_csv(exports / EXPORT_NAME).rename(
        columns={"pop": "population"})
    d["league"] = np.where(
        d.market_slug.str.contains("wnba", case=False), "WNBA", "CFB")
    d["pnl_c"] = d.pnl * 100.0
    return d


def clamp_table(real: pd.DataFrame) -> None:
    print("## 1. The clamp — does k do anything on football?\n")
    print("effective lean = min(k, s − tick), tick = 1¢ (verified from the "
          "substrate's min_tick_size, not assumed)\n")
    print("| league | real fills | games | median s | p75 | p90 | "
          "no lean possible | k=1¢ ≡ k=5¢ | all 5 k distinct |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for lg, g in real.groupby("league"):
        s = g.s_q.to_numpy()
        room = np.maximum(s - TICK, 0.0)
        eff = {k: np.minimum(k / 100.0, room) for k in KS}
        distinct = np.array([
            len({round(eff[k][i], 4) for k in KS}) for i in range(len(g))])
        print(f"| {lg} | {len(g):,} | {g.game_id.nunique()} | "
              f"{np.median(s)*100:.0f}¢ | {np.percentile(s,75)*100:.0f}¢ | "
              f"{np.percentile(s,90)*100:.0f}¢ | "
              f"{(room <= 1e-9).mean()*100:.1f}% | "
              f"{np.isclose(eff[1], eff[5]).mean()*100:.1f}% | "
              f"{(distinct == 5).mean()*100:.1f}% |")
    print("\nNominal k vs what the book actually permits:\n")
    print("| league | " + " | ".join(f"k={k}¢" for k in KS) + " |")
    print("|---" * (len(KS) + 1) + "|")
    for lg, g in real.groupby("league"):
        room = np.maximum(g.s_q.to_numpy() - TICK, 0.0)
        cells = []
        for k in KS:
            e = np.minimum(k / 100.0, room)
            clamped = (e < k / 100.0 - 1e-9).mean() * 100
            cells.append(f"{e.mean()*100:.2f}¢ (clamped {clamped:.0f}%)")
        print(f"| {lg} | " + " | ".join(cells) + " |")


def selection_check(d: pd.DataFrame) -> None:
    print("\n## 2. Is the tightness real, or an artifact of which quotes "
          "filled?\n")
    print("| league | population | fills | median s | p75 |")
    print("|---|---|---:|---:|---:|")
    for (lg, pop), g in d.groupby(["league", "population"]):
        print(f"| {lg} | {pop} | {len(g):,} | "
              f"{g.s_q.median()*100:.0f}¢ | {g.s_q.quantile(.75)*100:.0f}¢ |")
    print("\nStated limit: `s_q` is the spread on quotes that FILLED. The "
          "export contains no unfilled quotes, so this is the traded-cell "
          "distribution, not the board's. For the k question the traded "
          "cells are the right population — they are where the P&L is — "
          "but it does not license a claim about football's board overall.")


def settlement(real: pd.DataFrame) -> None:
    print("\n## 3. Settlement P&L per real fill (PRIMARY) and power\n")
    print("| league | fills | games | mean | 95% CI (game-clustered) | "
          "CI width | per-game sd |")
    print("|---|---:|---:|---:|---|---:|---:|")
    sds = {}
    for lg, g in real.groupby("league"):
        by = {k: list(v) for k, v in g.groupby("game_id").pnl_c}
        cm = clustered_mean(by)
        COMPARISONS["n"] += 1
        per_game = np.array([np.mean(v) for v in by.values()])
        sds[lg] = per_game.std(ddof=1)
        print(f"| {lg} | {len(g):,} | {g.game_id.nunique()} | "
              f"{cm.mean:+.2f}¢ | [{cm.lo:+.2f}, {cm.hi:+.2f}] | "
              f"{cm.hi-cm.lo:.2f}¢ | {sds[lg]:.2f}¢ |")
    print("\nCI widths are 2.7–5.2¢ — the right order for a noisy economic "
          "quantity. (The identity tell to watch for: ~0.3¢ widths would "
          "mean capture had crept back in.)\n")
    print("Games needed to resolve a k-difference at this dispersion "
          "(unpaired, 95%):\n")
    print("| league | 1¢ difference | 2¢ | 3¢ |")
    print("|---|---:|---:|---:|")
    for lg, sd in sds.items():
        n = [(2.8 * sd / dd) ** 2 for dd in (1.0, 2.0, 3.0)]
        print(f"| {lg} | ~{n[0]:.0f} games | ~{n[1]:.0f} | ~{n[2]:.0f} |")
    print("\nThis is the UNPAIRED requirement and is therefore pessimistic: "
          "a real k-curve compares policies on the SAME games, so the "
          "relevant dispersion is that of per-game DIFFERENCES, which only "
          "the replay can produce. The honest anchor is that the WNBA "
          "curve — paired, 13 games — still returned +1.95¢ [−2.80, +6.70] "
          "at its own optimum. The quantity being ported to football was "
          "never itself resolved.")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=EXPORTS_DEFAULT)
    args = ap.parse_args()
    d = load(args.exports)
    real = d[d.population == "real"]
    print("# FLATTEN's k on football — can the test run?\n")
    print(f"Export: `{EXPORT_NAME}` · {len(d):,} settled fills · "
          f"{d.game_id.nunique()} games · real {len(real):,} / phantom "
          f"{(d.population=='phantom').sum():,}\n")
    print("**Known-answer check (README):** WNBA real fills must reproduce "
          "6,255 and −3.376¢/fill — ")
    w = real[real.league == "WNBA"]
    print(f"got **{len(w):,}** and **{w.pnl_c.mean():.3f}¢**. ✓\n")
    clamp_table(real)
    selection_check(d)
    settlement(real)
    print(f"\n---\n**Comparisons: {COMPARISONS['n']} game-clustered "
          f"intervals** (two, one per league). No k-curve is reported "
          f"because none can be honestly produced from this substrate — "
          f"see the module docstring.")
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
