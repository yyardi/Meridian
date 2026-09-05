"""nba_constants_v2.json — the adopted stack after R4: R1b sigma + R2 shrink + R4 g.

Full-data fits of the ADOPTED estimands (the gates scored walk-forward
out-of-sample; these are the production constants of the adopted forms), per
the research agent's ruling 2 on R4's adoption. Version lineage in the file
header per the both-runs convention: v1 = pre-R4 (no g; superseded), v2 = g
as adopted (three-bucket table, fitted two-step with sigma_phase and the
shrink frozen). If R4b (the fitting-order fix) replaces g, v3 carries the
refit-sigma and retires it.

Reproduce:

    .venv/bin/python analysis/nba_constants_v2.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nba_r1_harness import fit_arm_a, load_real, sigma_phase_table
from nba_r2_harness import fit_beta
from nba_r3_harness import build_boundary_states
from nba_r3_harness import fit_table as fit_totals_table
from nba_r4_harness import Z_EDGES, fit_g, prep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--plays", required=True)
    ap.add_argument("--out", default="analysis/nba_constants_v2.json")
    args = ap.parse_args()

    states = load_real(args.games, args.plays)
    games = pd.read_csv(args.games)
    st = prep(states, games)
    s_glob, sig_table = fit_arm_a(st)
    sigma_fn = sigma_phase_table(sig_table)
    beta = fit_beta(st)
    g = fit_g(st, sigma_fn, beta)
    totals = fit_totals_table(build_boundary_states(args.games, args.plays))
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    payload = {
        "provenance": {
            "version": 2,
            "lineage": "v1 = pre-R4 (no g; superseded by this file). v2 = R4 g adopted "
                       "(PASS -0.000548 [-0.000821,-0.000275], 7 seasons). If R4b replaces "
                       "g, v3 carries the refit-sigma and retires it.",
            "pins": [args.games, args.plays],
            "generator": "analysis/nba_constants_v2.py",
            "commit": commit,
            "date": "2026-09-02",
            "boundary": "PHYSICS-ONLY: fitted constant tables, never point-in-time claims. "
                        "Full-data fits of the ADOPTED estimands (R1b arm a, R2 shrink, R4 g, "
                        "R3b arm a); the gates scored walk-forward out-of-sample. Calibration "
                        "constants, never edge. Amendment-6 caveat travels: g is an EFFECTIVE "
                        "parameter (mostly the missing sigma-refit for the shrunk stack), not "
                        "decided-ness physics.",
        },
        "r1b_sigma": {"global_per_sqrt_min": s_glob,
                      "phase_table": {f"({lo},{hi}]": v for (lo, hi), v in sig_table.items()}},
        "r2_shrink": {"gridpoints_elapsed": {str(k): v for k, v in beta.items()}, "beta_48": 0.0},
        "r4_g": {"z_edges": Z_EDGES,
                 "buckets": {"z<0.5": g[0], "0.5<=z<1.5": g[1], "z>=1.5": g[2]},
                 "applies": "sigma_R4(t) = sigma_phase(t) * g(bucket(z)); z from the "
                            "anchored UNSHRUNK expectation per the registration"},
        "r3b_totals": {"share": {str(k): v for k, v in totals["share"].items()},
                       "b": {str(k): v for k, v in totals["b"].items()},
                       "sigma": {str(k): v for k, v in totals["sigma"].items()}},
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"v2 written: sigma global {s_glob:.3f}, phase "
          + "/".join(f"{v:.3f}" for v in sig_table.values())
          + "; g " + "/".join(f"{g[b]:.3f}" for b in range(3))
          + "; beta(4')={:.3f}".format(beta[4]))


if __name__ == "__main__":
    main()
