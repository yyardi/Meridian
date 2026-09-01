"""Track C — is PULSE's fair_value calibrated, and if not, where does it break?

Runs entirely off the wave's pinned exports (never a live database):

    backups/exports/pulse_decisions_full_20260901T195202Z.csv
    backups/exports/resolved_outcomes_20260901T195202Z.csv

Reproduce:

    .venv/bin/python analysis/fv_calibration.py --selftest   # mutation-test the instrument
    .venv/bin/python analysis/fv_calibration.py              # the analysis

Frames, verified by assertion on every run (not assumed):
  - fair_value and market_bid/market_ask are always YES-frame, whatever `side` says
    (no-side entries satisfy edge_net == market_ask - fair_value exactly).
  - settlement is the MARKET's YES outcome: totals YES = over, spread YES =
    first-named margin + line > 0, winner YES = first-named team wins.

Sample-size discipline: n is reported in GAMES and in rows, every interval is
game-clustered (core.quote.adverse_selection.clustered_mean or a by-game
bootstrap). Hold rows arrive on a ~60s per-market cadence and neighbouring rows
are nearly the same observation; a 1-per-market-per-5-game-minutes resample is
run as sensitivity on every headline number.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.quote.adverse_selection import clustered_mean  # one copy to be right

DECISIONS_PIN = "backups/exports/pulse_decisions_full_20260901T195202Z.csv"
OUTCOMES_PIN = "backups/exports/resolved_outcomes_20260901T195202Z.csv"
BINS = np.linspace(0.0, 1.0, 11)  # ten fixed-width probability bins
BOOT = 2000
RNG_SEED = 20260901

CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


# ---------------------------------------------------------------- instruments


def murphy(p: np.ndarray, y: np.ndarray, bins: np.ndarray = BINS) -> dict:
    """Murphy decomposition: Brier = UNC - RES + REL, with fixed-width bins.

    REL (reliability): how far each bin's forecast sits from its realized rate —
    zero for a calibrated forecaster; fixable by recalibration.
    RES (resolution): how far the bins' realized rates spread from the base
    rate — a forecaster with no information has zero; NOT fixable by
    recalibration.
    """
    idx = np.clip(np.digitize(p, bins) - 1, 0, len(bins) - 2)
    ybar = y.mean()
    rel = res = 0.0
    n = len(p)
    for b in range(len(bins) - 1):
        m = idx == b
        nb = int(m.sum())
        if nb == 0:
            continue
        pb, yb = p[m].mean(), y[m].mean()
        rel += nb / n * (pb - yb) ** 2
        res += nb / n * (yb - ybar) ** 2
    unc = ybar * (1 - ybar)
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "unc": float(unc),
        "res": float(res),
        "rel": float(rel),
        # binned identity: brier_binned = unc - res + rel; the residual vs the
        # raw brier is within-bin variance of p and is reported, not hidden
        "within_bin": float(np.mean((p - y) ** 2) - (unc - res + rel)),
    }


def reliability_table(df: pd.DataFrame, col: str, bins: np.ndarray = BINS) -> pd.DataFrame:
    """Per-bin forecast vs realized, with a game-clustered CI on realized."""
    idx = np.clip(np.digitize(df[col].to_numpy(), bins) - 1, 0, len(bins) - 2)
    rows = []
    for b in range(len(bins) - 1):
        sub = df[idx == b]
        if len(sub) == 0:
            continue
        by_game = {g: v["y"].tolist() for g, v in sub.groupby("game_id")}
        cm = clustered_mean(by_game)
        rows.append(
            {
                "bin": f"[{bins[b]:.1f},{bins[b + 1]:.1f})",
                "forecast": sub[col].mean(),
                "realized": sub["y"].mean(),
                "lo": cm.lo if cm else np.nan,
                "hi": cm.hi if cm else np.nan,
                "rows": len(sub),
                "games": sub["game_id"].nunique(),
            }
        )
    return pd.DataFrame(rows)


def paired_diff(df: pd.DataFrame, a: str, b: str) -> dict:
    """Game-clustered mean of per-row Brier(a) - Brier(b). Negative: a better."""
    d = (df[a] - df["y"]) ** 2 - (df[b] - df["y"]) ** 2
    by_game = {g: v.tolist() for g, v in d.groupby(df["game_id"])}
    cm = clustered_mean(by_game)
    if cm is None:
        return {"mean": float(d.mean()), "lo": np.nan, "hi": np.nan, "rows": len(d), "games": df["game_id"].nunique()}
    return {"mean": cm.mean, "lo": cm.lo, "hi": cm.hi, "rows": cm.n, "games": cm.n_clusters}


def boot_by_game(df: pd.DataFrame, stat_fn, n_boot: int = BOOT, seed: int = RNG_SEED) -> tuple[float, float, float]:
    """Percentile CI for stat_fn(df) under a resample-games-with-replacement bootstrap."""
    rng = np.random.default_rng(seed)
    games = df["game_id"].unique()
    groups = dict(tuple(df.groupby("game_id")))
    point = stat_fn(df)
    draws = []
    for _ in range(n_boot):
        pick = rng.choice(games, size=len(games), replace=True)
        boot = pd.concat([groups[g] for g in pick], ignore_index=True)
        draws.append(stat_fn(boot))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return point, float(lo), float(hi)


def pava(p: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Isotonic regression of y on p (pool-adjacent-violators). Returns the
    breakpoints (unique sorted p) and fitted values, for stepwise interpolation."""
    order = np.argsort(p, kind="stable")
    ps, ys = p[order], y[order].astype(float)
    # pool ties on p first so the fit is a function of p
    up, inv = np.unique(ps, return_inverse=True)
    w = np.bincount(inv).astype(float)
    g = np.bincount(inv, weights=ys) / w
    vals, wts = list(g), list(w)
    blocks = [[i] for i in range(len(g))]
    i = 0
    while i < len(vals) - 1:
        if vals[i] > vals[i + 1] + 1e-12:
            tot = wts[i] + wts[i + 1]
            vals[i] = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / tot
            wts[i] = tot
            blocks[i] += blocks[i + 1]
            del vals[i + 1], wts[i + 1], blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    fitted = np.empty(len(up))
    for v, blk in zip(vals, blocks):
        fitted[blk] = v
    return up, fitted


