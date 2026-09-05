"""THE MODEL PIN — P(ride) exactly as the variance-aware Kelly gate uses it.

    .venv/bin/python analysis/ride_model_pin.py --verify

This file is the pin (docs/math/variance-aware-kelly.md, rule 12: a pin
declared in prose and not enforced in code is not a pin). It carries, as
committed constants:

* the FEATURES and their exact construction (identical to
  ``analysis/ride_predictor.py``'s, restated here so the pin stands alone);
* the standardization constants (MU, SD);
* the FROZEN logistic coefficients — **there is no refit rule; the
  coefficients are the pin.** They were fit ONCE on the full pinned
  in-sample ledger (``roundtrip_ledger_20260901T195202Z.csv``, 1,944 scored
  fills / 137 rides / 34 games). LOGO was the in-sample VALIDATION
  discipline (AUC 0.700, calibrated top quintile 18.0%/17.0% — the
  ride-predictor report); the forward gate scores with these frozen
  coefficients and never refits inside the cohort;
* the QUINTILE EDGES — quintiles of the frozen model's p̂ over the same
  in-sample ledger. Forward entries are binned by THESE edges, so "q5" and
  "q1" mean the same thing forward as they meant when the null was
  pre-committed;
* the SIZING MAP from p̂ to a fraction (the arm's definition needs it
  pinned no less than the model): **inverse-variance allocation in the
  pinned two-point tail model.** Each entry's per-$ variance under the
  mean-zero tail model (mean pinned at zero — the pre-committed null is
  the premise) is ``SIGMA2(p̂) = p̂ · L_RIDE² / (1 − p̂)``; the arm's
  fraction is ``f_i = min(F_CAP, s / SIGMA2(p̂_i))`` with ``s`` solved so
  the cohort mean equals the incumbent flat fraction ``F0`` (equal mean
  exposure, per the registration). This is the fractional-Kelly solution
  under the registration's own flat-mean premise (minimize volatility
  drag at fixed total exposure), and BY CONSTRUCTION it cannot zero an
  entry out — a map that embeds a mean model (e.g. the engine's 5¢
  target over cost) zeroes high-p̂ entries and thereby rebuilds the
  filter this gate exists to distinguish from a variance model. That map
  was considered and rejected here for exactly that reason.

``--verify`` refits from the pinned ledger and asserts the constants
reproduce — the pin is auditable, not hand-typed.

Label caveat travels with the pin: "ride" is optimistic-fill-defined, a
lower bound on real no-exit risk (ride share 17.7% at the measured 4.70¢
concession, drop-policy base — the ride-predictor report's addendum).

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: source of every frozen number below
PIN_LEDGER = "roundtrip_ledger_20260901T195202Z.csv"

CONT = ["minutes_left", "abs_margin", "ml_x_margin", "spread_px", "cost",
        "edge_net"]
DUMMY = ["is_spread", "is_winner", "is_yes"]
FEATURES = CONT + DUMMY

MU = {"minutes_left": 25.95607, "abs_margin": 6.846708,
      "ml_x_margin": 3.294448, "spread_px": 0.060087,
      "cost": 0.446214, "edge_net": 0.114875}
SD = {"minutes_left": 11.074452, "abs_margin": 6.239033,
      "ml_x_margin": 4.437562, "spread_px": 0.039993,
      "cost": 0.199113, "edge_net": 0.077104}
COEF = {"const": -2.754677, "minutes_left": 0.073545,
        "abs_margin": -0.395169, "ml_x_margin": 0.911362,
        "spread_px": -0.005166, "cost": -0.723345, "edge_net": -0.187656,
        "is_spread": -0.411623, "is_winner": -0.553641, "is_yes": 0.110943}

#: quintile edges of the frozen model's p̂ on the pinned in-sample ledger
QUINTILE_EDGES = [0.024999, 0.041443, 0.061083, 0.096625]

#: sizing-map constants (pinned)
L_RIDE = 0.8263   # in-sample mean ride loss per $ staked (pinned ledger)
F0 = 0.0467       # incumbent flat fraction: median stake/bankroll, pinned
                  # ledger's filled entries
F_CAP = 4 * F0    # clamp on the variance arm's fraction
DIVERGENCE_EPS = 0.1 * F0  # |f_var − F0| above this = a sizing-divergent
                           # entry (the registration's floor unit)


def build_features(m: pd.DataFrame) -> pd.DataFrame:
    """Exact feature construction. Input: entry-level rows carrying
    minutes_left, margin, market_bid/ask, entry cost per contract (YES
    frame), edge_net, strategy, side."""
    f = pd.DataFrame(index=m.index)
    f["minutes_left"] = m.minutes_left
    f["abs_margin"] = m.margin.abs()
    f["ml_x_margin"] = (40 - m.minutes_left) * f.abs_margin / 40
    f["spread_px"] = m.market_ask - m.market_bid
    f["cost"] = m.cost
    f["edge_net"] = m.edge_net
    f["is_spread"] = (m.strategy == "spread").astype(int)
    f["is_winner"] = (m.strategy == "winner").astype(int)
    f["is_yes"] = (m.side == "yes").astype(int)
    return f


def predict(m: pd.DataFrame) -> np.ndarray:
    """P(ride) from the frozen coefficients. No fitting happens here."""
    f = build_features(m)
    z = np.full(len(f), COEF["const"])
    for c in CONT:
        z += COEF[c] * (f[c].to_numpy() - MU[c]) / SD[c]
    for d in DUMMY:
        z += COEF[d] * f[d].to_numpy()
    return 1.0 / (1.0 + np.exp(-z))


def quintile(p: np.ndarray) -> np.ndarray:
    """1..5 by the PINNED edges (not the forward distribution)."""
    return 1 + np.searchsorted(QUINTILE_EDGES, p)


def sigma2(p: np.ndarray) -> np.ndarray:
    """Per-$ variance under the pinned mean-zero two-point tail model."""
    return p * L_RIDE ** 2 / (1.0 - p)


def variance_fractions(p: np.ndarray) -> np.ndarray:
    """The pinned sizing map: inverse-variance, capped, scaled by
    bisection so the mean fraction equals F0 (equal mean exposure)."""
    inv = 1.0 / sigma2(p)

    def mean_at(s: float) -> float:
        return float(np.minimum(F_CAP, s * inv).mean())

    lo, hi = 0.0, F_CAP / inv.min() if inv.min() > 0 else 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if mean_at(mid) < F0:
            lo = mid
        else:
            hi = mid
    return np.minimum(F_CAP, 0.5 * (lo + hi) * inv)


def verify(exports=None) -> int:
    """Refit from the pinned ledger; assert every constant reproduces."""
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "analysis"))
    import statsmodels.api as sm

    ledger = Path(exports or repo / "backups/exports") / PIN_LEDGER
    a = pd.read_csv(ledger)
    m = a[a.entry_filled & a.outcome.isin(["exit_fill", "settlement"])].copy()
    m["cost"] = m.entry_cost_per_contract
    y = (m.outcome == "settlement").astype(int)
    f = build_features(m)

    mu, sd = f[CONT].mean(), f[CONT].std()
    for c in CONT:
        assert abs(mu[c] - MU[c]) < 1e-4, f"MU[{c}] drifted: {mu[c]}"
        assert abs(sd[c] - SD[c]) < 1e-4, f"SD[{c}] drifted: {sd[c]}"

    X = f.copy()
    for c in CONT:
        X[c] = (X[c] - MU[c]) / SD[c]
    X.insert(0, "const", 1.0)
    res = sm.Logit(y, X.astype(float)).fit(disp=0, maxiter=200)
    for k, v in COEF.items():
        assert abs(res.params[k] - v) < 1e-4, \
            f"COEF[{k}] drifted: {res.params[k]} vs pinned {v}"

    p = predict(m)
    edges = np.quantile(p, [0.2, 0.4, 0.6, 0.8])
    for e, pinned in zip(edges, QUINTILE_EDGES):
        assert abs(e - pinned) < 1e-4, f"edge drifted: {e} vs {pinned}"

    ride_mean = float(m.loc[y == 1, "pnl_per_dollar"].mean())
    assert abs(-ride_mean - L_RIDE) < 1e-3, f"L_RIDE drifted: {ride_mean}"
    frac = (m.stake_usd / m.bankroll_usd).replace(
        [np.inf, -np.inf], np.nan).dropna()
    assert abs(float(frac.median()) - F0) < 1e-3, \
        f"F0 drifted: {frac.median()}"

    print(f"PIN VERIFIED against {PIN_LEDGER}: {len(m)} rows, "
          f"{int(y.sum())} rides; MU/SD, {len(COEF)} coefficients, "
          f"{len(QUINTILE_EDGES)} quintile edges, L_RIDE, F0 all reproduce.")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--exports", default=None,
                    help="directory holding the pinned ledger (default: "
                         "<repo>/backups/exports)")
    args = ap.parse_args()
    raise SystemExit(verify(args.exports) if args.verify else
                     print(__doc__) or 0)
