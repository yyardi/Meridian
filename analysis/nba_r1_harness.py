"""R1 — NBA win-curve sigma: the committed harness, pinned BEFORE first read.

Registration: docs/math/nba-constants-registrations.md (R1). This file pins
every formula, convention, and port-scaling choice so nothing is invented
after a number is seen. Standing terms honored here:

  - Walk-forward by season; ONLY out-of-sample seasons score.
  - Intervals cluster BY SEASON (the honest unit for a constant).
  - OT *states* excluded (no registered OT model); games reaching OT still
    score their regulation states against the eventual final winner.
  - PHYSICS-ONLY: fitted constant tables, never point-in-time claims.
  - Mutation (--selftest) runs before the first read of real data.

Reproduce:

    .venv/bin/python analysis/nba_r1_harness.py --selftest
    .venv/bin/python analysis/nba_r1_harness.py --games <games.csv> --plays <plays.csv.gz>

PINNED CONVENTIONS
==================

State and outcome
-----------------
margin m = home_score - away_score (home frame, always).
t = whole minutes remaining in regulation, evaluated on the grid t = 1..47.
The state at grid point t is the LAST play with minutes_left >= t (the state
entering that minute). y = 1 iff the home team wins the game (OT included in
the outcome; OT states never predicted on).

Anchor
------
p0 = de-vigged closing moneyline home probability, proportional de-vig:
p0 = q_h / (q_h + q_a) with q the implied probabilities of the raw prices.

The curve — IDENTICAL for every arm
-----------------------------------
    E_arm = sigma_arm(48) * sqrt(48) * PhiInv(p0)      # pregame margin implied
    P_arm(m, t) = Phi( (m + E_arm * t/48) / (sigma_arm(t) * sqrt(t)) )

E is derived through the arm's own sigma because a moneyline is a probability,
not a margin: each sigma table is thereby tested END-TO-END (its pregame
implication and its in-game decay) against the same de-vigged input. Flagged
to research before first read; a closing-spread-anchored variant runs as a
LABELED SENSITIVITY only, never the gate.

The three arms — sigma(t) tables in points per sqrt(minute)
-----------------------------------------------------------
(a) NBA-fitted, walk-forward: two-step MLE on training seasons only.
    Step 1: global sigma by Bernoulli MLE of the full curve (E inside).
    Step 2: E frozen from step 1; per-phase sigma by per-bucket MLE on
    t-buckets (36,48], (24,36], (12,24], (0,12]. The phase table is the arm;
    the global value and per-phase table BOTH report as the physics table.
(b) WNBA port. 2.628 is points per sqrt(minute) — A RATE, dimensionless in
    game length — so it needs NO 40->48 rescale; the trap would be porting
    the implied 16.6-point full-game sd. Its phase decay ports by QUARTER
    BOUNDARY CORRESPONDENCE (quarters are the structural unit both leagues
    share): sigma_b(t) is piecewise-linear through (36, 2.98), (24, 2.77),
    (12, 2.40) — the WNBA boundary-implied values — held flat at 2.98 for
    t > 36 and flat at 2.40 for t <= 12 (extrapolating the decay below the
    last measured boundary would be fitting by another name). The flat
    segment above 36 intentionally does NOT pass through the global 2.628:
    the boundary values ARE the decay; the global is not a boundary point.
(c) The 2.0 rule of thumb: sigma(t) = 2.0, flat.

Gate arithmetic
---------------
Per-state Brier per arm; pairwise per-state diffs; season-clustered mean and
95% CI via core.quote.adverse_selection.clustered_mean with clusters = the
EVALUATION SEASON (df = seasons - 1). A per-season table prints alongside.
PASS/adopt = one arm dominates BOTH others with CIs excluding zero.
Floors: >= 8 evaluated forward seasons. At 10 with no dominant arm:
INDISTINGUISHABLE-AT-POWER; pre-committed tie-break adopts (a), recorded as
adoption-by-tie-break, never superiority.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean

REG_MINUTES = 48.0
GRID = np.arange(1, 48)  # minutes remaining, 1..47
PHASES = [(36.0, 48.0), (24.0, 36.0), (12.0, 24.0), (0.0, 12.0)]  # (lo, hi] in t_left
SIGMA_BOUNDS = (0.5, 8.0)

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


# ------------------------------------------------------------------ sigma tables


def sigma_wnba_port(t: np.ndarray) -> np.ndarray:
    """Arm (b): WNBA boundary-implied decay, quarter-correspondence port."""
    return np.interp(t, [12.0, 24.0, 36.0], [2.40, 2.77, 2.98])  # np.interp clamps flat outside


def sigma_flat(value: float):
    return lambda t: np.full_like(np.asarray(t, dtype=float), value)


def sigma_phase_table(table: dict[tuple[float, float], float]):
    """Piecewise-constant sigma(t) from a per-phase table."""

    def f(t):
        t = np.asarray(t, dtype=float)
        out = np.empty_like(t)
        for (lo, hi), v in table.items():
            out[(t > lo) & (t <= hi)] = v
        out[t > PHASES[0][1]] = table[PHASES[0]]
        out[t <= 0] = table[PHASES[-1]]
        return out

    return f


# ------------------------------------------------------------------ the curve


def curve_prob(m: np.ndarray, t: np.ndarray, p0: np.ndarray, sigma_fn) -> np.ndarray:
    """The one registered curve. sigma_fn maps t_left -> points/sqrt(min)."""
    e = sigma_fn(np.full_like(np.asarray(t, dtype=float), REG_MINUTES)) * np.sqrt(REG_MINUTES) * norm.ppf(p0)
    z = (m + e * t / REG_MINUTES) / (sigma_fn(t) * np.sqrt(t))
    return norm.cdf(z)


def fit_arm_a(train: pd.DataFrame) -> tuple[float, dict[tuple[float, float], float]]:
    """Two-step MLE on TRAINING rows only. Returns (global sigma, phase table)."""
    m, t, p0, y = (train[c].to_numpy(float) for c in ["m", "t", "p0", "y"])

    def nll_global(s):
        p = np.clip(curve_prob(m, t, p0, sigma_flat(s)), 1e-9, 1 - 1e-9)
        return -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))

    s_glob = minimize_scalar(nll_global, bounds=SIGMA_BOUNDS, method="bounded").x

    # E frozen from the global fit; per-phase sigma by per-bucket MLE
    e = s_glob * np.sqrt(REG_MINUTES) * norm.ppf(p0)
    table = {}
    for lo, hi in PHASES:
        mask = (t > lo) & (t <= hi)
        mm, tt, ee, yy = m[mask], t[mask], e[mask], y[mask]

        def nll_phase(s):
            p = np.clip(norm.cdf((mm + ee * tt / REG_MINUTES) / (s * np.sqrt(tt))), 1e-9, 1 - 1e-9)
            return -np.sum(yy * np.log(p) + (1 - yy) * np.log(1 - p))

        table[(lo, hi)] = minimize_scalar(nll_phase, bounds=SIGMA_BOUNDS, method="bounded").x
    return float(s_glob), {k: float(v) for k, v in table.items()}


# ------------------------------------------------------------------ walk-forward


def walk_forward(states: pd.DataFrame) -> pd.DataFrame:
    """Fit (a) on seasons <= k, evaluate all arms on season k+1. Returns
    per-state eval rows with each arm's Brier. Only forward seasons appear."""
    seasons = sorted(states.season.unique())
    rows = []
    fitted = {}
    for i in range(1, len(seasons)):
        train = states[states.season.isin(seasons[:i])]
        ev = states[states.season == seasons[i]].copy()
        s_glob, table = fit_arm_a(train)
        fitted[seasons[i]] = {"global": s_glob, "table": table}
        arms = {
            "a": sigma_phase_table(table),
            "b": sigma_wnba_port,
            "c": sigma_flat(2.0),
        }
        for name, fn in arms.items():
            p = curve_prob(ev.m.to_numpy(float), ev.t.to_numpy(float), ev.p0.to_numpy(float), fn)
            ev[f"brier_{name}"] = (p - ev.y.to_numpy(float)) ** 2
        rows.append(ev)
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def gate_read(ev: pd.DataFrame) -> None:
    """Pairwise season-clustered diffs + per-season table + the verdict frame."""
    seasons = sorted(ev.season.unique())
    print(f"forward seasons evaluated: {len(seasons)} (floor >= 8): {seasons}")
    pairs = [("a", "b"), ("a", "c"), ("b", "c")]
    wins = {k: 0 for k in "abc"}
    for x, z in pairs:
        d = ev[f"brier_{x}"] - ev[f"brier_{z}"]
        cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
        verdict = ""
        if cm.hi < 0:
            verdict = f"{x} better, CI excludes zero"
            wins[x] += 1
        elif cm.lo > 0:
            verdict = f"{z} better, CI excludes zero"
            wins[z] += 1
        else:
            verdict = "CI straddles zero"
        print(f"  Brier({x})-Brier({z}): {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}]  "
              f"rows={cm.n} seasons={cm.n_clusters}  -> {verdict}")
    per = ev.groupby("season")[[f"brier_{k}" for k in "abc"]].mean()
    print("\nper-season mean Brier (a=NBA-fit, b=WNBA-port, c=2.0):")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    dominant = [k for k, w in wins.items() if w == 2]
    if len(seasons) < 8:
        print("\nVERDICT FRAME: below the 8-season floor — NO READ.")
    elif dominant:
        print(f"\nVERDICT FRAME: arm ({dominant[0]}) dominates both others with CIs excluding zero.")
    else:
        print("\nVERDICT FRAME: no arm dominates both others."
              + (" At 10 forward seasons this is INDISTINGUISHABLE-AT-POWER;"
                 " the pre-committed tie-break adopts (a) — recorded as"
                 " adoption-by-tie-break, never superiority." if len(seasons) >= 10 else ""))


