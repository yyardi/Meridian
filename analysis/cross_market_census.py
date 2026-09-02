"""B1 census — cross-market coherence + B2's update-lag attribution (folded).

    .venv/bin/python analysis/cross_market_census.py [--exports DIR]
                                                     [--workdir DIR]
    .venv/bin/python analysis/cross_market_census.py --selftest

Speed-1 item 4. Two instruments, one artifact, per the R2 fold (C's attack
on B2 accepted: staleness is ATTRIBUTION, the entry-policy claim rides on
the cross-type census alone).

**Part 1 — the winner↔spread triangle.** Winner YES and spread YES share
one frame (V19/V28: first team's margin m, integers, no ties after OT), so
each spread rung at line ℓ is a point on the margin survival function:
S(−ℓ) = spread mid, and the winner mid must equal S(0.5) = P(m ≥ 1).
At every 200ms instant where the winner book and BOTH bracketing rungs
are two-sided, we interpolate S(0.5) linearly between the bracketing
points and record gap = winner_mid − Ŝ(0.5). The census reports the gap
distribution, episode counts (|gap| above {2, 5, 10}¢ persisting ≥
{1, 5}s), the bracket width per instant (the interpolation-uncertainty
bound, printed so a "violation" narrower than its bracket is never
counted), coverage (instants where the triangle was computable at all —
bookless-endgames says winner books die first), and the toll benchmark
BESIDE the gaps (both legs' spreads + 0.06·p(1−p) fees) without assuming
any capture. Counts before ratios throughout.

**Part 2 — update-lag attribution (B2, demoted per C's attack, demands
carried).** CENSORING HEADER, quoted from the R2 record: the 200ms pin
cannot order rung updates faster than one poll apart, so the observable
population is the ≳400ms tail of the lag distribution — and that boundary
approximately EQUALS the capturability bar (measured ~260ms detection +
36ms RTT + an unmeasurable venue queue; write-latency.md), so the
observable tail ≈ the actionable tail, missing only spectator-sport
episodes. Within each game's spread ladder and totals ladder: an update
EPISODE begins when any rung's mid moves ≥ 1¢; the episode's lag is the
time until the LAST rung of the same ladder moves (rungs that never move
within 30s are counted as non-participants, not laggards). We report the
episode count, the lag distribution of the observable tail, participation,
and the temporal-clustering check C demanded (are long-lag episodes
bunched in time — venue congestion would slow OUR order exactly then).
No capture economics are computed here at all — attribution only.

Both parts run per event from a one-pass split of the tick pin into
per-event files (the pin is 17M rows; per-event is the tractable unit).

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

TICKS = "live_ticks_pulse_games_20260901T195202Z.csv.gz"
CHUNK = 2_000_000
FEE_THETA = 0.06
GAP_THRESHOLDS = [0.02, 0.05, 0.10]      # ¢ levels for episode counting
PERSIST_S = [1.0, 5.0]                   # episode persistence floors
LAG_EPISODE_START = 0.01                 # a rung "moves" on a >=1c mid change
LAG_WINDOW_S = 30.0                      # non-participation horizon
RESAMPLE_MS = 200                        # native grid; stated, not assumed
X_BRACKET_MAX = 7.0     # points; a wider bracket around x=0.5 makes linear
                        # interpolation of S meaningless (spot-checked: the
                        # largest raw "episode" was a 22-point blowout
                        # bracket around a perfectly coherent book) — such
                        # instants are EXCLUDED and counted, not data


def split_per_event(ticks_path: Path, workdir: Path) -> list[Path]:
    """One pass: split the pin into per-event CSV files (appended
    incrementally — never the whole pin in memory)."""
    workdir.mkdir(parents=True, exist_ok=True)
    done = sorted(workdir.glob("evt_*.csv"))
    if done:
        return done
    reader = pd.read_csv(
        ticks_path, chunksize=CHUNK,
        usecols=["event_slug", "market_slug", "sports_market_type", "line",
                 "captured_at", "best_bid", "best_ask"])
    seen: set[str] = set()
    for chunk in reader:
        for slug, g in chunk.groupby("event_slug", sort=False):
            path = workdir / f"evt_{slug}.csv"
            g.drop(columns=["event_slug"]).to_csv(
                path, mode="a", header=slug not in seen, index=False)
            seen.add(slug)
    return sorted(workdir.glob("evt_*.csv"))


# ----------------------------------------------------------------------- #
# Part 1 — the triangle
# ----------------------------------------------------------------------- #

def triangle_for_event(df: pd.DataFrame) -> dict:
    """Winner mid vs interpolated S(0.5) on the event's 200ms grid."""
    win = df[df.sports_market_type.str.endswith("winner")]
    spr = df[df.sports_market_type.str.endswith("spread")].copy()
    out = {"n_winner_rows": len(win), "n_instants": 0, "n_triangle": 0,
           "gaps": [], "widths": [], "tolls": [], "episodes": {},
           "times": [], "too_wide": 0, "bracket_pts": np.nan}
    if win.empty or spr.empty:
        return out
    win = win.dropna(subset=["best_bid", "best_ask"])
    spr = spr.dropna(subset=["best_bid", "best_ask"])
    if win.empty or spr.empty:
        return out
    spr["x"] = -spr.line.astype(float)          # S(x): P(m > x)
    spr["mid"] = (spr.best_bid + spr.best_ask) / 2
    spr["spread_px"] = spr.best_ask - spr.best_bid
    win = win.assign(mid=(win.best_bid + win.best_ask) / 2,
                     spread_px=win.best_ask - win.best_bid)

    # align on the winner's own instants; last-known rung state as-of
    grid = win[["captured_at", "mid", "spread_px"]].rename(
        columns={"mid": "wmid", "spread_px": "wspread"})
    out["n_instants"] = len(grid)
    rungs = {}
    for x, g in spr.groupby("x"):
        s = g.set_index("captured_at")[["mid", "spread_px"]]
        s = s[~s.index.duplicated(keep="last")]
        rungs[x] = s
    xs = np.array(sorted(rungs))
    lo_c = xs[xs < 0.5].max() if (xs < 0.5).any() else None
    hi_c = xs[xs > 0.5].min() if (xs > 0.5).any() else None
    if lo_c is None or hi_c is None:
        return out
    out["bracket_pts"] = float(hi_c - lo_c)
    if hi_c - lo_c > X_BRACKET_MAX:
        out["too_wide"] = out["n_instants"]
        return out
    tol = pd.Timedelta(seconds=2)      # a rung older than this is STALE,
                                       # not a quote — bookless rungs must
                                       # not fake a live triangle
    lo = rungs[lo_c].reindex(grid.captured_at, method="ffill",
                             tolerance=tol)
    hi = rungs[hi_c].reindex(grid.captured_at, method="ffill",
                             tolerance=tol)
    ok = lo.mid.notna().to_numpy() & hi.mid.notna().to_numpy()
    if not ok.any():
        return out
    w = (0.5 - lo_c) / (hi_c - lo_c)
    s_hat = (1 - w) * lo.mid.to_numpy() + w * hi.mid.to_numpy()
    gap = grid.wmid.to_numpy() - s_hat
    width = np.abs(lo.mid.to_numpy() - hi.mid.to_numpy())
    toll = (grid.wspread.to_numpy() / 2
            + (lo.spread_px.to_numpy() + hi.spread_px.to_numpy()) / 4
            + FEE_THETA * grid.wmid.to_numpy() * (1 - grid.wmid.to_numpy()))
    t = grid.captured_at.to_numpy()[ok]
    gap, width, toll = gap[ok], width[ok], toll[ok]
    out["n_triangle"] = int(ok.sum())
    out["gaps"] = gap
    out["widths"] = width
    out["tolls"] = toll
    out["times"] = t

    # episodes: |gap| beyond BOTH the threshold and the bracket width,
    # persisting; a violation narrower than its interpolation bracket is
    # never counted
    for thr in GAP_THRESHOLDS:
        viol = (np.abs(gap) > thr) & (np.abs(gap) > width / 2)
        for per in PERSIST_S:
            n_ep = 0
            run_start = None
            for j in range(len(viol)):
                if viol[j]:
                    if run_start is None:
                        run_start = t[j]
                    elif ((t[j] - run_start) / np.timedelta64(1, "s")
                          >= per):
                        n_ep += 1
                        run_start = None   # count once, reset
                else:
                    run_start = None
            out["episodes"][(thr, per)] = n_ep
    return out


