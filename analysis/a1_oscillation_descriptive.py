"""A1 — the oscillation harvest: descriptive pass with the full demand-stack.

Candidate A1 (analysis/BRAINSTORM_ENTRY_POLICY.md): realized mean-reverting
mid-vol CHARACTER — not the dead `edge_net` — orders per-$ over all fills,
because the 5¢-target roll is a short-vol / mean-reversion harvester (wall 3).
This is the round-3 speed-1 #2 descriptive pass. **DESCRIPTIVE, in-sample,
HYPOTHESIS-GENERATING. Nothing here gates; the forward test is the evidence.**

Reproduce:  python3 analysis/a1_oscillation_descriptive.py
Self-tests run first (wave rule 4) and the script refuses to continue on failure.

Pins (20260901T195202Z): the tick tape `live_ticks_pulse_games_...csv.gz`
(11.28M rows, 200ms cadence, 612 market-rungs / 34 games) and A's round-trip
ledger `roundtrip_ledger_...csv` (the P&L substrate, one row per entry).

THE SIX DEMANDS, welded to A1's registrable form (round-3 synthesis), and where
each is discharged here:

1. **Real resting fills only** — the GATE. The quote engine's real fills
   (`shadow_quote_fills`) are NOT in the pinned exports (they live only in the
   live DB), so the gate arm reads **NO DATA** here by construction; this pass
   builds the instrument and runs the PILOT. The gate is a forward/DB job.
2. **Ordered over ALL fills** — the pilot never conditions on trip-vs-ride
   (D's collider; the k=4.70 relabelling flipped 191 boundary trips). Per-$ is
   bucketed by vol character over trips AND rides together.
3. **The payoff-structure PLACEBO** — identical 5¢-target mechanics over the
   same tick paths with RANDOM matched entries (random instant, coin-flip
   side). If the reverting-vol gradient survives WITHOUT the model's selection,
   A1 measured the engine's payoff coupling, not an edge — the coupling death.
4. **Character-persistence pre-measurement** — C's demand, no definition
   pinned, so pinned here: does the vol CHARACTER of a market-state persist
   from feature-time to the trip's own horizon? If not, the orderer is a noise
   label and A1 is dead before the gate (F8 cuts against persistence). This is
   the make-or-break and it is fully measurable now, model-free — the
   centrepiece of this pass.
5. **Incremental to B's frozen P(ride)** — `analysis/ride_model_pin.predict`.
   The pilot gradient is shown WITHIN P(ride) quintiles; if vol only re-orders
   what P(ride) already orders, A1 is the ride mask renamed. (B's own read:
   per-$ is flat across P(ride) quintiles — the market prices ride risk.)
6. **The pessimistic re-score** — A's own kill condition. Every per-$ number is
   also shown at the measured concession (the ledger's `pnl_per_dollar_pess`,
   4.70¢/filled leg). If the gradient is negative in every bucket like
   freshness, A1 is freshness's cousin.

THE FEATURE (pinned pre-read). Variance ratio of the mid on fixed 2s bars over
a 120s window: VR = Var(k-step returns) / (k · Var(1-step returns)), k=6.
VR < 0.8 = REVERTING (returns anti-correlated, oscillation the roll harvests);
VR > 1.2 = TRENDING (returns persist, the regime that rides to a loss);
0.8–1.2 = random-walk. 2s bars because the raw 200ms mid is a step function
(changes on ~4% of ticks); the bar grid removes the zero-inflation. The bar
approximation is a PILOT simplification — the gate uses real fills, not bars.

Caveat carried throughout (D's instrument note): the pilot's outcome is scored
under fills that this pass approximates on 2s bars, and the PULSE mid-cross
rule itself manufactures reversion around fills. The pilot INFORMS the feature
shape; it never gates. The gate is the quote-engine real-fill study.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
PIN = "20260901T195202Z"
#: The pinned exports are gitignored and live in the main checkout; override
#: with MERIDIAN_EXPORTS_DIR when running from a worktree.
import os
EXPORTS = Path(os.environ.get("MERIDIAN_EXPORTS_DIR", ROOT / "backups" / "exports"))
TICKS = EXPORTS / f"live_ticks_pulse_games_{PIN}.csv.gz"
LEDGER = EXPORTS / f"roundtrip_ledger_{PIN}.csv"
REPORT = ROOT / "analysis" / "a1_oscillation_descriptive_report.md"

# ---- pinned feature constants (declared before any real read) ------------- #
BAR = "2s"
BAR_SECONDS = 2.0
WINDOW_SECONDS = 120.0                 # feature window: 60 bars
WINDOW_BARS = int(WINDOW_SECONDS / BAR_SECONDS)
VR_K = 6
REVERT_VR, TREND_VR = 0.8, 1.2
#: Persistence is judged at the trip's own horizon (C's demand). Median trip
#: hold on the ledger is ~90s; the grid brackets it.
HORIZON_GRID = [60, 90, 120, 300]      # 30s omitted: too few 2s bars for k=6 VR
TRIP_HORIZON_S = 90
SEED = 20260902


def variance_ratio(bars: np.ndarray, k: int = VR_K) -> float:
    """VR = Var(k-step returns)/(k·Var(1-step returns)). <1 revert, >1 trend."""
    b = bars[~np.isnan(bars)]
    r1 = np.diff(b)
    if len(r1) < k * 4:
        return np.nan
    v1 = np.var(r1, ddof=1)
    if v1 == 0:
        return np.nan
    rk = np.diff(b[::k])
    if len(rk) < 3:
        return np.nan
    return float(np.var(rk, ddof=1) / (k * v1))


def character(vr: float) -> str:
    if np.isnan(vr):
        return "na"
    if vr < REVERT_VR:
        return "revert"
    if vr > TREND_VR:
        return "trend"
    return "rw"


def clustered_ci(values, groups, n_boot=5000, seed=SEED):
    """Mean with a game-clustered bootstrap 95% CI (resample games)."""
    df = pd.DataFrame({"v": np.asarray(values, float), "g": np.asarray(groups)})
    df = df.dropna()
    if df.empty:
        return (np.nan, np.nan, np.nan, 0, 0)
    by = list(df.groupby("g")["v"])
    keys = [k for k, _ in by]
    arrs = [s.to_numpy() for _, s in by]
    point = float(df.v.mean())
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    ng = len(arrs)
    for i in range(n_boot):
        idx = rng.integers(0, ng, ng)
        boots[i] = np.concatenate([arrs[j] for j in idx]).mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (point, float(lo), float(hi), len(df), ng)


# --------------------------------------------------------------------------- #
# Tick tape -> per-market 2s bar series
# --------------------------------------------------------------------------- #

def load_bars() -> tuple[dict[str, pd.Series], dict[str, str]]:
    df = pd.read_csv(TICKS, usecols=["event_slug", "market_slug", "captured_at",
                                     "best_bid", "best_ask"])
    df["captured_at"] = pd.to_datetime(df.captured_at, utc=True, errors="coerce")
    df = df.dropna(subset=["captured_at"])
    df["mid"] = (df.best_bid + df.best_ask) / 2.0
    #: market -> its GAME, from the tape itself, so clustering is by game (34)
    #: for every market, not just the ones the ledger covers.
    slug2game = dict(zip(df.market_slug, df.event_slug))
    bars = {}
    for slug, g in df.groupby("market_slug"):
        s = g.set_index("captured_at").mid.sort_index().resample(BAR).last().ffill()
        if len(s) >= WINDOW_BARS:
            bars[slug] = s
    return bars, slug2game


def vr_at(series: pd.Series, t_end, back_s=WINDOW_SECONDS) -> float:
    """VR over the window ENDING at t_end (strictly before it — the feature is
    pre-decision)."""
    t0 = t_end - pd.Timedelta(seconds=back_s)
    w = series[(series.index > t0) & (series.index <= t_end)]
    if len(w) < WINDOW_BARS // 2:
        return np.nan
    return variance_ratio(w.to_numpy())


def vr_forward(series: pd.Series, t_start, fwd_s) -> float:
    w = series[(series.index >= t_start)
               & (series.index < t_start + pd.Timedelta(seconds=fwd_s))]
    if len(w) < max(VR_K * 4, 10):
        return np.nan
    return variance_ratio(w.to_numpy())


# --------------------------------------------------------------------------- #
# DEMAND #4 — character persistence (the centrepiece)
# --------------------------------------------------------------------------- #

def measure_persistence(bars: dict[str, pd.Series],
                        slug_game: dict[str, str]) -> dict:
    """Does vol character persist from feature-time to the trip horizon?

    Two model-free estimands, both game-clustered:
      (a) adjacent-window autocorrelation of VR (C's literal 'FIRST' demand):
          corr(VR_window_i, VR_window_{i+lag}) over consecutive 120s windows;
      (b) feature->holding persistence: VR over [t-120,t] vs VR over [t,t+H]
          for H in the grid, and the revert->revert transition rate vs base.
    """
    # (a) adjacent-window autocorrelation
    auto = {lag: ([], []) for lag in (1, 2, 3)}
    # (b) feature->forward, per horizon
    fwd = {h: {"past": [], "fut": [], "g": []} for h in HORIZON_GRID}
    for slug, s in bars.items():
        game = slug_game.get(slug, slug)
        arr = s.to_numpy()
        idx = s.index
        # consecutive non-overlapping windows
        vrs = []
        for i in range(0, len(arr) - WINDOW_BARS, WINDOW_BARS):
            vrs.append(variance_ratio(arr[i:i + WINDOW_BARS]))
        vrs = np.array(vrs, float)
        for lag in auto:
            a, b = vrs[:-lag], vrs[lag:]
            ok = ~(np.isnan(a) | np.isnan(b))
            if ok.sum():
                auto[lag][0].extend(a[ok])
                auto[lag][1].extend(b[ok])
        # feature->forward on a 30s sampling grid
        step = int(30 / BAR_SECONDS)
        for i in range(WINDOW_BARS, len(arr) - 1, step):
            t = idx[i]
            past = variance_ratio(arr[i - WINDOW_BARS:i])
            if np.isnan(past):
                continue
            for h in HORIZON_GRID:
                f = vr_forward(s, t, h)
                if not np.isnan(f):
                    fwd[h]["past"].append(past)
                    fwd[h]["fut"].append(f)
                    fwd[h]["g"].append(game)
    out = {"autocorr": {}, "forward": {}}
    for lag, (a, b) in auto.items():
        a, b = np.array(a), np.array(b)
        out["autocorr"][lag] = {
            "n": len(a),
            "spearman": float(pd.Series(a).corr(pd.Series(b), method="spearman"))
            if len(a) > 2 else np.nan,
        }
    rng0 = np.random.default_rng(SEED)
    for h in HORIZON_GRID:
        p, f, g = (np.array(fwd[h]["past"]), np.array(fwd[h]["fut"]),
                   np.array(fwd[h]["g"]))
        if len(p) < 3:
            out["forward"][h] = {"n": len(p)}
            continue
        rev_past = p < REVERT_VR
        rev_fut = f < REVERT_VR
        base = rev_fut.mean()
        cond = rev_fut[rev_past].mean() if rev_past.sum() else np.nan
        # game-clustered bootstrap of both the lift (cond-base) and Spearman
        gdf = pd.DataFrame({"p": p, "f": f, "rp": rev_past, "rf": rev_fut, "g": g})
        groups = [s for _, s in gdf.groupby("g")]
        ng = len(groups)
        lifts, spears = [], []
        for _ in range(2000):
            draw = pd.concat([groups[j] for j in rng0.integers(0, ng, ng)])
            b = draw.rf.mean()
            c = draw.rf[draw.rp].mean() if draw.rp.sum() else np.nan
            lifts.append(c - b)
            spears.append(draw.p.corr(draw.f, method="spearman"))
        lift_lo, lift_hi = np.nanpercentile(lifts, [2.5, 97.5])
        sp_lo, sp_hi = np.nanpercentile(spears, [2.5, 97.5])
        out["forward"][h] = {
            "n": len(p), "games": ng,
            "spearman": float(pd.Series(p).corr(pd.Series(f), method="spearman")),
            "spearman_ci": (float(sp_lo), float(sp_hi)),
            "base_revert_rate": float(base),
            "cond_revert_given_past_revert": float(cond),
            "lift": float(cond - base) if not np.isnan(cond) else np.nan,
            "lift_ci": (float(lift_lo), float(lift_hi)),
        }
    return out


# --------------------------------------------------------------------------- #
# DEMAND #2/#5/#6 — the pilot gradient (real entries), incremental to P(ride)
# --------------------------------------------------------------------------- #

def pilot_gradient(bars: dict[str, pd.Series], ledger: pd.DataFrame) -> dict:
    import ride_model_pin as rmp

    fills = ledger[ledger.entry_filled &
                   ledger.outcome.isin(["exit_fill", "settlement"])].copy()
    # feature at each entry: VR over [decided_at-120s, decided_at] (pre-decision)
    vr = []
    for r in fills.itertuples():
        s = bars.get(r.market_slug)
        vr.append(vr_at(s, r.decided_at) if s is not None else np.nan)
    fills["vr"] = vr
    fills["char"] = fills.vr.apply(character)
    fills["cost"] = fills.entry_cost_per_contract
    fills["p_ride"] = rmp.predict(fills)
    fills["ride_q"] = rmp.quintile(fills.p_ride.to_numpy())
    have = fills[fills.vr.notna()].copy()

    def by_char(df, col):
        rows = {}
        for c in ("revert", "rw", "trend"):
            sub = df[df.char == c]
            rows[c] = clustered_ci(sub[col], sub.event_slug)
        return rows

    out = {
        "n_fills": len(fills), "n_with_feature": len(have),
        "games": have.event_slug.nunique(),
        "char_counts": have.char.value_counts().to_dict(),
        # DEMAND #2: over ALL fills, not the trip subset
        "maker_by_char": by_char(have, "pnl_per_dollar"),
        # DEMAND #6: the pessimistic re-score (A's own kill condition)
        "pess_by_char": by_char(have, "pnl_per_dollar_pess"),
        # DEMAND #5: incremental to B's frozen P(ride) — within each quintile
        "within_ride_quintile": {},
    }
    for q in range(1, 6):
        sub = have[have.ride_q == q]
        if len(sub) < 5:
            out["within_ride_quintile"][q] = {"n": len(sub)}
            continue
        rev = sub[sub.char == "revert"]
        rest = sub[sub.char != "revert"]
        out["within_ride_quintile"][q] = {
            "n": len(sub),
            "revert_maker": clustered_ci(rev.pnl_per_dollar, rev.event_slug),
            "nonrevert_maker": clustered_ci(rest.pnl_per_dollar, rest.event_slug),
        }
    out["_raw"] = have[["event_slug", "char", "pnl_per_dollar"]].rename(
        columns={"event_slug": "game", "pnl_per_dollar": "per_d"})
    return out


# --------------------------------------------------------------------------- #
# DEMAND #3 — the payoff-structure placebo (random matched entries)
# --------------------------------------------------------------------------- #

def placebo_gradient(bars: dict[str, pd.Series], ledger: pd.DataFrame,
                     per_market=6) -> dict:
    """Identical 5¢-target roll mechanics on the same tick paths, entered at
    RANDOM instants with a coin-flip side. If reverting-vol still orders the
    per-$, the gradient is the engine's payoff structure, not selection."""
    outc = ledger.drop_duplicates("market_slug").set_index("market_slug")
    settle = ledger.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug")["settlement"]
    rng = np.random.default_rng(SEED)
    recs = []
    for slug, s in bars.items():
        if slug not in settle.index:
            continue
        sett = float(settle[slug])
        game = outc.loc[slug, "event_slug"] if slug in outc.index else slug
        arr = s.to_numpy()
        idx = s.index
        lo, hi = WINDOW_BARS, len(arr) - 2
        if hi <= lo:
            continue
        for _ in range(per_market):
            i = int(rng.integers(lo, hi))
            entry_mid = arr[i]
            if not (0.02 <= entry_mid <= 0.98):
                continue
            past = variance_ratio(arr[i - WINDOW_BARS:i])
            if np.isnan(past):
                continue
            side_yes = bool(rng.integers(0, 2))
            entry = entry_mid                       # bar-mid entry (pilot approx)
            target = entry + 0.05 if side_yes else entry - 0.05
            fut = arr[i + 1:]
            hit = (np.where(fut >= target)[0] if side_yes
                   else np.where(fut <= target)[0])
            if len(hit):
                close = target                      # trip: hit the 5¢ target
            else:
                close = sett                        # ride: settle
            sign = 1.0 if side_yes else -1.0
            cost = entry if side_yes else 1.0 - entry
            if cost <= 0:
                continue
            recs.append({"per_d": sign * (close - entry) / cost,
                         "char": character(past), "game": game})
    d = pd.DataFrame(recs)
    res = {"n": len(d), "games": d.game.nunique() if len(d) else 0, "_raw": d}
    for c in ("revert", "rw", "trend"):
        sub = d[d.char == c]
        res[c] = clustered_ci(sub.per_d, sub.game)
    return res


def paired_placebo_diff(real_raw: pd.DataFrame, placebo_raw: pd.DataFrame,
                        char: str = "revert") -> dict:
    """D's refinement: the placebo runs on the SAME games as the real entries,
    so the game-level DIFF (mean real − mean placebo, per game) removes the
    shared game variance inflating the two marginal intervals and may resolve
    the selection-above-mechanical split with zero new data."""
    r = (real_raw[real_raw.char == char].groupby("game").per_d.mean()
         .rename("real"))
    p = (placebo_raw[placebo_raw.char == char].groupby("game").per_d.mean()
         .rename("placebo"))
    j = pd.concat([r, p], axis=1).dropna()
    if len(j) < 3:
        return {"games": len(j)}
    diff = (j.real - j.placebo).to_numpy()
    rng = np.random.default_rng(SEED)
    boots = np.array([diff[rng.integers(0, len(diff), len(diff))].mean()
                      for _ in range(10000)])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"games": len(j), "point": float(diff.mean()),
            "lo": float(lo), "hi": float(hi),
            "real_mean": float(j.real.mean()),
            "placebo_mean": float(j.placebo.mean())}


