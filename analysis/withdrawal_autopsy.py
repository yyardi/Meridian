"""Withdrawal autopsy — did the engine cancel entries that were about to fill?

    .venv/bin/python analysis/withdrawal_autopsy.py

STRUCTURAL FACT FIRST (per D's review): the tape has no expired state for
entries at all — the engine withdraws an entry the moment its estimate no
longer clears zero at the resting price (docs/math/pulse-live.md, entry
management), so ALL 1,019 unfilled intents end `withdrawn` by
construction. "Unfilled" on this tape MEANS "we cancelled", and the
question that decides between a pricing problem and a policy problem is:
where was the market when we pulled, would the order have filled if left
resting — and would that fill have been worth anything?

For each withdrawn intent this script reports, from the pinned tick export
(`live_ticks_pulse_games_20260901T195202Z.csv`, 200ms stream):

* rest time  — withdrawn_at − decided_at
* distance-to-fill at withdrawal — signed gap between the last two-sided
  mid at/before the pull and the resting price, in the direction a fill
  needed (yes: mid must fall to ≤ limit, so gap = mid − limit;
  no: mid must rise to ≥ limit, so gap = limit − mid)
* would-it-have-filled — whether ANY later tick's two-sided mid crossed
  the resting price (the tape's own fill rule, applied to the order we
  cancelled), and how long after the pull the first crossing came

Split late (Q4 or ≤5 min) vs early, per the B×D late-game cell. All
descriptive, in-sample, same pins. The fill rule's optimism caveat applies
to the counterfactual fills exactly as it does to real ones: a
"would-have-filled" is an upper-bound claim on that entry existing, and
says nothing about its exit.

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
EXPORTS = REPO / "backups/exports"  # override with --exports when running
                                    # from a worktree without the data files
TAPE_NAME = "pulse_decisions_full_20260901T195202Z.csv"
TICKS_NAME = "live_ticks_pulse_games_20260901T195202Z.csv.gz"
CHUNK = 2_000_000


def targets_from_tape(exports: Path) -> pd.DataFrame:
    df = pd.read_csv(exports / TAPE_NAME)
    w = df[(df.action == "enter") & df.withdrawn_at.notna()].copy()
    assert w.filled_at.isna().all()
    # all stamps are +00; convert to UTC then drop tz so every comparison
    # below is explicit datetime64 against datetime64 (no naive/aware mix)
    w["decided_at"] = (pd.to_datetime(w.decided_at, utc=True, format="ISO8601")
                       .dt.tz_localize(None))
    w["withdrawn_at"] = (pd.to_datetime(w.withdrawn_at, utc=True, format="ISO8601")
                         .dt.tz_localize(None))
    w["rest_s"] = (w.withdrawn_at - w.decided_at).dt.total_seconds()
    w["late"] = w.period.astype(str).str.startswith("Q4") | (w.minutes_left <= 5)
    return w[["id", "event_slug", "market_slug", "side", "limit_price", "decided_at",
              "withdrawn_at", "rest_s", "late", "period", "minutes_left",
              "estimates_version", "strategy"]].reset_index(drop=True)


def scan_ticks(t: pd.DataFrame, exports: Path) -> pd.DataFrame:
    """One streaming pass: per target, last two-sided mid ≤ withdrawn_at and
    first two-sided mid crossing the limit after withdrawn_at."""
    t = t.copy()
    t["mid_at_pull"] = np.nan
    t["mid_at_pull_ts"] = pd.NaT
    t["crossed_at"] = pd.NaT
    slugs = set(t.market_slug)
    by_slug = {s: g.index.to_numpy() for s, g in t.groupby("market_slug")}

    reader = pd.read_csv(
        exports / TICKS_NAME, chunksize=CHUNK,
        usecols=["market_slug", "captured_at", "best_bid", "best_ask"])
    for chunk in reader:
        chunk = chunk[chunk.market_slug.isin(slugs)]
        if chunk.empty:
            continue
        chunk = chunk.dropna(subset=["best_bid", "best_ask"])
        if chunk.empty:
            continue
        chunk["captured_at"] = (pd.to_datetime(chunk.captured_at, utc=True, format="ISO8601")
                                .dt.tz_localize(None))
        chunk["mid"] = (chunk.best_bid + chunk.best_ask) / 2
        for slug, g in chunk.groupby("market_slug", sort=False):
            ts = g.captured_at.to_numpy()
            mid = g.mid.to_numpy()
            for i in by_slug[slug]:
                w_at = t.at[i, "withdrawn_at"].to_datetime64()
                pre = ts <= w_at
                if pre.any():
                    j = np.flatnonzero(pre)[-1]
                    prev = t.at[i, "mid_at_pull_ts"]
                    if pd.isna(prev) or ts[j] > prev.to_datetime64():
                        t.at[i, "mid_at_pull"] = mid[j]
                        t.at[i, "mid_at_pull_ts"] = pd.Timestamp(ts[j])
                post = ts > w_at
                if post.any():
                    m, s = mid[post], ts[post]
                    hit = (m <= t.at[i, "limit_price"] + 1e-9
                           if t.at[i, "side"] == "yes"
                           else m >= t.at[i, "limit_price"] - 1e-9)
                    if hit.any():
                        first = pd.Timestamp(s[np.flatnonzero(hit)[0]])
                        prev = t.at[i, "crossed_at"]
                        if pd.isna(prev) or first < prev:
                            t.at[i, "crossed_at"] = first
    return t


def report(t: pd.DataFrame) -> None:
    t["gap_c"] = np.where(
        t.side == "yes",
        (t.mid_at_pull - t.limit_price) * 100,
        (t.limit_price - t.mid_at_pull) * 100)
    t["would_fill"] = t.crossed_at.notna()
    t["cross_delay_s"] = (t.crossed_at - t.withdrawn_at).dt.total_seconds()

    print("# Withdrawal autopsy — every unfilled intent was cancelled by us")
    print()
    print("Trigger (registered rule, not inferred): the entry limit is "
          "withdrawn the moment the estimate no longer clears zero at that "
          "price — a model mind-change, never an expiry.")
    print()
    q = [0.25, 0.5, 0.75]
    for lab, g in [("EARLY (not Q4, >5min)", t[~t.late]),
                   ("LATE (Q4 or <=5min)", t[t.late])]:
        n = len(g)
        print(f"## {lab}: n={n}, games={g.event_slug.nunique()}")
        print(f"rest time s      : {np.round(g.rest_s.quantile(q).to_numpy(), 1)}"
              f"  mean {g.rest_s.mean():.0f}")
        gg = g.dropna(subset=["gap_c"])
        print(f"gap at pull (c)  : {np.round(gg.gap_c.quantile(q).to_numpy(), 1)}"
              f"  (n={len(gg)} with a two-sided pre-pull tick; "
              f"<=2c: {(gg.gap_c <= 2).mean()*100:.0f}%)")
        wf = g.would_fill
        print(f"would have filled: {wf.sum()}/{n} = {wf.mean()*100:.0f}% "
              f"(mid later crossed the cancelled price; upper-bound rule)")
        d = g.loc[g.would_fill, "cross_delay_s"]
        if len(d):
            print(f"crossing delay s : {np.round(d.quantile(q).to_numpy(), 1)}")
        print()
    print("By version x strategy, would-have-filled % (late only):")
    late = t[t.late]
    for (v, s), g in late.groupby(["estimates_version", "strategy"]):
        print(f"  {v} {s:7s}: {g.would_fill.mean()*100:3.0f}%  (n={len(g)})")


def value_counterfactuals(t: pd.DataFrame, exports: Path) -> None:
    """Money-at-price at the cancelled limit, ridden to settlement, per-$,
    clustered by game — the check that separates "we cancelled fills we
    wanted" from "the fills we could get were worthless". Settlements come
    from A's ledger; the would-fill leg inherits the fill rule's optimism
    ONCE (the counterfactual entry), like any ride."""
    import sys
    sys.path.insert(0, str(REPO))
    from core.quote.adverse_selection import clustered_mean
    from core.pulse.live_report import settlement_score

    a = pd.read_csv(exports / "roundtrip_ledger_20260901T195202Z.csv")
    j = t.merge(a[["entry_decision_id", "settlement"]],
                left_on="id", right_on="entry_decision_id", how="left")
    j = j[j.settlement.notna()].copy()
    j["ride_ret"] = [
        (lambda sr: sr[1] / sr[0] - 1.0)(settlement_score(
            side=r.side, entry_price=float(r.limit_price),
            settlement=int(r.settlement)))
        for r in j.itertuples()]

    def cm(g, label):
        d = {k: list(v) for k, v in g.groupby("event_slug").ride_ret}
        c = clustered_mean(d)
        if c is None:
            print(f"{label:44s} n={len(g):4d} G={g.event_slug.nunique():2d}"
                  f"  (needs >=2 games)")
            return
        print(f"{label:44s} n={len(g):4d} G={g.event_slug.nunique():2d}  "
              f"{c.mean*100:+6.1f}c [{c.lo*100:+6.1f},{c.hi*100:+6.1f}]")

    print()
    print("Counterfactual value of the cancels (money-at-price at the "
          "cancelled limit, per-$, clustered):")
    wf, nf = j[j.would_fill], j[~j.would_fill]
    cm(wf, "cancelled + WOULD have filled (all)")
    cm(wf[~wf.late], "  early")
    cm(wf[wf.late], "  late")
    cm(nf, "cancelled + never crossed (never fillable)")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path, default=EXPORTS)
    args = ap.parse_args()
    t = targets_from_tape(args.exports)
    print(f"<!-- {len(t)} withdrawn intents "
          f"({t.late.sum()} late), scanning {TICKS_NAME} -->")
    t = scan_ticks(t, args.exports)
    report(t)
    t["would_fill"] = t.crossed_at.notna()
    value_counterfactuals(t, args.exports)
    out = args.exports / "withdrawal_autopsy_20260901T195202Z.csv"
    t.to_csv(out, index=False)
    print(f"<!-- per-intent rows written to {out.name} (gitignored, "
          f"regenerable from the pins) -->")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
