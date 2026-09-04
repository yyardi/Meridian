"""The martingale null for D's accumulator test — built BEFORE the real number.

    .venv/bin/python analysis/accumulator_martingale_null.py [--exports DIR]
    .venv/bin/python analysis/accumulator_martingale_null.py --selftest

D's hypothesis: v1 may be a passive POSITION ACCUMULATOR with slightly
better-than-mid entries rather than a market maker — we take on
fairly-priced inventory and hold it to a binary, and the loss is in the
holding. The registered test is whether per-game P&L tracks the game's
outcome direction against our net position.

★ WHY THAT TEST NEEDS A NULL, AND WHY THE NULL IS NOT "NO RELATIONSHIP".
Our net position is CREATED BY THE PRICE PATH, not chosen independently
of it. A resting bid fills only when the mid comes DOWN to it, so we
accumulate long into declines; a resting ask accumulates short into
rallies. A binary's price path terminates AT its outcome. So net
position and outcome are linked through the path before any skill
enters, and a naive test is close to guaranteed to return a confident
"our position is on the wrong side" under a completely fair market.

The null is therefore **the relationship a martingale plus this fill
rule already produces**. Under a martingale, accumulating into declines
is fair; the real question is whether continuation exceeds martingale,
and only the null says where that line sits.

★ PRE-DECLARED STATISTIC — fixed here before any null was generated, and
never evaluated on the observed settlements by this script (D's
registration owns the real number; see THE FIREWALL below).

    per real fill i:  x_i = side_i * (s_m(i) - mid_at_fill_i)
                      side = +1 for a bid fill (we are long YES),
                             -1 for an ask fill (we are short YES)
    S = mean_i x_i          (reported in cents)

S is P&L measured against the MID AT FILL rather than against our quote
price. That removes our execution edge (the excess the mid travelled to
reach us) and isolates exactly D's question: **was the position on the
right side of the eventual outcome, relative to what the market itself
believed at the moment we took it on?**

★ CORRECTION, AND IT IS THE WHOLE REASON THE NULL WAS WORTH BUILDING.
When this statistic was declared I wrote that a fair accumulator scores
S = 0. **That was wrong, and the null caught it.** A fair market scores
S = **+3.17c**, and the offset is mechanical rather than skill: within a
market, bid fills land where the mid is BELOW its market average (0.459
vs 0.490) and ask fills where it is ABOVE (0.547 vs 0.514), because the
mid must travel to reach a resting quote. Measuring against a
market-level expectation therefore hands BOTH sides a positive offset —
the same selection structure as the four forced gradients, now living
inside the summary statistic itself.

The offset is derivable in closed form with no settlements at all:
    E[S | fair] = mean_i side_i * (p_m(i) - mid_i)  =  +3.174c
which matches the resampling null's +3.176c. The statistic is unchanged
from its declaration; only my stated expectation of it was wrong, which
is precisely the error a null exists to prevent. **Anyone comparing D's
S against zero would misread a fair result as a 3-cent edge, or a
3-cent deficit as fair.**

★ WHY THE NULL'S DISPERSION IS THE WHOLE POINT. Settlement is constant
within a market (verified: 0 of 564 markets carry more than one value),
so thousands of fills share a handful of binary draws. A per-fill
interval would treat 13,651 fills as 13,651 observations when the
effective n is nearer 564 markets across 24 games. The null reproduces
that dependence exactly, because it resamples at the level the
randomness actually lives — the market.

★ TWO CONSTRUCTIONS, both requested, because disagreement between them
is itself informative about which link carries the claim.

  (a) RESAMPLE: draw each market's settlement s_m ~ Bernoulli(p_m) with
      p_m = the mean mid at our own real fills in that market. This is
      "the market was fair at the moments we traded". It keeps the fill
      selection — every bit of "we accumulate long into declines" is
      preserved — and breaks only the link between the path and the
      terminal outcome beyond what the mid already said.

  (b) PERMUTE: shuffle the observed market settlements ACROSS markets,
      stratified by p_m decile. Stratification is not optional: a market
      priced at 0.9 must not receive the outcome of one priced at 0.1,
      or the null tests calibration rather than direction.

★ THE FIREWALL. This script never computes S on the observed
settlements. Construction (a) never reads them at all. Construction (b)
reads them only to permute them and evaluates no identity permutation.
I have not seen the observed value of S and nothing here reports it — a
null built by someone who has seen the answer is a weaker null.

★ MUTATION TESTS (rule 4, applied to the null itself): on synthetic
data the pipeline must read ~zero and inside its own band when outcomes
are fair, and must land decisively outside the band when a directional
effect is injected. `--selftest` runs both.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

EXPORT_NAME = "quote_fills_classified_20260904T142200Z.csv"
N_REPS = 4000
SEED = 20260904


def statistic(side: np.ndarray, mid: np.ndarray, settle_per_fill: np.ndarray
              ) -> float:
    """The pre-declared S, in cents. Pure function of its arguments."""
    return float(np.mean(side * (settle_per_fill - mid)) * 100.0)


def build_frame(exports: Path) -> pd.DataFrame:
    d = pd.read_csv(exports / EXPORT_NAME).rename(columns={"pop": "population"})
    r = d[d.population == "real"].copy()
    r["mid_f"] = (r.bb + r.ba) / 2
    r["sgn"] = np.where(r.side == "bid", 1.0, -1.0)
    return r[["market_slug", "game_id", "sgn", "mid_f", "settlement"]]


def null_distributions(r: pd.DataFrame, reps: int = N_REPS) -> dict:
    rng = np.random.default_rng(SEED)
    codes, uniq = pd.factorize(r.market_slug)
    sgn = r.sgn.to_numpy()
    mid = r.mid_f.to_numpy()
    # p_m: mean mid at our own real fills, per market — the market's own
    # belief at the moments we traded
    p_m = (pd.Series(mid).groupby(codes).mean()
           .reindex(range(len(uniq))).to_numpy())

    # (a) RESAMPLE — never touches observed settlements
    a = np.empty(reps)
    for i in range(reps):
        s_m = (rng.random(len(uniq)) < p_m).astype(float)
        a[i] = statistic(sgn, mid, s_m[codes])

    # (b) PERMUTE — observed settlements shuffled within p_m decile
    obs_m = (r.groupby(r.market_slug.map({u: j for j, u in enumerate(uniq)}))
             .settlement.first().reindex(range(len(uniq))).to_numpy())
    strata = pd.qcut(p_m, 10, labels=False, duplicates="drop")
    b = np.empty(reps)
    for i in range(reps):
        s_m = obs_m.copy()
        for st in np.unique(strata):
            idx = np.flatnonzero(strata == st)
            s_m[idx] = rng.permutation(s_m[idx])
        b[i] = statistic(sgn, mid, s_m[codes])
    return {"resample": a, "permute": b, "n_markets": len(uniq),
            "n_fills": len(r), "n_games": r.game_id.nunique()}


def report(name: str, x: np.ndarray) -> None:
    lo, hi = np.percentile(x, [2.5, 97.5])
    print(f"| {name} | {x.mean():+.3f}c | {x.std(ddof=1):.3f}c | "
          f"[{lo:+.3f}, {hi:+.3f}] | [{np.percentile(x,0.5):+.3f}, "
          f"{np.percentile(x,99.5):+.3f}] |")


def selftest() -> int:
    rng = np.random.default_rng(7)
    n_mkt, per = 500, 25
    codes = np.repeat(np.arange(n_mkt), per)
    p_m = rng.uniform(0.15, 0.85, n_mkt)
    mid = p_m[codes] + rng.normal(0, 0.01, n_mkt * per)
    sgn = rng.choice([1.0, -1.0], n_mkt * per)
    frame = pd.DataFrame({"market_slug": codes, "game_id": codes % 24,
                          "sgn": sgn, "mid_f": mid})
    ok = True
    # FAIR: outcomes drawn at the mid
    s_fair = (rng.random(n_mkt) < p_m).astype(float)
    f = frame.assign(settlement=s_fair[codes])
    nd = null_distributions(f, reps=600)
    s_obs = statistic(sgn, mid, s_fair[codes])
    lo, hi = np.percentile(nd["resample"], [2.5, 97.5])
    inside = lo <= s_obs <= hi
    print(f"fair synthetic     : S={s_obs:+.3f}c  null95=[{lo:+.3f},{hi:+.3f}] "
          f"-> {'OK (inside)' if inside else 'FAIL'}")
    ok &= inside
    # INJECTED: markets we are net-long settle 0 more often than the mid says
    net = pd.Series(sgn).groupby(codes).sum().to_numpy()
    p_bias = np.clip(p_m - 0.18 * np.sign(net), 0.02, 0.98)
    s_bias = (rng.random(n_mkt) < p_bias).astype(float)
    g = frame.assign(settlement=s_bias[codes])
    nd2 = null_distributions(g, reps=600)
    s_obs2 = statistic(sgn, mid, s_bias[codes])
    lo2, hi2 = np.percentile(nd2["resample"], [2.5, 97.5])
    outside = s_obs2 < lo2
    print(f"injected directional: S={s_obs2:+.3f}c  null95=[{lo2:+.3f},{hi2:+.3f}] "
          f"-> {'OK (detected)' if outside else 'FAIL'}")
    ok &= outside
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=REPO / "backups/exports")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    r = build_frame(args.exports)
    nd = null_distributions(r)
    print("# The martingale null for the accumulator test\n")
    print(f"Real fills {nd['n_fills']:,} · markets {nd['n_markets']} · "
          f"games {nd['n_games']} · {N_REPS:,} replications · seed {SEED}\n")
    sgn = r.sgn.to_numpy(); mid = r.mid_f.to_numpy()
    codes, uniq = pd.factorize(r.market_slug)
    p_m = (pd.Series(mid).groupby(codes).mean()
           .reindex(range(len(uniq))).to_numpy())
    analytic = float(np.mean(sgn * (p_m[codes] - mid)) * 100)
    print("**S = mean over real fills of side x (settlement - mid_at_fill), "
          "in cents.** Pre-declared before any null was generated.\n")
    print(f"**A fair market does NOT score zero on it: E[S | fair] = "
          f"{analytic:+.3f}c**, derived in closed form from mids and sides "
          f"with no settlements. Bid fills land below their market's mean "
          f"mid and ask fills above it, so the fill rule hands both sides a "
          f"positive offset. Comparing S against 0 would misread a fair "
          f"result as a 3-cent edge.\n")
    print("| null | mean | sd | 95% band | 99% band |")
    print("|---|---:|---:|---|---|")
    report("(a) resample at the mid", nd["resample"])
    report("(b) permute within p decile", nd["permute"])
    a, b = nd["resample"], nd["permute"]
    print(f"\n**The bar: |S| must fall outside roughly "
          f"[{np.percentile(a,2.5):+.2f}, {np.percentile(a,97.5):+.2f}]c "
          f"to be surprising at 95% under a fair market with this fill "
          f"rule.** A per-fill interval over {nd['n_fills']:,} fills would "
          f"be roughly sqrt({nd['n_fills']}/{nd['n_markets']}) ="
          f" {np.sqrt(nd['n_fills']/nd['n_markets']):.1f}x too narrow, "
          f"because settlement is constant within a market and the "
          f"randomness lives at the market level.\n")
    print(f"**The two constructions differ in CENTRE by "
          f"{a.mean()-b.mean():+.2f}c** ({a.mean():+.2f} resample vs "
          f"{b.mean():+.2f} permute), with near-identical dispersion "
          f"({a.std(ddof=1):.2f} vs {b.std(ddof=1):.2f}). That gap is "
          f"informative, as predicted: (a) assumes the mid is CALIBRATED "
          f"and draws outcomes from it; (b) inherits the observed outcome "
          f"rate within each price decile and breaks only the pairing "
          f"between markets and outcomes. The difference is therefore the "
          f"contribution of the market's own calibration error over our "
          f"fills.\n")
    print("**Recommendation: use (b) as the primary bar.** It tests what D "
          "is actually asking — is our POSITION on the wrong side — "
          "without additionally assuming the mid is well calibrated, which "
          "is a separate claim with its own evidence. Report (a) beside it "
          "as the sensitivity that adds the calibration assumption.\n")
    print("Construction (a) never reads observed settlements; (b) reads "
          "them only to permute, and no identity permutation is evaluated. "
          "**No observed value of S is computed anywhere in this script, "
          "and the author has not seen it.**\n")
    print("No in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
