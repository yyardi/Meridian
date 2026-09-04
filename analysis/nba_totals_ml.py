"""Can a learned model beat the NBA closing TOTAL out-of-sample? — pre-registered.

    .venv/bin/python analysis/nba_totals_ml.py --selftest    # instrument + leakage probes
    .venv/bin/python analysis/nba_totals_ml.py --fit         # the run

EVERYTHING IN THIS DOCSTRING WAS WRITTEN BEFORE ANY MODEL WAS FIT.
==================================================================
A gradient-boosted learner is the strongest possible instance of the family this
programme has spent a day cataloguing: **it can fit any structure, and unlike a
ratio or a gradient it has no natural tell.** So the design is projected through
the four doors first (`analysis/FORCED_GRADIENTS.md`), and the defence that
matters is not a null — it is a per-feature point-in-time proof.

★ FINDING BEFORE FITTING — THE BASELINE IS 0.5, AND NOT BY LAZINESS
-------------------------------------------------------------------
The instruction was "the baseline is the closing line's own implied probability,
never 0.5". **For TOTALS that instruction cannot be followed as written, and the
reason is structural rather than convenient:** this export carries the closing
total (the LINE) but no totals PRICE, and a closing total is by construction the
balance point at which the book takes equal money each way. Its implied P(over)
IS ~0.5. Measured here: **over rate 0.5011 on 7,896 non-push games** (78 pushes,
0.98%), mean(actual - line) +0.513 points on sd 18.28.

So `Brier(baseline) = 0.25` exactly, and the question becomes the sharpest
possible form of itself: **does the model have ANY out-of-sample predictive power
over the closing total?** That is a harder and cleaner test than beating a
moneyline, not an easier one. The 0.5011 over-rate is itself the line's
efficiency, measured.

★ THE FOUR DOORS, PROJECTED ON THIS DESIGN BEFORE FITTING
----------------------------------------------------------
**STAGE 1 — STATISTIC.** Brier(model) - 0.25 on held-out games. The model's
output is free to sit either side; nothing in the statistic reproduces its own
inputs. CLEAN.

**STAGE 2 — POPULATION.** Games carrying a closing total: 7,974 of 13,143. The
missing ones are WHOLE SEASONS (2015, 2023, 2024 have no odds), not games chosen
within a season — coverage inside a covered season is ~99.8%. So selection is by
vendor-season, not by anything correlated with the outcome. CLEAN, with the
season list printed.

**STAGE 3 — PARTITION.** The disagreement bands are inherited from the PULSE
work rather than tuned here: |p_model - 0.5| in <=2pp / 2-5pp / 5-10pp / >10pp.
Re-banding would be a new analysis.

**STAGE 4 — DECISION RULE. THE DANGEROUS DOOR, AND IT IS ASYMMETRIC.**
Rule: *model beats 0.25 out-of-sample, game-clustered CI excluding zero => the
line is beatable.* Projecting the achievable outcome range onto its branches:

  - "does not beat"  reachable, and it is the EXPECTED outcome: a flexible
    learner handed a balanced line will learn to output ~0.5 and score ~0.25.
  - "beats"          reachable by real structure — **AND EQUALLY REACHABLE BY
    LEAKAGE**, which is the whole problem.

**No null on the outcome can distinguish those two**, because leakage is a
property of how a feature was CONSTRUCTED, not of the distribution it produces.
A shuffled-target null tests the pipeline, not the features. Therefore the
registered defence is:

  (a) **every feature carries a written point-in-time proof** — it must be
      computable from information strictly PRIOR to tip-off of the game it
      describes. Rolling team form uses `shift(1)` before any window, so a
      game never contributes to its own feature. Stated per feature below.
  (b) **a temporal placebo**: the identical pipeline with the target SHUFFLED
      WITHIN SEASON must read Brier ~0.25 and a CI spanning zero. If a shuffled
      target still beats the baseline, the leak is in the plumbing.
  (c) **a line-only control**: a model given ONLY the closing line and the
      teams. If the full feature set does not beat this control, the extra
      features add nothing and any headline is about the line, not the model.

**AND THE FORKING-PATHS RULE, since a learner has infinite configurations:**
ONE configuration is declared here and fit once —
`HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05,
max_iter=300, min_samples_leaf=50, l2_regularization=1.0, random_state=20260904)`.
Chosen a priori as ordinary regularised defaults, blind to any result. **Trying
a second configuration and reporting the better one is the defect this clause
exists to prevent**; if a second is ever run, both print.

★ VALIDATION SCHEME — FORWARD IN TIME, NEVER RANDOM
----------------------------------------------------
Random CV on 13k games with the line as a feature would look magnificent and
mean nothing. Scheme: **expanding-window by season.** Fit on all covered seasons
strictly before season k, predict season k. Seasons 2017-2022 and 2025 are
evaluated (2016 has 24 games and is training-only). Intervals cluster BY GAME,
which here is also the row unit — one row per game, so clustering is the
ordinary interval and is stated rather than implied.

**THE 88 LIVE-PRICE GAMES ARE NOT IN THIS FILE AT ALL** (they are WNBA, in the
predictions pin). The NBA test here is the forward seasons; the WNBA live-price
set is a separate cohort and is not touched by this module.

★ WHAT WOULD MAKE THIS A REAL RESULT, AND WHAT WOULD NOT
---------------------------------------------------------
Real: model Brier < 0.25 out-of-sample with a CI off zero, surviving the
placebo, beating the line-only control, and holding on the disagreement cut —
because a model can beat the baseline on average and lose where it would act,
which is exactly what the current hand-built model does.

Not real: a headline that rests on one season, or that vanishes under the
placebo, or that lives entirely in the <=2pp band where nothing would be traded.

*No in-sample result justifies capital. The forward test is the evidence.*
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean

GAMES = "backups/exports/nba_games_20260901T225326Z.csv"
EVAL_SEASONS = [2017, 2018, 2019, 2020, 2021, 2022, 2025]
BANDS = [(0.00, 0.02, "<=2pp"), (0.02, 0.05, "2-5pp"), (0.05, 0.10, "5-10pp"), (0.10, 1.0, ">10pp")]
SEED = 20260904
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def build_features(g: pd.DataFrame) -> pd.DataFrame:
    """Team-game long form with STRICTLY PRIOR rolling features.

    POINT-IN-TIME PROOF, per feature. Every rolling quantity is computed with
    `.shift(1)` applied BEFORE the window, so a game never enters its own
    feature and the value for game t uses only games 1..t-1 for that team:

      rest_days        days since that team's previous game            PRIOR
      roll_pts_for     mean points scored, prior 10 games              PRIOR
      roll_pts_against mean points conceded, prior 10 games            PRIOR
      roll_total       mean combined total, prior 10 games             PRIOR
      roll_pace_dev    mean (game total - closing line), prior 10      PRIOR
      games_played     count of prior games this season                PRIOR
      closing_total / closing_spread  known before tip by definition   PRIOR
      is_home, season, month                                           PRIOR

    Nothing here reads the current game's score. The selftest asserts it by
    checking that a feature row for game t is unchanged when game t's own
    outcome is altered.
    """
    g = g[(g.max_period >= 4) & g.closing_total.notna()].copy()
    g["game_date"] = pd.to_datetime(g.game_date)
    g["total"] = g.team0_score + g.team1_score
    long = pd.concat([
        g.assign(team=g.team0, opp=g.team1, pts_for=g.team0_score, pts_against=g.team1_score,
                 is_home=(g.team0_homeaway == "home").astype(int)),
        g.assign(team=g.team1, opp=g.team0, pts_for=g.team1_score, pts_against=g.team0_score,
                 is_home=(g.team1_homeaway == "home").astype(int)),
    ], ignore_index=True).sort_values(["team", "game_date"])

    grp = long.groupby("team", group_keys=False)
    long["rest_days"] = grp.game_date.diff().dt.days
    for col, src in [("roll_pts_for", "pts_for"), ("roll_pts_against", "pts_against"),
                     ("roll_total", "total")]:
        long[col] = grp[src].apply(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    long["pace_dev"] = long.total - long.closing_total
    long["roll_pace_dev"] = grp.pace_dev.apply(lambda s: s.shift(1).rolling(10, min_periods=3).mean())
    long["games_played"] = long.groupby(["team", "season"]).cumcount()

    home = long[long.is_home == 1].set_index("game_id")
    away = long[long.is_home == 0].set_index("game_id")
    feat = pd.DataFrame(index=home.index)
    for side, src in [("h", home), ("a", away)]:
        for c in ["rest_days", "roll_pts_for", "roll_pts_against", "roll_total",
                  "roll_pace_dev", "games_played"]:
            feat[f"{side}_{c}"] = src[c]
    feat["closing_total"] = home.closing_total
    feat["closing_spread"] = home.closing_spread
    feat["season"] = home.season
    feat["month"] = home.game_date.dt.month
    feat["game_date"] = home.game_date
    feat["total"] = home.total
    feat["over"] = (home.total > home.closing_total).astype(int)
    feat["push"] = (home.total == home.closing_total)
    return feat.reset_index()


FEATURES = ["closing_total", "closing_spread", "season", "month",
            "h_rest_days", "h_roll_pts_for", "h_roll_pts_against", "h_roll_total",
            "h_roll_pace_dev", "h_games_played",
            "a_rest_days", "a_roll_pts_for", "a_roll_pts_against", "a_roll_total",
            "a_roll_pace_dev", "a_games_played"]
LINE_ONLY = ["closing_total", "closing_spread", "season", "month"]


def walk_forward(feat: pd.DataFrame, cols: list[str], shuffle: bool = False,
                 seed: int = SEED) -> pd.DataFrame:
    """Expanding-window by season. Fit on seasons < k, predict season k."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    rng = np.random.default_rng(seed)
    d = feat[~feat.push].copy()
    if shuffle:  # the temporal placebo: destroy the target within season
        d["over"] = d.groupby("season").over.transform(lambda s: rng.permutation(s.values))
    out = []
    for k in EVAL_SEASONS:
        tr, te = d[d.season < k], d[d.season == k]
        if len(tr) < 500 or te.empty:
            continue
        m = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300,
                                           min_samples_leaf=50, l2_regularization=1.0,
                                           random_state=seed)
        m.fit(tr[cols], tr.over)
        p = m.predict_proba(te[cols])[:, 1]
        out.append(te.assign(p=p, brier=(p - te.over) ** 2, base=(0.5 - te.over) ** 2,
                             diff=(p - te.over) ** 2 - (0.5 - te.over) ** 2,
                             train_seasons=len(tr)))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def report_result(ev: pd.DataFrame, label: str, indent: str = "") -> None:
    if ev.empty or ev.game_id.nunique() < 2:
        print(f"{indent}{label}: too few games")
        return
    cm = clustered_mean({g: [v] for g, v in zip(ev.game_id, ev["diff"])})
    verdict = ("MODEL BEATS THE LINE" if cm.hi < 0 else
               "model worse than the line" if cm.lo > 0 else "spans zero — no edge shown")
    print(f"{indent}{label:<32s} Brier {ev.brier.mean():.5f} vs 0.25000 | "
          f"diff {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] n={len(ev):,} -> {verdict}")


