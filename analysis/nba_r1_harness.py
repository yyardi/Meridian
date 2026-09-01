"""R1b — NBA win-curve sigma: the committed harness, pinned BEFORE first read.

Registration: docs/math/nba-constants-registrations.md — R1b (supersedes R1;
anchor is the closing SPREAD). Standing terms honored here:

  - Walk-forward by season; ONLY out-of-sample seasons score.
  - Intervals cluster BY SEASON (the honest unit for a constant).
  - OT *states* excluded; OT *games* kept — regulation states score against
    the eventual final winner.
  - PHYSICS-ONLY: fitted constant tables, never point-in-time claims.
  - Mutation (--selftest) runs before the first read of real data; the
    mutation form is the amended clause adopted on main (PR #132).

Reproduce:

    .venv/bin/python analysis/nba_r1_harness.py --selftest
    .venv/bin/python analysis/nba_r1_harness.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz

PINNED CONVENTIONS — each verified empirically on the pins, printed at load
===========================================================================

Games file. team0 is ALWAYS home, team1 ALWAYS away (asserted). Margin and
outcome are home-frame: m = home - away, y = 1 iff home wins the final
(OT included in the outcome). closing_spread is home-frame with NEGATIVE =
home favored — verified before first use: P(home win | spread <= -5) = 0.764,
P(home win | spread >= +5) = 0.268, and where moneylines exist the favorite
agrees 99.6% of the time. Therefore the anchor is E = -closing_spread
(expected home margin). Games with max_period < 4 (exhibition/suspended
defects) and games without a closing spread are excluded, with counts printed
per season.

Plays file. clock_display counts DOWN within a period; formats "M:SS"/"MM:SS"
(minutes:seconds remaining) and "SS.s"/"S.s" (seconds remaining, final
minute); anything else is dropped and counted. File order within a game is
NOT chronological (verified); chronological order is reconstructed by sorting
on (period, -minutes_left, home_score+away_score), valid because scores are
monotone in play time. minutes_left = (4 - period)*12 + clock minutes, for
periods 1-4 only; period >= 5 (OT states) dropped and counted.

Feed-quality exclusions (counts printed): a game is kept iff its play feed
reaches the final regulation minute (some play with minutes_left <= 1) AND
its plays' final margin agrees with the games-table margin within 2 points
(the games table is authoritative for y; a feed that truncates mid-game would
otherwise report stale states as endgame states).

State grid. t = whole minutes remaining in regulation, grid t = 1..47; the
state at t is the LAST play with minutes_left >= t (the state entering that
minute).

The curve — IDENTICAL for every arm (R1b: E direct from the spread)
-------------------------------------------------------------------
    P_arm(m, t) = Phi( (m + E * t/48) / (sigma_arm(t) * sqrt(t)) ),  E = -closing_spread

The R1 moneyline inversion (E through the arm's own sigma) survives ONLY as a
labelled sensitivity on ML-covered seasons, never gating, per R1b.

The three arms — sigma(t) tables in points per sqrt(minute)
-----------------------------------------------------------
(a) NBA-fitted, walk-forward: two-step MLE on training seasons only.
    Step 1: global sigma by Bernoulli MLE of the full curve.
    Step 2: per-phase sigma by per-bucket MLE on t-buckets (36,48], (24,36],
    (12,24], (0,12]. The phase table is the arm; global and per-phase BOTH
    report as the physics table with season-clustered spread across folds.
(b) WNBA port (convention per PR #130, carried unchanged): 2.628 is points
    per sqrt(minute) — A RATE, dimensionless in game length — so NO 40->48
    rescale; the trap would be porting the implied 16.6-point full-game sd.
    Phase decay ports by QUARTER BOUNDARY CORRESPONDENCE: sigma_b(t)
    piecewise-linear through (36, 2.98), (24, 2.77), (12, 2.40), flat
    outside. The flat segment above 36 intentionally does NOT pass through
    the global 2.628: the boundary values ARE the decay.
(c) The 2.0 rule of thumb: sigma(t) = 2.0, flat.

Walk-forward per R1b
--------------------
First fit trains on 2015-16; evaluated seasons 2017..2022 contiguous (each
trained on all prior spread-covered seasons), plus 2025 as a PARTIAL-COVERAGE
season, labelled, trained on <= 2022. 2023/24 carry no odds and are neither
trained on nor evaluated. Floors: >= 6 evaluated seasons.

Gate arithmetic
---------------
Per-state Brier per arm; pairwise per-state diffs; season-clustered mean and
95% CI via core.quote.adverse_selection.clustered_mean, clusters = evaluation
season. PASS/adopt = one arm dominates BOTH others with CIs excluding zero.
At all 7 with no dominant arm: INDISTINGUISHABLE-AT-POWER, tie-break adopts
(a), recorded as adoption-by-tie-break. Any INDISTINGUISHABLE verdict prints
the selftest's generator-recovery separability beside it: the arms ARE
separable at this cohort size, so the verdict is about basketball, not power.
"""

