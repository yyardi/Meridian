"""R4 — margin-conditional sigma (the lead-band arm): committed harness.

Registration: docs/math/nba-r4-lead-band-sigma.md — DRAFT at commit 77a1434,
awaiting research sign-off. THIS HARNESS COMPUTES NOTHING REAL until the
signed text lands on main; --selftest only until then.

Reproduce:

    .venv/bin/python analysis/nba_r4_harness.py --selftest
    .venv/bin/python analysis/nba_r4_harness.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz

PINNED (from the registration):

    z          = |m + E*t/48| / (sigma_phase(t) * sqrt(t))    # incumbent units
    buckets    : z in [0, 0.5) / [0.5, 1.5) / [1.5, inf)
    sigma_R4   = sigma_phase(t) * g(bucket)                    # g fitted 2-step
    P_R4       = Phi( (E + (1-s(elapsed))*dev) / (sigma_R4 * sqrt(t)) )

Incumbent = adopted R1b arm (a) sigma + R2 shrink, refit per fold; g fitted on
TOP with sigma_phase and the shrink FROZEN (two-step, R1b discipline). Anchor,
shrink table, outcome frame, OT handling untouched. The harness refuses the
registration's forbidden forms by construction: no cell/band literals appear
anywhere, no output remapping exists, the shrink table is read-only.

Folds: eval 2017-2022 + 2025 (PARTIAL, train <= 2022), floor >= 6. Gate:
paired per-state Brier (R4 - incumbent), season-clustered. Boundary carried
verbatim: calibration work on the uncertainty engine — NEVER edge work.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm, t as tdist

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean
from nba_r1_harness import GRID, REG_MINUTES, fit_arm_a, load_real, sigma_phase_table
from nba_r2_harness import fit_beta, shrink_fn

Z_EDGES = [0.5, 1.5]
G_BOUNDS = (0.5, 2.0)
EVAL_SEASONS_R4 = [2017, 2018, 2019, 2020, 2021, 2022]
PARTIAL_SEASON = 2025
FLOOR = 6

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."
BOUNDARY_LINE = ("BOUNDARY (disposition #172, verbatim duty): calibration work on the model's "
                 "uncertainty engine. NOT edge work; says nothing about any market; Track 2 is separate.")


# ------------------------------------------------------------------ the arm


def zbucket(st: pd.DataFrame, sigma_fn) -> np.ndarray:
    t = st.t.to_numpy(float)
    z = np.abs(st.m.to_numpy(float) + st.e.to_numpy(float) * t / REG_MINUTES) / (sigma_fn(t) * np.sqrt(t))
    return np.digitize(z, Z_EDGES)  # 0, 1, 2


def stack_prob(st: pd.DataFrame, sigma_fn, beta: dict, g: dict | None = None) -> np.ndarray:
    """The adopted stack; with g, sigma_phase -> sigma_phase * g(bucket)."""
    t = st.t.to_numpy(float)
    s = shrink_fn(beta)(st.elapsed.to_numpy(float))
    num = st.e.to_numpy(float) + (1 - s) * st.dev.to_numpy(float)
    sig = sigma_fn(t)
    if g is not None:
        sig = sig * np.vectorize(g.get)(zbucket(st, sigma_fn))
    return norm.cdf(num / (sig * np.sqrt(t)))


def fit_g(train: pd.DataFrame, sigma_fn, beta: dict) -> dict[int, float]:
    """Step-2 MLE: per-bucket multiplier with sigma_phase and shrink FROZEN.
    Buckets are disjoint, so the fit separates into three 1-D problems."""
    t = train.t.to_numpy(float)
    s = shrink_fn(beta)(train.elapsed.to_numpy(float))
    num = train.e.to_numpy(float) + (1 - s) * train.dev.to_numpy(float)
    base = sigma_fn(t) * np.sqrt(t)
    y = train.y.to_numpy(float)
    buckets = zbucket(train, sigma_fn)
    out = {}
    for b in range(len(Z_EDGES) + 1):
        mask = buckets == b
        nb, bb, yb = num[mask], base[mask], y[mask]

        def nll(gv):
            p = np.clip(norm.cdf(nb / (gv * bb)), 1e-9, 1 - 1e-9)
            return -np.sum(yb * np.log(p) + (1 - yb) * np.log(1 - p))

        out[b] = float(minimize_scalar(nll, bounds=G_BOUNDS, method="bounded").x)
    return out


# ------------------------------------------------------------------ walk-forward + gate


def prep(states: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    st = states.dropna(subset=["e"]).copy()
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    hm = pd.Series((games.team0_score - games.team1_score).values, index=games.game_id.values)
    st["dev_final"] = st.game_id.map(hm) - st.e
    return st


def walk_forward_r4(st: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(st.season.unique())
    folds = [(s, [x for x in seasons if x < s]) for s in EVAL_SEASONS_R4 if s in seasons]
    if PARTIAL_SEASON in seasons:
        folds.append((PARTIAL_SEASON, [x for x in seasons if x <= 2022]))
    rows, fitted = [], {}
    for eval_season, train_seasons in folds:
        train, ev = st[st.season.isin(train_seasons)], st[st.season == eval_season].copy()
        _, sig_table = fit_arm_a(train)
        sigma_fn = sigma_phase_table(sig_table)
        beta = fit_beta(train)
        g = fit_g(train, sigma_fn, beta)
        fitted[eval_season] = {"g": g, "train": train_seasons}
        ev["p_inc"] = stack_prob(ev, sigma_fn, beta)
        ev["p_r4"] = stack_prob(ev, sigma_fn, beta, g)
        ev["p_sigonly"] = norm.cdf((ev.e.to_numpy(float) + ev.dev.to_numpy(float))
                                   / (sigma_fn(ev.t.to_numpy(float)) * np.sqrt(ev.t.to_numpy(float))))
        rows.append(ev)
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def band_tilt(ev: pd.DataFrame, pcol: str) -> tuple[float, float, float, int]:
    """Diagnostic only: realized - predicted for the leader in the atlas cells
    (t in [18,36], lead 4-19). Season-clustered. NEVER gated."""
    cell = ev[(ev.t >= 18) & (ev.t <= 36) & (ev.m.abs() >= 4) & (ev.m.abs() <= 19)]
    y_l = np.where(cell.m > 0, cell.y, 1 - cell.y)
    p_l = np.where(cell.m > 0, cell[pcol], 1 - cell[pcol])
    d = pd.Series(y_l - p_l, index=cell.index)
    cm = clustered_mean({s: d[cell.season == s].tolist() for s in cell.season.unique()})
    return cm.mean, cm.lo, cm.hi, cm.n


def gate_read_r4(ev: pd.DataFrame) -> None:
    seasons = sorted(ev.season.unique())
    label = lambda s: f"{s}(PARTIAL)" if s == PARTIAL_SEASON else str(s)
    print(f"forward seasons evaluated: {len(seasons)} (floor >= {FLOOR}): {[label(s) for s in seasons]}")
    fitted = ev.attrs.get("fitted", {})
    print("\nfitted g per fold (buckets z<0.5 / 0.5-1.5 / >=1.5):")
    for s, f in fitted.items():
        print(f"  {label(s):<13s} " + " / ".join(f"{f['g'][b]:.3f}" for b in range(3))
              + f"   trained {f['train'][0]}..{f['train'][-1]}")
    d = (ev.p_r4 - ev.y) ** 2 - (ev.p_inc - ev.y) ** 2
    cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
    print(f"\npaired Brier (R4 - incumbent), season-clustered (negative favours R4):")
    print(f"  {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}]  rows={cm.n} seasons={cm.n_clusters}")
    per = ev.groupby("season").apply(
        lambda f: pd.Series({"r4": ((f.p_r4 - f.y) ** 2).mean(), "inc": ((f.p_inc - f.y) ** 2).mean()}),
        include_groups=False)
    per.index = [label(s) for s in per.index]
    print("\nper-season mean Brier:")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    if len(seasons) < FLOOR:
        print(f"\nVERDICT FRAME: below the {FLOOR}-season floor — NO READ.")
    elif cm.hi < 0:
        print("\nVERDICT FRAME: PASS — CI excludes zero in R4's favour.")
    elif cm.lo > 0:
        print("\nVERDICT FRAME: FAIL — CI excludes zero against R4. The band gap stands"
              "\nas a documented model limitation; this arm's z-family theory of it is refuted.")
    else:
        print("\nVERDICT FRAME: CI straddles zero."
              + ("\nAt all 7: NO-MARGINAL-VALUE — g is not added; the band gap stands as a"
                 "\ndocumented model limitation; the gate closes. A straddle does not retract"
                 "\nthe atlas finding — it refutes this arm's z-family theory of it."
                 if len(seasons) >= 7 else ""))
    print("\nDIAGNOSTICS (descriptive, never gated):")
    for name, col in [("incumbent", "p_inc"), ("R4", "p_r4"), ("sigma-only (attribution)", "p_sigonly")]:
        m, lo, hi, n = band_tilt(ev, col)
        print(f"  atlas-cell tilt under {name:<24s} {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  rows={n}")
    print(f"\n{BOUNDARY_LINE}")
    print(CAPITAL_LINE)


# ------------------------------------------------------------------ selftest


def _synth_r4(seed: int, g_true=(1.0, 1.0, 1.0), n_seasons=9, games_per=1200,
              sigma_base=2.5, e_sd=9.0, shuffle=False) -> pd.DataFrame:
    """Margin walks whose per-minute step sd is sigma_base * g_true(bucket of
    the CURRENT z) — margin-conditional variance by construction. The fitted g
    is an effective parameter of the induced process (the walk's variance is
    path-dependent), so recovery tolerances are directional-and-loose by
    design, stated in the test."""
    rng = np.random.default_rng(seed)
    n = n_seasons * games_per
    e = rng.normal(0, e_sd, n)
    m = np.zeros(n)
    path = np.empty((49, n))
    path[0] = 0.0
    for step in range(1, 49):
        t_left = REG_MINUTES - step + 1  # horizon during this minute
        z = np.abs(m + e * t_left / REG_MINUTES) / (sigma_base * np.sqrt(np.maximum(t_left, 1e-9)))
        gmult = np.select([z < Z_EDGES[0], z < Z_EDGES[1]], [g_true[0], g_true[1]], g_true[2])
        m = m + e / REG_MINUTES + sigma_base * gmult * rng.normal(size=n)
        path[step] = m
    y = (path[48] > 0).astype(float)
    if shuffle:
        y = rng.permutation(y)
    season = np.repeat(np.arange(n_seasons), games_per)
    frames = []
    for t in GRID:
        elapsed = int(REG_MINUTES - t)
        frames.append(pd.DataFrame({
            "game_id": np.arange(n), "season": season, "t": float(t),
            "m": path[elapsed], "e": e, "y": y,
        }))
    st = pd.concat(frames, ignore_index=True)
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    st["dev_final"] = st.game_id.map(pd.Series(path[48], index=np.arange(n))) - st.e
    return st


def _fold_fit(st: pd.DataFrame, train_mask):
    train = st[train_mask]
    _, sig_table = fit_arm_a(train)
    sigma_fn = sigma_phase_table(sig_table)
    beta = fit_beta(train)
    return sigma_fn, beta, fit_g(train, sigma_fn, beta)


def _paired(ev: pd.DataFrame, pa: np.ndarray, pb: np.ndarray):
    d = pd.Series((pa - ev.y.to_numpy(float)) ** 2 - (pb - ev.y.to_numpy(float)) ** 2, index=ev.index)
    return clustered_mean({s: d[ev.season == s].tolist() for s in ev.season.unique()})


def selftest() -> None:
    """The adopted mutation clause, R4 form (see registration draft).

    Two design facts, learned from this suite's own first failures and kept
    visible: (a) the two-step form lets sigma_phase absorb any z-effect that
    is collinear with the clock, so the fitted g is an EFFECTIVE parameter of
    the residual — recovery asserts ordering and direction with magnitude
    bounds, not equality to the injected values, and the injected effect must
    be strong enough to survive phase absorption (as the real atlas tilt did,
    having been measured AGAINST the fitted phase model); (b) fitting g on
    shuffled outcomes inflates it toward the wide bound (flatness wins on
    destroyed signal), so the shuffled null tests a FIXED sharper table, per
    the adopted clause's artifact-direction form.
    """
    ok = True
    G_TRUE = (1.25, 1.00, 0.60)  # atlas direction; e_sd=9 puts z-variation inside
    # mid-game (where the real tilt lives), decorrelating it from the clock so
    # phase absorption cannot swallow the whole injection

    st = _synth_r4(5, g_true=G_TRUE)
    tr_mask = st.season < 4
    sigma_fn, beta, g = _fold_fit(st, tr_mask)
    print(f"[1] recovery (injected {G_TRUE}; effective-parameter test: strict ordering, "
          f"separation g0-g2 >= 0.12): fitted {tuple(round(g[b], 3) for b in range(3))}")
    ok &= g[2] < g[1] < g[0] and (g[0] - g[2]) >= 0.12

    ev = st[~tr_mask]
    p_fit = stack_prob(ev, sigma_fn, beta, g)
    for name, mult in [("wider", 1.3), ("narrower", 1 / 1.3)]:
        gd = {b: v * mult for b, v in g.items()}
        cm = _paired(ev, p_fit, stack_prob(ev, sigma_fn, beta, gd))
        print(f"[2] fitted-g vs {name}-g: {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want hi<0)")
        ok &= cm.hi < 0

    # [3] at the REAL gate's power: 7 eval seasons x ~1,230 games, family-optimal
    # (fitted) table vs incumbent. sigma-correction Brier value is second-order,
    # so this doubles as the arm's power prognosis and prints as such.
    big = _synth_r4(8, g_true=G_TRUE, n_seasons=11, games_per=1230)
    sigma_b, beta_b, g_b = _fold_fit(big, big.season < 4)
    evb = big[big.season >= 4]
    cm = _paired(evb, stack_prob(evb, sigma_b, beta_b, g_b), stack_prob(evb, sigma_b, beta_b))
    print(f"[3] het generator at real-gate power (7 eval seasons), R4 vs incumbent: "
          f"{cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want hi<0)")
    ok &= cm.hi < 0

    hom = _synth_r4(6, g_true=(1.0, 1.0, 1.0))
    sigma_h, beta_h, g_h = _fold_fit(hom, hom.season < 4)
    evh = hom[hom.season >= 4]
    cmh = _paired(evh, stack_prob(evh, sigma_h, beta_h, g_h), stack_prob(evh, sigma_h, beta_h))
    print(f"[4] homoskedastic null: fitted g {tuple(round(g_h[b], 3) for b in range(3))} (want ~1 ±0.05); "
          f"gate {cmh.mean:+.6f} [{cmh.lo:+.6f}, {cmh.hi:+.6f}] (want straddle)")
    ok &= all(abs(g_h[b] - 1.0) < 0.05 for b in range(3)) and cmh.lo < 0 < cmh.hi

    sh = _synth_r4(7, g_true=G_TRUE, shuffle=True)
    sigma_s, beta_s, g_s = _fold_fit(sh, sh.season < 4)
    evs = sh[sh.season >= 4]
    sharp = {0: 0.8, 1: 0.8, 2: 0.8}
    cms = _paired(evs, stack_prob(evs, sigma_s, beta_s, sharp), stack_prob(evs, sigma_s, beta_s))
    print(f"[5] shuffled null, FIXED sharper table vs incumbent (sharper must NOT win): "
          f"{cms.mean:+.6f} [{cms.lo:+.6f}, {cms.hi:+.6f}] (want not hi<0); "
          f"fit-on-shuffle diagnostic: g inflates to {tuple(round(g_s[b], 3) for b in range(3))} "
          f"(flatness winning on destroyed signal — the artifact, visible)")
    ok &= not (cms.hi < 0)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games")
    ap.add_argument("--plays")
    ap.add_argument("--i-confirm-registration-landed", action="store_true",
                    help="required for a real read: asserts the signed R4 text is on main")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")
    if not args.i_confirm_registration_landed:
        raise SystemExit("REFUSED: the R4 registration is a DRAFT awaiting research sign-off; "
                         "this harness computes nothing real until the signed text lands on main. "
                         "Re-run with --i-confirm-registration-landed once it has.")
    states = load_real(args.games, args.plays)
    games = pd.read_csv(args.games)
    st = prep(states, games)
    ev = walk_forward_r4(st)
    print("\n=== R4 GATE READ — out-of-sample seasons only ===")
    gate_read_r4(ev)


if __name__ == "__main__":
    main()