def iso_predict(bp: np.ndarray, fv: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Stepwise-linear interpolation of the isotonic fit, clamped to [0,1]."""
    return np.clip(np.interp(p, bp, fv), 0.0, 1.0)


def logo_recalibrated(df: pd.DataFrame, col: str = "fv") -> np.ndarray:
    """Leave-one-GAME-out isotonic recalibration of `col` against y.

    The held-out game never contributes to its own mapping, so the result is
    the honest in-window ceiling for what a monotone recalibration could do.
    """
    out = np.full(len(df), np.nan)
    for g in df["game_id"].unique():
        tr = df[df["game_id"] != g]
        te_mask = (df["game_id"] == g).to_numpy()
        bp, fitted = pava(tr[col].to_numpy(), tr["y"].to_numpy())
        out[te_mask] = iso_predict(bp, fitted, df.loc[te_mask, col].to_numpy())
    return out


# ---------------------------------------------------------------- self-test


def selftest() -> None:
    """Mutation-test the instruments on synthetic data before any real data.

    1. A perfectly calibrated forecaster must read REL ~ 0.
    2. An injected overconfidence must be recovered in size and direction.
    3. An uninformative-but-calibrated forecaster must read RES ~ 0, REL ~ 0.
    4. The paired head-to-head must find a known better forecaster, with a
       clustered CI that excludes zero.
    5. PAVA must reproduce a known monotone mapping and never decrease.
    """
    rng = np.random.default_rng(7)
    n_games, rows_per_game = 200, 60
    game = np.repeat(np.arange(n_games), rows_per_game)
    p_true = rng.uniform(0.02, 0.98, n_games * rows_per_game)
    # outcome is per GAME-ish here; for the instrument test independence is fine
    y = (rng.uniform(size=len(p_true)) < p_true).astype(float)

    ok = True

    m = murphy(p_true, y)
    print(f"[1] calibrated series: REL={m['rel']:.5f} (want ~0), RES={m['res']:.4f}, UNC={m['unc']:.4f}")
    ok &= m["rel"] < 0.002

    # overconfidence: report probabilities stretched away from 0.5
    stretch = np.clip(0.5 + 1.6 * (p_true - 0.5), 0.001, 0.999)
    m2 = murphy(stretch, y)
    # expected REL for this stretch: E[(stretch - p_true)^2] within bins
    expected = float(np.mean((stretch - p_true) ** 2))
    print(f"[2] injected overconfidence: REL={m2['rel']:.5f} vs injected size ~{expected:.5f}")
    ok &= 0.5 * expected < m2["rel"] < 1.5 * expected

    flat = np.full(len(y), y.mean())
    m3 = murphy(flat, y)
    print(f"[3] uninformative forecaster: RES={m3['res']:.5f} (want ~0), REL={m3['rel']:.5f} (want ~0)")
    ok &= m3["res"] < 1e-4 and m3["rel"] < 1e-4

    noisy = np.clip(p_true + rng.normal(0, 0.15, len(p_true)), 0.001, 0.999)
    df = pd.DataFrame({"a": noisy, "b": p_true, "y": y, "game_id": game})
    pdiff = paired_diff(df, "a", "b")
    print(f"[4] head-to-head, worse vs better: diff={pdiff['mean']:+.5f} [{pdiff['lo']:+.5f},{pdiff['hi']:+.5f}] (want >0, CI excl 0)")
    ok &= pdiff["lo"] > 0

    bp, fitted = pava(stretch, y)
    mono = np.all(np.diff(fitted) >= -1e-12)
    recal = iso_predict(bp, fitted, stretch)
    m5 = murphy(recal, y)
    print(f"[5] PAVA monotone={mono}, REL after recalibration={m5['rel']:.5f} (want ~0, was {m2['rel']:.5f})")
    ok &= mono and m5["rel"] < 0.15 * m2["rel"]

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- data


def load() -> pd.DataFrame:
    d = pd.read_csv(DECISIONS_PIN)
    r = pd.read_csv(OUTCOMES_PIN).drop_duplicates("market_slug")

    # --- verify the YES frame on THIS export, never assume it -------------
    e_no = d[(d.action == "enter") & (d.side == "no")].dropna(subset=["fair_value", "limit_price", "edge_net"])
    resid = (e_no.edge_net - (e_no.market_ask - e_no.fair_value)).abs()
    assert resid.max() < 1e-9, "fair_value/book no longer YES-frame on no rows"

    mk = d[["market_slug", "sports_market_type", "line"]].drop_duplicates("market_slug")
    mk = mk.merge(
        r[["market_slug", "settlement", "final_score_home", "final_score_away", "actual_total"]],
        on="market_slug",
        how="left",
    )
    assert mk.settlement.notna().all(), "unresolved markets in decisions export"

    t = mk[mk.sports_market_type == "basketball_team_full_game_total"]
    assert (t.settlement == (t.actual_total > t.line).astype(int)).all(), "totals YES != over"
    s = mk[mk.sports_market_type == "basketball_team_full_game_spread"]
    assert (s.settlement == ((s.final_score_away - s.final_score_home + s.line) > 0).astype(int)).all(), (
        "spread YES != away-margin+line>0"
    )
    w = mk[mk.sports_market_type == "basketball_team_full_game_winner"]
    assert (w.settlement == (w.final_score_away > w.final_score_home).astype(int)).all(), "winner YES != away wins"
    print(
        f"frame checks: totals {len(t)}/{len(t)}, spread {len(s)}/{len(s)}, winner {len(w)}/{len(w)} — all YES-frame as documented"
    )

    d = d.merge(mk[["market_slug", "settlement"]], on="market_slug", suffixes=("_row", ""))
    d["y"] = d["settlement"].astype(float)
    d["fv"] = d["fair_value"]
    d["mid"] = (d.market_bid + d.market_ask) / 2
    d["width"] = d.market_ask - d.market_bid
    d["t"] = pd.to_datetime(d.decided_at)
    d["mtype"] = d.sports_market_type.str.replace("basketball_team_full_game_", "", regex=False)
    return d


def resample_5min(df: pd.DataFrame) -> pd.DataFrame:
    """First row per market per 5 game-minutes — the autocorrelation sensitivity."""
    key = (df.minutes_left // 5).astype(int)
    return df.sort_values("t").groupby(["market_slug", key], as_index=False).first()


# ---------------------------------------------------------------- report


def fmt_pd(tag: str, r: dict) -> str:
    return f"  {tag:<42s} {r['mean']:+.5f}  [{r['lo']:+.5f}, {r['hi']:+.5f}]  rows={r['rows']:>5d} games={r['games']}"


def main() -> None:
    d = load()
    holds = d[(d.action == "hold") & d.fv.notna() & d.mid.notna()].copy()
    enters = d[(d.action == "enter") & d.fv.notna() & d.mid.notna()].copy()

    print("\n=== COMPOSITION (before any ratio) ===")
    print(f"window {d.t.min():%Y-%m-%d} → {d.t.max():%Y-%m-%d}, pins {DECISIONS_PIN}")
    print(f"holds with fv+book: {len(holds)} rows, {holds.game_id.nunique()} games, {holds.market_slug.nunique()} markets")
    print("ALL hold rows carry reason='position_open': holds exist only while a position is open.")
    print("They are unselected on the CURRENT tick's fv-vs-market gap, but the market was")
    print("selected by a past entry and by not-yet-exited. This is the least-selected fv")
    print("sample the system logs; it is not a random sample of game states.")
    print(f"rows by type: {holds.mtype.value_counts().to_dict()}")
    print(f"games by type: {holds.groupby('mtype').game_id.nunique().to_dict()}")
    print(f"rows by estimates_version: {holds.estimates_version.value_counts().to_dict()}")
    print(f"hold cadence: ~60s per market; book width median {holds.width.median():.2f}, p90 {holds.width.quantile(0.9):.2f}")
    print(f"|fv-mid| median {abs(holds.fv - holds.mid).median():.3f} on holds vs {abs(enters.fv - enters.mid).median():.3f} on entries")
    base = {g: v["y"].tolist() for g, v in holds.groupby("game_id")}
    cm = clustered_mean(base)
    print(f"base rate P(YES) on holds: {cm.mean:.3f} [{cm.lo:.3f}, {cm.hi:.3f}] games={cm.n_clusters}")

    print("\n=== RELIABILITY CURVE — holds, all types (realized CI game-clustered) ===")
    print(reliability_table(holds, "fv").to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    for mt in ["total", "spread", "winner"]:
        sub = holds[holds.mtype == mt]
        print(f"\n--- {mt} ({sub.game_id.nunique()} games) ---")
        print(reliability_table(sub, "fv").to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n=== RELIABILITY CURVE — the market mid on the same hold rows ===")
    print(reliability_table(holds, "mid").to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n=== MURPHY DECOMPOSITION — holds (bootstrap by game, 95% CI) ===")
    print("Brier = UNC - RES + REL.  REL: recalibration fixes it.  RES: it cannot.")
    for label, frame in [("all", holds)] + [(mt, holds[holds.mtype == mt]) for mt in ["total", "spread", "winner"]]:
        line = {"label": label, "games": frame.game_id.nunique(), "rows": len(frame)}
        for col in ["fv", "mid"]:
            for k in ["brier", "rel", "res"]:
                pt, lo, hi = boot_by_game(frame, lambda f, c=col, kk=k: murphy(f[c].to_numpy(), f["y"].to_numpy())[kk])
                line[f"{col}_{k}"] = f"{pt:.4f} [{lo:.4f},{hi:.4f}]"
        print(
            f"{line['label']:<7s} g={line['games']:>2d} r={line['rows']:>5d}\n"
            f"    model: Brier {line['fv_brier']}  REL {line['fv_rel']}  RES {line['fv_res']}\n"
            f"    mid  : Brier {line['mid_brier']}  REL {line['mid_rel']}  RES {line['mid_res']}"
        )
        for k in ["rel", "res"]:
            pt, lo, hi = boot_by_game(
                frame,
                lambda f, kk=k: murphy(f["fv"].to_numpy(), f["y"].to_numpy())[kk]
                - murphy(f["mid"].to_numpy(), f["y"].to_numpy())[kk],
            )
            print(f"    {k.upper()} diff (model - mid): {pt:+.4f} [{lo:+.4f},{hi:+.4f}]")

    print("\n=== HEAD-TO-HEAD — per-row Brier(model) - Brier(mid), game-clustered ===")
    print("negative = model beats the mid")
    print(fmt_pd("holds, all", paired_diff(holds, "fv", "mid")))
    for mt in ["total", "spread", "winner"]:
        print(fmt_pd(f"holds, {mt}", paired_diff(holds[holds.mtype == mt], "fv", "mid")))
    for per in ["Q1", "Q2", "HT", "Q3", "Q4"]:
        print(fmt_pd(f"holds, {per}", paired_diff(holds[holds.period == per], "fv", "mid")))
    for lo_m, hi_m in [(0, 10), (10, 20), (20, 40)]:
        sub = holds[(holds.minutes_left >= lo_m) & (holds.minutes_left < hi_m)]
        print(fmt_pd(f"holds, minutes_left [{lo_m},{hi_m})", paired_diff(sub, "fv", "mid")))
    for lo_a, hi_a in [(0, 5), (5, 100)]:
        sub = holds[(holds.margin.abs() >= lo_a) & (holds.margin.abs() < hi_a)]
        print(fmt_pd(f"holds, |margin| [{lo_a},{hi_a})", paired_diff(sub, "fv", "mid")))
    print(fmt_pd("holds, tight book (width<=0.05)", paired_diff(holds[holds.width <= 0.05], "fv", "mid")))
    print(fmt_pd("holds, wide book (width>0.05)", paired_diff(holds[holds.width > 0.05], "fv", "mid")))
    q = abs(holds.fv - holds.mid)
    for lab, m in [("agree (|fv-mid|<=0.05)", q <= 0.05), ("disagree (|fv-mid|>0.05)", q > 0.05)]:
        print(fmt_pd(f"holds, {lab}", paired_diff(holds[m], "fv", "mid")))
    for v in ["v1", "v3", "v4"]:
        print(fmt_pd(f"holds, estimates {v}", paired_diff(holds[holds.estimates_version == v], "fv", "mid")))
    band = (holds.mid >= 0.35) & (holds.mid <= 0.65)
    print(fmt_pd("holds, mid 0.35-0.65 (size band)", paired_diff(holds[band], "fv", "mid")))
    print(fmt_pd("holds, mid outside 0.35-0.65", paired_diff(holds[~band], "fv", "mid")))
    print(fmt_pd("ENTRIES (selection-conditioned!)", paired_diff(enters, "fv", "mid")))
    print(fmt_pd("entries, price 0.35-0.65", paired_diff(enters[(enters.mid >= 0.35) & (enters.mid <= 0.65)], "fv", "mid")))

    print("\n=== EXTREME-CONFIDENCE MISSES (holds) ===")
    print("A forecast <=0.02 that settles YES (or >=0.98 that settles NO) is a near-certain")
    print("claim that was wrong; each costs ~1.0 of Brier and they concentrate in few games.")
    for who, col in [("model", "fv"), ("mid", "mid")]:
        lo_m = holds[holds[col] <= 0.02]
        hi_m = holds[holds[col] >= 0.98]
        lo_miss, hi_miss = lo_m[lo_m.y == 1], hi_m[hi_m.y == 0]
        print(
            f"  {who}: <=0.02 rows={len(lo_m)} missed={len(lo_miss)} (games {sorted(lo_miss.game_id.unique().tolist())}); "
            f">=0.98 rows={len(hi_m)} missed={len(hi_miss)} (games {sorted(hi_miss.game_id.unique().tolist())})"
        )
    z = holds[holds.fv == 0.0]
    print(f"  fv==0.0 exactly: {len(z)} rows, {z.game_id.nunique()} games, mid on those rows median {z.mid.median():.3f}, missed={int((z.y == 1).sum())}")

    print("\n=== IS IT FIXABLE? LOGO isotonic recalibration of fv, then vs mid ===")
    print("Leave-one-game-out: the held-out game never shapes its own mapping.")
    holds = holds.reset_index(drop=True)
    holds["fv_recal"] = logo_recalibrated(holds)
    print(fmt_pd("recalibrated fv vs raw fv", paired_diff(holds, "fv_recal", "fv")))
    print(fmt_pd("recalibrated fv vs mid", paired_diff(holds, "fv_recal", "mid")))
    for mt in ["total", "spread", "winner"]:
        sub = holds[holds.mtype == mt]
        print(fmt_pd(f"recal vs mid, {mt}", paired_diff(sub, "fv_recal", "mid")))
    m_raw = murphy(holds.fv.to_numpy(), holds.y.to_numpy())
    m_rec = murphy(holds.fv_recal.to_numpy(), holds.y.to_numpy())
    m_mid = murphy(holds.mid.to_numpy(), holds.y.to_numpy())
    print(
        f"  point decomposition — model REL {m_raw['rel']:.4f} → recal {m_rec['rel']:.4f} (mid {m_mid['rel']:.4f}); "
        f"model RES {m_raw['res']:.4f} → recal {m_rec['res']:.4f} (mid {m_mid['res']:.4f})"
    )

    print("\n=== SENSITIVITY — 1 row per market per 5 game-minutes ===")
    hs = resample_5min(holds)
    print(f"rows {len(holds)} → {len(hs)}, games {hs.game_id.nunique()}")
    print(fmt_pd("resampled: model vs mid", paired_diff(hs, "fv", "mid")))
    print(fmt_pd("resampled: recal vs mid", paired_diff(hs, "fv_recal", "mid")))
    for k in ["rel", "res"]:
        pt, lo, hi = boot_by_game(hs, lambda f, kk=k: murphy(f["fv"].to_numpy(), f["y"].to_numpy())[kk])
        print(f"  resampled model {k.upper()}: {pt:.4f} [{lo:.4f},{hi:.4f}]")

    print("\n=== STANDING LANGUAGE ===")
    print("Everything above is IN-SAMPLE and DESCRIPTIVE — hypothesis-generating, nothing gates.")
    print("Dozens of slices were read; several sub-0.05 patterns are expected by chance alone.")
    print("Ranking is mechanism plausibility + robustness across slices, never p-value.")
    print(CAPITAL_LINE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="mutation-test the instruments on synthetic data")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        main()