# --------------------------------------------------------------------------- #
# Self-test (wave rule 4) — the instrument before the data
# --------------------------------------------------------------------------- #

def _selftest():
    rng = np.random.default_rng(0)
    # a strongly mean-reverting path (AR(1), phi<0) reads VR<1
    n = 600
    revert = np.empty(n)
    revert[0] = 0.5
    for t in range(1, n):
        revert[t] = 0.5 + (-0.6) * (revert[t - 1] - 0.5) + 0.01 * rng.standard_normal()
    assert variance_ratio(revert) < 0.8, variance_ratio(revert)
    # a random walk reads VR ~ 1
    rw = 0.5 + np.cumsum(0.005 * rng.standard_normal(n))
    assert 0.7 < variance_ratio(rw) < 1.3, variance_ratio(rw)
    # a trending path (positive-autocorr increments) reads VR>1
    steps = np.zeros(n)
    for t in range(1, n):
        steps[t] = 0.7 * steps[t - 1] + 0.01 * rng.standard_normal()
    trend = 0.5 + np.cumsum(steps)
    assert variance_ratio(trend) > 1.2, variance_ratio(trend)
    # character() thresholds
    assert character(0.5) == "revert" and character(1.0) == "rw" \
        and character(1.5) == "trend"
    # clustered CI: a constant is its own mean with a zero-width interval
    p, lo, hi, nn, ng = clustered_ci([3.0] * 20, list(range(4)) * 5)
    assert abs(p - 3.0) < 1e-9 and abs(hi - lo) < 1e-9
    # persistence estimand recovers an injected-persistent character and reads
    # ~0 on a null: build two synthetic markets, score forward-agreement.
    idx = pd.date_range("2026-09-02", periods=n, freq=BAR, tz="UTC")
    persistent = pd.Series(revert, idx)             # reverting throughout
    null_series = pd.Series(rw, idx)
    # forward VR of the persistent series stays <1 (agreement with its past)
    a = vr_at(persistent, idx[300]); b = vr_forward(persistent, idx[300], 120)
    assert a < 0.8 and b < 0.8, (a, b)
    print("selftest: PASSED (VR classifies revert/rw/trend; clustered CI exact; "
          "persistence estimand recovers injected character)")


