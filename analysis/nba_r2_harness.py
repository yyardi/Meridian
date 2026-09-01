"""R2 — NBA reversion-shrink curve: the committed harness, pinned BEFORE first read.

Registration: docs/math/nba-constants-registrations.md (R2). Built against the
SPREAD-ANCHORED deviation (the WNBA #89/#89-fg form: closing-spread anchor,
play-level margins) — the anchor question was put to research before any read;
this file computes nothing until that ruling lands. Team-blind anchors invert
reversion results (#16/#17), so no anchor-free form is invented here.

Reproduce:

    .venv/bin/python analysis/nba_r2_harness.py --selftest
    .venv/bin/python analysis/nba_r2_harness.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz

PINNED FORMULAS
===============

Deviation frame (home-frame throughout, E = -closing_spread per R1b's verified
convention):

    elapsed   = 48 - t
    dev_t     = m_t - E * elapsed/48          # deviation from prorated spread
    dev_final = home_margin_final - E

Estimand: beta(g) at 12 gridpoints, elapsed g = 4, 8, ..., 48. beta(48) = 0
FORCED by construction (banked points cannot revert); the 11 points g <= 44
are fitted. Per gridpoint the state is the LAST play with elapsed <= g (the
same snap as R1's minute grid at t = 48 - g). Fit: no-intercept OLS of
(dev_final - dev_t) on dev_t, beta = -slope; an intercept variant prints as
robustness, never gating.

The shrink enters the R1b-adopted anchored FV as

    s(elapsed): piecewise-linear through the fitted (g, beta_g), flat before
                g=4, linear from (44, beta_44) to the forced (48, 0)
    expected_final = E + (1 - s(elapsed)) * dev_t      # == m + E*t/48 - s*dev
    P_shrunk = Phi(expected_final / (sigma_a(t) sqrt(t)))
    P_plain  = Phi((E + dev_t)     / (sigma_a(t) sqrt(t)))

sigma_a is R1b's arm (a) phase table refit per fold on the SAME training
seasons, so shrunk-vs-plain isolates the shrink term alone.

Walk-forward: spread-covered seasons only (2015-2022, 2025). Eval 2016-2022
(train = prior covered seasons) + 2025 PARTIAL (train <= 2022) = 8 forward
seasons, EXACTLY the >= 8 floor. The closure clause's "at 10 forward seasons"
is unreachable at this coverage — flagged to research with the anchor
question; what happens at 8 with a straddling CI is research's to name.

Gate: paired per-state Brier (shrunk - plain) on eval states t = 1..47,
season-clustered via clustered_mean, clusters = evaluation season.
PASS = CI excludes zero in the shrink's favour; FAIL = excludes zero against.
BOTH pre-named readings print with the result: a ~0 read is REDUNDANCY OF
FORM (the anchor's drift term already pulls toward pregame expectation), a
finding about the FV's arithmetic, not absence of the physics.

The physics table beta(g) reports REGARDLESS of gate outcome: per-season
fits, mean and t-interval across seasons (df = seasons - 1) — the
season-clustered CI on a constant.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, t as tdist

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean
from nba_r1_harness import (
    GRID,
    PARTIAL_SEASON,
    REG_MINUTES,
    fit_arm_a,
    load_real,
    sigma_phase_table,
)

GRIDPOINTS = np.arange(4, 45, 4)  # fitted: elapsed 4..44; beta(48)=0 forced
EVAL_SEASONS_R2 = [2016, 2017, 2018, 2019, 2020, 2021, 2022]

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


# ------------------------------------------------------------------ beta fit


def add_dev(states: pd.DataFrame, finals: pd.DataFrame) -> pd.DataFrame:
    st = states.merge(finals, on="game_id")
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    st["dev_final"] = st.home_margin - st.e
    return st


def fit_beta(st: pd.DataFrame, intercept: bool = False) -> dict[int, float]:
    """beta(g) per gridpoint from states snapped at t = 48 - g."""
    out = {}
    for g in GRIDPOINTS:
        sub = st[st.t == REG_MINUTES - g]
        x = sub.dev.to_numpy(float)
        yv = (sub.dev_final - sub.dev).to_numpy(float)
        if intercept:
            slope = np.polyfit(x, yv, 1)[0]
        else:
            slope = np.sum(x * yv) / np.sum(x * x)
        out[int(g)] = float(-slope)
    return out


def shrink_fn(beta: dict[int, float]):
    """s(elapsed): piecewise-linear through fitted points, flat before 4,
    linear to the forced (48, 0)."""
    xs = list(GRIDPOINTS.astype(float)) + [REG_MINUTES]
    ys = [beta[int(g)] for g in GRIDPOINTS] + [0.0]

    def f(elapsed):
        return np.interp(np.asarray(elapsed, dtype=float), xs, ys)  # clamps flat outside

    return f


def score_arms(ev: pd.DataFrame, beta: dict[int, float], sigma_fn) -> pd.DataFrame:
    ev = ev.copy()
    t = ev.t.to_numpy(float)
    e = ev.e.to_numpy(float)
    dev = ev.dev.to_numpy(float)
    y = ev.y.to_numpy(float)
    denom = sigma_fn(t) * np.sqrt(t)
    s = shrink_fn(beta)(ev.elapsed.to_numpy(float))
    ev["brier_shrunk"] = (norm.cdf((e + (1 - s) * dev) / denom) - y) ** 2
    ev["brier_plain"] = (norm.cdf((e + dev) / denom) - y) ** 2
    return ev


# ------------------------------------------------------------------ walk-forward + gate


def walk_forward_r2(st: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(st.season.unique())
    folds = [(s, [x for x in seasons if x < s]) for s in EVAL_SEASONS_R2 if s in seasons]
    if PARTIAL_SEASON in seasons:
        folds.append((PARTIAL_SEASON, [x for x in seasons if x <= 2022]))
    rows, fitted = [], {}
    for eval_season, train_seasons in folds:
        train = st[st.season.isin(train_seasons)]
        ev = st[st.season == eval_season]
        beta = fit_beta(train)
        _, sigma_table = fit_arm_a(train)
        fitted[eval_season] = {"beta": beta, "train": train_seasons}
        rows.append(score_arms(ev, beta, sigma_phase_table(sigma_table)))
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def physics_table(st: pd.DataFrame) -> None:
    """Per-season beta fits; mean and t-interval across seasons. Reports
    REGARDLESS of the gate outcome."""
    seasons = sorted(st.season.unique())
    per = {s: fit_beta(st[st.season == s]) for s in seasons}
    per_i = {s: fit_beta(st[st.season == s], intercept=True) for s in seasons}
    n = len(seasons)
    tcrit = tdist.ppf(0.975, df=n - 1)
    print(f"THE PHYSICS TABLE — beta(g), per-season fits, {n} seasons, t-interval df={n - 1}")
    print("  g(elapsed)  mean beta   95% CI              no-int vs intercept   per-season range")
    for g in GRIDPOINTS:
        vals = np.array([per[s][int(g)] for s in seasons])
        vi = np.array([per_i[s][int(g)] for s in seasons])
        m, se = vals.mean(), vals.std(ddof=1) / np.sqrt(n)
        print(f"  {g:>4d}       {m:+.4f}   [{m - tcrit * se:+.4f}, {m + tcrit * se:+.4f}]   "
              f"{m:+.4f} / {vi.mean():+.4f}      [{vals.min():+.4f}, {vals.max():+.4f}]")
    print("  48         +0.0000   forced by construction — banked points cannot revert")


def gate_read_r2(ev: pd.DataFrame) -> None:
    seasons = sorted(ev.season.unique())
    label = lambda s: f"{s}(PARTIAL)" if s == PARTIAL_SEASON else str(s)
    print(f"forward seasons evaluated: {len(seasons)} (floor >= 7 of 8 available, "
          f"per the 2026-09-02 amendment): {[label(s) for s in seasons]}")
    d = ev.brier_shrunk - ev.brier_plain
    cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
    print(f"\npaired Brier (shrunk - plain), season-clustered (negative favours the shrink):")
    print(f"  {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}]  rows={cm.n} seasons={cm.n_clusters}")
    per = ev.groupby("season").apply(
        lambda f: pd.Series({"shrunk": f.brier_shrunk.mean(), "plain": f.brier_plain.mean()}),
        include_groups=False)
    per.index = [label(s) for s in per.index]
    print("\nper-season mean Brier:")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    if len(seasons) < 7:
        print("\nVERDICT FRAME: below the 7-season floor — NO READ.")
    elif cm.hi < 0:
        print("\nVERDICT FRAME: PASS — CI excludes zero in the shrink's favour.")
    elif cm.lo > 0:
        print("\nVERDICT FRAME: FAIL — CI excludes zero against the shrink.")
    else:
        print("\nVERDICT FRAME: CI straddles zero. Pre-named reading applies: REDUNDANCY OF"
              "\nFORM — the anchor's drift term already encodes the pull toward pregame"
              "\nexpectation; a finding about the FV's arithmetic, not absence of the physics."
              "\nThe physics table above stands as reference regardless."
              + ("\nPer the amended closure: at all 8 available forward seasons with the CI"
                 "\nstraddling zero -> NO-MARGINAL-VALUE, the term is not added, the gate closes."
                 if len(seasons) >= 8 else ""))
    print(f"\n{CAPITAL_LINE}")


# ------------------------------------------------------------------ selftest


def _synth_r2(seed: int, revert_per_min: float = 0.0, n_seasons=9, games_per=1200,
              sigma_step=2.4, e_sd=6.0, shuffle=False) -> pd.DataFrame:
    """Vectorized synthetic: dev follows an AR(1) per minute with pull
    `revert_per_min` toward the anchor; margin = E*elapsed/48 + dev.
    True beta(g) = 1 - (1 - r)^(48 - g)."""
    rng = np.random.default_rng(seed)
    n = n_seasons * games_per
    e = rng.normal(0, e_sd, n)
    dev = np.zeros(n)
    path = np.empty((49, n))
    path[0] = 0.0
    for step in range(1, 49):
        dev = (1 - revert_per_min) * dev + sigma_step * rng.normal(size=n)
        path[step] = dev
    final_margin = e + path[48]
    y = (final_margin > 0).astype(float)
    if shuffle:
        y = rng.permutation(y)
    season = np.repeat(np.arange(n_seasons), games_per)
    frames = []
    for t in GRID:  # t = minutes left 1..47; elapsed = 48 - t
        elapsed = int(REG_MINUTES - t)
        frames.append(pd.DataFrame({
            "game_id": np.arange(n), "season": season, "t": float(t),
            "m": e * elapsed / REG_MINUTES + path[elapsed], "e": e, "y": y,
            "home_margin": final_margin,
        }))
    st = pd.concat(frames, ignore_index=True)
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    st["dev_final"] = st.home_margin - st.e
    return st


def selftest() -> None:
    """Mutation before first read (amended clause; R2's arms share sigma, so
    the literal shuffled-null straddle is expected to hold here).

    1. Brownian (no reversion): fitted beta ~ 0 at every gridpoint, AND the
       gate with that honestly-fitted near-zero table straddles zero — the
       artifact-free null for the gate itself.
    2. Reverting generator (r=0.01/min): fitted beta matches the analytic
       1-(1-r)^(48-g) within tolerance, and the gate PASSES for the shrink.
    3. On Brownian data a deliberately nonzero table must LOSE to plain.
    4. On reverting data a distorted table (beta x3, capped 0.9) must LOSE
       to the fitted shrink.
    5. Shuffled outcomes — artifact direction, per the registration's own
       extension of the amended clause to R2 ("wherever its arms differ in
       sharpness"): the shrunk arm is LESS responsive to the destroyed live
       margin and therefore mechanically favoured, so the assertion is that
       the margin-responsive arm (plain) must never win. Discrimination is
       carried by 1-4.
    """
    ok = True
    br = _synth_r2(1, revert_per_min=0.0)
    b0 = fit_beta(br[br.season < 5])
    worst = max(abs(v) for v in b0.values())
    print(f"[1] Brownian: max |beta| over gridpoints = {worst:.4f} (want ~0)")
    ok &= worst < 0.03
    _, sig0 = fit_arm_a(br[br.season < 5])
    ev0 = score_arms(br[br.season >= 5], b0, sigma_phase_table(sig0))
    d = ev0.brier_shrunk - ev0.brier_plain
    cm = clustered_mean({s: d[ev0.season == s].tolist() for s in ev0.season.unique()})
    straddle = cm.lo < 0 < cm.hi
    print(f"    gate with fitted ~0 table on Brownian: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want straddle)")
    ok &= straddle

    rv = _synth_r2(2, revert_per_min=0.01)
    bt = fit_beta(rv[rv.season < 5])
    errs = {g: bt[int(g)] - (1 - 0.99 ** (48 - g)) for g in GRIDPOINTS}
    werr = max(abs(v) for v in errs.values())
    print(f"[2] reverting r=0.01: beta(4)={bt[4]:+.3f} (true {1 - 0.99 ** 44:+.3f}), "
          f"beta(44)={bt[44]:+.3f} (true {1 - 0.99 ** 4:+.3f}), max err {werr:.3f}")
    ok &= werr < 0.06
    _, sig = fit_arm_a(rv[rv.season < 5])
    evr = score_arms(rv[rv.season >= 5], bt, sigma_phase_table(sig))
    d = evr.brier_shrunk - evr.brier_plain
    cm = clustered_mean({s: d[evr.season == s].tolist() for s in evr.season.unique()})
    print(f"    gate on reverting data: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want hi<0)")
    ok &= cm.hi < 0

    _, sigb = fit_arm_a(br[br.season < 5])
    fake = {int(g): 0.3 for g in GRIDPOINTS}
    evb = score_arms(br[br.season >= 5], fake, sigma_phase_table(sigb))
    d = evb.brier_shrunk - evb.brier_plain
    cm = clustered_mean({s: d[evb.season == s].tolist() for s in evb.season.unique()})
    print(f"[3] fake shrink on Brownian: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want lo>0)")
    ok &= cm.lo > 0

    dist = {int(g): min(0.9, 3 * bt[int(g)]) for g in GRIDPOINTS}
    evd = score_arms(rv[rv.season >= 5], dist, sigma_phase_table(sig))
    d2 = evd.brier_shrunk - evr.brier_shrunk
    cm = clustered_mean({s: d2[evd.season == s].tolist() for s in evd.season.unique()})
    print(f"[4] distorted(x3) vs fitted on reverting: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want lo>0)")
    ok &= cm.lo > 0

    sh = _synth_r2(3, revert_per_min=0.01, shuffle=True)
    bsh = fit_beta(sh[sh.season < 5])
    _, sigs = fit_arm_a(sh[sh.season < 5])
    evs = score_arms(sh[sh.season >= 5], bsh, sigma_phase_table(sigs))
    d = evs.brier_shrunk - evs.brier_plain
    cm = clustered_mean({s: d[evs.season == s].tolist() for s in evs.season.unique()})
    print(f"[5] shuffled outcomes: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] "
          f"(artifact direction: plain must NOT win, want lo not > 0)")
    ok &= not (cm.lo > 0)

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
    states = load_real(args.games, args.plays)
    g = pd.read_csv(args.games)
    g["home_margin"] = g.team0_score - g.team1_score
    st = add_dev(states, g[["game_id", "home_margin"]])
    print("\n=== R2 PHYSICS TABLE — reports regardless of gate outcome ===")
    physics_table(st)
    ev = walk_forward_r2(st)
    print("\n=== R2 GATE READ — out-of-sample seasons only ===")
    gate_read_r2(ev)


if __name__ == "__main__":
    main()