# ------------------------------------------------------------------ data


def devig(ml_home: pd.Series, ml_away: pd.Series) -> pd.Series:
    """American moneylines -> proportional de-vigged home probability."""

    def implied(ml):
        ml = ml.astype(float)
        return np.where(ml < 0, -ml / (-ml + 100.0), 100.0 / (ml + 100.0))

    qh, qa = implied(ml_home), implied(ml_away)
    return pd.Series(qh / (qh + qa), index=ml_home.index)


def build_states(games: pd.DataFrame, plays: pd.DataFrame) -> pd.DataFrame:
    """Minute-grid states from plays. Requires games to already carry p0 and y.

    Play clock convention is bound at load time (see load_real); here plays
    carry `minutes_left` in regulation minutes (48 -> 0) and OT rows are
    already dropped. Grid state = last play with minutes_left >= t.
    """
    plays = plays.sort_values(["game_id", "minutes_left"], ascending=[True, False])
    frames = []
    for t in GRID:
        eligible = plays[plays.minutes_left >= t]
        snap = eligible.groupby("game_id").last().reset_index()
        snap["t"] = float(t)
        frames.append(snap[["game_id", "t", "m"]])
    states = pd.concat(frames, ignore_index=True)
    return states.merge(games[["game_id", "season", "p0", "y"]], on="game_id")


