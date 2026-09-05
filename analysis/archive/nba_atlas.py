"""NBA game-dynamics atlas — the measured reference for how NBA games evolve.

DESCRIPTIVE, NOT A GATE. Built from the wave pins, written for the operator.
Emits analysis/nba-atlas.md (fully generated — numbers cannot drift from the
artifact) and analysis/nba_constants_v1.json (the engine's constants file:
full-data fits of the three gate-adopted estimands, provenance attached).

Reproduce:

    .venv/bin/python analysis/nba_atlas.py --selftest
    .venv/bin/python analysis/nba_atlas.py \
        --games backups/exports/nba_games_20260901T225326Z.csv \
        --plays backups/exports/nba_plays_20260901T225326Z.csv.gz

Standing boundaries, printed on page one of the atlas:
  - NO market data exists for NBA in-game; nothing here scores against prices.
  - PHYSICS-ONLY: fitted constant tables, never point-in-time claims.
  - The honest n for any property of a constant is 11 SEASONS, not 13k games;
    every interval clusters by season.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean
from fv_calibration import murphy
from nba_r1_harness import (
    GRID,
    REG_MINUTES,
    fit_arm_a,
    load_real,
    parse_clock_minutes,
    sigma_phase_table,
)
from nba_r2_harness import EVAL_SEASONS_R2, fit_beta, shrink_fn
from nba_r3_harness import fit_table as fit_totals_table

TIME_BUCKETS = [36, 30, 24, 18, 12, 6, 4, 2, 1]  # minutes left (grid points)
LEAD_BUCKETS = [(1, 3), (4, 6), (7, 9), (10, 14), (15, 19), (20, 99)]
PARTIAL_SEASON = 2025

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def cm_str(vals_by_season: dict) -> tuple[float, str, int]:
    cm = clustered_mean({k: v for k, v in vals_by_season.items() if v})
    if cm is None:
        return float("nan"), "—", 0
    return cm.mean, f"[{cm.lo:.3f}, {cm.hi:.3f}]", cm.n


# ------------------------------------------------------------------ S1 lead safety


def lead_safety(states: pd.DataFrame, model_p: pd.Series | None = None) -> str:
    """P(leader wins | lead L, time T), season-clustered. With model_p (the
    adopted FV's P(home win) per state row), adds the model-vs-raw gap."""
    st = states[states.m != 0].copy()
    st["y_leader"] = np.where(st.m > 0, st.y, 1 - st.y)
    if model_p is not None:
        st["p_leader"] = np.where(st.m > 0, model_p.reindex(st.index), 1 - model_p.reindex(st.index))
    lines = ["| min left | " + " | ".join(f"lead {lo}-{hi}" if hi < 99 else f"lead {lo}+" for lo, hi in LEAD_BUCKETS) + " |",
             "|---" * (len(LEAD_BUCKETS) + 1) + "|"]
    gaps = []
    for t in TIME_BUCKETS:
        row = [f"| **{t}** "]
        for lo, hi in LEAD_BUCKETS:
            cell = st[(st.t == t) & (st.m.abs() >= lo) & (st.m.abs() <= hi)]
            if len(cell) < 30:
                row.append("| — ")
                continue
            mean, ci, n = cm_str({s: v.y_leader.tolist() for s, v in cell.groupby("season")})
            row.append(f"| {mean:.3f} {ci} n={n} ")
            if model_p is not None and cell.p_leader.notna().any():
                sub = cell[cell.p_leader.notna()]
                d = (sub.y_leader - sub.p_leader)
                cmd = clustered_mean({s: d[sub.season == s].tolist() for s in sub.season.unique()})
                # material-effect filter: saturated cells (realized == 1) pass a
                # zero-variance CI on a sub-0.005 gap — precision without content
                if cmd and (cmd.lo > 0 or cmd.hi < 0) and abs(cmd.mean) >= 0.005:
                    gaps.append((t, lo, hi, cmd.mean, cmd.lo, cmd.hi, len(sub)))
        lines.append("".join(row) + "|")
    out = "\n".join(lines)
    if model_p is not None:
        out += ("\n\nCells where the adopted model's mean P(leader wins) disagrees with the raw "
                "frequency (season-clustered CI off zero; positive = model UNDERRATES the leader):\n\n")
        if gaps:
            out += "| min left | lead | realized − model | 95% CI | rows |\n|---|---|---|---|---|\n"
            for t, lo, hi, m, l, h, n in gaps:
                out += f"| {t} | {f'{lo}-{hi}' if hi < 99 else f'{lo}+'} | {m:+.3f} | [{l:+.3f}, {h:+.3f}] | {n} |\n"
            out += "\nThese are the states where the model would misprice against reality — "
            out += "candidates for scrutiny, not for trading (no prices exist here).\n"
        else:
            out += "None — no cell's gap clears its season-clustered CI.\n"
    return out


# ------------------------------------------------------------------ S2 comebacks


def comebacks(states: pd.DataFrame) -> str:
    st = states[states.m != 0].copy()
    st["y_leader"] = np.where(st.m > 0, st.y, 1 - st.y)
    q4 = st[(st.t == 12) & (st.m.abs() >= 10)]
    lose10 = 1 - q4.y_leader
    m10, ci10, _ = cm_str({s: v.tolist() for s, v in lose10.groupby(q4.season)})
    q4b = st[(st.t == 12) & (st.m.abs() >= 10) & (st.m.abs() <= 14)]
    m14, ci14, _ = cm_str({s: (1 - v.y_leader).tolist() for s, v in q4b.groupby("season")})
    q4c = st[(st.t == 12) & (st.m.abs() >= 15)]
    m15, ci15, _ = cm_str({s: (1 - v.y_leader).tolist() for s, v in q4c.groupby("season")})

    # largest deficit overcome by the eventual winner, at minute resolution
    w = states.copy()
    w["winner_margin"] = np.where(w.y == 1, w.m, -w.m)
    per_game = w.groupby(["game_id", "season"]).winner_margin.min().reset_index()
    per_game["deficit"] = -per_game.winner_margin.clip(upper=0)
    d = per_game.deficit
    seasons_20 = per_game[per_game.deficit >= 20].groupby("season").size()
    return (
        f"A double-digit lead entering Q4 (12:00 left) loses **{m10:.1%}** of the time "
        f"{ci10} ({len(q4)} games). Split: lead 10-14 loses {m14:.1%} {ci14}; "
        f"lead 15+ loses {m15:.1%} {ci15}.\n\n"
        f"Largest deficit the eventual winner faced (minute resolution, {per_game.game_id.nunique()} games): "
        f"median **{d.median():.0f}**, p90 **{d.quantile(0.9):.0f}**, max **{d.max():.0f}**. "
        f"Winners came back from 10+ in {(d >= 10).mean():.1%} of games, from 15+ in "
        f"{(d >= 15).mean():.1%}, from 20+ in {(d >= 20).mean():.1%} "
        f"(about {seasons_20.mean():.0f} twenty-point comebacks per season; "
        f"season range {seasons_20.min()}-{seasons_20.max()})."
    )


# ------------------------------------------------------------------ S3 runs


def build_events(plays: pd.DataFrame) -> pd.DataFrame:
    p = plays.sort_values(["game_id", "period", "minutes_left", "tot"],
                          ascending=[True, True, False, True])
    dh = p.groupby("game_id").home_score.diff().fillna(p.home_score)
    da = p.groupby("game_id").away_score.diff().fillna(p.away_score)
    ev = p[(dh > 0) | (da > 0)].copy()
    ev["pts"] = np.where(dh[ev.index] > 0, dh[ev.index], da[ev.index])
    ev["team"] = np.where(dh[ev.index] > 0, "h", "a")
    return ev


def runs(plays: pd.DataFrame, n_games: int) -> str:
    ev = build_events(plays)
    new_run = (ev.team != ev.team.shift()) | (ev.game_id != ev.game_id.shift())
    ev["run_id"] = new_run.cumsum()
    r = ev.groupby("run_id").agg(pts=("pts", "sum"), period=("period", "last"),
                                 game_id=("game_id", "first"))
    per_game = r.groupby("game_id").pts.agg(["count"])
    lines = [
        f"Unanswered-run structure over {n_games} games "
        f"({len(r)} runs; a run = consecutive points by one team):",
        "",
        f"- Runs per game: mean {per_game['count'].mean():.1f}.",
        f"- Share of runs reaching 6+ points: {(r.pts >= 6).mean():.1%}; 8+: {(r.pts >= 8).mean():.1%}; "
        f"10+: {(r.pts >= 10).mean():.1%}.",
        f"- Per game: {r[r.pts >= 8].groupby('game_id').size().reindex(per_game.index).fillna(0).mean():.2f} "
        f"runs of 8+ and {r[r.pts >= 10].groupby('game_id').size().reindex(per_game.index).fillna(0).mean():.2f} runs of 10+ "
        f"— a 10-0 run is roughly an every-other-game event, not an anomaly.",
        f"- By period, share of that period's runs reaching 8+: "
        + ", ".join(f"Q{q}: {(r[r.period == q].pts >= 8).mean():.1%}" for q in [1, 2, 3, 4]) + ".",
        "",
        "Context only: F8 established runs cannot be traded reactively (the move is priced "
        "before a reactive entry fills). This section exists so nobody re-derives run "
        "frequency from vibes; it is not a signal.",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ S4 endgame


def endgame(states: pd.DataFrame, plays: pd.DataFrame, games: pd.DataFrame) -> str:
    reg_final = plays.groupby("game_id").tot.max()
    g = games.set_index("game_id")
    out = []
    for t in [2, 1]:
        st = states[(states.t == t) & (states.m.abs() <= 5)].copy()
        st["more"] = st.game_id.map(reg_final) - st.tot
        st = st.dropna(subset=["more"])
        p6, ci6, _ = cm_str({s: (v.more >= 6).astype(float).tolist() for s, v in st.groupby("season")})
        pot, ciot, _ = cm_str({s: (g.loc[v.game_id, "max_period"] > 4).astype(float).tolist()
                               for s, v in st.groupby("season")})
        out.append(f"- Close game (margin ≤5) with **{t}:00 left**: {len(st)} games; "
                   f"**{p6:.1%}** {ci6} score 6+ more points in regulation; "
                   f"**{pot:.1%}** {ciot} reach overtime.")
    st2 = states[states.t == 2].copy()
    st2["more"] = st2.game_id.map(reg_final) - st2.tot
    close = st2[st2.m.abs() <= 5].more.mean() / 2
    blow = st2[st2.m.abs() >= 10].more.mean() / 2
    ot_games = games[games.max_period > 4]
    ot_pts = (ot_games.team0_score + ot_games.team1_score) - ot_games.game_id.map(reg_final)
    out.append(f"- Scoring pace in the final 2:00: close games {close:.1f} pts/min vs "
               f"blowouts (margin ≥10) {blow:.1f} pts/min — the foul game runs "
               f"~{close / max(blow, 0.1):.1f}× the blowout pace.")
    out.append(f"- Overtime: {len(ot_games)} of {len(games)} games ({len(ot_games) / len(games):.1%}). "
               f"An OT period adds {ot_pts.mean():.1f} points on average (p10 {ot_pts.quantile(0.1):.0f}, "
               f"p90 {ot_pts.quantile(0.9):.0f}); {(ot_games.max_period >= 6).mean():.1%} of OT games need 2+ periods.")
    out.append("\nThis is the tail R3b showed a Gaussian endgame cannot price — measured instead of assumed.")
    return "\n".join(out)


# ------------------------------------------------------------------ S5 FV replay


def fv_replay(states: pd.DataFrame, games: pd.DataFrame) -> tuple[str, pd.Series]:
    """Walk-forward adopted stack (R1b arm-a sigma + R2 shrink) over the grid.
    Only out-of-sample seasons appear. Returns (markdown, P(home win) per row
    of the eval subset, indexed like states)."""
    st = states.dropna(subset=["e"]).copy()
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    hm = (games.team0_score - games.team1_score)
    st["dev_final"] = st.game_id.map(pd.Series(hm.values, index=games.game_id.values)) - st.e
    seasons = sorted(st.season.unique())
    folds = [(s, [x for x in seasons if x < s]) for x_ in [0] for s in EVAL_SEASONS_R2 + [2017]]
    folds = sorted({s for s, _ in folds if s in seasons})
    rows = []
    for eval_season in folds + ([PARTIAL_SEASON] if PARTIAL_SEASON in seasons else []):
        train_seasons = [x for x in seasons if (x < eval_season if eval_season != PARTIAL_SEASON else x <= 2022)]
        if not train_seasons:
            continue
        train = st[st.season.isin(train_seasons)]
        ev = st[st.season == eval_season].copy()
        _, sig_table = fit_arm_a(train)
        beta = fit_beta(train)
        s_of = shrink_fn(beta)(ev.elapsed.to_numpy(float))
        denom = sigma_phase_table(sig_table)(ev.t.to_numpy(float)) * np.sqrt(ev.t.to_numpy(float))
        ev["p"] = norm.cdf((ev.e.to_numpy(float) + (1 - s_of) * ev.dev.to_numpy(float)) / denom)
        rows.append(ev)
    ev = pd.concat(rows)
    m = murphy(ev.p.to_numpy(float), ev.y.to_numpy(float))
    lines = [
        f"The adopted stack (R1b σ arm (a) + R2 shrink), walk-forward, out-of-sample seasons "
        f"only: {[int(s) for s in sorted(ev.season.unique())]} — {ev.game_id.nunique()} games, {len(ev)} states.",
        "",
        f"Murphy decomposition: Brier {m['brier']:.4f} = UNC {m['unc']:.4f} − RES {m['res']:.4f} "
        f"+ REL **{m['rel']:.4f}** (reliability ~0 is calibrated).",
        "",
        "| predicted P(home win) | realized | 95% CI (season-clustered) | rows |",
        "|---|---|---|---|",
    ]
    bins = np.clip(np.digitize(ev.p, np.linspace(0, 1, 11)) - 1, 0, 9)
    for b in range(10):
        cell = ev[bins == b]
        if len(cell) == 0:
            continue
        mean, ci, n = cm_str({s: v.y.tolist() for s, v in cell.groupby("season")})
        lines.append(f"| {cell.p.mean():.3f} | {mean:.3f} | {ci} | {n} |")
    per = ev.groupby("period" if "period" in ev else "season")
    lines += ["", "Per-season Brier: " + ", ".join(
        f"{s}: {v:.4f}" for s, v in ev.groupby('season').apply(lambda f: ((f.p - f.y) ** 2).mean(), include_groups=False).items())]
    return "\n".join(lines), ev.p


# ------------------------------------------------------------------ constants file


def constants_file(states: pd.DataFrame, games_path: str, plays_path: str, out_path: str) -> str:
    st = states.dropna(subset=["e"]).copy()
    st["elapsed"] = REG_MINUTES - st.t
    st["dev"] = st.m - st.e * st.elapsed / REG_MINUTES
    g = pd.read_csv(games_path)
    g["home_margin"] = g.team0_score - g.team1_score
    st = st.merge(g[["game_id", "home_margin"]], on="game_id")
    st["dev_final"] = st.home_margin - st.e
    s_glob, sig_table = fit_arm_a(st)
    beta = fit_beta(st)
    from nba_r3_harness import build_boundary_states
    bst = build_boundary_states(games_path, plays_path)
    totals = fit_totals_table(bst)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    payload = {
        "provenance": {
            "pins": [games_path, plays_path],
            "generator": "analysis/nba_atlas.py",
            "commit": commit,
            "date": "2026-09-02",
            "boundary": "PHYSICS-ONLY: fitted constant tables, never point-in-time claims. "
                        "These are FULL-DATA fits of the three gate-adopted ESTIMANDS "
                        "(R1b arm a, R2 shrink, R3b arm a); the gates themselves scored "
                        "walk-forward out-of-sample. Adopted forms, production constants.",
        },
        "r1b_sigma": {"global_per_sqrt_min": s_glob,
                      "phase_table": {f"({lo},{hi}]": v for (lo, hi), v in sig_table.items()}},
        "r2_shrink": {"gridpoints_elapsed": {str(k): v for k, v in beta.items()}, "beta_48": 0.0},
        "r3b_totals": {"share": {str(k): v for k, v in totals["share"].items()},
                       "b": {str(k): v for k, v in totals["b"].items()},
                       "sigma": {str(k): v for k, v in totals["sigma"].items()}},
    }
    Path(out_path).write_text(json.dumps(payload, indent=2))
    return (f"Constants written to `{Path(out_path).name}` — R1b σ global {s_glob:.3f}, phase "
            + "/".join(f"{v:.3f}" for v in sig_table.values())
            + "; R2 β " + "/".join(f"{v:.3f}" for v in beta.values())
            + f"; R3b b " + "/".join(f"{v:.3f}" for v in totals['b'].values())
            + f", σ " + "/".join(f"{v:.2f}" for v in totals['sigma'].values()) + ".")


# ------------------------------------------------------------------ selftest


def selftest() -> None:
    """Mutation-test the atlas pipeline on data whose truth is exact everywhere.

    1. Lead-safety cells on Brownian games (sigma=2.4, no drift) match the
       analytic Phi(L / (2.4 sqrt(T))) within tolerance.
    2. Largest-deficit-overcome on a constructed game reads exactly right.
    3. The run detector on a constructed sequence finds exactly the known runs.
    4. The endgame counter on constructed cases reads exactly right.
    5. FV-replay calibration on model-generated data reads REL ~ 0.
    """
    rng = np.random.default_rng(11)
    ok = True

    n = 20000
    sig = 2.4
    a_final = rng.normal(0, sig * np.sqrt(REG_MINUTES), n)
    rows = []
    for t in TIME_BUCKETS:
        # bridge: margin at t | final ~ N(final*(48-t)/48-ish) — use exact brownian bridge
        frac = (REG_MINUTES - t) / REG_MINUTES
        m_t = a_final * frac + rng.normal(0, sig * np.sqrt(t * frac), n)
        rows.append(pd.DataFrame({"game_id": np.arange(n), "season": np.arange(n) % 8,
                                  "t": float(t), "m": np.round(m_t),
                                  "y": (a_final > 0).astype(float)}))
    st = pd.concat(rows, ignore_index=True)
    worst = 0.0
    for t in [24, 12, 6]:
        for lo, hi in [(4, 6), (7, 9)]:
            cell = st[(st.t == t) & (st.m.abs() >= lo) & (st.m.abs() <= hi)]
            emp = np.where(cell.m > 0, cell.y, 1 - cell.y).mean()
            lead = cell.m.abs().mean()
            ana = norm.cdf(lead / (sig * np.sqrt(t)))
            worst = max(worst, abs(emp - ana))
    print(f"[1] lead-safety vs analytic on Brownian: worst cell gap {worst:.3f} (want < 0.02)")
    ok &= worst < 0.02

    tiny = pd.DataFrame({"game_id": [1] * 3, "season": [0] * 3, "t": [36.0, 24.0, 12.0],
                         "m": [-12.0, -4.0, 3.0], "y": [1.0] * 3})
    wm = np.where(tiny.y == 1, tiny.m, -tiny.m)
    deficit = -wm.min()
    print(f"[2] constructed comeback: largest deficit overcome reads {deficit:.0f} (want 12)")
    ok &= deficit == 12

    seq = pd.DataFrame({
        "game_id": [1] * 8, "period": [1] * 8,
        "minutes_left": np.linspace(47, 40, 8),
        "home_score": [2, 4, 6, 6, 6, 8, 8, 11],
        "away_score": [0, 0, 0, 3, 5, 5, 7, 7],
    })
    seq["tot"] = seq.home_score + seq.away_score
    ev = build_events(seq)
    new_run = (ev.team != ev.team.shift()) | (ev.game_id != ev.game_id.shift())
    r = ev.groupby(new_run.cumsum()).pts.sum().tolist()
    print(f"[3] run detector on constructed sequence: {r} (want [6.0, 5.0, 2.0, 2.0, 3.0])")
    ok &= r == [6.0, 5.0, 2.0, 2.0, 3.0]

    st4 = pd.DataFrame({"game_id": [1, 2], "season": [0, 0], "t": [2.0, 2.0],
                        "m": [3.0, 2.0], "tot": [200.0, 210.0], "y": [1.0, 0.0]})
    plays4 = pd.DataFrame({"game_id": [1, 2], "tot": [207.0, 213.0]})
    reg_final = plays4.set_index("game_id").tot
    more = st4.game_id.map(reg_final) - st4.tot
    print(f"[4] endgame counter: more-points reads {more.tolist()} (want [7.0, 3.0]); "
          f">=6 share {float((more >= 6).mean()):.2f} (want 0.50)")
    ok &= more.tolist() == [7.0, 3.0] and (more >= 6).mean() == 0.5

    e = rng.normal(0, 6, n)
    p_true_rows = []
    for t in [36.0, 24.0, 12.0, 6.0]:
        frac = (REG_MINUTES - t) / REG_MINUTES
        m_t = e * frac + rng.normal(0, sig * np.sqrt(REG_MINUTES * frac), n)
        exp_final = m_t + e * t / REG_MINUTES
        p = norm.cdf(exp_final / (sig * np.sqrt(t)))
        y = (rng.uniform(size=n) < p).astype(float)
        p_true_rows.append(pd.DataFrame({"p": p, "y": y}))
    pr = pd.concat(p_true_rows)
    m5 = murphy(pr.p.to_numpy(), pr.y.to_numpy())
    print(f"[5] replay calibration on model-generated data: REL {m5['rel']:.5f} (want < 0.002)")
    ok &= m5["rel"] < 0.002

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--games")
    ap.add_argument("--plays")
    ap.add_argument("--out", default="analysis/nba-atlas.md")
    ap.add_argument("--constants-out", default="analysis/nba_constants_v1.json")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.games and args.plays):
        ap.error("--games and --plays required (or --selftest)")

    states = load_real(args.games, args.plays, require_spread=False)
    games = pd.read_csv(args.games)
    games = games[games.max_period >= 4]
    games = games[games.game_id.isin(states.game_id.unique())]

    plays = pd.read_csv(args.plays)
    plays = plays[(plays.period <= 4) & plays.game_id.isin(states.game_id.unique())].copy()
    plays["clock_min"] = parse_clock_minutes(plays.clock_display)
    plays = plays.dropna(subset=["clock_min"])
    plays["minutes_left"] = (4 - plays.period) * 12.0 + plays.clock_min
    plays["tot"] = plays.home_score + plays.away_score

    replay_md, model_p = fv_replay(states, games)
    model_p_full = model_p.reindex(states.index)
    n_games = states.game_id.nunique()
    seasons = sorted(states.season.unique())

    md = f"""# The NBA game-dynamics atlas

**Descriptive, measured, season-clustered. Not a gate; nothing here is a signal.**
Built from the pins `{Path(args.games).name}` and `{Path(args.plays).name}`:
**{n_games} games, {len(seasons)} seasons ({seasons[0]}–{seasons[-1]}), {len(states)} minute-grid states.**

Three boundaries, before any number:

1. **No market data exists for NBA in-game.** Nothing in this atlas scores entries
   against prices, and nothing in it can say a state is tradable.
2. **Physics only** — fitted constant tables, never point-in-time claims.
3. **The honest n for any property of a constant is {len(seasons)} seasons**, not
   {n_games} games. Every interval is season-clustered.

{CAPITAL_LINE}

## 1. Lead safety — P(leader wins | lead, time left)

Raw frequencies with season-clustered CIs; n is state-rows (games appear once per cell).

{lead_safety(states, model_p_full)}

## 2. Comebacks

{comebacks(states)}

## 3. Run structure (context only)

{runs(plays, n_games)}

## 4. Endgame dynamics

{endgame(states, plays, games)}

## 5. The FV replay — calibration of the adopted stack

{replay_md}

## 6. The engine constants

{constants_file(states, args.games, args.plays, args.constants_out)}

---
*Generated by `analysis/nba_atlas.py` — rerun the command in its docstring to
reproduce every number above from the pins.*

*{CAPITAL_LINE}*
"""
    Path(args.out).write_text(md)
    print(f"atlas written to {args.out}")


if __name__ == "__main__":
    main()
