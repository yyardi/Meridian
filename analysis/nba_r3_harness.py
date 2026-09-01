"""R3b — NBA totals coefficients: the committed harness, pinned BEFORE first read.

Registration: docs/math/nba-constants-registrations.md — R3 arms/gate, R3b
re-anchoring, and the R3b RULINGS of 2026-09-02 (verified on main before this
read). Floor >= 5 of 6; sigma port ruled for (i) RATE-KEYED: "THE INVARIANT
PORTED IS THE MATCHED-BOUNDARY RATE, NOT A WITHIN-GAME sqrt-t LAW" — option
(ii), the absolute triple 15.88/13.03/9.67 unchanged, is NOT arm (b) and runs
only as the LABELLED NEVER-GATING SENSITIVITY (b') beside the verdict.
Forbidden form: any port mixing rates and absolutes across boundaries.

Reproduce:

    .venv/bin/python analysis/nba_r3_harness.py --selftest
    .venv/bin/python analysis/nba_r3_harness.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz

PINNED FORMULAS (proposals 1-6, awaiting research)
==================================================

Boundaries: end-Q1 / half / end-Q3 states, snapped on the R1 grid at
t = 36 / 24 / 12 (elapsed 12 / 24 / 36). Anchor mu = closing_total; the line
scored against IS the anchor, so per arm:

    surprise = S_t - mu * share(boundary)
    T_hat    = mu + b(boundary) * surprise          # arm (c): T_hat = S_t * 48/elapsed
    P(over)  = 1 - Phi((mu - T_hat) / sigma(boundary))

Outcome: y = (actual final total > closing_total), OT-INCLUSIVE — the
settlement frame (OT games run +22.3 over their lines; pretending regulation
settles would misgrade 422 games). PUSH rows (actual == line) are excluded
from scoring and counted.

Arms:
(a) NBA-fitted walk-forward, per boundary: cumulative shares fitted on non-OT
    training games (ratio of sums — shares of REGULATION scoring); b by
    no-intercept OLS of (actual - mu) on surprise against OT-inclusive
    finals; sigma = residual sd of (actual - T_hat). The physics table.
(b) WNBA port, keyed BY QUARTER INDEX: b = 1.318 / 1.208 / 1.128 and shares
    0.2541 / 0.5022 / 0.7566 dimensionless, unchanged; sigma per proposal
    (i) as per-sqrt-minute rates 2.899 / 2.914 / 3.059 consumed as
    rate * sqrt(NBA minutes_left) -> 17.39 / 14.28 / 10.60. The absolute
    triple 15.88 / 13.03 / 9.67 unchanged is the named forbidden-form analog
    (20% more clock remains at each NBA boundary).
(c) Naive extrapolation, the interpretability floor, never adoptable:
    T_hat = S_t * 48/elapsed, given arm (a)'s FITTED sigma so it loses on
    projection naivety alone, not on an arbitrary sigma choice.

Walk-forward: totals coverage 2017-2022 + 2025 PARTIAL (2016 has 24 games,
unusable). Eval 2018-2022 (train = prior covered seasons) + 2025 (train
<= 2022) = 6 available forward seasons. Floor: proposed >= 5 of 6 (the
zero-margin question is research's; the harness prints against >= 5 and the
count so either ruling reads cleanly).

Gate: paired per-state Brier across arms at the three boundary states,
season-clustered via clustered_mean. PASS/adopt = dominant arm, CIs excluding
zero, per R1b's shape. Any INDISTINGUISHABLE verdict prints the selftest's
generator-recovery separability as its power note.
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
from nba_r1_harness import PARTIAL_SEASON, REG_MINUTES, load_real

BOUNDARIES = [36.0, 24.0, 12.0]  # t = minutes left at end-Q1 / half / end-Q3
BNAMES = {36.0: "endQ1", 24.0: "half", 12.0: "endQ3"}
EVAL_SEASONS_R3 = [2018, 2019, 2020, 2021, 2022]
FLOOR = 5  # proposed >= 5 of 6 available; the ruling may confirm or move it

WNBA_B = {36.0: 1.318, 24.0: 1.208, 12.0: 1.128}
WNBA_SHARE = {36.0: 0.2541, 24.0: 0.5022, 12.0: 0.7566}
WNBA_SIGMA_RATE = {36.0: 2.899, 24.0: 2.914, 12.0: 3.059}  # per sqrt-minute — ruling (i)
WNBA_SIGMA_PORTED = {t: WNBA_SIGMA_RATE[t] * np.sqrt(t) for t in BOUNDARIES}
WNBA_SIGMA_ABSOLUTE = {36.0: 15.88, 24.0: 13.03, 12.0: 9.67}  # sensitivity (b') ONLY, never gating

POWER_NOTE = ("POWER: selftest generator-recovery separates the arm tables with CIs excluding\n"
              "zero both ways at ~1,200 games/season x 5 eval seasons — an INDISTINGUISHABLE\n"
              "verdict is a statement about basketball, not about our power.")
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


# ------------------------------------------------------------------ fitting


def fit_table(train: pd.DataFrame) -> dict:
    """Arm (a): shares, b, sigma per boundary, on TRAINING rows only.
    train columns: t, tot (S_t), mu, actual, is_ot."""
    out = {"share": {}, "b": {}, "sigma": {}}
    reg = train[~train.is_ot]
    for t in BOUNDARIES:
        r = reg[reg.t == t]
        out["share"][t] = float(r.tot.sum() / r.actual.sum())  # ratio of sums, regulation only
    for t in BOUNDARIES:
        r = train[train.t == t]
        surprise = (r.tot - r.mu * out["share"][t]).to_numpy(float)
        resid = (r.actual - r.mu).to_numpy(float)  # OT-inclusive, settlement frame
        b = float(np.sum(surprise * resid) / np.sum(surprise * surprise))
        out["b"][t] = b
        out["sigma"][t] = float(np.std(resid - b * surprise, ddof=1))
    return out


def prob_over(df: pd.DataFrame, share, b, sigma) -> np.ndarray:
    t = df.t.to_numpy(float)
    sh = np.vectorize(share.get)(t)
    bb = np.vectorize(b.get)(t)
    sg = np.vectorize(sigma.get)(t)
    surprise = df.tot.to_numpy(float) - df.mu.to_numpy(float) * sh
    t_hat = df.mu.to_numpy(float) + bb * surprise
    return 1.0 - norm.cdf((df.mu.to_numpy(float) - t_hat) / sg)


def prob_over_naive(df: pd.DataFrame, sigma) -> np.ndarray:
    t = df.t.to_numpy(float)
    sg = np.vectorize(sigma.get)(t)
    t_hat = df.tot.to_numpy(float) * REG_MINUTES / (REG_MINUTES - t)
    return 1.0 - norm.cdf((df.mu.to_numpy(float) - t_hat) / sg)


def score_all(ev: pd.DataFrame, table: dict) -> pd.DataFrame:
    ev = ev.copy()
    y = ev.y_over.to_numpy(float)
    ev["brier_a"] = (prob_over(ev, table["share"], table["b"], table["sigma"]) - y) ** 2
    ev["brier_b"] = (prob_over(ev, WNBA_SHARE, WNBA_B, WNBA_SIGMA_PORTED) - y) ** 2
    ev["brier_c"] = (prob_over_naive(ev, table["sigma"]) - y) ** 2
    return ev


# ------------------------------------------------------------------ walk-forward + gate


def walk_forward_r3(st: pd.DataFrame) -> pd.DataFrame:
    seasons = sorted(st.season.unique())
    folds = [(s, [x for x in seasons if x < s]) for s in EVAL_SEASONS_R3 if s in seasons]
    if PARTIAL_SEASON in seasons:
        folds.append((PARTIAL_SEASON, [x for x in seasons if x <= 2022]))
    rows, fitted = [], {}
    for eval_season, train_seasons in folds:
        table = fit_table(st[st.season.isin(train_seasons)])
        fitted[eval_season] = {"table": table, "train": train_seasons}
        rows.append(score_all(st[st.season == eval_season], table))
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def physics_table(st: pd.DataFrame) -> None:
    """Per-season fits of share/b/sigma, t-intervals across seasons."""
    seasons = sorted(st.season.unique())
    per = {s: fit_table(st[st.season == s]) for s in seasons}
    n = len(seasons)
    tcrit = tdist.ppf(0.975, df=n - 1)
    print(f"THE PHYSICS TABLE — per-season fits, {n} seasons, t-interval df={n - 1}")
    print("  boundary  share [95% CI]              b [95% CI]                sigma [95% CI]        (WNBA port: share/b/sigma)")
    for t in BOUNDARIES:
        for key, fmt in [("share", "%.4f"), ("b", "%.3f"), ("sigma", "%.2f")]:
            pass
        sh = np.array([per[s]["share"][t] for s in seasons])
        bb = np.array([per[s]["b"][t] for s in seasons])
        sg = np.array([per[s]["sigma"][t] for s in seasons])
        ci = lambda v: (v.mean(), v.mean() - tcrit * v.std(ddof=1) / np.sqrt(n), v.mean() + tcrit * v.std(ddof=1) / np.sqrt(n))
        s_m, s_l, s_h = ci(sh)
        b_m, b_l, b_h = ci(bb)
        g_m, g_l, g_h = ci(sg)
        print(f"  {BNAMES[t]:<7s}  {s_m:.4f} [{s_l:.4f},{s_h:.4f}]   {b_m:.3f} [{b_l:.3f},{b_h:.3f}]"
              f"       {g_m:5.2f} [{g_l:5.2f},{g_h:5.2f}]     ({WNBA_SHARE[t]:.4f} / {WNBA_B[t]:.3f} / {WNBA_SIGMA_PORTED[t]:.2f})")


def gate_read_r3(ev: pd.DataFrame) -> None:
    seasons = sorted(ev.season.unique())
    label = lambda s: f"{s}(PARTIAL)" if s == PARTIAL_SEASON else str(s)
    print(f"forward seasons evaluated: {len(seasons)} (floor >= {FLOOR} of 6 available, "
          f"per the 2026-09-02 R3b rulings): {[label(s) for s in seasons]}")
    pairs = [("a", "b"), ("a", "c"), ("b", "c")]
    wins = {k: 0 for k in "abc"}
    print("\npairwise paired Brier, season-clustered (negative favours the first arm):")
    for x, z in pairs:
        d = ev[f"brier_{x}"] - ev[f"brier_{z}"]
        cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
        if cm.hi < 0:
            verdict, _ = f"({x}) better, CI excludes zero", wins.__setitem__(x, wins[x] + 1)
        elif cm.lo > 0:
            verdict, _ = f"({z}) better, CI excludes zero", wins.__setitem__(z, wins[z] + 1)
        else:
            verdict = "CI straddles zero"
        print(f"  Brier({x})-Brier({z}): {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}]  "
              f"rows={cm.n} seasons={cm.n_clusters}  -> {verdict}")
    per = ev.groupby("season")[["brier_a", "brier_b", "brier_c"]].mean()
    per.index = [label(s) for s in per.index]
    print("\nper-season mean Brier (a=NBA-fit, b=WNBA-port, c=naive floor):")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    dominant = [k for k, w in wins.items() if w == 2]
    if len(seasons) < FLOOR:
        print(f"\nVERDICT FRAME: below the {FLOOR}-season floor — NO READ.")
    elif dominant:
        d0 = dominant[0]
        extra = " Arm (c) is the interpretability floor and is never adoptable." if d0 == "c" else ""
        print(f"\nVERDICT FRAME: arm ({d0}) dominates both others with CIs excluding zero.{extra}")
    else:
        print("\nVERDICT FRAME: no arm dominates both others."
              + ("\nAt all 6 available seasons: INDISTINGUISHABLE-AT-POWER; the pre-committed"
                 "\ntie-break adopts (a) — recorded as adoption-by-tie-break, never superiority."
                 if len(seasons) >= 6 else ""))
        print(POWER_NOTE)
    print(f"\n{CAPITAL_LINE}")


# ------------------------------------------------------------------ data


def build_boundary_states(games_path: str, plays_path: str) -> pd.DataFrame:
    states = load_real(games_path, plays_path)
    g = pd.read_csv(games_path)
    g["actual"] = g.team0_score + g.team1_score
    g["is_ot"] = g.max_period > 4
    g = g.dropna(subset=["closing_total"]).rename(columns={"closing_total": "mu"})
    st = states[states.t.isin(BOUNDARIES)].merge(
        g[["game_id", "mu", "actual", "is_ot"]], on="game_id")
    # the registration's coverage is 2017-2022 + 2025; 2016's ~24 lined games
    # are declared unusable and enter NOTHING — not training, not the table
    n_2016 = st[st.season == 2016].game_id.nunique()
    st = st[st.season != 2016]
    print(f"season 2016 excluded entirely per the coverage citation ({n_2016} lined games unusable)")
    n0 = len(st)
    push = st.actual == st.mu
    st = st[~push].copy()
    st["y_over"] = (st.actual > st.mu).astype(float)
    print(f"boundary states: {n0} rows -> {len(st)} after excluding {int(push.sum())} push rows "
          f"(actual == line) · OT games in sample: {int(st[st.is_ot].game_id.nunique())} "
          f"(settlement frame is OT-inclusive)")
    print(f"{st.game_id.nunique()} games, per season: {st.groupby('season').game_id.nunique().to_dict()}")
    return st


# ------------------------------------------------------------------ selftest


def _synth_r3(seed: int, b_table=None, sigma_table=None, share_table=None,
              n_seasons=8, games_per=1200, shuffle=False) -> pd.DataFrame:
    """Generator whose target (b, sigma) hold EXACTLY at every boundary.

    Latent final deviation A ~ N(0, sigma_F^2), actual = mu + A. Per boundary
    the surprise is surprise_t = c_t*A + w_t with the analytic solution
        Var(surprise_t) = v_t = (sigma_F^2 - sigma_t^2) / b_t^2
        c_t = b_t * v_t / sigma_F^2,   Var(w_t) = v_t - c_t^2 sigma_F^2
    which delivers regression slope exactly b_t and residual sd exactly
    sigma_t at every boundary simultaneously (requires sigma_F > sigma_t)."""
    rng = np.random.default_rng(seed)
    b_table = b_table or {36.0: 1.30, 24.0: 1.20, 12.0: 1.10}
    sigma_table = sigma_table or {36.0: 17.0, 24.0: 14.0, 12.0: 10.0}
    share_table = share_table or {36.0: 0.25, 24.0: 0.50, 12.0: 0.75}
    sigma_f = max(sigma_table.values()) + 2.0
    n = n_seasons * games_per
    mu = rng.normal(222, 10, n)
    a = rng.normal(0, sigma_f, n)
    frames = []
    for t in BOUNDARIES:
        v = (sigma_f**2 - sigma_table[t] ** 2) / b_table[t] ** 2
        c = b_table[t] * v / sigma_f**2
        w_sd = np.sqrt(v - c**2 * sigma_f**2)
        surprise = c * a + rng.normal(0, w_sd, n)
        frames.append(pd.DataFrame({
            "game_id": np.arange(n), "season": np.repeat(np.arange(n_seasons), games_per),
            "t": t, "tot": mu * share_table[t] + surprise, "mu": mu,
        }))
    st = pd.concat(frames, ignore_index=True)
    actual = mu + a
    st["actual"] = st.game_id.map(pd.Series(actual, index=np.arange(n)))
    st["is_ot"] = False
    if shuffle:
        st["actual"] = st.game_id.map(pd.Series(rng.permutation(actual), index=np.arange(n)))
        st["y_over"] = (st.actual > st.mu).astype(float)
    else:
        st["y_over"] = (st.actual > st.mu).astype(float)
    return st


def selftest() -> None:
    """The adopted three-part mutation clause, R3 form.

    1. Fitter recovers the generator's half-boundary b and sigma within
       tolerance (the half boundary is where the generator's targets are
       exact by construction).
    2. Distorted sigma tables lose to the fitted table in BOTH directions.
    3. Generator-recovery both ways: data generated under the WNBA-port
       table awards the win to (b) over the fitted-NBA-shape table and vice
       versa, at real-cohort power.
    4. Shuffled outcomes: the sharper (smaller-sigma) table must never win.
    """
    ok = True
    st = _synth_r3(1)
    tr, ev = st[st.season < 4], st[st.season >= 4]
    table = fit_table(tr)
    print(f"[1] fitted at half: b={table['b'][24.0]:.3f} (true 1.200), "
          f"sigma={table['sigma'][24.0]:.2f} (true 14.00), share={table['share'][24.0]:.4f} (true 0.5000)")
    ok &= abs(table["b"][24.0] - 1.20) < 0.05 and abs(table["sigma"][24.0] - 14.0) < 0.7

    y = ev.y_over.to_numpy(float)
    base = (prob_over(ev, table["share"], table["b"], table["sigma"]) - y) ** 2
    for name, mult in [("wide x1.5", 1.5), ("narrow /1.5", 1 / 1.5)]:
        sig2 = {t: v * mult for t, v in table["sigma"].items()}
        alt = (prob_over(ev, table["share"], table["b"], sig2) - y) ** 2
        d = pd.Series(base - alt, index=ev.index)
        cm = clustered_mean({s: d[ev.season == s].tolist() for s in ev.season.unique()})
        print(f"[2] fitted vs {name}: {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] (want hi<0)")
        ok &= cm.hi < 0

    # the rival must differ from the port as much as real arms plausibly do —
    # a near-identical rival would make "separable at power" vacuous
    nba_ish = {"b": {36.0: 1.45, 24.0: 1.32, 12.0: 1.15},
               "sigma": {36.0: 19.5, 24.0: 15.5, 12.0: 11.5},
               "share": {36.0: 0.26, 24.0: 0.51, 12.0: 0.76}}
    wnba_t = {"b": WNBA_B, "sigma": WNBA_SIGMA_PORTED, "share": WNBA_SHARE}
    for gen_name, gen, rival_name, rival in [("wnba-port", wnba_t, "nba-ish", nba_ish),
                                             ("nba-ish", nba_ish, "wnba-port", wnba_t)]:
        gs = _synth_r3(seed=int(sum(map(ord, gen_name))), b_table=gen["b"],
                       sigma_table=gen["sigma"], share_table=gen["share"])
        gev = gs[gs.season >= 2]  # 6 eval seasons — the real cohort's shape (df=5)
        yv = gev.y_over.to_numpy(float)
        pg = (prob_over(gev, gen["share"], gen["b"], gen["sigma"]) - yv) ** 2
        pr = (prob_over(gev, rival["share"], rival["b"], rival["sigma"]) - yv) ** 2
        d = pd.Series(pg - pr, index=gev.index)
        cm = clustered_mean({s: d[gev.season == s].tolist() for s in gev.season.unique()})
        print(f"[3] generated under {gen_name}, vs {rival_name}: {cm.mean:+.5f} "
              f"[{cm.lo:+.5f}, {cm.hi:+.5f}] (want hi<0)")
        ok &= cm.hi < 0

    sh = _synth_r3(9, shuffle=True)
    sev = sh[sh.season >= 4]
    yv = sev.y_over.to_numpy(float)
    sharp = {t: v / 1.5 for t, v in nba_ish["sigma"].items()}
    ps = (prob_over(sev, nba_ish["share"], nba_ish["b"], sharp) - yv) ** 2
    pt = (prob_over(sev, nba_ish["share"], nba_ish["b"], nba_ish["sigma"]) - yv) ** 2
    d = pd.Series(ps - pt, index=sev.index)
    cm = clustered_mean({s: d[sev.season == s].tolist() for s in sev.season.unique()})
    print(f"[4] shuffled null, sharper-vs-true: {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] "
          f"(sharper must NOT win)")
    ok &= not (cm.hi < 0)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games")
    ap.add_argument("--plays")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")
    st = build_boundary_states(args.games, args.plays)
    print("\n=== R3b PHYSICS TABLE — reports regardless of gate outcome ===")
    physics_table(st)
    ev = walk_forward_r3(st)
    print("\n=== R3b GATE READ — out-of-sample seasons only ===")
    gate_read_r3(ev)
    # (b') — LABELLED NEVER-GATING SENSITIVITY, per the ruling: the absolute
    # triple unchanged, "so that if absolute-invariance is somehow true it
    # shows up honestly without gating anything."
    y = ev.y_over.to_numpy(float)
    bprime = (prob_over(ev, WNBA_SHARE, WNBA_B, WNBA_SIGMA_ABSOLUTE) - y) ** 2
    print("\n=== SENSITIVITY (b') — absolute-sigma port, NEVER GATING ===")
    for x, brier_x in [("a", ev.brier_a), ("b", ev.brier_b)]:
        d = pd.Series(brier_x.to_numpy() - bprime, index=ev.index)
        cm = clustered_mean({s: d[ev.season == s].tolist() for s in sorted(ev.season.unique())})
        print(f"  Brier({x})-Brier(b'): {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}]  seasons={cm.n_clusters}")
    print("  (the gate above stands on the rate-keyed port regardless)")


if __name__ == "__main__":
    main()