# ------------------------------------------------------------------ selftest


def _synth(seed: int, n_seasons=11, games_per=400, sigma_fn=None, shuffle=False):
    """Brownian-margin seasons with a moneyline consistent with the true curve."""
    rng = np.random.default_rng(seed)
    sigma_fn = sigma_fn or sigma_flat(2.6)
    rows, games = [], []
    gid = 0
    for season in range(n_seasons):
        for _ in range(games_per):
            e_true = rng.normal(0, 6)
            s48 = float(sigma_fn(np.array([REG_MINUTES]))[0])
            p0 = float(norm.cdf(e_true / (s48 * np.sqrt(REG_MINUTES))))
            # simulate margin minute-by-minute with per-minute sd = sigma(t)
            m = 0.0
            path = {}
            for t in range(47, -1, -1):  # after minute 48-t ... walk down
                drift = e_true / REG_MINUTES
                m += drift + float(sigma_fn(np.array([t + 1.0]))[0]) * rng.normal()
                path[t] = m
            y = 1.0 if m > 0 else 0.0
            games.append({"game_id": gid, "season": season, "p0": np.clip(p0, 0.02, 0.98), "y": y})
            for t in GRID:
                rows.append({"game_id": gid, "season": season, "t": float(t), "m": path[t], "p0": np.clip(p0, 0.02, 0.98), "y": y})
            gid += 1
    states = pd.DataFrame(rows)
    if shuffle:
        # permute the VALUES against the game_id index — a bare .sample(frac=1)
        # reorders rows but keeps index->value pairs, i.e. does not shuffle at all
        ys = states.groupby("game_id").y.first()
        states["y"] = states.game_id.map(pd.Series(rng.permutation(ys.to_numpy()), index=ys.index))
    return states