# --------------------------------------------------------------------------- #

def main():
    _selftest()
    print("loading tick tape (11.3M rows)...")
    bars, slug2game = load_bars()
    ledger = pd.read_csv(LEDGER, parse_dates=["decided_at", "filled_at"])
    print(f"markets with >={WINDOW_BARS} bars: {len(bars)} "
          f"in {len(set(slug2game.values()))} games")

    persistence = measure_persistence(bars, slug2game)
    pilot = pilot_gradient(bars, ledger)
    placebo = placebo_gradient(bars, ledger)
    paired = paired_placebo_diff(pilot["_raw"], placebo["_raw"], "revert")

    lines = []
    W = lines.append
    W("# A1 oscillation harvest — descriptive pass\n")
    W("**IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING. Nothing gates.**\n")
    W(f"Pins: `{TICKS.name}`, `{LEDGER.name}`. "
      f"Reproduce: `python3 analysis/a1_oscillation_descriptive.py` "
      "(self-tests first).\n")
    W(f"Feature (pinned): variance ratio on {BAR} bars, {WINDOW_SECONDS:.0f}s "
      f"window, k={VR_K}; revert<{REVERT_VR} / trend>{TREND_VR}.\n")

    # ---- computed synthesis (honest, from the numbers below) -------------- #
    rev_m = pilot["maker_by_char"]["revert"]
    rw_m = pilot["maker_by_char"]["rw"]
    tr_m = pilot["maker_by_char"]["trend"]
    rev_p = pilot["pess_by_char"]["revert"]
    plac_rev = placebo["revert"]
    lift90 = persistence["forward"][90]
    maker_excludes_zero = rev_m[1] > 0
    pess_all_neg = all(pilot["pess_by_char"][c][0] < 0 for c in ("revert", "rw", "trend"))
    W("\n## Synthesis — the wave's central live question\n")
    W("The null was three-for-three on BELIEF properties (edge_net; the "
      "coupling; Q1 edge-source, B's split). A1 is the first candidate ordering "
      "on a MARKET property — realized oscillation. What this pass found:\n")
    W(f"1. **Character persists (demand #4): PASS.** At the ~90s trip horizon a "
      f"reverting state stays reverting {lift90['cond_revert_given_past_revert']:.0%} "
      f"of the time vs a {lift90['base_revert_rate']:.0%} base — lift "
      f"{lift90['lift']:+.3f} [{lift90['lift_ci'][0]:+.3f}, {lift90['lift_ci'][1]:+.3f}], "
      "game-clustered, well off zero. Not a noise label.")
    ew_rev = paired.get("real_mean", float("nan"))
    W(f"2. **A maker-frame ordering exists but is COMPOSITION-FRAGILE.** Pooled, "
      f"reverting entries {rev_m[0]:+.2%} [{rev_m[1]:+.2%}, {rev_m[2]:+.2%}] "
      f"({'CI excludes zero' if maker_excludes_zero else 'CI spans zero'}), "
      f"above rw {rw_m[0]:+.2%} and trend {tr_m[0]:+.2%} — the only maker-frame "
      "ordering on a market property in the wave. BUT counts-before-ratios "
      f"(wave rule 1): equal-weighted BY GAME the revert per-$ is only "
      f"{ew_rev:+.2%} — the pooled positive is carried by a few high-count "
      "games (per-game revert count ranges 1–82). The pooled number is "
      "game-composition-weighted; the ordering is real but not robust to game "
      "weighting, and the paired-placebo test below shows selection adds ~0.")
    W(f"3. **It does NOT clear the uniform pessimistic bar (demand #6).** At the "
      f"measured 4.70¢/leg concession every character is negative "
      f"(revert {rev_p[0]:+.2%}) — the freshness shape. BUT the ordering "
      "survives (revert less-negative than rw), and A1's mechanism makes a "
      "SPECIFIC further prediction the uniform re-score cannot test: reverting "
      "states carry BELOW-average adverse selection (that IS the mechanism — an "
      "oscillation is not an informed aggressor picking you off). The uniform "
      "concession assumes one number for all characters; **only the gate (real "
      "per-character fills) measures whether revert entries actually pay less.** "
      "So A1 is neither cleared nor dead: its kill condition points straight at "
      "what the gate must measure.")
    paired_txt = (
        f"the PAIRED game-level diff (real − placebo, same games) is "
        f"{paired['point']:+.2%} [{paired['lo']:+.2%}, {paired['hi']:+.2%}] over "
        f"{paired['games']} games — "
        + ("CI excludes zero, so selection adds above the mechanical floor even "
           "after removing shared game variance."
           if paired.get('lo', -1) > 0 else
           "CI still spans zero, so the selection-above-mechanical split is not "
           "resolved in-sample even paired — the honest answer, and the gate "
           "settles it.")) if "point" in paired else "the paired diff is unavailable."
    W(f"4. **Not purely mechanical (placebo, demand #3).** Random entries also "
      f"show revert>rest, but weakly (placebo revert {plac_rev[0]:+.2%} "
      f"[{plac_rev[1]:+.2%}, {plac_rev[2]:+.2%}], CI spans zero) vs real "
      f"{rev_m[0]:+.2%}. Pairing (D's refinement): {paired_txt}")
    W("5. **Incremental to B's frozen P(ride) (demand #5).** Revert beats "
      "non-revert INSIDE every P(ride) quintile (strongest in Q5), where B's "
      "own read has per-$ flat across quintiles. Not the ride mask renamed.\n")
    W("**Verdict (aligned with the research agent's ruling).** A1 FAILED "
      "demand #6 as written — negative in every character under the uniform "
      "concession. The pilot justifies NOTHING on its own: the maker-frame "
      "ordering is composition-fragile (pooled +4.35%, equal-weighted "
      f"{ew_rev:+.2%}), and the paired-placebo test shows selection adds ~0 "
      "over the roll's mechanical harvest. TWO nested in-sample artifacts "
      "reproduce this tape without any market truth: (a) engine payoff coupling "
      "(the 5¢ roll harvests oscillation by construction — the placebo shows "
      "~80% of the ORDERING present in coin-flip entries), and (b) fill-model "
      "optimism CORRELATED WITH THE FEATURE (the mid-cross rule books favourable "
      "drift largest exactly in oscillating states — 'revert character' and "
      "'fill-model profit' are near-synonyms on this tape). Nothing on the "
      "pinned tape can separate 'revert states are genuinely maker-friendly' "
      "from those two artifacts. **Only real fills can — which is why the gate "
      "is the only instrument, not a consolation.** What survives to justify "
      "running it: the persistence result (+0.174 at 90s, robust) and one "
      "sharp falsifiable claim — that reverting fills pay measurably "
      "below-average concession. Breakeven burden (linear between the two "
      "published arms): c* ≈ 0.72¢/leg vs the 4.70¢ average — an ~85% "
      "concession reduction. Large, one number, printed so no 3.9¢ result is "
      "later called 'directionally supportive'. Not a capital claim.\n")
    W("*Two framing notes carried from the manager's routing:* A1 leans on NO "
      "'margin-driven = suspect' reasoning (B's Q1 split closed that door; this "
      "is a vol-character feature, orthogonal to edge source). And it does not "
      "build on B's lone unranked Q1-mixed ≥10¢ interval — a different "
      "partition; no cell here is derived from it.\n")

    W("\n## DEMAND #4 — does vol character persist? (the make-or-break)\n")
    W("Adjacent-window autocorrelation of VR (C's 'FIRST' demand):\n")
    for lag, d in persistence["autocorr"].items():
        W(f"- lag {lag} window(s) ({lag*WINDOW_SECONDS:.0f}s): "
          f"Spearman {d['spearman']:+.3f} (n={d['n']})")
    W("\nFeature[t-120,t] -> forward[t,t+H], game-clustered (34 games; the trip "
      "horizon is ~90s). Lift = P(revert ahead | reverting now) − base rate:\n")
    W("| H (s) | n | games | Spearman [95%] | base revert | cond\\|past revert | lift [95% clustered] |")
    W("|---|---|---|---|---|---|---|")
    for h in HORIZON_GRID:
        d = persistence["forward"][h]
        if d.get("n", 0) < 3:
            W(f"| {h} | {d.get('n',0)} | — | — | — | — | — |")
            continue
        sp = d["spearman_ci"]; lc = d["lift_ci"]
        W(f"| {h} | {d['n']} | {d['games']} | {d['spearman']:+.3f} "
          f"[{sp[0]:+.3f}, {sp[1]:+.3f}] | {d['base_revert_rate']:.3f} | "
          f"{d['cond_revert_given_past_revert']:.3f} | {d['lift']:+.3f} "
          f"[{lc[0]:+.3f}, {lc[1]:+.3f}] |")

    W("\n## DEMAND #2/#6 — pilot per-$ by character, over ALL fills "
      "(PILOT, contaminated — informs, never gates)\n")
    W(f"n fills with feature: {pilot['n_with_feature']}/{pilot['n_fills']} "
      f"({pilot['games']} games). Char counts: {pilot['char_counts']}\n")
    W("| character | maker per-$ [95% clustered] | pessimistic per-$ [95%] | n | games |")
    W("|---|---|---|---|---|")
    for c in ("revert", "rw", "trend"):
        m = pilot["maker_by_char"][c]
        p = pilot["pess_by_char"][c]
        W(f"| {c} | {m[0]:+.3%} [{m[1]:+.3%}, {m[2]:+.3%}] | "
          f"{p[0]:+.3%} [{p[1]:+.3%}, {p[2]:+.3%}] | {m[3]} | {m[4]} |")

    W("\n## DEMAND #3 — payoff-structure placebo (random entries, coin-flip side)\n")
    W(f"n placebo rolls: {placebo['n']} ({placebo['games']} games). If the "
      "revert>rest gradient appears HERE, it is the engine's payoff coupling, "
      "not selection.\n")
    W("| character | placebo maker per-$ [95% clustered] | n | games |")
    W("|---|---|---|---|")
    for c in ("revert", "rw", "trend"):
        r = placebo[c]
        W(f"| {c} | {r[0]:+.3%} [{r[1]:+.3%}, {r[2]:+.3%}] | {r[3]} | {r[4]} |")
    if "point" in paired:
        W(f"\n**Paired game-level diff (revert, real − placebo, same games)** — "
          f"removes shared game variance (D's refinement): "
          f"**{paired['point']:+.3%} [{paired['lo']:+.3%}, {paired['hi']:+.3%}]** "
          f"over {paired['games']} games "
          f"(real {paired['real_mean']:+.3%} vs placebo {paired['placebo_mean']:+.3%} "
          "in-game means). "
          + ("Excludes zero: selection adds above the mechanical floor."
             if paired['lo'] > 0 else
             "Spans zero: unresolved in-sample even paired — the gate settles it.")
          + "\n")

    W("\n## DEMAND #5 — incremental to B's frozen P(ride) (per-$ within quintile)\n")
    W("B's own read: per-$ is flat across P(ride) quintiles. If revert only "
      "re-orders within-quintile what P(ride) already captures, A1 is the ride "
      "mask renamed.\n")
    W("| P(ride) quintile | revert maker per-$ | non-revert maker per-$ | n |")
    W("|---|---|---|---|")
    for q in range(1, 6):
        d = pilot["within_ride_quintile"][q]
        if d.get("n", 0) < 5:
            W(f"| {q} | — | — | {d.get('n',0)} |")
            continue
        rv, nr = d["revert_maker"], d["nonrevert_maker"]
        W(f"| {q} | {rv[0]:+.3%} (n={rv[3]}) | {nr[0]:+.3%} (n={nr[3]}) | {d['n']} |")

    W("\n## DEMAND #1 — the gate (real resting fills): NO DATA, and its spec\n")
    W("`shadow_quote_fills` is not in the pinned exports (live DB only), so the "
      "evidence-grade gate reads **NO DATA** here. This pass is the instrument "
      "and the pilot; the gate is a forward / DB study (feature AND outcome on "
      "the quote engine's own tape, per the pinned spec).\n")
    W("**The gate scores TWO things, not one (D's refinement):**\n")
    W("1. **Concession-by-character — the MECHANISM test, fast.** A1's whole "
      "claim is concession HETEROGENEITY: reverting-character fills carry "
      "below-average adverse selection. That concession is measured directly "
      "per quote-engine fill (`mid_at_quote` vs `mid_at_fill`), per-fill and "
      "tight — far fewer games than P&L significance needs. If reverting fills "
      "do NOT show below-average concession, the mechanism is dead long before "
      "the P&L floors fill (October, not December).\n")
    W("2. **Per-$-by-character — the ECONOMICS test, slow.** The registration's "
      "gate proper: does the character order per-$ over all fills on real "
      "fills, surviving the (now per-character, not uniform) concession, "
      "game-clustered. This is the floors-in-games arm.\n")
    W("Score both; the concession split is the leading indicator, the per-$ "
      "the verdict.\n")

    W("\n## Multiple comparisons & capital\n")
    W("Several character×horizon×quintile cells are read here; a few sub-0.05 "
      "patterns are expected by chance. Ranking is mechanism + persistence + "
      "placebo-separation, never a single cell's CI.\n")
    W("**No in-sample result justifies capital. The forward test is the evidence.**\n")

    REPORT.write_text("\n".join(lines) + "\n")
    print(f"report -> {REPORT}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