def main_fit() -> None:
    g = pd.read_csv(GAMES)
    feat = build_features(g)
    print("=== COMPOSITION (before any ratio) ===")
    print(f"games with closing_total and 4+ periods: {len(feat):,} · "
          f"seasons {sorted(feat.season.unique())}")
    print(f"per season: {feat.season.value_counts().sort_index().to_dict()}")
    d = feat[~feat.push]
    print(f"pushes excluded: {int(feat.push.sum())} ({feat.push.mean():.2%}) · "
          f"over rate {d.over.mean():.4f} — the line's own efficiency, and the baseline")
    print(f"feature rows complete: {d[FEATURES].notna().all(axis=1).mean():.1%} "
          f"(early-season rows lack a 10-game window by construction; the learner "
          f"handles NaN natively rather than dropping them)")

    print("\n=== 1. THE RESULT — expanding-window by season, baseline 0.25 ===")
    ev = walk_forward(feat, FEATURES)
    report_result(ev, "full feature set")
    print("\n  per evaluated season:")
    for s, v in ev.groupby("season"):
        report_result(v, f"  {s}", indent="  ")

    print("\n=== 2. CONTROLS ===")
    lo = walk_forward(feat, LINE_ONLY)
    report_result(lo, "line-only control")
    print("  If the full set does not beat this, the extra features add nothing.")
    pl = walk_forward(feat, FEATURES, shuffle=True)
    report_result(pl, "TEMPORAL PLACEBO (shuffled)")
    print("  Must span zero at ~0.25. If a shuffled target beats the baseline, the leak")
    print("  is in the plumbing and every number above is void.")

    print("\n=== 3. THE DISAGREEMENT CUT (a model can beat on average and lose where it acts) ===")
    ev = ev.assign(conf=(ev.p - 0.5).abs())
    for lo_b, hi_b, lab in BANDS:
        report_result(ev[(ev.conf >= lo_b) & (ev.conf < hi_b)], f"  |p-0.5| {lab}", indent="  ")
    print(f"  share of games where the model deviates >5pp from the line: "
          f"{(ev.conf > 0.05).mean():.1%}")

    print("\n=== 4. WHAT THE MODEL LEARNED ===")
    print(f"  p range [{ev.p.min():.3f}, {ev.p.max():.3f}], sd {ev.p.std():.4f}, mean {ev.p.mean():.4f}")
    print("  A model that has learned to copy a balanced line sits at ~0.5 with tiny sd —")
    print("  which is itself the finding, not a failure to converge.")
    print(f"\n{CAPITAL_LINE}")


