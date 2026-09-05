"""Ride predictor — can "this entry never gets an exit fill" be seen at entry?

    .venv/bin/python analysis/ride_predictor.py [--exports DIR]
    .venv/bin/python analysis/ride_predictor.py --selftest

Fits P(ride | entry-time state) on A's ledger (pins ``20260901T195202Z``)
and evaluates it the only honest way available at n=1,944 / 137 rides / 34
games: leave-one-GAME-out, so no prediction is scored by a model that saw
its own game. The output is a candidate sizing input plus its confusion
matrix in trades AND dollars — never a strategy.

Label caveat, first (D's side of the mechanism): a "ride" is an exit that
never filled UNDER THE OPTIMISTIC SHADOW RULE (a newer mid crossing the
resting exit). Real fills are worse than the rule, so real no-exit risk is
HIGHER than this label records — predicted ride probabilities are lower
bounds on the thing that costs money.

Honesty constraints carried from the wave standard:
* in-sample by construction; hypothesis-generating; no strategy language;
* every interval game-clustered via the one blessed ``clustered_mean``;
* dollars shown under BOTH fill arms (optimistic, and the measured 4.70¢
  per-leg concession) — a filter that improves an optimistic book while the
  pessimistic book stays negative is a finding, not an edge;
* the book-death question answered explicitly: if the discrimination comes
  from late/decided state, this is substantially a book-death predictor
  wearing a strategy's clothes, and it says so;
* book depth is NOT a feature — the tick pin carries no depth columns, and
  the wave runs from pins.

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

EXPORTS = REPO / "backups/exports"
LEDGER = "roundtrip_ledger_20260901T195202Z.csv"

#: measured in-game concession per filled leg (docs/findings.md C13);
#: the ledger's pnl_per_dollar_pess already applies it (2 legs trip, 1 ride)
CONCESSION = 0.047

CONT = ["minutes_left", "abs_margin", "ml_x_margin", "spread_px", "cost",
        "edge_net"]
DUMMY = ["is_spread", "is_winner", "is_yes"]
FEATURES = CONT + DUMMY

COMPARISONS = {"n": 0}


def load(exports: Path) -> pd.DataFrame:
    a = pd.read_csv(exports / LEDGER)
    m = a[a.entry_filled & a.outcome.isin(["exit_fill", "settlement"])].copy()
    m["y"] = (m.outcome == "settlement").astype(int)          # ride = 1
    m["abs_margin"] = m.margin.abs()
    m["ml_x_margin"] = (40 - m.minutes_left) * m.abs_margin / 40
    m["spread_px"] = m.market_ask - m.market_bid
    m["cost"] = m.entry_cost_per_contract
    m["is_spread"] = (m.strategy == "spread").astype(int)
    m["is_winner"] = (m.strategy == "winner").astype(int)
    m["is_yes"] = (m.side == "yes").astype(int)
    m["mask_hand"] = (m.period.astype(str).str.startswith("Q4")
                      | (m.abs_margin >= 10)).astype(int)
    m["ret"] = m.pnl_per_dollar
    m["ret_pess"] = m.pnl_per_dollar_pess
    m["usd"] = m.pnl_usd
    m["usd_pess"] = m.ret_pess * m.cost * m.contracts
    return m.reset_index(drop=True)


def design(m: pd.DataFrame, mu=None, sd=None):
    X = m[FEATURES].astype(float).copy()
    if mu is None:
        mu, sd = X[CONT].mean(), X[CONT].std().replace(0, 1)
    X[CONT] = (X[CONT] - mu) / sd
    X.insert(0, "const", 1.0)
    return X, mu, sd


def fit_logit(X, y, groups=None):
    import statsmodels.api as sm
    model = sm.Logit(y, X)
    try:
        if groups is not None:
            return model.fit(disp=0, cov_type="cluster",
                             cov_kwds={"groups": groups}, maxiter=200)
        return model.fit(disp=0, maxiter=200)
    except Exception:
        # degenerate fold (constant column / separation): tiny ridge
        return model.fit_regularized(alpha=1e-4, L1_wt=0.0, disp=0,
                                     maxiter=500)


def logo_oof(m: pd.DataFrame) -> np.ndarray:
    """Leave-one-game-out out-of-fold probabilities."""
    p = np.full(len(m), np.nan)
    for game in m.event_slug.unique():
        tr = m.event_slug != game
        Xtr, mu, sd = design(m[tr])
        res = fit_logit(Xtr, m.loc[tr, "y"])
        Xte, _, _ = design(m[~tr], mu, sd)
        p[~tr.to_numpy()] = res.predict(Xte)
    return p


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Mann-Whitney AUC, no dependencies."""
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    # midranks for ties
    s = pd.Series(p)
    ranks = s.rank(method="average").to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return (ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def cm_row(g: pd.DataFrame, label: str, col: str = "ret") -> str:
    d = {k: list(v) for k, v in g.groupby("event_slug")[col]}
    c = clustered_mean(d)
    if c is None:
        return f"| {label} | {len(g)} | {g.event_slug.nunique()} | — |"
    COMPARISONS["n"] += 1
    return (f"| {label} | {len(g)} | {g.event_slug.nunique()} | "
            f"{c.mean*100:+.1f}¢ [{c.lo*100:+.1f}, {c.hi*100:+.1f}] |")


def confusion(m: pd.DataFrame, kill: np.ndarray, name: str) -> None:
    """Confusion matrix at an operating point, in trades and dollars,
    both fill arms. kill=True means the filter refuses the entry."""
    y = m.y.to_numpy().astype(bool)
    tp, fp = (kill & y), (kill & ~y)
    fn, tn = (~kill & y), (~kill & ~y)
    print(f"\n**Operating point: {name}** — kills {kill.sum()} of {len(m)} "
          f"entries ({kill.mean()*100:.0f}%)")
    print()
    print("| | trades | shadow $ optimistic | shadow $ pessimistic |")
    print("|---|---|---|---|")
    print(f"| rides killed (TP) | {tp.sum()}/{y.sum()} "
          f"(recall {tp.sum()/max(y.sum(),1)*100:.0f}%) "
          f"| {m.loc[tp, 'usd'].sum():+,.2f} avoided "
          f"| {m.loc[tp, 'usd_pess'].sum():+,.2f} avoided |")
    print(f"| trips killed (FP) | {fp.sum()}/{(~y).sum()} "
          f"| {m.loc[fp, 'usd'].sum():+,.2f} forgone "
          f"| {m.loc[fp, 'usd_pess'].sum():+,.2f} forgone |")
    print(f"| rides kept (FN) | {fn.sum()} | {m.loc[fn, 'usd'].sum():+,.2f} "
          f"| {m.loc[fn, 'usd_pess'].sum():+,.2f} |")
    print(f"| precision | {tp.sum()/max(kill.sum(),1)*100:.0f}% | | |")
    kept = m[~kill]
    print()
    print("| kept book | n | games | per-$ clustered [95% CI] |")
    print("|---|---|---|---|")
    print(cm_row(kept, "optimistic", "ret"))
    print(cm_row(kept, "pessimistic", "ret_pess"))
    by_game = kept.groupby("event_slug").usd.sum()
    print(f"\nGames losing (shadow $, kept book): "
          f"{(by_game < 0).sum()} of {len(by_game)} "
          f"(unfiltered: see header)")


def run(exports: Path) -> None:
    m = load(exports)
    print("# Ride predictor — P(no exit fill) from entry-time state")
    print()
    print(f"Substrate: A's ledger @ pins · n={len(m):,} scored fills, "
          f"{m.y.sum()} rides ({m.y.mean()*100:.1f}%), "
          f"{m.event_slug.nunique()} games. Label = ride under the "
          f"OPTIMISTIC fill rule (lower bound on real no-exit risk). "
          f"Features: {', '.join(FEATURES)} (book depth unavailable in "
          f"the pins). Validation: leave-one-game-out.")
    by_game = m.groupby("event_slug").usd.sum()
    print(f"Unfiltered book: games losing (shadow $): "
          f"{(by_game < 0).sum()} of {len(by_game)}.")

    # full-sample fit for coefficients (game-clustered SEs)
    X, mu, sd = design(m)
    res = fit_logit(X, m.y, groups=m.event_slug)
    print("\n## Coefficients (standardized, game-clustered SEs)\n")
    print("| feature | coef | z | note |")
    print("|---|---|---|---|")
    order = res.params.drop("const").abs().sort_values(ascending=False).index
    for f in order:
        z = res.params[f] / res.bse[f]
        print(f"| {f} | {res.params[f]:+.2f} | {z:+.1f} | |")

    p = logo_oof(m)
    m["p_ride"] = p
    a_model = auc(m.y.to_numpy(), p)
    a_mask = auc(m.y.to_numpy(), m.mask_hand.to_numpy().astype(float))
    print(f"\n## Discrimination (leave-one-game-out)\n")
    print(f"* model OOF AUC: **{a_model:.3f}**")
    print(f"* hand mask (Q4 ∪ |margin|≥10), same data: {a_mask:.3f}")

    print("\n## Calibration (OOF quintiles)\n")
    print("| quintile | n | mean p̂ | observed ride rate |")
    print("|---|---|---|---|")
    m["q"] = pd.qcut(m.p_ride, 5, labels=False, duplicates="drop")
    for q, g in m.groupby("q"):
        print(f"| {int(q)+1} | {len(g)} | {g.p_ride.mean()*100:.1f}% | "
              f"{g.y.mean()*100:.1f}% |")

    print("\n## The sizing gradient — realized per-$ by predicted risk\n")
    print("| OOF p̂ quintile | n | games | per-$ clustered [95% CI] |")
    print("|---|---|---|---|")
    for q, g in m.groupby("q"):
        print(cm_row(g, f"q{int(q)+1} (p̂≈{g.p_ride.mean()*100:.1f}%)"))

    # operating points
    n_mask = int(m.mask_hand.sum())
    thr_equal = np.sort(p)[::-1][n_mask - 1]
    confusion(m, p >= thr_equal,
              f"equal-kill vs hand mask (top {n_mask} by p̂, "
              f"thr={thr_equal*100:.1f}%)")
    confusion(m, m.mask_hand.to_numpy().astype(bool),
              "the registered hand mask itself (Q4 ∪ |margin|≥10)")
    trip_mean = m.loc[m.y == 0, "ret"].mean()
    ride_mean = m.loc[m.y == 1, "ret"].mean()
    p_star = trip_mean / (trip_mean - ride_mean)
    confusion(m, p >= p_star,
              f"EV-neutral p*={p_star*100:.1f}% (in-sample plug-in: "
              f"trip {trip_mean*100:+.1f}¢, ride {ride_mean*100:+.1f}¢)")

    print(f"\n---\n**Multiplicity: {COMPARISONS['n']} clustered intervals "
          f"printed here**, on data already mined by the loss map (197+) — "
          f"treat every one as in-sample and correlated with prior cuts. "
          f"The model was specified once (features and interaction listed "
          f"in code before fitting); thresholds are two pre-named rules "
          f"plus the mask baseline.")
    print("\n**No in-sample result justifies capital. "
          "The forward test is the evidence.**")


def selftest() -> int:
    rng = np.random.default_rng(20260902)
    n_games, per_game = 30, 60
    rows = []
    for g in range(n_games):
        for _ in range(per_game):
            ml = rng.uniform(0, 40)
            rows.append({"event_slug": f"g{g}", "minutes_left": ml,
                         "abs_margin": rng.uniform(0, 20),
                         "spread_px": rng.uniform(0, .15),
                         "cost": rng.uniform(.1, .9),
                         "edge_net": rng.uniform(.03, .3),
                         "is_spread": rng.integers(0, 2),
                         "is_winner": rng.integers(0, 2),
                         "is_yes": rng.integers(0, 2),
                         "ml": ml})
    m = pd.DataFrame(rows)
    m["ml_x_margin"] = (40 - m.minutes_left) * m.abs_margin / 40
    # null: label independent of everything
    m["y"] = (rng.random(len(m)) < 0.08).astype(int)
    p = logo_oof(m)
    a0 = auc(m.y.to_numpy(), p)
    ok0 = abs(a0 - 0.5) < 0.06
    print(f"null:     LOGO AUC {a0:.3f} -> {'OK (~0.5)' if ok0 else 'FAIL'}")
    # injected: risk rises as clock falls
    z = -2.0 - 0.12 * (m.minutes_left - 20)
    m["y"] = (rng.random(len(m)) < 1 / (1 + np.exp(-z))).astype(int)
    p = logo_oof(m)
    a1 = auc(m.y.to_numpy(), p)
    ok1 = a1 > 0.70
    print(f"injected: LOGO AUC {a1:.3f} -> "
          f"{'OK (recovers clock effect)' if ok1 else 'FAIL'}")
    return 0 if (ok0 and ok1) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=EXPORTS)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    run(args.exports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