from __future__ import annotations

import argparse
import re
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
EVAL_SEASONS = [2017, 2018, 2019, 2020, 2021, 2022]
PARTIAL_SEASON = 2025  # labelled partial-coverage, train <= 2022
NO_ODDS_SEASONS = {2023, 2024}

POWER_LINE = (
    "POWER (from --selftest generator-recovery at ~1,200 games/season, 6 eval seasons):\n"
    "  data generated under flat-2.0 beats the WNBA port  -0.00210 [-0.00274, -0.00146]\n"
    "  data generated under the WNBA port beats flat-2.0  -0.00097 [-0.00172, -0.00021]\n"
    "  The arms ARE separable at this cohort size; an INDISTINGUISHABLE verdict is a\n"
    "  statement about basketball, not about our power."
)
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


def curve_prob(m: np.ndarray, t: np.ndarray, e: np.ndarray, sigma_fn) -> np.ndarray:
    """The one registered curve (R1b): E enters directly from the spread."""
    t = np.asarray(t, dtype=float)
    z = (m + e * t / REG_MINUTES) / (sigma_fn(t) * np.sqrt(t))
    return norm.cdf(z)


def fit_arm_a(train: pd.DataFrame) -> tuple[float, dict[tuple[float, float], float]]:
    """Two-step MLE on TRAINING rows only. Returns (global sigma, phase table)."""
    m, t, e, y = (train[c].to_numpy(float) for c in ["m", "t", "e", "y"])

    def nll(s, mm, tt, ee, yy):
        p = np.clip(norm.cdf((mm + ee * tt / REG_MINUTES) / (s * np.sqrt(tt))), 1e-9, 1 - 1e-9)
        return -np.sum(yy * np.log(p) + (1 - yy) * np.log(1 - p))

    s_glob = minimize_scalar(lambda s: nll(s, m, t, e, y), bounds=SIGMA_BOUNDS, method="bounded").x
    table = {}
    for lo, hi in PHASES:
        mask = (t > lo) & (t <= hi)
        table[(lo, hi)] = float(
            minimize_scalar(lambda s: nll(s, m[mask], t[mask], e[mask], y[mask]), bounds=SIGMA_BOUNDS, method="bounded").x
        )
    return float(s_glob), table


# ------------------------------------------------------------------ walk-forward


def walk_forward(states: pd.DataFrame) -> pd.DataFrame:
    """R1b folds: eval 2017..2022 trained on prior spread-covered seasons;
    2025 trained on <= 2022. Returns per-state eval rows with per-arm Brier."""
    rows = []
    fitted = {}
    folds = [(s, [x for x in sorted(states.season.unique()) if x < s]) for s in EVAL_SEASONS]
    if PARTIAL_SEASON in states.season.unique():
        folds.append((PARTIAL_SEASON, [x for x in sorted(states.season.unique()) if x <= 2022]))
    for eval_season, train_seasons in folds:
        train = states[states.season.isin(train_seasons)]
        ev = states[states.season == eval_season].copy()
        s_glob, table = fit_arm_a(train)
        fitted[eval_season] = {"global": s_glob, "table": table, "train": train_seasons}
        arms = {"a": sigma_phase_table(table), "b": sigma_wnba_port, "c": sigma_flat(2.0)}
        for name, fn in arms.items():
            p = curve_prob(ev.m.to_numpy(float), ev.t.to_numpy(float), ev.e.to_numpy(float), fn)
            ev[f"brier_{name}"] = (p - ev.y.to_numpy(float)) ** 2
        rows.append(ev)
    out = pd.concat(rows, ignore_index=True)
    out.attrs["fitted"] = fitted
    return out