# ----------------------------------------------------------------------- #
# Part 2 — update-lag attribution
# ----------------------------------------------------------------------- #

TRIGGER_MOVE = 0.03     # a >=3c rung move opens a response episode
RESPONSE_MOVE = 0.02    # a same-direction >=2c move on another rung responds
RESPONSE_CAP_S = 10.0   # responses later than this are not responses


def spread_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Survey module (NBA day-one consumable): per market type × period,
    the bid-ask spread distribution and two-sided share. Input: any tick
    frame with sports_market_type, event_period, best_bid, best_ask.
    Returns one row per (type, period): n rows, share two-sided, spread
    p50/p90 in cents over two-sided rows. Counts before ratios."""
    d = df.copy()
    d["mtype"] = d.sports_market_type.str.rsplit("_", n=1).str[-1]
    d["two"] = d.best_bid.notna() & d.best_ask.notna()
    d["spread_px"] = d.best_ask - d.best_bid
    if "event_period" not in d.columns:
        d["event_period"] = "ALL"      # period split only when the input
                                       # carries the venue period column
    rows = []
    for (mt, per), g in d.groupby(["mtype", "event_period"],
                                  dropna=False):
        two = g[g.two]
        rows.append({
            "mtype": mt, "period": per, "n_rows": len(g),
            "n_two_sided": len(two),
            "share_two_sided": len(two) / len(g) if len(g) else np.nan,
            "spread_p50_c": (two.spread_px.quantile(.5) * 100
                             if len(two) else np.nan),
            "spread_p90_c": (two.spread_px.quantile(.9) * 100
                             if len(two) else np.nan)})
    return pd.DataFrame(rows)


def validate_lag_instrument(seed: int = 7) -> bool:
    """Rule-15 consumable: the jitter-null + known-lag pair for
    lags_for_event, callable from any consumer's self-test (the survey
    must run this against ITS import, not trust this file's history).
    Returns True iff the instrument recovers a planted 1.5s co-move AND
    invents nothing on independent ±1¢ jitter."""
    t0 = pd.Timestamp("2026-01-01")
    rows = []
    for s in np.arange(0, 60, 0.2):
        m1 = 0.60 if s < 30 else 0.55
        m2 = 0.40 if s < 31.5 else 0.35
        for slug, m, line in (("s1", m1, 2.5), ("s2", m2, -3.5)):
            rows.append({"market_slug": slug, "sports_market_type":
                         "basketball_team_full_game_spread", "line": line,
                         "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                         "best_bid": m - 0.01, "best_ask": m + 0.01})
    lags = lags_for_event(pd.DataFrame(rows), "spread")
    ok = len(lags) == 1 and 1.2 < lags[0][1] < 1.8
    rng = np.random.default_rng(seed)
    rows = []
    for s in np.arange(0, 300, 0.2):
        for slug, base, line in (("s1", 0.60, 2.5), ("s2", 0.40, -3.5)):
            m = base + rng.choice([-0.01, 0.0, 0.01])
            rows.append({"market_slug": slug, "sports_market_type":
                         "basketball_team_full_game_spread", "line": line,
                         "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                         "best_bid": m - 0.01, "best_ask": m + 0.01})
    return ok and len(lags_for_event(pd.DataFrame(rows), "spread")) == 0


def lags_for_event(df: pd.DataFrame, kind: str) -> list[tuple]:
    """Directional co-move response lags. A >=3c move on one rung opens an
    episode; every OTHER rung's first same-direction >=2c move within 10s
    is a response, and its delay is one lag observation. Independent 1c
    jitter opens (almost) no episodes and answers (almost) none — the
    jitter-null mutation enforces exactly that. All rungs of one board
    share direction in the YES frame (all rise when the first team's
    outlook improves / when pace rises)."""
    lad = df[df.sports_market_type.str.endswith(kind)].dropna(
        subset=["best_bid", "best_ask"]).copy()
    if lad.empty or lad.market_slug.nunique() < 2:
        return []
    lad["mid"] = (lad.best_bid + lad.best_ask) / 2
    per_rung = {}
    trig = []
    for slug, g in lad.groupby("market_slug"):
        m = g.mid.to_numpy()
        ts = g.captured_at.to_numpy()
        d = np.diff(m)
        per_rung[slug] = (ts, d)
        big = np.abs(d) >= TRIGGER_MOVE
        for j in np.flatnonzero(big):
            trig.append((ts[1:][j], slug, np.sign(d[j])))
    trig.sort(key=lambda x: x[0])
    lags = []
    last_t0 = None
    for t0, slug0, sgn in trig:
        if last_t0 is not None and (t0 - last_t0) / np.timedelta64(1, "s")                 < RESPONSE_CAP_S:
            continue                     # one episode per quiet window
        last_t0 = t0
        for slug, (ts, d) in per_rung.items():
            if slug == slug0:
                continue
            sel = (ts[1:] > t0) & ((ts[1:] - t0) / np.timedelta64(1, "s")
                                   <= RESPONSE_CAP_S)
            resp = sel & (d * sgn >= RESPONSE_MOVE)
            if resp.any():
                j = int(np.argmax(resp))
                lags.append((pd.Timestamp(t0),
                             float((ts[1:][j] - t0)
                                   / np.timedelta64(1, "s"))))
    return lags


# ----------------------------------------------------------------------- #

def run(exports: Path, workdir: Path) -> int:
    files = split_per_event(exports / TICKS, workdir)
    print("# B1 census — the winner↔spread triangle, with B2's "
          "update-lag attribution\n")
    print(f"Pin: `{TICKS}` split into {len(files)} events · native grid "
          f"{RESAMPLE_MS}ms.\n")
    print("**Censoring header (C's demand, quoted):** the 200ms pin cannot "
          "order rung updates faster than one poll apart — the observable "
          "lag population is the ≳400ms tail, which approximately EQUALS "
          "the capturability bar (~260ms detection + 36ms RTT + an "
          "unmeasurable venue queue, write-latency.md): the observable "
          "tail ≈ the actionable tail, missing only spectator-sport "
          "episodes. Part 2 computes NO capture economics — attribution "
          "only.\n")

    tri_rows, all_lags = [], {"spread": [], "total": []}
    tot_gap, tot_w = [], []
    for f in files:
        df = pd.read_csv(f)
        df["captured_at"] = (
            pd.to_datetime(df.captured_at, utc=True, format="ISO8601")
            .dt.tz_localize(None))
        df = df.sort_values("captured_at")
        r = triangle_for_event(df)
        tri_rows.append({
            "event": f.stem.replace("evt_", ""),
            "winner_rows": r.get("n_winner_rows", 0),
            "instants": r["n_instants"], "triangle": r["n_triangle"],
            "too_wide": r.get("too_wide", 0),
            "bracket_pts": r.get("bracket_pts", np.nan),
            **{f"ep_{int(thr*100)}c_{int(p)}s": r["episodes"].get((thr, p), 0)
               for thr in GAP_THRESHOLDS for p in PERSIST_S}})
        if r["n_triangle"]:
            tot_gap.append(pd.Series(np.abs(r["gaps"])))
            tot_w.append(pd.Series(r["widths"]))
        for kind in ("spread", "total"):
            all_lags[kind].extend(lags_for_event(df, kind))

    tri = pd.DataFrame(tri_rows)
    print("## Part 1 — triangle coverage and episodes (counts first)\n")
    print(f"Winner rows total {tri.winner_rows.sum():,} · two-sided "
          f"(the grid) {tri.instants.sum():,} "
          f"({tri.instants.sum() / max(tri.winner_rows.sum(), 1) * 100:.0f}%"
          f" — the winner-book death of the bookless doc lives in THIS "
          f"gap) · triangle computable (both bracketing rungs two-sided "
          f"within 2s): {tri.triangle.sum():,} "
          f"({tri.triangle.sum() / max(tri.instants.sum(), 1) * 100:.1f}% "
          f"of the grid) · events with any triangle: "
          f"{(tri.triangle > 0).sum()}/{len(tri)} · events excluded for "
          f"bracket > {X_BRACKET_MAX:g} pts around x=0.5 (blowout boards; "
          f"interpolation meaningless): {(tri.too_wide > 0).sum()} · "
          f"bracket width in points, median across events: "
          f"{tri.bracket_pts.median():g}.")
    if tot_gap:
        g = pd.concat(tot_gap)
        wdt = pd.concat(tot_w)
        print(f"\n|gap| quantiles (¢): p50 {g.quantile(.5)*100:.1f} · "
              f"p90 {g.quantile(.9)*100:.1f} · p99 {g.quantile(.99)*100:.1f} "
              f"· max {g.max()*100:.1f}; bracket width median "
              f"{wdt.median()*100:.1f}¢ (the interpolation bound).")
    print("\nEpisodes (|gap| > threshold AND > bracket/2, persisting):\n")
    print("| threshold | ≥1s | ≥5s | events with any |")
    print("|---|---|---|---|")
    for thr in GAP_THRESHOLDS:
        c1 = tri[f"ep_{int(thr*100)}c_1s"].sum()
        c5 = tri[f"ep_{int(thr*100)}c_5s"].sum()
        ev = (tri[f"ep_{int(thr*100)}c_1s"] > 0).sum()
        print(f"| {thr*100:.0f}¢ | {c1} | {c5} | {ev} |")

    print("\n## Part 2 — update-lag attribution (observable tail only)\n")
    rng = np.random.default_rng(20260902)
    for kind in ("spread", "total"):
        pairs = all_lags[kind]
        if len(pairs) == 0:
            print(f"* {kind} ladders: no multi-rung update episodes found.")
            continue
        lg = np.array([x[1] for x in pairs])
        t0s = np.array([x[0].value for x in pairs], dtype=float) / 1e9
        obs = lg[lg >= 0.4]
        print(f"* {kind} ladders: {len(lg)} response lags; observable tail "
              f"(≥0.4s): {len(obs)} ({len(obs)/len(lg)*100:.0f}%) — "
              f"p50 {np.median(lg):.2f}s, p90 "
              f"{np.quantile(lg, .9):.2f}s (cap {RESPONSE_CAP_S:.0f}s). "
              f"Sub-0.4s mass is left-censored, not fast: unmeasurable.")
        # C's congestion check: do LONG lags cluster in wall-clock time
        # (venue-wide slowness would also slow OUR order at capture time)?
        long_t = np.sort(t0s[lg >= 5.0])
        if len(long_t) >= 10:
            near = float(np.mean(np.diff(long_t) <= 30.0))
            shuf = []
            for _ in range(10):
                s = np.sort(rng.uniform(t0s.min(), t0s.max(),
                                        size=len(long_t)))
                shuf.append(float(np.mean(np.diff(s) <= 30.0)))
            verdict = ("CLUSTERED — capture would select against us; "
                       "C's confound live"
                       if near > 2 * np.mean(shuf)
                       else "no strong clustering")
            print(f"  congestion check: {near*100:.0f}% of long-lag "
                  f"(≥5s) episodes within 30s of the next one, vs "
                  f"{np.mean(shuf)*100:.0f}% under uniform shuffle — "
                  f"{verdict}. (Cross-event pooling; wall-clock.)")

    print("\nNo capture claim is made anywhere above; the toll benchmark "
          "and the wall's racing bar stand between any episode and an "
          "entry policy. Even a null census is the venue's flow-structure "
          "map.")
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    return 0


def selftest() -> int:
    t0 = pd.Timestamp("2026-01-01")
    rows = []

    def tick(sec, mtype, line, mid, slug):
        rows.append({"market_slug": slug, "sports_market_type": mtype,
                     "line": line, "captured_at": t0 + pd.Timedelta(seconds=sec),
                     "best_bid": mid - 0.01, "best_ask": mid + 0.01})
    # coherent segment: tight bracket (x=-0.5, x=1.5), S linear =>
    # S(0.5)=.50 = winner mid -> gap 0; bracket width 8c -> bound 4c
    for s in range(0, 100):
        tick(s, "basketball_team_full_game_winner", np.nan, 0.50, "w")
        tick(s, "basketball_team_full_game_spread", 0.5, 0.54, "s1")   # x=-0.5
        tick(s, "basketball_team_full_game_spread", -1.5, 0.46, "s2")  # x=1.5
    # injected desync: winner jumps 12c for 10s, rungs stay -> gap 12c
    # clears BOTH the 10c threshold and the 4c interpolation bound
    for s in range(100, 110):
        tick(s, "basketball_team_full_game_winner", np.nan, 0.62, "w")
        tick(s, "basketball_team_full_game_spread", 0.5, 0.54, "s1")
        tick(s, "basketball_team_full_game_spread", -1.5, 0.46, "s2")
    df = pd.DataFrame(rows)
    r = triangle_for_event(df)
    ep = r["episodes"].get((0.10, 1.0), 0)
    coherent_ok = float(np.abs(np.asarray(r["gaps"])[:95]).max()) < 0.005
    print(f"triangle: coherent gap max "
          f"{np.abs(np.asarray(r['gaps'])[:95]).max()*100:.2f}c -> "
          f"{'OK' if coherent_ok else 'FAIL'}; injected 12c/10s episodes "
          f"(10c,1s): {ep} -> {'OK' if ep >= 1 else 'FAIL'}")

    # lag: s1 drops 5c at t=30, s2 follows 1.5s later -> one lag ~1.5s
    rows2 = []
    for s in np.arange(0, 60, 0.2):
        m1 = 0.60 if s < 30 else 0.55
        m2 = 0.40 if s < 31.5 else 0.35
        rows2.append({"market_slug": "s1", "sports_market_type":
                      "basketball_team_full_game_spread", "line": 2.5,
                      "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                      "best_bid": m1 - 0.01, "best_ask": m1 + 0.01})
        rows2.append({"market_slug": "s2", "sports_market_type":
                      "basketball_team_full_game_spread", "line": -3.5,
                      "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                      "best_bid": m2 - 0.01, "best_ask": m2 + 0.01})
    lags = lags_for_event(pd.DataFrame(rows2), "spread")
    ok_lag = len(lags) == 1 and 1.2 < lags[0][1] < 1.8
    print(f"lag census: co-move lags {[x[1] for x in lags]} -> "
          f"{'OK (~1.5s recovered)' if ok_lag else 'FAIL'}")

    # jitter null: independent +/-1c flicker on both rungs, no co-moves
    rng = np.random.default_rng(7)
    rows3 = []
    for s in np.arange(0, 300, 0.2):
        for slug, base, line in (("s1", 0.60, 2.5), ("s2", 0.40, -3.5)):
            m = base + rng.choice([-0.01, 0.0, 0.01])
            rows3.append({"market_slug": slug, "sports_market_type":
                          "basketball_team_full_game_spread", "line": line,
                          "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                          "best_bid": m - 0.01, "best_ask": m + 0.01})
    jlags = lags_for_event(pd.DataFrame(rows3), "spread")
    ok_null = len(jlags) == 0
    print(f"jitter null: episodes {len(jlags)} -> "
          f"{'OK (no invented propagation)' if ok_null else 'FAIL'}")
    return 0 if (coherent_ok and ep >= 1 and ok_lag and ok_null) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path,
                    default=REPO / "backups/exports")
    ap.add_argument("--workdir", type=Path, required=False,
                    default=Path(__file__).resolve().parent
                    / ".b1_census_events")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return selftest() if args.selftest else run(args.exports, args.workdir)


if __name__ == "__main__":
    raise SystemExit(main())
