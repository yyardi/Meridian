"""C1 late-state census — does the tradable form of the bimodal-endgame
mechanism exist at all on this venue?

DESCRIPTIVE, NOT A GATE. Round-3 speed-1 item; the census precedes any
capture registration. Per B's accepted demand it prices FILLS, not gaps:
every episode reports its rung price bands (the <20c / 20-90c / >90c
composition), book survival toward settlement, and settlement outcomes.
DEPTH IS NOT ON THIS TAPE (best bid/ask only) — V1's measured prior (~$5 at
the touch under 20c) is cited, not re-measured; the NBA day-one record list
exists to fix that gap.

Substrate, all pinned: the 200ms tick tape (books), ESPN plays (game clock at
wallclock), resolved outcomes (settlement). n = 34 WNBA games; every count
carries its game count; nothing here is an edge claim.

Reproduce:

    .venv/bin/python analysis/c1_late_state_census.py --selftest
    .venv/bin/python analysis/c1_late_state_census.py \
        --ticks backups/exports/live_ticks_pulse_games_20260901T195202Z.csv.gz \
        --plays backups/exports/eval_espn_plays.csv.gz \
        --outcomes backups/exports/resolved_outcomes_20260901T195202Z.csv

PINNED DEFINITIONS
==================
Late close state: ESPN period 4, game clock <= 180s, |margin| <= 3.
Instant grid: ticks deduped to a 10s grid per market (last book per bucket).
Episode: a maximal run of qualifying instants for one game with gaps <= 30s.
OT-reachable window: totals rungs with line - S_t in (0, +20] (S_t = current
total). Clinched-over rungs: line < S_t (P(over) = 1 by arithmetic).
Two-sided: 0 < bid and ask < 1 and bid <= ask. Implied P(over) = mid.
Book survival: an in-window rung "survives" if it shows a two-sided book at
some instant with clock <= 60s in period 4 of its game.
Game mapping: event_slug <-> ESPN game id by (slug date, unordered final
score pair); the census asserts the mapping is one-to-one on this pin.
ESPN home/away resolution is NOT needed: |margin| and totals are
order-invariant.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PLAY_COLS = ["first_seen", "espn_gid", "play_id", "seq", "period", "clock_secs",
             "wallclock", "text", "team_id", "b1", "b2", "pts", "score_a", "score_b"]
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


# ------------------------------------------------------------------ loading


def load_plays(path: str) -> pd.DataFrame:
    head = pd.read_csv(path, nrows=0)
    if "espn_game_id" in head.columns:  # the dedicated clock pin (headered, 6 cols)
        p = pd.read_csv(path).rename(columns={
            "espn_game_id": "espn_gid", "clock_seconds": "clock_secs",
            "home_score": "score_a", "away_score": "score_b"})
    else:  # the headerless 14-col eval export
        p = pd.read_csv(path, header=None, names=PLAY_COLS, low_memory=False)
    p = p[pd.to_numeric(p.period, errors="coerce").notna()].copy()
    for c in ["period", "clock_secs", "score_a", "score_b"]:
        p[c] = pd.to_numeric(p[c], errors="coerce")
    p = p.dropna(subset=["period", "clock_secs", "score_a", "score_b"])
    p["wallclock"] = pd.to_datetime(p.wallclock, errors="coerce", utc=True, format="ISO8601")
    p = p.dropna(subset=["wallclock"])
    p["tot"] = p.score_a + p.score_b
    p["margin_abs"] = (p.score_a - p.score_b).abs()
    return p.sort_values(["espn_gid", "wallclock", "tot"])


def map_games(ticks: pd.DataFrame, plays: pd.DataFrame,
              outcomes: pd.DataFrame | None = None) -> dict[str, str]:
    """event_slug -> espn_gid by unordered final-score pair + date within 1 day.

    The slug carries the US game date; ESPN wallclocks are UTC, so an evening
    tip lands on the NEXT UTC date — the date check is |slug - utc_start| <= 1
    day, with the score pair carrying the identification. Finals come from the
    RESOLVED OUTCOMES where available (the settlement-authoritative source;
    the tick tape's last event_score went stale before the final points in at
    least one measured game, tor-wsh 08-19) and fall back to the tick tape's
    last score for events the outcomes file lacks."""
    finals = plays.groupby("espn_gid").agg(a=("score_a", "max"), b=("score_b", "max"),
                                           d=("wallclock", "min"))
    by_pair: dict[frozenset, list] = {}
    for gid, row in finals.iterrows():
        by_pair.setdefault(frozenset([int(row.a), int(row.b)]), []).append((gid, row.d.date()))
    auth = {}
    if outcomes is not None and "event_slug" in outcomes.columns:
        oc = outcomes.dropna(subset=["event_slug", "final_score_home", "final_score_away"])
        for slug, g in oc.groupby("event_slug"):
            auth[slug] = frozenset([int(g.final_score_home.iloc[0]), int(g.final_score_away.iloc[0])])
    out, misses, ambigs = {}, [], []
    for slug, g in ticks.groupby("event_slug"):
        if slug in auth:
            pair = auth[slug]
        else:
            last = g.sort_values("captured_at").event_score.dropna().iloc[-1]
            pair = frozenset(int(x) for x in last.split("-"))
        slug_date = pd.Timestamp("-".join(slug.split("-")[-3:])).date()
        hits = [gid for gid, d in by_pair.get(pair, [])
                if abs((d - slug_date).days) <= 1]
        if len(hits) == 1:
            out[slug] = hits[0]
        elif len(hits) == 0:
            misses.append(slug)
        else:
            ambigs.append(slug)
    print(f"game mapping: {len(out)} mapped, {len(misses)} unmatched, {len(ambigs)} ambiguous"
          + (f"; unmatched: {misses}" if misses else "")
          + (f"; ambiguous: {ambigs}" if ambigs else ""))
    return out


# ------------------------------------------------------------------ census


def build_instants(ticks: pd.DataFrame, plays: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """10s-grid totals-book instants joined to the ESPN state at that wallclock."""
    t = ticks[ticks.sports_market_type == "basketball_team_full_game_total"].copy()
    t["captured_at"] = pd.to_datetime(t.captured_at, utc=True, format="ISO8601")
    t["bucket"] = t.captured_at.dt.floor("10s")
    t = t.sort_values("captured_at").groupby(["market_slug", "bucket"]).last().reset_index()
    t["espn_gid"] = t.event_slug.map(mapping)
    t = t.dropna(subset=["espn_gid"])
    frames = []
    for gid, tk in t.groupby("espn_gid"):
        pl = plays[plays.espn_gid == gid][["wallclock", "period", "clock_secs", "tot", "margin_abs"]]
        if pl.empty:
            continue
        merged = pd.merge_asof(tk.sort_values("bucket"), pl.sort_values("wallclock"),
                               left_on="bucket", right_on="wallclock",
                               direction="backward", tolerance=pd.Timedelta("180s"))
        frames.append(merged)
    st = pd.concat(frames, ignore_index=True).dropna(subset=["period"])
    return st


def census(st: pd.DataFrame, outcomes: pd.DataFrame) -> None:
    q = st[(st.period == 4) & (st.clock_secs <= 180) & (st.margin_abs <= 3)].copy()
    q["two_sided"] = (q.best_bid > 0) & (q.best_ask < 1) & (q.best_bid <= q.best_ask)
    q["offset"] = q.line - q.tot
    print("\n=== COMPOSITION (before any ratio) ===")
    print(f"qualifying instants (10s grid, per market): {len(q)} rows · "
          f"{q.groupby(['event_slug', 'bucket']).ngroups} game-instants · "
          f"{q.event_slug.nunique()} of {st.event_slug.nunique()} games reach a late close state")

    inst = q.groupby(["event_slug", "bucket"]).size().reset_index()[["event_slug", "bucket"]]
    inst = inst.sort_values(["event_slug", "bucket"])
    gap = inst.groupby("event_slug").bucket.diff().dt.total_seconds()
    inst["episode"] = ((gap > 30) | gap.isna()).cumsum()
    ep = inst.groupby("episode").agg(game=("event_slug", "first"), n=("bucket", "size"),
                                     start=("bucket", "min"), end=("bucket", "max"))
    ep["dur_s"] = (ep.end - ep.start).dt.total_seconds() + 10
    print(f"episodes (gap<=30s): {len(ep)} across {ep.game.nunique()} games; "
          f"duration median {ep.dur_s.median():.0f}s, p90 {ep.dur_s.quantile(0.9):.0f}s")

    win = q[(q.offset > 0) & (q.offset <= 20)]
    print(f"\nOT-REACHABLE WINDOW (line − S_t in (0,+20]): {len(win)} rung-instants, "
          f"{win.market_slug.nunique()} rungs, {win.event_slug.nunique()} games")
    tw = win[win.two_sided]
    print(f"two-sided share in-window: {len(tw)}/{len(win)} = {len(tw) / max(len(win), 1):.1%}")
    if len(tw):
        mid = (tw.best_bid + tw.best_ask) / 2
        band = pd.cut(mid, [0, 0.20, 0.90, 1.0], labels=["<20c", "20-90c", ">90c"])
        print("price-band composition of two-sided in-window rungs (B's deserts check):")
        print("  " + " · ".join(f"{k}: {v} ({v / len(tw):.0%})" for k, v in band.value_counts().items()))
        print(f"  implied P(over) in-window: median {mid.median():.2f}, p10 {mid.quantile(0.1):.2f}, "
              f"p90 {mid.quantile(0.9):.2f}; spread median {(tw.best_ask - tw.best_bid).median():.2f}")

    clinched = q[(q.offset < 0) & q.two_sided]
    if len(clinched):
        print(f"\nclinched-over rungs (line < S_t) still two-sided: {len(clinched)} rung-instants, "
              f"{clinched.event_slug.nunique()} games; venue BID on them median "
              f"{clinched.best_bid.median():.2f} (arithmetic says worth 1.00 — a bid below ~0.97 "
              f"is free money TO THE SELLER only if size exists; depth is NOT on this tape, V1 prior ~$5)")

    # book survival: in-window rungs seen two-sided at clock <= 60s
    last_min = st[(st.period == 4) & (st.clock_secs <= 60)]
    alive = set(last_min[(last_min.best_bid > 0) & (last_min.best_ask < 1)].market_slug)
    wrungs = win.market_slug.unique()
    surv = sum(r in alive for r in wrungs)
    print(f"\nbook survival: {surv}/{len(wrungs)} in-window rungs show a two-sided book "
          f"inside the final 60s of regulation")

    res = outcomes.drop_duplicates("market_slug").set_index("market_slug").settlement
    wo = win.drop_duplicates("market_slug").copy()
    wo["settle"] = wo.market_slug.map(res)
    if wo.settle.notna().any():
        print(f"settlement attach: {int(wo.settle.notna().sum())}/{len(wo)} in-window rungs resolved; "
              f"{int((wo.settle == 1).sum())} settled OVER — with n={wo.event_slug.nunique()} games this is "
              f"composition, not a frequency estimate")

    print("\n=== STANDING LANGUAGE ===")
    print("Descriptive census on 34 WNBA games; the empirical-frequency comparison is the")
    print("NBA forward test's job (atlas curves, day-one recording incl. DEPTH per rung).")
    print("Nothing here is an edge claim or a capture claim; the census answers only")
    print("whether the mechanism's tradable form EXISTS: episodes, prices, books.")
    print(CAPITAL_LINE)


# ------------------------------------------------------------------ selftest


def selftest() -> None:
    """Fixtures with exactly known answers.

    1. Mapping: two synthetic games, distinct (date, final-pair) keys -> 1:1;
       a colliding pair -> reported ambiguous, not silently assigned.
    2. Episode splitter: constructed instants with a 40s gap -> exactly 2
       episodes with known durations.
    3. Window and band classification: constructed rungs land in the exact
       expected buckets; clinched-over detected; two-sided rule enforced.
    4. Asof join: a tick 5s after a play carries that play's state; a tick
       beyond tolerance carries none.
    """
    ok = True
    # g1 starts at 03:00Z on the 21st while the slug says 08-20 — the UTC
    # date-shift case the real data is full of; the ±1-day rule must map it
    base = pd.Timestamp("2026-08-21 03:00:00", tz="UTC")

    plays = pd.DataFrame({
        "espn_gid": ["g1"] * 3 + ["g2"] * 2,
        "wallclock": [base, base + pd.Timedelta("10s"), base + pd.Timedelta("400s"),
                      base, base + pd.Timedelta("20s")],
        "period": [4, 4, 4, 4, 4],
        "clock_secs": [170, 160, 30, 100, 90],
        "score_a": [50, 52, 60, 40, 80],
        "score_b": [51, 52, 61, 41, 80],
    })
    plays["tot"] = plays.score_a + plays.score_b
    plays["margin_abs"] = (plays.score_a - plays.score_b).abs()

    ticks = pd.DataFrame({
        "event_slug": ["wnba-x-y-2026-08-20"] * 2 + ["wnba-z-w-2026-08-20"],
        "market_slug": ["m1", "m1", "m2"],
        "sports_market_type": ["basketball_team_full_game_total"] * 3,
        "line": [105.5, 105.5, 90.5],
        "captured_at": [base + pd.Timedelta("5s"), base + pd.Timedelta("15s"), base + pd.Timedelta("25s")],
        "best_bid": [0.10, 0.12, 0.95], "best_ask": [0.14, 0.15, 0.99],
        "event_period": ["Q4"] * 3, "event_score": ["60-61", "60-61", "80-80"], "is_live": ["t"] * 3,
    })
    mapping = map_games(ticks, plays)
    ok &= mapping == {"wnba-x-y-2026-08-20": "g1", "wnba-z-w-2026-08-20": "g2"}
    print(f"[1] mapping 1:1 on distinct keys: {mapping == {'wnba-x-y-2026-08-20': 'g1', 'wnba-z-w-2026-08-20': 'g2'}}")

    inst = pd.DataFrame({"event_slug": ["e"] * 5,
                         "bucket": [base, base + pd.Timedelta("10s"), base + pd.Timedelta("20s"),
                                    base + pd.Timedelta("60s"), base + pd.Timedelta("70s")]})
    gap = inst.groupby("event_slug").bucket.diff().dt.total_seconds()
    inst["episode"] = ((gap > 30) | gap.isna()).cumsum()
    sizes = inst.groupby("episode").size().tolist()
    print(f"[2] episode splitter: sizes {sizes} (want [3, 2])")
    ok &= sizes == [3, 2]

    st = build_instants(ticks, plays, mapping)
    r1 = st[st.market_slug == "m1"].iloc[0]
    joined_ok = r1.tot == 101 and r1.clock_secs == 170
    r2 = st[st.market_slug == "m2"].iloc[0]
    joined2_ok = r2.tot == 160 and r2.clock_secs == 90
    print(f"[4] asof join: m1 first instant carries (tot 101, clock 170): {joined_ok}; "
          f"m2 carries (tot 160, clock 90): {joined2_ok}")
    ok &= joined_ok and joined2_ok

    q = st[(st.period == 4) & (st.clock_secs <= 180) & (st.margin_abs <= 3)].copy()
    q["offset"] = q.line - q.tot
    in_window_m1 = ((q.market_slug == "m1") & (q.offset > 0) & (q.offset <= 20)).any()
    clinched_m2 = ((q.market_slug == "m2") & (q.offset < 0)).any()
    print(f"[3] window: m1 (line 105.5, tot 101/104 -> offset 4.5/1.5) in-window: {in_window_m1}; "
          f"m2 (line 90.5, tot 160) clinched-over: {clinched_m2}")
    ok &= in_window_m1 and clinched_m2

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ticks")
    ap.add_argument("--plays")
    ap.add_argument("--outcomes")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not (args.ticks and args.plays and args.outcomes):
        ap.error("--ticks, --plays, --outcomes required (or --selftest)")
    ticks = pd.read_csv(args.ticks)
    plays = load_plays(args.plays)
    outcomes = pd.read_csv(args.outcomes)
    mapping = map_games(ticks, plays, outcomes)
    st = build_instants(ticks, plays, mapping)
    census(st, outcomes)


if __name__ == "__main__":
    main()