def gate_read(ev: pd.DataFrame) -> None:
    seasons = sorted(ev.season.unique())
    label = lambda s: f"{s}(PARTIAL)" if s == PARTIAL_SEASON else str(s)
    print(f"forward seasons evaluated: {len(seasons)} (floor >= 6): {[label(s) for s in seasons]}")
    fitted = ev.attrs.get("fitted", {})
    if fitted:
        print("\nTHE PHYSICS TABLE — arm (a) per fold (points per sqrt-minute):")
        print("  eval  global   Q1(36,48]  Q2(24,36]  Q3(12,24]  Q4(0,12]   trained on")
        for s, f in fitted.items():
            tv = [f["table"][p] for p in PHASES]
            print(f"  {label(s):<11s} {f['global']:.3f}   " + "      ".join(f"{v:.3f}" for v in tv)
                  + f"   {f['train'][0]}..{f['train'][-1]}")
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
    per = ev.groupby("season")[[f"brier_{k}" for k in "abc"]].mean()
    per.index = [label(s) for s in per.index]
    print("\nper-season mean Brier (a=NBA-fit, b=WNBA-port, c=2.0):")
    print(per.to_string(float_format=lambda v: f"{v:.5f}"))
    dominant = [k for k, w in wins.items() if w == 2]
    if len(seasons) < 6:
        print("\nVERDICT FRAME: below the 6-season floor — NO READ.")
    elif dominant:
        print(f"\nVERDICT FRAME: arm ({dominant[0]}) dominates both others with CIs excluding zero.")
    else:
        print("\nVERDICT FRAME: no arm dominates both others."
              + ("\nAt all 7 available seasons: INDISTINGUISHABLE-AT-POWER; the pre-committed"
                 "\ntie-break adopts (a) — recorded as adoption-by-tie-break, never superiority."
                 if len(seasons) >= 7 else ""))
        print(POWER_LINE)
    print(f"\n{CAPITAL_LINE}")


# ------------------------------------------------------------------ data


CLOCK_MS = re.compile(r"^(\d{1,2}):(\d{2})$")
CLOCK_S = re.compile(r"^(\d{1,2}(?:\.\d)?)$")


def parse_clock_minutes(s: pd.Series) -> pd.Series:
    """Minutes remaining IN PERIOD from clock_display; NaN for unparseable."""
    s = s.astype(str)
    ms = s.str.extract(CLOCK_MS)
    sec = s.str.extract(CLOCK_S)
    out = pd.to_numeric(ms[0]) + pd.to_numeric(ms[1]) / 60.0
    return out.fillna(pd.to_numeric(sec[0]) / 60.0)