def _pair(ev: pd.DataFrame, x: str, z: str):
    d = ev[f"brier_{x}"] - ev[f"brier_{z}"]
    return clustered_mean({s: d[ev.season == s].tolist() for s in ev.season.unique()})


def _score(ev: pd.DataFrame, arms: dict) -> pd.DataFrame:
    ev = ev.copy()
    for name, fn in arms.items():
        p = curve_prob(ev.m.to_numpy(float), ev.t.to_numpy(float), ev.p0.to_numpy(float), fn)
        ev[f"brier_{name}"] = (p - ev.y.to_numpy(float)) ** 2
    return ev


def selftest() -> None:
    """Mutation-test the instrument before any real data.

    1. Walk-forward fitter recovers a known sigma within tolerance.
    2. Distorted tables LOSE to the truth — in BOTH directions (x1.5 wider
       and /1.5 narrower), CI excluding zero each way.
    3. Generator-recovery: data generated under table X, the harness awards
       the win to X over a rival table — run for both a flat-2.0 generator
       (vs the WNBA port) and a WNBA-port generator (vs flat 2.0). This is
       the artifact-free null-family check: the win must follow the
       generator, not any fixed arm.
    4. Shuffled-outcome null: the SHARPER (narrower-sigma) table must never
       win. NOTE, flagged to research before first read: the registration's
       literal 'no arm dominating' is unsatisfiable under Brier for arms of
       unequal sharpness — destroyed signal mechanically rewards the flatter
       table — so this clause asserts the known artifact direction instead,
       and test 3 carries the discrimination burden the null was meant to.
    """
    ok = True
    states = _synth(11)
    seasons = sorted(states.season.unique())

    train = states[states.season.isin(seasons[:5])]
    s_glob, table = fit_arm_a(train)
    print(f"[1] fitter on sigma_true=2.6 synthetic: global {s_glob:.3f}, phases "
          + ", ".join(f"{v:.3f}" for v in table.values()))
    ok &= abs(s_glob - 2.6) < 0.15

    ev = _score(states[~states.season.isin(seasons[:5])],
                {"true": sigma_flat(2.6), "wide": sigma_flat(2.6 * 1.5), "narrow": sigma_flat(2.6 / 1.5)})
    for rival in ["wide", "narrow"]:
        cm = _pair(ev, "true", rival)
        print(f"[2] true vs {rival}: {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] (want hi<0)")
        ok &= cm.hi < 0

    for gen_name, gen_fn, rival_name, rival_fn in [
        ("flat2.0", sigma_flat(2.0), "wnba-port", sigma_wnba_port),
        ("wnba-port", sigma_wnba_port, "flat2.0", sigma_flat(2.0)),
    ]:
        # games_per matches the real cohort (~1,200 games/season) so this
        # doubles as a power statement: separability at the size we'll have
        g = _synth(seed=int(sum(map(ord, gen_name))), sigma_fn=gen_fn, games_per=1200)
        evg = _score(g[~g.season.isin(seasons[:5])], {"gen": gen_fn, "rival": rival_fn})
        cm = _pair(evg, "gen", "rival")
        print(f"[3] generated under {gen_name}, vs {rival_name}: {cm.mean:+.5f} "
              f"[{cm.lo:+.5f}, {cm.hi:+.5f}] (want hi<0)")
        ok &= cm.hi < 0

    sh = _synth(11, shuffle=True)
    ev = _score(sh[~sh.season.isin(seasons[:5])],
                {"sharp": sigma_flat(2.6 / 1.5), "true": sigma_flat(2.6)})
    cm = _pair(ev, "sharp", "true")
    print(f"[4] shuffled null, sharper-vs-true: {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] "
          f"(sharper must NOT win: want lo not > 0 in sharp's favour, i.e. hi>0 or straddle)")
    ok &= not (cm.hi < 0)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games", help="pinned games CSV")
    ap.add_argument("--plays", help="pinned plays CSV(.gz)")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")
    raise SystemExit(
        "load_real is bound after the manager pins the export and names the "
        "clock and odds conventions; the formulas above are frozen regardless."
    )


if __name__ == "__main__":
    main()
