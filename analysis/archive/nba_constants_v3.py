"""nba_constants_v3.json — the adopted stack after R4b: shrunk-fit sigma' + R2 shrink. g RETIRED.

Full-data fits of the ADOPTED estimands (the gates scored walk-forward
out-of-sample; these are the production constants of the adopted forms), per
the research agent's ruling 2 on R4's adoption. Version lineage in the file
header per the both-runs convention: v1 = pre-R4 (no g; superseded), v2 = g
as adopted (three-bucket table, fitted two-step with sigma_phase and the
shrink frozen). If R4b (the fitting-order fix) replaces g, v3 carries the
refit-sigma and retires it.

Reproduce:

    .venv/bin/python analysis/nba_constants_v3.py \
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
from nba_r4_harness import prep
from nba_r4b_harness import fit_sigma_shrunk


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", required=True)
    ap.add_argument("--plays", required=True)
    ap.add_argument("--out", default="analysis/nba_constants_v3.json")
    args = ap.parse_args()

    states = load_real(args.games, args.plays)
    games = pd.read_csv(args.games)
    st = prep(states, games)
    beta = fit_beta(st)
    s_glob, sig_table = fit_sigma_shrunk(st, beta)
    totals = fit_totals_table(build_boundary_states(args.games, args.plays))
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    payload = {
        "provenance": {
            "version": 3,
            "lineage": "v1 = pre-R4 (superseded). v2 = R4 g adopted (superseded). v3 = R4b "
                       "PASS (-0.000048 [-0.000073,-0.000024], 7 seasons, outright not "
                       "tie-break): sigma refit under the SHRUNK mean replaces sigma_phase+g; "
                       "g RETIRED. Parameters mean what they say.",
            "pins": [args.games, args.plays],
            "generator": "analysis/nba_constants_v3.py",
            "commit": commit,
            "date": "2026-09-02",
            "boundary": "PHYSICS-ONLY: fitted constant tables, never point-in-time claims. "
                        "Full-data fits of the ADOPTED estimands (R4b sigma-prime under the "
                        "shrunk mean, R2 shrink, R3b arm a); the gates scored walk-forward "
                        "out-of-sample. Calibration constants, never edge.",
        },
        "r4b_sigma_shrunk_fit": {"global_per_sqrt_min": s_glob,
                      "phase_table": {f"({lo},{hi}]": v for (lo, hi), v in sig_table.items()},
                      "applies": "sigma for the SHRUNK-mean stack: P = Phi((E+(1-s)dev)/(sigma'*sqrt(t)))"},
        "r2_shrink": {"gridpoints_elapsed": {str(k): v for k, v in beta.items()}, "beta_48": 0.0},
        "r3b_totals": {"share": {str(k): v for k, v in totals["share"].items()},
                       "b": {str(k): v for k, v in totals["b"].items()},
                       "sigma": {str(k): v for k, v in totals["sigma"].items()}},
    }
    Path(args.out).write_text(json.dumps(payload, indent=2))
    print(f"v3 written: sigma' global {s_glob:.3f}, phase "
          + "/".join(f"{v:.3f}" for v in sig_table.values())
          + "; g RETIRED; beta(4')={:.3f}".format(beta[4]))


if __name__ == "__main__":
    main()
