"""R4b — sigma refit under the shrunk mean: committed harness.

Registration: docs/math/nba-r4b-sigma-refit.md — DRAFT at 163f63a, awaiting
research sign-off. COMPUTES NOTHING REAL until the signed text lands on main;
--selftest only until then.

Reproduce:

    .venv/bin/python analysis/nba_r4b_harness.py --selftest
    .venv/bin/python analysis/nba_r4b_harness.py --games ... --plays ... \
        --i-confirm-registration-landed

Arms (from the registration):
  (a) incumbent = ADOPTED post-R4 stack: sigma_phase (UNSHRUNK-fit) + R2
      shrink + R4 g — the full R4 pipeline refit per fold.
  (b) R4b = sigma'_phase fitted by MLE with the mean FROZEN at the SHRUNK
      expectation (beta fitted exactly as R2 registered, first) + R2 shrink.
      No g anywhere. The arms differ in exactly one thing: fitting order.

Gate: paired Brier (R4b - incumbent), season-clustered, folds and floor as
R4. PASS -> R4b replaces g (constants v3). FAIL -> g carries information the
uniform refit does not (the z-gradient theory's first positive evidence).
Straddle at all 7 -> the pre-committed SIMPLICITY TIE-BREAK replaces the
effective-parameter form with the structurally-correct one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean
from nba_r1_harness import PHASES, REG_MINUTES, SIGMA_BOUNDS, fit_arm_a, load_real, sigma_phase_table
from nba_r2_harness import _synth_r2, fit_beta, shrink_fn
from nba_r4_harness import (
    EVAL_SEASONS_R4,
    FLOOR,
    PARTIAL_SEASON,
    _paired,
    _synth_r4,
    band_tilt,
    fit_g,
    prep,
    stack_prob,
)

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."
BOUNDARY_LINE = ("BOUNDARY: calibration work on the model's uncertainty engine. NOT edge work; "
                 "says nothing about any market; Track 2 is separate.")


# ------------------------------------------------------------------ the R4b fit


def fit_sigma_shrunk(train: pd.DataFrame, beta: dict) -> tuple[float, dict]:
    """Step 2 of the registered order: sigma' by MLE with the mean frozen at
    the SHRUNK expectation. Global first, then the four phase buckets."""
    t = train.t.to_numpy(float)
    s = shrink_fn(beta)(train.elapsed.to_numpy(float))
    num = train.e.to_numpy(float) + (1 - s) * train.dev.to_numpy(float)
    y = train.y.to_numpy(float)

    def nll(sig, mask):
        p = np.clip(norm.cdf(num[mask] / (sig * np.sqrt(t[mask]))), 1e-9, 1 - 1e-9)
        return -np.sum(y[mask] * np.log(p) + (1 - y[mask]) * np.log(1 - p))

    all_mask = np.ones(len(t), dtype=bool)
    s_glob = float(minimize_scalar(lambda v: nll(v, all_mask), bounds=SIGMA_BOUNDS, method="bounded").x)
    table = {}
    for lo, hi in PHASES:
        mask = (t > lo) & (t <= hi)
        table[(lo, hi)] = float(minimize_scalar(lambda v: nll(v, mask), bounds=SIGMA_BOUNDS, method="bounded").x)
    return s_glob, table


def prob_r4b(ev: pd.DataFrame, sigma_fn_shrunk, beta: dict) -> np.ndarray:
    t = ev.t.to_numpy(float)
    s = shrink_fn(beta)(ev.elapsed.to_numpy(float))
    num = ev.e.to_numpy(float) + (1 - s) * ev.dev.to_numpy(float)
    return norm.cdf(num / (sigma_fn_shrunk(t) * np.sqrt(t)))


# ------------------------------------------------------------------ walk-forward + gate


def walk_forward_r4b(st: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(st.season.unique())
    folds = [(s, [x for x in seasons if x < s]) for s in EVAL_SEASONS_R4 if s in seasons]
    if PARTIAL_SEASON in seasons:
        folds.append((PARTIAL_SEASON, [x for x in seasons if x <= 2022]))
    rows, fitted = [], {}
    for eval_season, train_seasons in folds:
        train, ev = st[st.season.isin(train_seasons)], st[st.season == eval_season].copy()
        beta = fit_beta(train)  # R2's registered fit, shared by both arms
        # incumbent: unshrunk-fit sigma + shrink + g (the full adopted pipeline)
        _, sig_unshrunk = fit_arm_a(train)
        sigma_fn = sigma_phase_table(sig_unshrunk)
        g = fit_g(train, sigma_fn, beta)
        ev["p_inc"] = stack_prob(ev, sigma_fn, beta, g)
        # R4b: shrunk-fit sigma', no g
        s_glob, sig_shrunk = fit_sigma_shrunk(train, beta)
        sigma_fn_b = sigma_phase_table(sig_shrunk)
        ev["p_r4b"] = prob_r4b(ev, sigma_fn_b, beta)
        fitted[eval_season] = {
            "sigma_shrunk": {"global": s_glob, "table": sig_shrunk},
            "sigma_unshrunk_x_gbar": {k: v * np.mean(list(g.values())) for k, v in sig_unshrunk.items()},
            "g": g, "train": train_seasons,
        }
        rows.append(ev)
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def gate_read_r4b(ev: pd.DataFrame) -> None:
    seasons = sorted(ev.season.unique())
    label = lambda s: f"{s}(PARTIAL)" if s == PARTIAL_SEASON else str(s)
    print(f"forward seasons evaluated: {len(seasons)} (floor >= {FLOOR}): {[label(s) for s in seasons]}")
    fitted = ev.attrs.get("fitted", {})
    print("\nsigma' (shrunk-fit) vs sigma*gbar (the effective form), per fold, Q1..Q4 phases:")
    for s, f in fitted.items():
        a = " ".join(f"{f['sigma_shrunk']['table'][p]:.3f}" for p in PHASES)
        b = " ".join(f"{f['sigma_unshrunk_x_gbar'][p]:.3f}" for p in PHASES)
        print(f"  {label(s):<13s} sigma': {a}   sigma*gbar: {b}   g: "
              + "/".join(f"{f['g'][k]:.3f}" for k in range(3)))
    d = (ev.p_r4b - ev.y) ** 2 - (ev.p_inc - ev.y) ** 2
    cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
    print(f"\npaired Brier (R4b - incumbent), season-clustered (negative favours R4b):")
    print(f"  {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}]  rows={cm.n} seasons={cm.n_clusters}")
    per = ev.groupby("season").apply(
        lambda f: pd.Series({"r4b": ((f.p_r4b - f.y) ** 2).mean(), "inc": ((f.p_inc - f.y) ** 2).mean()}),
        include_groups=False)
    per.index = [label(s) for s in per.index]
    print("\nper-season mean Brier:")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    if len(seasons) < FLOOR:
        print(f"\nVERDICT FRAME: below the {FLOOR}-season floor — NO READ.")
    elif cm.hi < 0:
        print("\nVERDICT FRAME: PASS — R4b REPLACES g (constants v3; g retired).")
    elif cm.lo > 0:
        print("\nVERDICT FRAME: FAIL — g carries information the uniform refit does not."
              "\nRecorded as the z-gradient theory's FIRST positive evidence; g stands.")
    else:
        print("\nVERDICT FRAME: CI straddles zero."
              + ("\nPRE-COMMITTED SIMPLICITY TIE-BREAK: the structurally-correct form REPLACES"
                 "\nthe effective-parameter form — fewer free parameters, and its parameters"
                 "\nmean what they say. Recorded as replacement-by-tie-break, never superiority."
                 "\n(This straddle LICENSES the simpler form; it is not R4's uninformative one.)"
                 if len(seasons) >= 7 else ""))
    print("\nDIAGNOSTICS (descriptive, never gated):")
    for name, col in [("incumbent (post-R4)", "p_inc"), ("R4b", "p_r4b")]:
        m, lo, hi, n = band_tilt(ev, col)
        print(f"  atlas-cell tilt under {name:<20s} {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  rows={n}")
    print(f"\n{BOUNDARY_LINE}")
    print(CAPITAL_LINE)


# ------------------------------------------------------------------ selftest


def _score_arms(ev, sigma_fn_unshrunk, sigma_fn_shrunk, beta, g):
    p_inc = stack_prob(ev, sigma_fn_unshrunk, beta, g)
    p_r4b = prob_r4b(ev, sigma_fn_shrunk, beta)
    return p_inc, p_r4b


def selftest() -> None:
    """Mutation per the draft's clause.

    1. On a reverting generator (R2's, known pull), the shrunk-mean fitter's
       sigma' is BELOW the unshrunk-fit sigma in every phase (the refit sees
       the variance the shrink removed) and recovery is directionally sane.
    2. Distorted sigma' loses to fitted in BOTH directions.
    3. The discrimination pair at real-gate power:
       (i) reverting generator: R4b must beat the PRE-R4 stack (unshrunk
           sigma + shrink, no g) — the synthetic reproduction of R4's real
           finding;
       (ii) true-z-gradient generator (R4's): the g-incumbent must beat R4b —
           the gate's FAIL branch is detectable.
    4. Plain Brownian generator (no reversion, no gradient): gate straddles.
    5. Shuffled null: a FIXED sharper table must never win.
    """
    ok = True

    rv = _synth_r2(21, revert_per_min=0.01, n_seasons=11, games_per=1230)
    rv = rv.rename(columns={})  # columns already match: t, m, e, y, elapsed, dev, dev_final, season, game_id
    tr = rv[rv.season < 4]
    beta = fit_beta(tr)
    _, sig_u = fit_arm_a(tr)
    _, sig_s = fit_sigma_shrunk(tr, beta)
    below = all(sig_s[p] < sig_u[p] for p in PHASES)
    print(f"[1] reverting generator: sigma' below unshrunk sigma in all phases: {below} "
          f"(sigma' {['%.3f' % sig_s[p] for p in PHASES]} vs {['%.3f' % sig_u[p] for p in PHASES]})")
    ok &= below

    ev = rv[rv.season >= 4]
    sigma_fn_s = sigma_phase_table(sig_s)
    p_fit = prob_r4b(ev, sigma_fn_s, beta)
    for name, mult in [("wider", 1.3), ("narrower", 1 / 1.3)]:
        sig_d = {p: v * mult for p, v in sig_s.items()}
        p_d = prob_r4b(ev, sigma_phase_table(sig_d), beta)
        cm = _paired(ev, p_fit, p_d)
        print(f"[2] fitted sigma' vs {name}: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want hi<0)")
        ok &= cm.hi < 0

    p_pre_r4 = stack_prob(ev, sigma_phase_table(sig_u), beta)  # pre-R4 stack: unshrunk sigma, no g
    cm = _paired(ev, p_fit, p_pre_r4)
    print(f"[3i] reverting gen, R4b vs PRE-R4 stack: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want hi<0)")
    ok &= cm.hi < 0

    # [3ii] runs twice: at REAL power the FAIL branch is near-undetectable even
    # for a gradient stronger than plausible reality (that read is the PROGNOSIS
    # and prints), and at ELEVATED power (3x games) the instrument must detect
    # it — proving the gate CAN see a z-gradient in principle.
    for tag, gp, assert_it in [("real power (prognosis)", 1230, False), ("elevated 3x power", 3690, True)]:
        zg = _synth_r4(22, g_true=(1.25, 1.00, 0.60), n_seasons=11, games_per=gp)
        trz = zg[zg.season < 4]
        beta_z = fit_beta(trz)
        _, sig_uz = fit_arm_a(trz)
        sigma_fn_uz = sigma_phase_table(sig_uz)
        g_z = fit_g(trz, sigma_fn_uz, beta_z)
        _, sig_sz = fit_sigma_shrunk(trz, beta_z)
        evz = zg[zg.season >= 4]
        p_incz, p_r4bz = _score_arms(evz, sigma_fn_uz, sigma_phase_table(sig_sz), beta_z, g_z)
        cm = _paired(evz, p_r4bz, p_incz)
        want = "want lo>0" if assert_it else "prognosis, no assertion"
        print(f"[3ii] z-gradient gen at {tag}, R4b vs g-incumbent: "
              f"{cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] ({want})")
        if assert_it:
            ok &= cm.lo > 0

    br = _synth_r2(23, revert_per_min=0.0, n_seasons=11, games_per=1230)
    trb = br[br.season < 4]
    beta_b = fit_beta(trb)
    _, sig_ub = fit_arm_a(trb)
    sigma_fn_ub = sigma_phase_table(sig_ub)
    g_b = fit_g(trb, sigma_fn_ub, beta_b)
    _, sig_sb = fit_sigma_shrunk(trb, beta_b)
    evb = br[br.season >= 4]
    p_incb, p_r4bb = _score_arms(evb, sigma_fn_ub, sigma_phase_table(sig_sb), beta_b, g_b)
    cm = _paired(evb, p_r4bb, p_incb)
    straddle = cm.lo < 0 < cm.hi
    print(f"[4] plain Brownian: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want straddle)")
    ok &= straddle

    sh = _synth_r2(24, revert_per_min=0.01, shuffle=True, n_seasons=9, games_per=1200)
    trs = sh[sh.season < 4]
    beta_s2 = fit_beta(trs)
    _, sig_us = fit_arm_a(trs)
    evs = sh[sh.season >= 4]
    sharp = {p: v / 1.5 for p, v in sig_us.items()}
    p_sharp = prob_r4b(evs, sigma_phase_table(sharp), beta_s2)
    p_base = prob_r4b(evs, sigma_phase_table(sig_us), beta_s2)
    cm = _paired(evs, p_sharp, p_base)
    print(f"[5] shuffled null, fixed sharper vs base: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want not hi<0)")
    ok &= not (cm.hi < 0)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games")
    ap.add_argument("--plays")
    ap.add_argument("--i-confirm-registration-landed", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")
    if not args.i_confirm_registration_landed:
        raise SystemExit("REFUSED: the R4b registration is a DRAFT awaiting research sign-off; "
                         "nothing real computes until the signed text lands on main.")
    states = load_real(args.games, args.plays)
    games = pd.read_csv(args.games)
    st = prep(states, games)
    ev = walk_forward_r4b(st)
    print("\n=== R4b GATE READ — out-of-sample seasons only ===")
    gate_read_r4b(ev)


if __name__ == "__main__":
    main()