def load_real(games_path: str, plays_path: str) -> pd.DataFrame:
    g = pd.read_csv(games_path)
    assert (g.team0_homeaway == "home").all() and (g.team1_homeaway == "away").all(), "team0/team1 frame changed"
    g = g.rename(columns={"team0_score": "home_final", "team1_score": "away_final"})
    g["home_margin"] = g.home_final - g.away_final
    assert (g.home_margin != 0).all(), "tied final — impossible in NBA, data defect"
    g["y"] = (g.home_margin > 0).astype(float)
    g["e"] = -g.closing_spread  # NEGATIVE spread = home favored, verified below

    print("=== COMPOSITION AND CONVENTION CHECKS (before any ratio) ===")
    s = g.dropna(subset=["closing_spread"])
    big_n, big_p = s[s.closing_spread <= -5], s[s.closing_spread >= 5]
    ml = s.dropna(subset=["closing_ml_home", "closing_ml_away"])
    fav_agree = (ml[ml.closing_spread < 0].closing_ml_home < ml[ml.closing_spread < 0].closing_ml_away).mean()
    print(f"spread sign: P(home win|spread<=-5)={(big_n.home_margin > 0).mean():.3f} (n={len(big_n)}), "
          f"P(home win|spread>=+5)={(big_p.home_margin > 0).mean():.3f} (n={len(big_p)}), "
          f"ML favorite agreement {fav_agree:.3f} -> E = -closing_spread confirmed")
    n0 = len(g)
    bad_period = g.max_period < 4
    no_spread = g.closing_spread.isna()
    g = g[~bad_period & ~no_spread]
    print(f"games: {n0} -> {len(g)} (excluded {int(bad_period.sum())} max_period<4 defects, "
          f"{int((no_spread & ~bad_period).sum())} without closing spread)")
    print("spread-covered games by season:", g.season.value_counts().sort_index().to_dict())

    p = pd.read_csv(plays_path)
    n_plays = len(p)
    p = p[p.period <= 4].copy()
    n_ot = n_plays - len(p)
    p["clock_min"] = parse_clock_minutes(p.clock_display)
    n_bad_clock = int(p.clock_min.isna().sum())
    p = p.dropna(subset=["clock_min"])
    p["minutes_left"] = (4 - p.period) * 12.0 + p.clock_min
    print(f"plays: {n_plays} -> {len(p)} (dropped {n_ot} OT-state plays, {n_bad_clock} unparseable clocks)")

    # feed quality: reaches the final regulation minute AND agrees with finals
    lastp = p.sort_values(["game_id", "period", "minutes_left"], ascending=[True, True, False]) \
             .groupby("game_id").last()
    reach = p.groupby("game_id").minutes_left.min() <= 1.0
    q = g.merge(lastp[["home_score", "away_score"]], on="game_id", how="left")
    agree = (q.home_score - q.away_score - q.home_margin).abs() <= 2
    okset = set(q.game_id[agree & q.game_id.map(reach).fillna(False)])
    print(f"feed quality: {len(g) - len(okset)} games excluded "
          f"(feed truncated before final minute, missing plays, or margin disagreement > 2)")
    g = g[g.game_id.isin(okset)]

    # chronological order within game: scores are monotone, so total points breaks clock ties
    p = p[p.game_id.isin(okset)]
    p = p.sort_values(["game_id", "minutes_left", "home_score"], ascending=[True, False, True])
    frames = []
    for t in GRID:
        snap = p[p.minutes_left >= t].groupby("game_id")[["home_score", "away_score"]].last()
        snap["t"] = float(t)
        frames.append(snap.reset_index())
    states = pd.concat(frames, ignore_index=True)
    states["m"] = states.home_score - states.away_score
    states["tot"] = states.home_score + states.away_score  # for R3b; R1's arithmetic ignores it
    states = states.merge(g[["game_id", "season", "e", "y"]], on="game_id")
    print(f"states: {len(states)} rows, {states.game_id.nunique()} games, "
          f"{states.season.nunique()} seasons, grid t=1..47")
    return states[["game_id", "season", "t", "m", "tot", "e", "y"]]


# ------------------------------------------------------------------ ML sensitivity
# Registered inside R1b as a never-gating labelled sensitivity; executed after
# the primary read, per its registered never-gating status; ordering disclosed.
# Nothing in the gate arithmetic above is touched by this section.


def devig_home_prob(ml_home: pd.Series, ml_away: pd.Series) -> pd.Series:
    """American moneylines -> proportional de-vigged home probability."""

    def implied(ml):
        ml = ml.astype(float)
        return np.where(ml < 0, -ml / (-ml + 100.0), 100.0 / (ml + 100.0))

    qh, qa = implied(ml_home), implied(ml_away)
    return pd.Series(qh / (qh + qa), index=ml_home.index)


