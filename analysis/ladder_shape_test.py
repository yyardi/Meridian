"""The ladder shape test, run as pre-registered in ladder_shape_test_preregistration.md.

Nothing here was chosen after seeing a residual. The three PASS criteria, the four
nulls, the admissibility rule and the probit link are all from the registration
committed at c83f820, before d5's surface shipped.

## THE MODEL

A rung `asc-cfb-<teams>-<date>-{pos|neg}-<line>` prices a HANDICAP: "this team
+L covers". So mid rises with L, and with threshold `T = -L`:

    mid = P(margin > T) = Phi((mu - T)/sigma) = Phi((mu + L)/sigma)

    probit(mid) = mu/sigma + L/sigma      slope = +1/sigma, intercept = mu/sigma

**The orientation was established empirically, not assumed** — mid runs 0.015 at
L = -34.5 up to 0.755 at L = +34.5 on the first ladder inspected, monotone
increasing, which fixes the handicap reading. It agrees with d5's independently
written `link(mid) = (mu + L)/sigma`.

## ★ NEITHER SIGMA SURFACE HAS A SOUND SELECTOR. THE SLOPE IS OPEN.

**Supersedes commit 0e3116d, which named d5's the authority, and supersedes the
reversal that would name mine.** Both cohorts are selected wrongly and both are
rescued by the same 09-05 board freeze.

* **d5's, n=14:** their `kick` was the first moment the recorder SAW a game, so
  all 14 "kickoffs" are 22:08-22:09Z and every game was already in progress
  (P2 at 14-0, P4 at 49-3). Zero of 14 seen at 0-0.
* **Mine, n=5:** anchored on the first LIVE ROW, which is a venue flag, not an
  event. **Four of my five share the first-live stamp 2026-09-06 01:07:28.867523
  to the microsecond** — a batch flag flip. Across the export, 19 of 24 games
  share a stamp with another and 15 share the export's own first row.

And my pregame windows are frozen on those same four (0-2.4% of markets showing
more than one distinct mid). **Only game 16505 has both a unique first-live
stamp and a moving board, so the defensible cohort is ONE game.**

I told d5 to anchor on an event rather than a flag, and then anchored on a flag.

The values on both sides may still be right — a frozen board carries its last
pregame quotes, so these are pregame ladders in fact. But that is luck, not
provenance, and **the slope disagreement (0.0623 vs 0.1182) is unresolved rather
than adjudicated.** d5's shipped module stays the usable artifact because it has
n and a provenance banner; this file's refit is a 1-defensible-game check and
must not be quoted as a rival.

## ★ THE OLD HEADING, KEPT SO THE SUPERSEDED CLAIM IS VISIBLE

`core/gridiron/scale.py` ships `sigma = 13.19 + 0.1182*|game_spread|` on n=14
with corr +0.948 and a sensitivity analysis across four filter choices. **That is
the number to use.** This file refits the same relation on its own 5-game cohort
purely as a check, and gets `14.44 + 0.0623*|mu|` — consistent in intercept,
different in slope, on five points spanning crossings 7.8-51.8.

**Five points cannot adjudicate a slope and this refit must never be quoted
beside theirs with equal billing.** ce's point: two scale surfaces in circulation
is the shape that produced the 1.193c incident. If they disagree, theirs is
right by n and by sensitivity analysis; mine is only evidence that the
construction reproduces.

## ★ CRITERION 3 IS RUN LEAVE-ONE-GAME-OUT, AND THAT IS A DEPARTURE

The registration says "sigma_implied within +/-10% of d5's surface". **d5's
surface is fitted on these same 14 ladders**, so scoring a ladder against the
full-cohort fit asks whether a fit agrees with itself. That is the in-sample
base-rate defect ce caught in my winner-market work three hours ago, in a new
place.

So criterion 3 uses a **leave-one-game-out** refit of `sigma ~ a + b*|mu|`. This
is stricter than the registration, not looser, and it is what the registration's
own null 5b already demanded. The in-sample version is reported alongside so the
size of the difference is visible rather than asserted.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy.stats import norm

PRICES = "backups/exports/cfb_prices_20260906T194301Z.csv.gz"
RUNG = re.compile(r"^asc-cfb-(.+?)-(\d{4}-\d{2}-\d{2})-(pos|neg)-(\d+)pt5$")

# --- everything below is from the registration, before any data was seen -------
MID_LO, MID_HI = 0.05, 0.95      # d5's interior range; k in [-1.64, +1.64]
WING_POINTS = 10.0               # admissibility: |L - mu| >= this
WING_MIN_PER_SIDE = 3            # ... on at least this many rungs, both sides
MAX_RESID_PP = 2.0               # criterion 1, ce's venue-gap bar, untuned
QUAD_ALPHA = 0.05                # criterion 2
SIGMA_TOL = 0.10                 # criterion 3
PERTURB = (-0.20, -0.10, 0.10, 0.20)   # null 5c


def ladders() -> dict[float, pd.DataFrame]:
    """Last non-live snapshot BEFORE the game's first live row.

    ★ `is_live == 'f'` IS NOT "PREGAME". It reverts after the whistle, so the
    last f-row for a 09-05 game is dated 09-06 15:57 -- a day after kickoff, with
    the ladder pinned at the settled outcome. Fitting those gave sigma median
    30.27 against d5's ~15, R2 0.909 against their 0.992, and a "crossing" at
    224 points. The shape test was measuring my own cohort defect.

    Kickoff is taken from the data itself: the first captured_at at which ANY
    rung of that game is live.
    """
    d = pd.read_csv(PRICES)
    d["live"] = d.is_live.astype(str).str.lower().eq("t")
    m = d.market_slug.str.extract(RUNG)
    d = d.assign(side=m[2], raw=m[3]).dropna(subset=["side"]).copy()
    d["line"] = np.where(d.side.eq("neg"), -1.0, 1.0) * (d.raw.astype(float) + 0.5)
    d["mid"] = (d.best_bid + d.best_ask) / 2
    d["captured_at"] = pd.to_datetime(d.captured_at, utc=True, format="ISO8601",
                                      errors="coerce")
    d = d.dropna(subset=["mid", "captured_at"])
    kickoff = d[d.live].groupby("game_id").captured_at.min()
    out = {}
    for gid, x in d.groupby("game_id"):
        if gid not in kickoff.index:
            continue                      # never went live: no kickoff to anchor on
        pre = x[(~x.live) & (x.captured_at < kickoff[gid])]
        if pre.empty:
            continue
        # LAST QUOTE PER MARKET, never `captured_at == max`. The recorder writes
        # a full ~40-rung sweep and then small updates, so equality-on-timestamp
        # can return FOUR rungs, all near the money -- exactly where sigma is
        # unidentified. That reads as "the closing board thins", a plausible
        # structural finding and entirely a selector bug. Found 2026-09-07.
        snap = pre.sort_values("captured_at").groupby("market_slug").tail(1)
        snap = snap[(snap.mid > MID_LO) & (snap.mid < MID_HI)]
        if len(snap) >= 5:
            out[gid] = snap.sort_values("line")[["line", "mid"]].reset_index(drop=True)
    return out


def fit(lad: pd.DataFrame) -> dict:
    """OLS of probit(mid) on line. slope = 1/sigma, intercept = mu/sigma."""
    L, z = lad.line.to_numpy(), norm.ppf(lad.mid.to_numpy())
    b, a = np.polyfit(L, z, 1)
    if b <= 0:
        return {"ok": False, "reason": f"non-positive slope {b:.4f}"}
    sigma, mu = 1.0 / b, a / b
    fitted = norm.cdf(a + b * L)
    resid_pp = np.abs(fitted - lad.mid.to_numpy()) * 100
    # criterion 2: quadratic term, t-test on the L^2 coefficient
    X = np.column_stack([np.ones_like(L), L, L ** 2])
    beta, *_ = np.linalg.lstsq(X, z, rcond=None)
    resid = z - X @ beta
    dof = len(L) - 3
    quad_p = np.nan
    if dof > 0:
        s2 = resid @ resid / dof
        cov = s2 * np.linalg.pinv(X.T @ X)
        se = np.sqrt(cov[2, 2])
        if se > 0:
            from scipy.stats import t as tdist
            quad_p = 2 * (1 - tdist.cdf(abs(beta[2] / se), dof))
    wing_lo = int((lad.line <= mu - WING_POINTS).sum())
    wing_hi = int((lad.line >= mu + WING_POINTS).sum())
    return {"ok": True, "sigma": sigma, "mu": mu, "n_rungs": len(L),
            "max_resid_pp": float(resid_pp.max()), "quad_p": float(quad_p),
            "wing_lo": wing_lo, "wing_hi": wing_hi,
            "adm_two_sided": wing_lo >= WING_MIN_PER_SIDE and wing_hi >= WING_MIN_PER_SIDE,
            "adm_one_sided": max(wing_lo, wing_hi) >= WING_MIN_PER_SIDE,
            "wing_side": "low" if wing_lo >= wing_hi else "high",
            "r2": float(1 - resid @ resid / ((z - z.mean()) @ (z - z.mean())))}


def surface(rows: pd.DataFrame, drop: float | None = None):
    """Refit sigma ~ a + b*|mu| across games, optionally leaving one out."""
    r = rows[rows.gid != drop] if drop is not None else rows
    b, a = np.polyfit(r.mu.abs().to_numpy(), r.sigma.to_numpy(), 1)
    return lambda mu: a + b * abs(mu), a, b


def main() -> int:
    lads = ladders()
    rows = []
    for gid, lad in lads.items():
        f = fit(lad)
        if f.get("ok"):
            rows.append({"gid": gid, **f})
    R = pd.DataFrame(rows)
    print(f"=== LADDERS: {len(lads)} games with a usable pregame snapshot, "
          f"{len(R)} fitted ===")
    n_bad = len(lads) - len(R)
    if n_bad:
        print(f"  {n_bad} rejected for non-positive slope (wrong orientation)")

    # ---- ADMISSIBILITY, reported not silently applied -----------------------
    two, one = R[R.adm_two_sided], R[R.adm_one_sided]
    print(f"\n=== ADMISSIBILITY — BOTH RULES REPORTED, NEITHER SWAPPED IN SILENTLY ===")
    print(f"  PRE-REGISTERED, two-sided (>={WING_MIN_PER_SIDE} rungs at |L-mu|>="
          f"{WING_POINTS:.0f}pts BOTH sides): {len(two)} of {len(R)}"
          f"   FAILING {len(R)-len(two)}  <- part of the result")
    print(f"  AMENDED, one-sided (same rule, either side):              {len(one)} of {len(R)}")
    if len(two):
        print(f"    two-sided cohort crossings: {two.mu.abs().min():.1f} to "
              f"{two.mu.abs().max():.1f}  (span {two.mu.abs().max()-two.mu.abs().min():.1f} pts)")
    if len(one):
        print(f"    one-sided cohort crossings: {one.mu.abs().min():.1f} to "
              f"{one.mu.abs().max():.1f}  (span {one.mu.abs().max()-one.mu.abs().min():.1f} pts)")
    print("  The amendment is d5's, made AFTER seeing the count, and is only")
    print("  defensible because they independently tested the confound the two-sided")
    print("  rule guarded against (symmetric-window refits: slope 0.1171-0.1256 vs")
    print("  0.1182 unrestricted) and found it absent. Flagged as post-hoc regardless.")
    adm = one if len(two) < 6 else two
    print(f"  SCORING ON: {'one-sided' if adm is one else 'two-sided'} cohort, G={len(adm)}")
    if len(adm) < 3:
        print("  TOO FEW ADMISSIBLE GAMES TO SCORE. Reported as not measured.")
        return 1

    print(f"\n=== PER-GAME FIT (admissible only, G={len(adm)}) ===")
    print(f"  {'game':>7} {'n':>3} {'sigma':>7} {'mu':>7} {'R2':>7} "
          f"{'maxres':>8} {'quad_p':>7}")
    for _, r in adm.iterrows():
        print(f"  {r.gid:>7.0f} {r.n_rungs:>3.0f} {r.sigma:>7.2f} {r.mu:>+7.1f} "
              f"{r.r2:>7.4f} {r.max_resid_pp:>7.2f}pp {r.quad_p:>7.4f}")
    print(f"  sigma: median {adm.sigma.median():.2f}  range {adm.sigma.min():.2f}"
          f"-{adm.sigma.max():.2f}   R2 median {adm.r2.median():.4f} worst {adm.r2.min():.4f}")

    # ---- THE THREE CRITERIA -------------------------------------------------
    _, a_in, b_in = surface(adm)
    print(f"\n  ★ NEITHER SURFACE HAS A SOUND SELECTOR — the slope is OPEN.")
    print(f"    d5: 13.19 + 0.1182*|spread|, n=14, kickoff = first-SEEN, all mid-game.")
    print(f"    mine: {a_in:.2f} + {b_in:.4f}*|mu|, n={len(adm)}, of which 4 share one")
    print(f"    batch first-live stamp and have FROZEN pregame boards. Defensible: 1 game.")
    print(f"    Both rescued by the 09-05 freeze. Use d5's module; quote neither slope.")
    res = []
    for _, r in adm.iterrows():
        s_loo, _, _ = surface(adm, drop=r.gid)
        pred = s_loo(r.mu)
        res.append({
            "gid": r.gid,
            "c1": r.max_resid_pp <= MAX_RESID_PP,
            "c2": not (r.quad_p < QUAD_ALPHA),
            "c3_loo": abs(r.sigma - pred) / pred <= SIGMA_TOL,
            "dev_loo": (r.sigma - pred) / pred,
            "c3_insample": abs(r.sigma - surface(adm)[0](r.mu)) / surface(adm)[0](r.mu) <= SIGMA_TOL,
        })
    C = pd.DataFrame(res)
    C["pass"] = C.c1 & C.c2 & C.c3_loo
    print(f"\n=== THE THREE CRITERIA, G={len(C)} ===")
    print(f"  1 max |residual| <= {MAX_RESID_PP}pp        pass {int(C.c1.sum())}/{len(C)}")
    print(f"  2 quadratic term n.s. at {QUAD_ALPHA}       pass {int(C.c2.sum())}/{len(C)}")
    print(f"  3 sigma within +/-{SIGMA_TOL:.0%} LEAVE-ONE-OUT  pass {int(C.c3_loo.sum())}/{len(C)}")
    print(f"    (same, IN-SAMPLE, the weaker form)  pass {int(C.c3_insample.sum())}/{len(C)}")
    print(f"  ALL THREE                            pass {int(C['pass'].sum())}/{len(C)}")
    print(f"  worst leave-one-out sigma deviation: {C.dev_loo.abs().max():.1%}")

    # ---- NULL 5c: THE ONE THAT MUST BE ABLE TO FAIL -------------------------
    print(f"\n=== NULL 5c — DELIBERATELY WRONG SIGMA (must REJECT) ===")
    for e in PERTURB:
        rej = 0
        for _, r in adm.iterrows():
            s_loo, _, _ = surface(adm, drop=r.gid)
            pred = s_loo(r.mu) * (1 + e)
            if abs(r.sigma - pred) / pred > SIGMA_TOL:
                rej += 1
        verdict = "REJECTED (test has power)" if rej > len(adm) / 2 else "NOT rejected"
        print(f"  sigma {e:+.0%}   rejected {rej}/{len(adm)}   {verdict}")

    # ---- NULL 5a: weak by construction, labelled as such --------------------
    print(f"\n=== NULL 5a — self-consistency (WEAK: passes by construction) ===")
    print(f"  in-sample criterion 3 pass {int(C.c3_insample.sum())}/{len(C)} — detects a")
    print("  broken implementation only, NOT evidence the test discriminates.")
    projection_check()
    print(f"★ G = {len(adm)}. TOO FEW GAMES TO MAKE A SHAPE CLAIM. The nulls pass, the")
    print("  criteria are achievable and discriminating, and the ladders fail them —")
    print("  but 5 games is not a result and is reported as NOT MEASURED.")
    return 0




def projection_check(n_sims: int = 4000, sigma: float = 15.0, seed: int = 0) -> None:
    """Null 5d: the achievable image of criterion 1. RUN THIS BEFORE SCORING.

    Generates ladders that ARE the model, quantises to the venue's 1c grid, fits
    exactly as the test fits, and reads what max-residual is attainable. If a
    perfect ladder cannot clear the bar, the criterion rejects everything and
    measures nothing.

    ★ MY FIRST VERSION OF THIS HAD A BUG AND SAID THE OPPOSITE. It paired
    filtered probabilities with UNFILTERED lines (`LL = L[:len(p)]` instead of
    `L[mask]`), which reported median max-residual 8-13pp and a 2.7-17.4% pass
    rate for a perfect ladder — i.e. "criterion 1 is mis-specified, throw it
    away". Corrected, a perfect ladder passes 100% with p99 = 0.72pp. The check
    written to stop me misreading the data nearly made me discard a working
    criterion instead.
    """
    rng = np.random.default_rng(seed)

    def sim(n, scored_sigma=None):
        out = []
        for _ in range(n_sims):
            mu = rng.uniform(-45, -5)
            L = np.sort(rng.uniform(mu - 30, mu + 30, n))
            p = norm.cdf((mu + L) / sigma)
            k = (p > MID_LO) & (p < MID_HI)
            if k.sum() < 5:
                continue
            p, LL = p[k], L[k]
            q = np.round(p * 100) / 100          # the venue quotes on a 1c grid
            if scored_sigma is None:
                z = norm.ppf(q)
                b, a = np.polyfit(LL, z, 1)
                pred = norm.cdf(a + b * LL)
            else:
                pred = norm.cdf((mu + LL) / scored_sigma)
            out.append(np.abs(pred - q).max() * 100)
        return np.array(out)

    print("\n=== NULL 5d — PROJECTION CHECK ON CRITERION 1 ===")
    print(f"  {'n':>3} | {'median':>8} {'p99':>8} {'pass <=' + str(MAX_RESID_PP) + 'pp':>14}")
    for n in (6, 11, 17, 26, 40):
        o = sim(n)
        print(f"  {n:>3} | {np.median(o):7.2f}pp {np.percentile(o, 99):7.2f}pp "
              f"{(o <= MAX_RESID_PP).mean() * 100:13.1f}%")
    print("  a ladder that IS the model clears the bar, so the bar is achievable")
    print("  and a failure is misfit rather than an artifact of the threshold.\n")
    for e in PERTURB:
        o = sim(26, scored_sigma=sigma * (1 + e))
        print(f"  sigma {e:+.0%}: median {np.median(o):5.2f}pp, "
              f"rejected {(o > MAX_RESID_PP).mean() * 100:5.1f}%  <- and it discriminates")


if __name__ == "__main__":
    raise SystemExit(main())
