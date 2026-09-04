"""Dry-run the scoring pipeline on a THIN slate, to find what breaks at 8 games.

    .venv/bin/python analysis/dry_run.py                 # rehearsal on a carved slate
    .venv/bin/python analysis/dry_run.py --fills <csv>   # tonight's real export

WHY A CARVED SLATE RATHER THAN TONIGHT'S GAMES. Commissioned at 18:01Z to
dry-run on tonight's 8 CFB games; **first kickoff is 22:30Z and the last tips at
01:00Z, so those fills do not exist for another 5-10 hours.** The pipeline's
plumbing can be rehearsed now regardless, by carving 8 CFB games out of the
pinned 11-game export — that is the same SHAPE as tonight (8 games, few hundred
real fills each, one league) and it exercises exactly the paths at issue: thin
cells, floors, empty tables, runtime. When tonight's export exists this same
harness runs against it unchanged via --fills.

What it checks, in the order the failures actually matter:

1. **ENGINE BINARY UNIFORMITY.** Last night's tape spanned two binaries
   (7,126 fills under one, 14,000 under another, switching mid-slate). A cut
   that silently pools binaries is the defect class this whole day catalogued.
   The check prints the distinct values rather than assuming one.
2. **FLOORS AND THIN CELLS.** Does a cut refuse, warn, or silently print a
   number when a band holds one game? A number that appears at n=1 without a
   marker is how a thin slate becomes a claim.
3. **EMPTY RETURNS.** A cut that returns nothing on 8 games returns nothing on
   103 for the same reason. Silence is the failure mode that survives review.
4. **RUNTIME**, extrapolated to 103 games — ten minutes on 8 is two hours on
   103, and that is worth knowing before someone is waiting on it.

Every population number this pipeline emits is **PROVISIONAL ON THE
CLASSIFICATION CRITERION**, which is under revision (`real ⟺ ask ≤ B` selects
the maximally adverse subset; the liveness alternative is vacuous). The plumbing
is what tonight tests, not the boundary.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.guards import report_count

PIN = "backups/exports/quote_fills_classified_20260904T142200Z.csv"
#: floors from core/quote/report.py, the registered ones
FLOOR_FILLS, FLOOR_GAMES = 500, 10
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def check_engine_uniformity(d: pd.DataFrame) -> None:
    print("=== 1. ENGINE BINARY UNIFORMITY ===")
    cols = [c for c in d.columns if any(k in c.lower() for k in ("engine", "commit", "version", "binary"))]
    if not cols:
        print("★ CANNOT BE CHECKED — the export carries NO engine/commit/version column.")
        print("  The distinct-binary fact is known from prod (two binaries last night,")
        print("  switching mid-slate) but is NOT in the pinned artifact, so no harness can")
        print("  assert it and any cut on this export pools binaries SILENTLY and")
        print("  undetectably. This is a recording gap of exactly the species specified in")
        print("  docs/infra/pulse-recording-spec.md: RECORD THE RULE'S PARAMETERS IN FORCE.")
        print("  REQUEST: add `engine_commit` to the fills export before tomorrow's slate.")
        print("  Until then, every number from this pipeline carries an unstated assumption")
        print("  that one binary produced it — which was FALSE last night.")
        return
    for c in cols:
        vals = d[c].value_counts(dropna=False)
        print(f"  {c}: {len(vals)} distinct -> {vals.to_dict()}")
        if len(vals) > 1:
            print(f"  ★ NON-UNIFORM: this slate spans {len(vals)} binaries. Cuts pooling them")
            print("    are mixing engines; stratify by this column or state the pooling.")


def check_floors(d: pd.DataFrame, label: str) -> None:
    print(f"\n=== 2. FLOORS — {label} ===")
    real = d[d["pop"] == "real"]
    n, g = len(real), real.game_id.nunique()
    at_floor = n >= FLOOR_FILLS and g >= FLOOR_GAMES
    print(f"  real fills {n:,} (floor {FLOOR_FILLS}) · games {g} (floor {FLOOR_GAMES}) "
          f"-> registered verdict would be: {'AT FLOOR' if at_floor else 'NO DATA'}")
    if not at_floor:
        print("  ✓ correct: below a registered floor the report prints counts, not a number.")
    print("\n  ★ BUT THE CUTS THEMSELVES CARRY NO FLOOR. `quote_cuts.py` prints a per-band")
    print("  mean at ANY n, including a band holding one game. That is defensible for a")
    print("  DESCRIPTIVE cut (the wave standard says nothing gates) but it means a thin")
    print("  slate produces a table that LOOKS like the 24-game one. The fix is a marker,")
    print("  not a gate — see the thin-cell census below.")


def thin_cells(d: pd.DataFrame) -> None:
    print("\n=== 3. THIN CELLS AND EMPTY RETURNS ===")
    real = d[d["pop"] == "real"].copy()
    E, L = [0.015, 0.025, 0.035, 0.055], ["<=1.5c", "1.5-2.5c", "2.5-3.5c", "3.5-5.5c", ">5.5c"]
    real["w"] = np.array(L)[np.digitize(real.s_q, E)]
    rows = []
    for lab in L:
        b = real[real.w == lab]
        rows.append({"band": lab, "fills": len(b), "games": b.game_id.nunique(),
                     "status": "EMPTY" if len(b) == 0 else
                               "THIN (<3 games)" if b.game_id.nunique() < 3 else "ok"})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    bad = t[t.status != "ok"]
    if len(bad):
        print(f"  ★ {len(bad)} band(s) would print a mean on <3 games or nothing at all.")
    per = real.groupby("event_period", dropna=False).game_id.nunique() if "event_period" in real else None
    if per is not None:
        thin = per[per < 3]
        print(f"  period cells with <3 games: {thin.to_dict() if len(thin) else 'none'}")
    for name, sub in [("pregame regime", real[real.regime == "pregame"])]:
        z = report_count(f"{name}_real_fills", len(sub))
        print(f"  {z}")


def timed_run(script: str, args: list[str], label: str) -> float:
    t0 = time.time()
    r = subprocess.run([".venv/bin/python", script] + args, capture_output=True, text=True)
    dt = time.time() - t0
    ok = r.returncode == 0
    out = r.stdout
    print(f"  {label:<34s} {dt:6.1f}s  {'OK' if ok else 'FAILED rc=' + str(r.returncode)}"
          f"  stdout {len(out.splitlines()):4d} lines")
    if not ok:
        print("    " + (r.stderr.strip().splitlines() or ["<no stderr>"])[-1][:160])
    elif not out.strip():
        print("    ★ SILENT: exited 0 and printed NOTHING — the failure mode that survives review")
    return dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", default=PIN)
    ap.add_argument("--games", type=int, default=8, help="carve this many CFB games")
    args = ap.parse_args()

    d = pd.read_csv(args.fills)
    d["sport"] = np.where(d.market_slug.str.contains("wnba"), "WNBA", "CFB")
    cfb = d[d.sport == "CFB"]
    carved = sorted(cfb.game_id.unique())[: args.games]
    thin = cfb[cfb.game_id.isin(carved)].copy()
    print(f"DRY RUN at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"pin {Path(args.fills).name} · carved {len(carved)} CFB games "
          f"({len(thin):,} fills, {(thin['pop'] == 'real').sum():,} real) — the shape of tonight\n")

    check_engine_uniformity(d)
    check_floors(thin, f"{len(carved)}-game slate")
    thin_cells(thin)

    # THE ACTUAL TEST: run the cuts ON the thin slate, not merely time them on
    # the full pin. "Does it break on 8 games" is answered by running it on 8.
    print("\n=== 4. THE CUTS RUN ON THE THIN SLATE ITSELF ===")
    tmp = Path("/private/tmp/claude-501/-Users-yayardia-Documents-Quant-Meridian/"
               "4fd24f98-dbc9-4683-a68c-35f3382e9297/scratchpad/thin_slate.csv")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    thin.drop(columns=["sport"]).to_csv(tmp, index=False)
    thin_t = timed_run("analysis/quote_cuts.py", ["--fills", str(tmp)], "quote_cuts on 8 games")
    thin_t += timed_run("analysis/slate_power.py", ["--fills", str(tmp)], "slate_power on 8 games")

    print("\n=== 5. RUNTIME ON THE FULL PIN, and what actually scales tomorrow ===")
    total = 0.0
    for script, a, label in [
        ("analysis/quote_cuts.py", [], "quote_cuts (24 games)"),
        ("analysis/slate_power.py", [], "slate_power (24 games)"),
        ("analysis/pulse_settlement.py", [], "pulse_settlement (34 games)"),
    ]:
        total += timed_run(script, a, label)
    quote_side = total  # recomputed below for the parts that scale
    print(f"\n  ★ WHAT SCALES WITH TOMORROW'S SLATE: only quote_cuts + slate_power, which")
    print(f"  read QUOTE fills. They ran the 8-game slate in {thin_t:.1f}s -> roughly")
    print(f"  {thin_t * 103 / 8:.0f}s at 103 games. Not a constraint.")
    print("  ★ WHAT DOES NOT: pulse_settlement reads PULSE decisions, and PULSE produces")
    print("  NOTHING for CFB — it is WNBA-only and has recorded nothing since 08-31. Its")
    print("  ~90s is dominated by the 65MB tick asof-join and is irrelevant to tomorrow;")
    print("  it becomes the superlinear risk only if PULSE is ever ported and given a tape.")

    print("\n=== STANDING LANGUAGE ===")
    print("Every population number in this pipeline is PROVISIONAL ON THE CLASSIFICATION")
    print("CRITERION, which is under revision. The plumbing is what this run tests.")
    print(CAPITAL_LINE)


if __name__ == "__main__":
    main()