def ml_sensitivity(states: pd.DataFrame, games_path: str) -> None:
    """R1's original construction: E through the arm's OWN sigma(48) from the
    de-vigged closing moneyline — the mildly circular form R1b demoted. Run on
    ML-covered games in the same eval folds; never gating."""
    g = pd.read_csv(games_path)
    g = g.dropna(subset=["closing_ml_home", "closing_ml_away"]).copy()
    g["p0"] = devig_home_prob(g.closing_ml_home, g.closing_ml_away).clip(0.02, 0.98)
    st = states.merge(g[["game_id", "p0"]], on="game_id")
    print("\n=== SENSITIVITY — ML inversion (registered never-gating; executed after the")
    print("    primary read per its registered status; ordering disclosed) ===")
    print(f"ML-covered states: {len(st)} rows, {st.game_id.nunique()} games, "
          f"seasons {sorted(st.season.unique())}")
    rows = []
    folds = [(s, [x for x in sorted(st.season.unique()) if x < s]) for s in EVAL_SEASONS]
    if PARTIAL_SEASON in st.season.unique():
        folds.append((PARTIAL_SEASON, [x for x in sorted(st.season.unique()) if x <= 2022]))
    for eval_season, train_seasons in folds:
        train, ev = st[st.season.isin(train_seasons)], st[st.season == eval_season].copy()
        if len(train) == 0 or len(ev) == 0:
            print(f"  fold {eval_season}: skipped (train seasons with ML: {train_seasons})")
            continue
        s_glob, table = fit_arm_a(train)  # trains on the SPREAD anchor as gated
        for name, fn in [("a", sigma_phase_table(table)), ("b", sigma_wnba_port), ("c", sigma_flat(2.0))]:
            e_ml = fn(np.full(len(ev), REG_MINUTES)) * np.sqrt(REG_MINUTES) * norm.ppf(ev.p0.to_numpy(float))
            p = curve_prob(ev.m.to_numpy(float), ev.t.to_numpy(float), e_ml, fn)
            ev[f"brier_{name}"] = (p - ev.y.to_numpy(float)) ** 2
        rows.append(ev)
    ev = pd.concat(rows, ignore_index=True)
    seasons = sorted(ev.season.unique())
    for x, z in [("a", "b"), ("a", "c"), ("b", "c")]:
        d = ev[f"brier_{x}"] - ev[f"brier_{z}"]
        cm = clustered_mean({s: d[ev.season == s].tolist() for s in seasons})
        print(f"  ML-anchored Brier({x})-Brier({z}): {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}]  "
              f"rows={cm.n} seasons={cm.n_clusters}")
    print("  (sensitivity only — the gate stands on the spread anchor regardless)")


# ------------------------------------------------------------------ selftest


def _synth(seed: int, n_seasons=11, games_per=400, sigma_fn=None, shuffle=False):
    """Brownian-margin seasons with a spread anchor consistent with the truth."""
    rng = np.random.default_rng(seed)
    sigma_fn = sigma_fn or sigma_flat(2.6)
    rows = []
    gid = 0
    for season in range(n_seasons):
        for _ in range(games_per):
            e_true = rng.normal(0, 6)
            m = 0.0
            path = {}
            for t in range(47, -1, -1):
                m += e_true / REG_MINUTES + float(sigma_fn(np.array([t + 1.0]))[0]) * rng.normal()
                path[t] = m
            y = 1.0 if m > 0 else 0.0
            for t in GRID:
                rows.append({"game_id": gid, "season": season, "t": float(t), "m": path[t], "e": e_true, "y": y})
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
        p = curve_prob(ev.m.to_numpy(float), ev.t.to_numpy(float), ev.e.to_numpy(float), fn)
        ev[f"brier_{name}"] = (p - ev.y.to_numpy(float)) ** 2
    return ev


def selftest() -> None:
    """The amended mutation clause (adopted on main), run before any real read.

    1. Walk-forward fitter recovers a known sigma within tolerance.
    2. Distorted tables LOSE to the truth in BOTH directions, CI excluding zero.
    3. Generator-recovery: the win follows the generating table, both
       directions, at real-cohort power (~1,200 games/season).
    4. Shuffled-outcome null asserts the artifact direction: the sharper
       table must never win (flatness mechanically wins on destroyed signal).
    """
    ok = True
    states = _synth(11)
    seasons = sorted(states.season.unique())

    s_glob, table = fit_arm_a(states[states.season.isin(seasons[:5])])
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
          f"(sharper must NOT win)")
    ok &= not (cm.hi < 0)

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games", help="pinned games CSV")
    ap.add_argument("--plays", help="pinned plays CSV(.gz)")
    ap.add_argument("--ml-sensitivity", action="store_true",
                    help="run the registered never-gating ML-inversion sensitivity")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")
    states = load_real(args.games, args.plays)
    ev = walk_forward(states)
    print("\n=== R1b GATE READ — out-of-sample seasons only ===")
    gate_read(ev)
    if args.ml_sensitivity:
        ml_sensitivity(states, args.games)


if __name__ == "__main__":
    main()