def selftest() -> None:
    """Instrument checks, and the leakage probes the four-door projection demands."""
    ok = True
    g = pd.read_csv(GAMES)
    feat = build_features(g)

    # 1. POINT-IN-TIME: altering a game's own score must not change its own features.
    g2 = g.copy()
    tgt = g2[(g2.max_period >= 4) & g2.closing_total.notna()].index[500]
    gid = g2.loc[tgt, "game_id"]
    g2.loc[tgt, "team0_score"] = g2.loc[tgt, "team0_score"] + 40
    f2 = build_features(g2)
    a = feat[feat.game_id == gid][FEATURES].iloc[0]
    b = f2[f2.game_id == gid][FEATURES].iloc[0]
    same = a.equals(b)
    print(f"[point-in-time] altering game {gid}'s own score leaves its own features "
          f"unchanged: {same}")
    ok &= bool(same)

    # 2. and it MUST change a LATER game's features (else the rolling window is dead)
    later = feat[(feat.game_date > feat[feat.game_id == gid].game_date.iloc[0])]
    changed = not feat.loc[later.index[:200], FEATURES].equals(f2.loc[later.index[:200], FEATURES])
    print(f"[rolling live] the same alteration DOES change later games' features: {changed} "
          f"(a rolling feature that never changes is a dead feature)")
    ok &= changed

    # 3. the baseline is exactly 0.25 by construction
    b025 = ((0.5 - np.array([0, 1])) ** 2).mean()
    print(f"[baseline] Brier(0.5) on any binary target = {b025:.5f} (want 0.25000)")
    ok &= abs(b025 - 0.25) < 1e-12

    # 4. the placebo must be able to DETECT leakage: hand the pipeline the answer.
    leaky = feat.copy()
    leaky["cheat"] = leaky.over  # the target itself as a feature
    ev = walk_forward(leaky, FEATURES + ["cheat"])
    cm = clustered_mean({k: [v] for k, v in zip(ev.game_id, ev["diff"])})
    print(f"[leak probe] a model handed the ANSWER as a feature: diff {cm.mean:+.5f} "
          f"[{cm.lo:+.5f}, {cm.hi:+.5f}] -> detected: {cm.hi < 0}")
    ok &= cm.hi < 0

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.fit:
        main_fit()
    else:
        print(__doc__)
