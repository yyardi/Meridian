"""Does PULSE's model forecast better than the price it bets against? — 88 games.

    .venv/bin/python analysis/pulse_signal.py --selftest
    .venv/bin/python analysis/pulse_signal.py

**No fill rule anywhere in this.** Forecast vs price vs what happened. The 81%
phantom share is a property of the fill SIMULATOR and says nothing about whether
`model_probability` predicts settlement; this module asks the separate question.

Substrate: `backups/exports/pulse_predictions_20260904T183000Z.csv.gz` —
186,210 rows, 1,584 markets, **88 games**, every row joined to a settled
outcome. That is 2.6x the games any PULSE scoring has used.

EVERYTHING BELOW WAS FIXED BEFORE ANY NUMBER WAS COMPUTED
=========================================================

**THE PRIMARY RESULT IS THE DISAGREEMENT CUT, NOT OVERALL BRIER.** Trading
happens only where the model disagrees with the market, so a statistic computed
over the population you do not trade tells you nothing about the population you
do. The model could beat the market on average and still lose money by being
worst exactly where it acts. Overall Brier is context; the disagreement split is
the result.

**Bands, INHERITED from the 34-game run rather than tuned here** (that is the
point of inheriting them): |model_probability - market_mid| in
    <=2c | 2-5c | 5-10c | >10c,  with the headline split at 5c.

**DEDUPE RULE — declared, with its rationale.** ~118 predictions per market, one
opinion logged repeatedly as the price moves (model_probability changes in
1,534/1,584 markets, market_mid in 1,580). PRIMARY = **the FIRST prediction per
market**: it is a fixed, early information point, and it is what the 34-game run
used, so the two are comparable. SENSITIVITY = the LAST. Both are reported;
neither is chosen after seeing which reads better.

**CLUSTER BY GAME (88), never by market.** Eighteen markets on one game are one
opinion expressed eighteen times, all resolving off the same final score.

**MODEL VERSION IS NOT POOLED SILENTLY.** Three versions share the file and they
are wildly imbalanced (v4 183,538 rows / 83 games · v3 2,417 / 11 · v2 255 / 12).
A pooled Brier measures a mixture. v4 is the primary cohort and is stated as
such; v3 and v2 are reported with their game counts so their thinness is visible.

**★ THE `is_actionable` CONFOUND, found in composition and handled rather than
discovered in review.** The obvious reading — "does the model do better where it
wanted to act" — is contaminated, because actionability is NEGATIVELY correlated
with disagreement: declined rows carry a LARGER mean gap (0.0715) than actionable
ones (0.0370). So `is_actionable` is not "edge above threshold"; the engine
declines when the disagreement is large. Comparing the two populations
unconditionally would therefore re-express the disagreement effect and be read
as an opportunity-cost result. **The split is reported CONDITIONED ON THE
DISAGREEMENT BAND**, which is the only form in which it answers its own question.

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

PIN = "backups/exports/pulse_predictions_20260904T183000Z.csv.gz"
BANDS = [(0.00, 0.02, "agree     <=2c"), (0.02, 0.05, "mild      2-5c"),
         (0.05, 0.10, "disagree  5-10c"), (0.10, 1.01, "strong    >10c")]
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def load(path: str = PIN) -> pd.DataFrame:
    d = pd.read_csv(path)
    d = d.dropna(subset=["market_mid", "model_probability", "settlement"]).copy()
    d["y"] = d.settlement.astype(float)
    d["b_model"] = (d.model_probability - d.y) ** 2
    d["b_mkt"] = (d.market_mid - d.y) ** 2
    d["diff"] = d.b_model - d.b_mkt
    d["gap"] = (d.model_probability - d.market_mid).abs()
    d["actionable"] = d.is_actionable.astype(str).str.lower().isin(["t", "true", "1"])
    return d


def dedupe(d: pd.DataFrame, which: str = "first") -> pd.DataFrame:
    s = d.sort_values("predicted_at")
    return (s.groupby("market_slug").first() if which == "first"
            else s.groupby("market_slug").last()).reset_index()


def row(x: pd.DataFrame, label: str, indent: str = "  ") -> None:
    if x.empty or x.game_id.nunique() < 2:
        print(f"{indent}{label:<34s} n={len(x):<5d} G={x.game_id.nunique() if len(x) else 0} "
              f"— too few clusters for an interval")
        return
    cm = clustered_mean({g: v["diff"].tolist() for g, v in x.groupby("game_id")})
    verdict = "model better" if cm.hi < 0 else "MODEL WORSE" if cm.lo > 0 else "spans zero"
    print(f"{indent}{label:<34s} model {x.b_model.mean():.4f} market {x.b_mkt.mean():.4f} | "
          f"diff {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] G={cm.n_clusters} n={cm.n:,} "
          f"-> {verdict}")


def report(d: pd.DataFrame) -> None:
    print("=== COMPOSITION (before any ratio) ===")
    print(f"rows {len(d):,} · markets {d.market_slug.nunique():,} · games {d.game_id.nunique()} · "
          f"{d.predicted_at.min()[:10]} to {d.predicted_at.max()[:10]}")
    print(f"model_version rows {d.model_version.value_counts().to_dict()}")
    print(f"model_version games {d.groupby('model_version').game_id.nunique().to_dict()} "
          f"— v4 is the cohort; v3/v2 are thin and are shown, not pooled in silently")
    print(f"is_actionable: {d.actionable.mean():.1%} true")
    print(f"★ CONFOUND: mean |model-mid| is {d[~d.actionable].gap.mean():.4f} on DECLINED rows vs "
          f"{d[d.actionable].gap.mean():.4f} on actionable ones —")
    print("  the engine declines the LARGE disagreements, so actionability is negatively")
    print("  correlated with the very axis the primary result cuts on. Handled by")
    print("  conditioning, below; an unconditional split would restate the disagreement effect.")

    f = dedupe(d, "first")
    print(f"\ndeduped to one row per market (FIRST prediction): {len(f):,} rows / "
          f"{f.game_id.nunique()} games")

    print("\n=== 1. THE RESULT — Brier by disagreement band (v4 cohort) ===")
    print("positive diff = model WORSE than the market it is betting against")
    v4 = f[f.model_version == "v4"]
    for lo, hi, lab in BANDS:
        row(v4[(v4.gap >= lo) & (v4.gap < hi)], lab)
    print()
    row(v4[v4.gap <= 0.05], "ALL agreements  <=5c")
    row(v4[v4.gap > 0.05], "ALL disagreements >5c  <-- where it trades")
    print(f"  share of markets where the model disagrees >5c: "
          f"{(v4.gap > 0.05).mean():.1%} ({int((v4.gap > 0.05).sum())} of {len(v4)})")

    print("\n=== 2. CONTEXT — overall Brier, and by market type (v4) ===")
    row(v4, "overall")
    for mt, g in v4.groupby("sports_market_type"):
        row(g, "  " + mt.replace("basketball_team_full_game_", ""))

    print("\n=== 3. BY MODEL VERSION (pooling these would measure a mixture) ===")
    for v, g in f.groupby("model_version"):
        row(g, f"{v}  ({g.game_id.nunique()} games)")

    print("\n=== 4. is_actionable, CONDITIONED ON DISAGREEMENT (the confound) ===")
    print("Unconditional first, shown only to demonstrate why it must not be read:")
    row(v4[v4.actionable], "  actionable (UNCONDITIONAL)")
    row(v4[~v4.actionable], "  declined   (UNCONDITIONAL)")
    print("Conditioned — the same comparison inside each band, which is the honest form:")
    for lo, hi, lab in BANDS:
        b = v4[(v4.gap >= lo) & (v4.gap < hi)]
        row(b[b.actionable], f"  {lab} actionable", indent="    ")
        row(b[~b.actionable], f"  {lab} declined", indent="    ")

    print("\n=== 5. SENSITIVITY — dedupe by LAST prediction instead of FIRST ===")
    l4 = dedupe(d, "last")
    l4 = l4[l4.model_version == "v4"]
    row(l4[l4.gap <= 0.05], "LAST: agreements <=5c")
    row(l4[l4.gap > 0.05], "LAST: disagreements >5c")
    print("  A result that flips between first and last is a result about WHEN the opinion")
    print("  was taken, not about the model.")

    print("\n=== 6. LAMBDA* — does the model add information ON TOP OF the market? ===")
    print("A DIFFERENT QUESTION from the Brier comparison: forecast combination needs")
    print("INDEPENDENT information, not SUPERIOR information. A model with several times")
    print("the market's error variance can still carry a positive blend weight and improve")
    print("the reference price. Leave-one-GAME-out, declared before running; lambda is not")
    print("clipped, so a negative weight can appear if the model subtracts information.")
    lambda_star(v4, "v4 (all bands)")
    lambda_star(v4[v4.gap > 0.05], "v4, disagreements >5c")
    lambda_star(v4[v4.gap <= 0.05], "v4, agreements <=5c")
    for v, g in f.groupby("model_version"):
        if v != "v4":
            lambda_star(g, f"{v} ({g.game_id.nunique()} games)")

    print("\n=== MULTIPLE COMPARISONS ===")
    print("~25 band-level intervals here across bands, types, versions and the conditioned")
    print("actionable split. Several will look striking by chance. Ranking is by mechanism")
    print("and robustness across slices, never by which interval is narrowest.")
    print(CAPITAL_LINE)


def fit_lambda(train: pd.DataFrame) -> float:
    """The inverse-variance blend weight, fitted by least squares on TRAINING games.

    Constrained form, ONE parameter: y ~ (1-L)*mid + L*fv, i.e. minimise
    ||(y - mid) - L*(fv - mid)||^2, whose solution is the OLS slope of
    (y - mid) on (fv - mid) with no intercept. **Deliberately NOT clipped to
    [0,1]:** clipping would hide a negative weight, which is the finding that the
    model actively subtracts information.
    """
    x = (train.model_probability - train.market_mid).to_numpy(float)
    r = (train.y - train.market_mid).to_numpy(float)
    denom = float(np.sum(x * x))
    return float(np.sum(x * r) / denom) if denom > 0 else 0.0


def lambda_star(d: pd.DataFrame, label: str) -> None:
    """Does the model add information ON TOP OF the market? — LOGO by game.

    DECLARED BEFORE RUNNING (see module docstring's discipline): fold scheme is
    LEAVE-ONE-GAME-OUT over the cohort's games; lambda is fitted on the other
    games only and applied to the held-out one, so no game informs its own
    prediction. An in-sample joint fit would hand back a positive coefficient
    almost regardless — two parameters absorbing whatever they are given.

    PRIMARY TEST: out-of-sample paired Brier(blend) - Brier(market),
    game-clustered. If the blend beats the market with an interval off zero, the
    model carries information the market does not — **even if it forecasts worse
    alone**, which is a different question from the Brier comparison above.
    """
    games = sorted(d.game_id.unique())
    if len(games) < 3:
        print(f"  {label}: {len(games)} games — too few for leave-one-game-out")
        return
    rows, lams = [], []
    for g in games:
        tr, te = d[d.game_id != g], d[d.game_id == g].copy()
        lam = fit_lambda(tr)
        lams.append(lam)
        te["blend"] = (1 - lam) * te.market_mid + lam * te.model_probability
        te["b_blend"] = (te.blend - te.y) ** 2
        te["d_blend_mkt"] = te.b_blend - te.b_mkt
        te["d_blend_model"] = te.b_blend - te.b_model
        rows.append(te)
    ev = pd.concat(rows, ignore_index=True)
    lams = np.array(lams)
    # lambda's OWN uncertainty, by resampling GAMES — the selftest showed a binary
    # outcome makes the point estimate noisy, so a bare lambda would mislead.
    rng = np.random.default_rng(20260904)
    groups = dict(tuple(d.groupby("game_id")))
    boot = [fit_lambda(pd.concat([groups[k] for k in rng.choice(games, len(games), replace=True)],
                                 ignore_index=True)) for _ in range(400)]
    lo_l, hi_l = np.percentile(boot, [2.5, 97.5])
    cm = clustered_mean({g: v.d_blend_mkt.tolist() for g, v in ev.groupby("game_id")})
    cm2 = clustered_mean({g: v.d_blend_model.tolist() for g, v in ev.groupby("game_id")})
    verdict = ("blend BEATS the market — the model adds information" if cm.hi < 0
               else "blend is WORSE than the market" if cm.lo > 0 else "spans zero")
    print(f"  {label}: lambda* {fit_lambda(d):+.4f} [{lo_l:+.4f}, {hi_l:+.4f}] "
          f"(by-game bootstrap) · per-fold mean {lams.mean():+.4f}, G={len(games)}")
    print(f"    OOS blend - market : {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] n={cm.n:,} "
          f"-> {verdict}")
    print(f"    OOS blend - model  : {cm2.mean:+.6f} [{cm2.lo:+.6f}, {cm2.hi:+.6f}]")


def selftest() -> None:
    """The instrument must recover a known answer before reporting an unknown one."""
    ok = True
    rng = np.random.default_rng(11)
    n_games, per = 40, 30
    g = np.repeat(np.arange(n_games), per)
    truth = rng.uniform(0.1, 0.9, n_games * per)
    y = (rng.uniform(size=len(truth)) < truth).astype(float)

    # 1. a model equal to the market must read ~0 with an interval covering it
    d = pd.DataFrame({"game_id": g, "y": y, "model_probability": truth, "market_mid": truth})
    d["b_model"] = (d.model_probability - d.y) ** 2
    d["b_mkt"] = (d.market_mid - d.y) ** 2
    d["diff"] = d.b_model - d.b_mkt
    cm = clustered_mean({k: v["diff"].tolist() for k, v in d.groupby("game_id")})
    print(f"[null] identical forecasts: diff {cm.mean:+.6f} [{cm.lo:+.6f}, {cm.hi:+.6f}] (want ~0)")
    ok &= abs(cm.mean) < 1e-9

    # 2. a KNOWN-WORSE model must be detected, and a known-better one too
    for label, noise, want_sign in [("worse", 0.15, +1), ("better", -0.10, -1)]:
        if want_sign > 0:
            model = np.clip(truth + rng.normal(0, noise, len(truth)), 0.001, 0.999)
            market = truth
        else:  # market is the noisy one, so the model is better
            model = truth
            market = np.clip(truth + rng.normal(0, abs(noise), len(truth)), 0.001, 0.999)
        dd = pd.DataFrame({"game_id": g, "y": y, "model_probability": model, "market_mid": market})
        dd["diff"] = (dd.model_probability - dd.y) ** 2 - (dd.market_mid - dd.y) ** 2
        cm = clustered_mean({k: v["diff"].tolist() for k, v in dd.groupby("game_id")})
        detected = (cm.lo > 0) if want_sign > 0 else (cm.hi < 0)
        print(f"[{label}] injected: diff {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}] "
              f"-> detected with CI off zero: {detected}")
        ok &= detected

    # 3. the dedupe rule must actually reduce to one row per market
    many = pd.DataFrame({"market_slug": ["a"] * 5 + ["b"] * 3,
                         "predicted_at": list(range(5)) + list(range(3)),
                         "model_probability": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]})
    fst, lst = dedupe(many, "first"), dedupe(many, "last")
    print(f"[dedupe] 8 rows/2 markets -> first {len(fst)} rows "
          f"{fst.model_probability.tolist()} · last {len(lst)} rows {lst.model_probability.tolist()}")
    ok &= len(fst) == 2 and fst.model_probability.tolist() == [0.1, 0.6] \
        and lst.model_probability.tolist() == [0.5, 0.8]

    # 4. lambda* must recover a KNOWN blend weight and read ~0 on a useless model.
    #    Construction: truth t; market sees t + eps, model sees t + eta, both
    #    unbiased and independent, so the optimal weight on the model is
    #    lam* = var(eps) / (var(eps) + var(eta)).
    # 4a. ALGEBRA, on a continuous outcome where the estimator should be near-exact.
    #     Separated from 4b because a binary outcome adds Bernoulli noise that
    #     swamps the regressor: with sd(mdl-mkt)~0.06 and sd(y-t)~0.45, the slope's
    #     own SE is ~0.2 at n=1,200. My first version of this test asserted a 0.12
    #     tolerance on binary data at that n and FAILED — the estimator was right
    #     and the test was underpowered. That is why lambda is reported below with
    #     an interval and never as a bare point estimate.
    for s_eps, s_eta in [(0.03, 0.05), (0.06, 0.02)]:
        t = rng.uniform(0.2, 0.8, 40000)
        mkt = t + rng.normal(0, s_eps, len(t))
        mdl = t + rng.normal(0, s_eta, len(t))
        yy = t + rng.normal(0, 0.01, len(t))  # continuous outcome: algebra only
        want = s_eps**2 / (s_eps**2 + s_eta**2)
        got = fit_lambda(pd.DataFrame({"y": yy, "model_probability": mdl, "market_mid": mkt}))
        print(f"[lambda algebra] sigma_eps={s_eps} sigma_eta={s_eta}: fitted {got:+.4f} "
              f"vs theory {want:.4f}")
        ok &= abs(got - want) < 0.03

    # 4b. UNBIASEDNESS on a BINARY outcome, at a sample where the noise averages out.
    t = rng.uniform(0.2, 0.8, 400000)
    mkt = np.clip(t + rng.normal(0, 0.03, len(t)), 0.001, 0.999)
    mdl = np.clip(t + rng.normal(0, 0.05, len(t)), 0.001, 0.999)
    yy = (rng.uniform(size=len(t)) < t).astype(float)
    got = fit_lambda(pd.DataFrame({"y": yy, "model_probability": mdl, "market_mid": mkt}))
    print(f"[lambda binary] n=400k: fitted {got:+.4f} vs theory 0.2647 "
          f"(binary noise is why this needs 400k and the real run needs an interval)")
    ok &= abs(got - 0.2647) < 0.06

    # 4c. a USELESS model must read ~0
    mdl_bad = np.clip(rng.uniform(0.2, 0.8, len(t)), 0.001, 0.999)  # pure noise, no t
    got = fit_lambda(pd.DataFrame({"y": yy, "model_probability": mdl_bad, "market_mid": mkt}))
    print(f"[lambda useless] model carrying NO information: fitted {got:+.4f} (want ~0)")
    ok &= abs(got) < 0.03

    #    and the OOS machinery must DETECT a genuinely informative model
    t = rng.uniform(0.2, 0.8, n_games * per)
    mkt = np.clip(t + rng.normal(0, 0.10, len(t)), 0.001, 0.999)
    mdl = np.clip(t + rng.normal(0, 0.10, len(t)), 0.001, 0.999)
    yy = (rng.uniform(size=len(t)) < t).astype(float)
    dd = pd.DataFrame({"game_id": g, "y": yy, "model_probability": mdl, "market_mid": mkt})
    dd["b_model"] = (dd.model_probability - dd.y) ** 2
    dd["b_mkt"] = (dd.market_mid - dd.y) ** 2
    dd["diff"] = dd.b_model - dd.b_mkt
    print("[lambda OOS] two equally-noisy independent forecasts — blend must beat the market:")
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lambda_star(dd, "synthetic")
    line = [l for l in buf.getvalue().splitlines() if "blend - market" in l][0]
    print(f"   {line.strip()}")
    ok &= "BEATS" in line

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--pin", default=PIN)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    report(load(args.pin))


if __name__ == "__main__":
    main()
