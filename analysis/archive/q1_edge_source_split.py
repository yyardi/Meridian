"""The Q1 edge-source split — speed-1 item 1: the diagnostic, not a candidate.

    .venv/bin/python analysis/q1_edge_source_split.py [--exports DIR]
    .venv/bin/python analysis/q1_edge_source_split.py --selftest

43% of all PULSE fills land in Q1 (O1: "it acts very odd at tip, taking so
many positions"), and β(4′) ≈ 0.45 (the R2 physics) says nearly half of an
early margin deviation dies before the final — Q1 is where live-margin
information is WEAKEST. So the flood is defensible only if Q1 entries are
ANCHOR-driven (pregame line vs venue price) rather than MARGIN-driven (the
model trading its own most-reverting input). Nobody has cut this.

The decomposition, exact by construction from the engine's own formulas:

* winner/spread (core/live_fv.py, core/pulse/live.py): FV = Φ((margin +
  E·t/40 + line₀)/(σ√t)) with E the pinned pregame drift and line₀ = line
  (spread) or 0 (winner). E inverts per row from the row's own FV; the
  ON-SCRIPT margin at elapsed e is E·e/40, giving FV_anchor =
  Φ((E + line₀)/(σ√t)).
* totals (core/live_totals_fv.py): proj = A + b(e)·(S − A·share(e)) ⇒
  A = (proj − b·S)/(1 − b·share), with b, share imported from the module
  itself; FV_anchor = over_probability(A, line, σ_row). Early-Q1 rows are
  where recovery is LEAST sensitive to b — exactly where this diagnostic
  looks.

Then, side-signed in the entry's own direction:
  edge_anchor = ±(FV_anchor − mid)   — the anchor-vs-market term
  edge_margin = ±(FV − FV_anchor)    — the live-margin-deviation term
  (additive: their sum is the model-vs-mid gap)
and margin_share = |edge_margin| / (|edge_anchor| + |edge_margin|).
Classes: ANCHOR-driven < 1/3 ≤ mixed ≤ 2/3 < MARGIN-driven.

Instrument checks, printed before any result:
* totals round-trip: over_probability(proj_row, line, σ_row) must equal the
  row's fair_value (validates that the stored proj/σ are what priced it);
  rows off by > 1e-3 are excluded and counted.
* winner/spread drift constancy: E is pinned per EVENT for the engine
  process's life, so recovered E must be ~constant across a game's
  winner+spread fills; the per-event E range is printed, and rows from
  events with range > 2.0 points are excluded and counted (catches v4's
  flag-widened σ, which the tape does not carry).
* --selftest builds rows THROUGH the engine's own functions with known
  drift/deviation composition: on-script rows must decompose to
  margin_share ≈ 0, pure-margin rows to ≈ 1.

Scoring: per-$ realized (A's ledger, optimistic; the pessimistic column
beside it), clustered by game. Exit policy is fixed by construction — the
whole tape is the incumbent exit — and no cut conditions on exit outcome.
Descriptive, in-sample; every interval counted.

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean          # noqa: E402
from core.live_fv import DEFAULT_SIGMA, REGULATION_MINUTES        # noqa: E402
from core.live_totals_fv import (                                 # noqa: E402
    expected_share, surprise_coefficient, over_probability, project_total)

LEDGER = "roundtrip_ledger_20260901T195202Z.csv"
DRIFT_RANGE_MAX = 2.0          # points; per-event recovered-E range bound
ROUNDTRIP_TOL = 1e-3
EDGE_BUCKETS = [0.03, 0.06, 0.10, 1.0]
COMPARISONS = {"n": 0}


def decompose(m: pd.DataFrame) -> pd.DataFrame:
    """Add FV_anchor, edge components, margin_share; mark invalid rows."""
    m = m.copy()
    t = m.minutes_left.to_numpy(float)
    e = REGULATION_MINUTES - t
    fv = m.fair_value.to_numpy(float).clip(1e-6, 1 - 1e-6)
    mid = ((m.market_bid + m.market_ask) / 2).to_numpy(float)
    line = m.line.to_numpy(float)
    margin = m.margin.to_numpy(float)
    is_tot = (m.strategy == "total").to_numpy()
    is_win = (m.strategy == "winner").to_numpy()
    line0 = np.where(is_win, 0.0, line)

    fv_anchor = np.full(len(m), np.nan)
    drift = np.full(len(m), np.nan)
    bad = np.zeros(len(m), dtype=bool)

    # winner/spread: invert for the pinned drift E
    ws = ~is_tot
    with np.errstate(all="ignore"):
        z = sstats.norm.ppf(fv[ws])
        st = DEFAULT_SIGMA * np.sqrt(t[ws])
        E = (z * st - margin[ws] - line0[ws]) * REGULATION_MINUTES / t[ws]
        drift[ws] = E
        fv_anchor[ws] = sstats.norm.cdf((E + line0[ws]) / st)

    # totals: recover the pregame anchor A
    tt = is_tot
    b = np.array([surprise_coefficient(x) for x in e[tt]])
    sh = np.array([expected_share(x) for x in e[tt]])
    S = m.total_so_far.to_numpy(float)[tt]
    proj = m.projected_total.to_numpy(float)[tt]
    sig = m.total_sigma.to_numpy(float)[tt]
    denom = 1.0 - b * sh
    A = np.where(np.abs(denom) > 1e-9, (proj - b * S) / denom, np.nan)
    fv_anchor[tt] = [over_probability(projected_total=a, line=l, sigma=s)
                     if np.isfinite(a) else np.nan
                     for a, l, s in zip(A, line[tt], sig)]
    # round-trip: the stored proj/σ must reproduce the stored fair value
    rebuilt = np.array([over_probability(projected_total=p, line=l, sigma=s)
                        for p, l, s in zip(proj, line[tt], sig)])
    bad_t = np.abs(rebuilt - fv[tt]) > ROUNDTRIP_TOL
    idx_t = np.flatnonzero(tt)
    bad[idx_t[bad_t]] = True
    m["roundtrip_err"] = np.nan
    m.loc[m.index[idx_t], "roundtrip_err"] = np.abs(rebuilt - fv[tt])

    m["drift"] = drift
    m["fv_anchor"] = fv_anchor
    sgn = np.where(m.side.to_numpy() == "yes", 1.0, -1.0)
    m["edge_anchor"] = sgn * (fv_anchor - mid)
    m["edge_margin"] = sgn * (fv - fv_anchor)
    tot_abs = np.abs(m.edge_anchor) + np.abs(m.edge_margin)
    m["margin_share"] = np.where(tot_abs > 1e-9,
                                 np.abs(m.edge_margin) / tot_abs, 0.0)
    m["bad"] = bad | ~np.isfinite(fv_anchor)

    # drift constancy per event (winner/spread rows only)
    rng = (m[ws].groupby("event_slug").drift
           .agg(lambda s: s.max() - s.min()))
    bad_events = set(rng[rng > DRIFT_RANGE_MAX].index)
    m.loc[ws & m.event_slug.isin(bad_events).to_numpy(), "bad"] = True
    m.attrs["drift_ranges"] = rng
    m.attrs["bad_events"] = bad_events
    return m


def klass(share: pd.Series) -> pd.Series:
    return pd.cut(share, [-0.01, 1 / 3, 2 / 3, 1.01],
                  labels=["anchor-driven", "mixed", "margin-driven"])


def cm_row(g: pd.DataFrame, label: str, col: str) -> str:
    d = {k: list(v) for k, v in g.groupby("event_slug")[col]}
    c = clustered_mean(d)
    if c is None:
        return f"| {label} | {len(g)} | {g.event_slug.nunique()} | — |"
    COMPARISONS["n"] += 1
    flag = " ◄" if c.hi < 0 else (" ▷" if c.lo > 0 else "")
    return (f"| {label} | {len(g)} | {g.event_slug.nunique()} | "
            f"{c.mean * 100:+.1f}¢ [{c.lo * 100:+.1f}, "
            f"{c.hi * 100:+.1f}]{flag} |")


def run(exports: Path) -> int:
    a = pd.read_csv(exports / LEDGER)
    m = a[a.entry_filled & a.outcome.isin(["exit_fill", "settlement"])].copy()
    m["ret"] = m.pnl_per_dollar
    m["ret_pess"] = m.pnl_per_dollar_pess
    m = decompose(m)

    print("# The Q1 edge-source split — anchor-vs-market or margin-deviation?")
    print()
    print(f"Substrate: A's ledger @ pins · {len(m):,} fills / "
          f"{m.event_slug.nunique()} games · decomposition via the engine's "
          f"own formulas (σ={DEFAULT_SIGMA}); β(4′)≈0.45 (R2) is the prior "
          f"that makes margin-driven Q1 entries suspect. Exit policy fixed "
          f"(whole tape = incumbent exit; no cut conditions on exit "
          f"outcome).")
    rng = m.attrs["drift_ranges"]
    n_bad = int(m.bad.sum())
    print(f"\n**Instrument checks:** totals round-trip max err "
          f"{m.roundtrip_err.max():.5f} (tol {ROUNDTRIP_TOL}); "
          f"winner/spread per-event recovered-drift range median "
          f"{rng.median():.3f} pts, p90 {rng.quantile(.9):.3f} "
          f"(bound {DRIFT_RANGE_MAX}); excluded rows total {n_bad} "
          f"({len(m.attrs['bad_events'])} drift-inconsistent events).")
    m = m[~m.bad].copy()
    m["k"] = klass(m.margin_share)
    m["q1"] = m.period.astype(str) == "Q1"

    print("\n## Composition first — counts, before any ratio\n")
    comp = m.groupby([m.period, "k"], observed=True).size().unstack(fill_value=0)
    print("| period | " + " | ".join(comp.columns) + " | mean margin_share |")
    print("|---" * (len(comp.columns) + 2) + "|")
    for per in comp.index:
        ms = m.loc[m.period == per, "margin_share"].mean()
        print(f"| {per} | " + " | ".join(str(comp.loc[per, c])
                                         for c in comp.columns)
              + f" | {ms:.2f} |")

    print("\n## Q1 per-$ by edge source (clustered by game)\n")
    print("| cut | n | games | per-$ [95% CI] |")
    print("|---|---|---|---|")
    q1 = m[m.q1]
    for k, g in q1.groupby("k", observed=True):
        print(cm_row(g, f"Q1 {k} — optimistic", "ret"))
        print(cm_row(g, f"Q1 {k} — pessimistic", "ret_pess"))
    print(cm_row(q1, "Q1 all — optimistic", "ret"))

    print("\n### Q1, source × claimed-edge bucket (optimistic)\n")
    print("| cut | n | games | per-$ [95% CI] |")
    print("|---|---|---|---|")
    eb = pd.cut(q1.edge_net, EDGE_BUCKETS,
                labels=["3–6¢", "6–10¢", "≥10¢"])
    for (k, b), g in q1.groupby(["k", eb], observed=True):
        if len(g):
            print(cm_row(g, f"Q1 {k}, edge {b}", "ret"))

    print("\n### Context — the same split, Q2 onward (optimistic)\n")
    print("| cut | n | games | per-$ [95% CI] |")
    print("|---|---|---|---|")
    for k, g in m[~m.q1].groupby("k", observed=True):
        print(cm_row(g, f"Q2+ {k}", "ret"))

    print(f"\n---\n**Comparisons: {COMPARISONS['n']} clustered intervals** "
          f"on data mined before (loss map 197+; every cell here is "
          f"in-sample and correlated with those cuts). Descriptive — the "
          f"diagnostic reprices priors, it registers nothing.")
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    return 0


def selftest() -> int:
    from core.live_fv import fair_value, pregame_margin_from_price
    rows = []
    E_true = pregame_margin_from_price(0.65, DEFAULT_SIGMA)
    for i, t in enumerate([36.0, 32.0, 30.0]):
        e = REGULATION_MINUTES - t
        m_on = E_true * e / REGULATION_MINUTES          # on-script margin
        for off, name in ((0.0, "on"), (8.0, "off")):
            fv = fair_value(margin=m_on + off, minutes_left=t,
                            pregame_price=0.65, sigma=DEFAULT_SIGMA)
            # mid placed at the ANCHOR-only value for the off rows so the
            # residual gap is purely margin-sourced
            fva = float(sstats.norm.cdf(
                E_true / (DEFAULT_SIGMA * np.sqrt(t))))
            rows.append({"strategy": "winner", "side": "yes",
                         "line": np.nan, "margin": m_on + off,
                         "minutes_left": t, "fair_value": fv,
                         "market_bid": (fva if off else fv - 0.06) - 0.01,
                         "market_ask": (fva if off else fv - 0.06) + 0.01,
                         "total_so_far": 0, "projected_total": np.nan,
                         "total_sigma": np.nan,
                         "event_slug": "g1", "period": "Q1",
                         "which": name})
    # totals: on-script (surprise 0) and off-script rows
    A_true, line = 165.0, 162.5
    for e_min, off in ((6.0, 0.0), (6.0, 12.0), (9.0, 0.0)):
        S = A_true * expected_share(e_min) + off
        proj = project_total(pregame_mu=A_true, total_so_far=S,
                             elapsed_minutes=e_min)
        sig = 20.0
        fv = over_probability(projected_total=proj, line=line, sigma=sig)
        fva = over_probability(projected_total=A_true, line=line, sigma=sig)
        rows.append({"strategy": "total", "side": "yes", "line": line,
                     "margin": 0, "minutes_left": REGULATION_MINUTES - e_min,
                     "fair_value": fv,
                     "market_bid": (fva if off else fv - 0.06) - 0.01,
                     "market_ask": (fva if off else fv - 0.06) + 0.01,
                     "total_so_far": S, "projected_total": proj,
                     "total_sigma": sig, "event_slug": "g2", "period": "Q1",
                     "which": "off" if off else "on"})
    df = decompose(pd.DataFrame(rows))
    on = df[df.which == "on"]
    off = df[df.which == "off"]
    ok1 = bool((on.margin_share < 0.05).all())
    ok2 = bool((off.margin_share > 0.95).all())
    print(f"on-script rows  -> margin_share max {on.margin_share.max():.4f} "
          f"{'OK (~0: anchor-driven)' if ok1 else 'FAIL'}")
    print(f"off-script rows -> margin_share min {off.margin_share.min():.4f} "
          f"{'OK (~1: margin-driven)' if ok2 else 'FAIL'}")
    return 0 if (ok1 and ok2) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path,
                    default=REPO / "backups/exports")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return selftest() if args.selftest else run(args.exports)


if __name__ == "__main__":
    raise SystemExit(main())
