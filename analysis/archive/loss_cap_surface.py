"""Loss-cap counterfactual surface — the operator's O3, honestly scored.

    .venv/bin/python analysis/loss_cap_surface.py [--exports DIR]
    .venv/bin/python analysis/loss_cap_surface.py --selftest

Wall fact this tests: losers held longer lose monotonically more — WITH
the named confound that holding time is not chosen, it is what happens
when the exit doesn't fill. So the naive "cap losses at k¢" reading is
the confound restated. The honest version, per entry, on the tick pin:

  WOULD a rule "exit at the touch when the position has been ≥ k¢
  underwater for ≥ m minutes" have beaten WHAT ACTUALLY HAPPENED to that
  same entry — taker-priced (the real touch at the fire instant, plus
  the 0.06·p(1−p) fee), paired per entry, game-clustered?

The deliverable is the (k, m) SURFACE — 5 × 5 = 25 pre-declared cells,
grid size printed for multiplicity — not a chosen point.

Pre-named traps, carried:
1. **The confound is the analysis**: every comparison is per-entry paired
   (counterfactual minus realized for the SAME entry); no cell ever
   compares capped entries to an average.
2. **Book availability at the cap instant**: the cap fires at the first
   TWO-SIDED tick where the underwater run has lasted ≥ m (one-sided
   ticks can neither fire nor reset a run — you cannot observe or trade
   a book that isn't there). An entry whose condition was met but that
   never saw another two-sided tick before its window ended is scored
   UNEXECUTED (realized outcome stands) and counted — the count is a
   finding (bookless-endgames predicts it).
3. **Exit-policy work**: the engine-mediated compensation applies — no
   result here may be inherited by the flat-quintile analyses (the
   dispositions-page correction); a loss-cap changes the payoff
   structure, so the ride-risk netting must be recomputed under it.

Scoring arms: the realized side uses A's ledger per-$ (optimistic) and
its pessimistic column; the counterfactual side prices the cap exit at
the real touch (fee included) and, in the pessimistic arm, carries the
same single entry-leg concession as the realized side — so entry-leg
optimism cancels in the pair and the arms differ mainly on the realized
EXIT leg, which is exactly where the fill-model uncertainty lives.

Underwater is in YES-frame price: a yes position entered at L is
(L − mid) underwater; a no position is (mid − L). Cap exit value per
contract: yes → bid − fee; no → (1 − ask) − fee, fee = 0.06·p·(1−p) at
the execution price. Windows: filled_at → exit_filled_at (trips) or the
market's last tick (rides). A cap fires only strictly before the
realized exit.

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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

LEDGER = "roundtrip_ledger_20260901T195202Z.csv"
TICKS = "live_ticks_pulse_games_20260901T195202Z.csv.gz"
CHUNK = 2_000_000
FEE_THETA = 0.06
CONCESSION = 0.047

#: the pre-declared grid — 25 cells; every interval printed is counted
KS = [0.03, 0.05, 0.10, 0.15, 0.20]
MS_MIN = [0.5, 1.0, 2.0, 5.0, 10.0]

COMPARISONS = {"n": 0}


def load_entries(exports: Path) -> pd.DataFrame:
    a = pd.read_csv(exports / LEDGER)
    m = a[a.entry_filled & a.outcome.isin(["exit_fill", "settlement"])].copy()
    m["cost"] = m.entry_cost_per_contract
    m["ret"] = m.pnl_per_dollar
    m["ret_pess"] = m.pnl_per_dollar_pess
    for c in ("filled_at", "exit_filled_at"):
        m[c] = (pd.to_datetime(m[c], utc=True, format="ISO8601")
                .dt.tz_localize(None))
    m["win_end"] = m.exit_filled_at  # NaT for rides -> capped at last tick
    return m.reset_index(drop=True)


def scan(entries: pd.DataFrame, ticks_path: Path) -> dict:
    """One streaming pass. Per entry × k: maintain the underwater run
    across chunks; per (k, m): record the first executable fire."""
    idx_by_slug: dict[str, list[int]] = {}
    for i, slug in enumerate(entries.market_slug):
        idx_by_slug.setdefault(slug, []).append(i)

    run_start = {}          # (i, k) -> Timestamp of current run start
    fires = {}              # (i, k, m) -> dict(exit_val=..)
    cond_met = set()        # (i, k, m) where duration was ever reached
    last_tick = {}          # i -> last two-sided tick ts seen in window

    ent = entries
    reader = pd.read_csv(
        ticks_path, chunksize=CHUNK,
        usecols=["market_slug", "captured_at", "best_bid", "best_ask"])
    for chunk in reader:
        chunk = chunk[chunk.market_slug.isin(idx_by_slug)]
        if chunk.empty:
            continue
        chunk = chunk.dropna(subset=["best_bid", "best_ask"])
        if chunk.empty:
            continue
        chunk["captured_at"] = (
            pd.to_datetime(chunk.captured_at, utc=True, format="ISO8601")
            .dt.tz_localize(None))
        for slug, g in chunk.groupby("market_slug", sort=False):
            ts = g.captured_at.to_numpy()
            bid = g.best_bid.to_numpy()
            ask = g.best_ask.to_numpy()
            mid = (bid + ask) / 2
            for i in idx_by_slug[slug]:
                w0 = ent.filled_at.iloc[i].to_datetime64()
                w1 = (ent.win_end.iloc[i].to_datetime64()
                      if pd.notna(ent.win_end.iloc[i]) else None)
                sel = ts > w0
                if w1 is not None:
                    sel &= ts < w1
                if not sel.any():
                    continue
                t_, b_, a_, m_ = ts[sel], bid[sel], ask[sel], mid[sel]
                last_tick[i] = pd.Timestamp(t_[-1])
                tns = t_.astype("datetime64[ns]").astype("int64")
                L = float(ent.entry_limit_price.iloc[i])
                yes = ent.side.iloc[i] == "yes"
                uw = (L - m_) if yes else (m_ - L)
                for k in KS:
                    q = uw >= k - 1e-12
                    rs = run_start.get((i, k))
                    if not q.any():
                        run_start[(i, k)] = None
                        continue
                    starts = q & np.concatenate(([True], ~q[:-1]))
                    rs_ns = np.where(starts, tns, np.nan).astype(float)
                    if rs is not None and q[0]:
                        rs_ns[0] = rs.value          # continue carried run
                    rs_ns = pd.Series(rs_ns).ffill().to_numpy()
                    dur_min = np.where(q, (tns - rs_ns) / 60e9, -1.0)
                    for mm in MS_MIN:
                        key = (i, k, mm)
                        if key in fires:
                            continue
                        cand = dur_min >= mm
                        if cand.any():
                            j = int(np.argmax(cand))
                            cond_met.add(key)
                            p_exec = b_[j] if yes else a_[j]
                            fee = FEE_THETA * p_exec * (1 - p_exec)
                            val = (b_[j] - fee) if yes \
                                else ((1 - a_[j]) - fee)
                            fires[key] = {"exit_val": float(val)}
                    run_start[(i, k)] = (pd.Timestamp(int(rs_ns[-1]))
                                         if q[-1] else None)
    # finalize: runs still active at window end whose duration reached m
    # without ever seeing an executable (two-sided) tick again
    for (i, k), rs in run_start.items():
        if rs is None or i not in last_tick:
            continue
        dur_end = (last_tick[i] - rs).total_seconds() / 60.0
        for mm in MS_MIN:
            key = (i, k, mm)
            if dur_end >= mm and key not in fires:
                cond_met.add(key)
    return {"fires": fires, "cond_met": cond_met}


def surface(entries: pd.DataFrame, scanned: dict) -> None:
    fires, cond_met = scanned["fires"], scanned["cond_met"]
    print("\n## The (k, m) surface — paired per-entry, clustered by game\n")
    print(f"Grid declared pre-compute: {len(KS)}×{len(MS_MIN)} = "
          f"{len(KS) * len(MS_MIN)} cells × 2 arms = "
          f"{len(KS) * len(MS_MIN) * 2} clustered intervals. At 95%, "
          f"expect ~{len(KS) * len(MS_MIN) * 2 // 20} spurious.\n")
    print("| k¢ | m min | fired | unexec | Δ per-$ optimistic [95% CI] | "
          "Δ per-$ pessimistic [95% CI] |")
    print("|---|---|---|---|---|---|")
    for k in KS:
        for mm in MS_MIN:
            cf_o, cf_p = {}, {}
            n_fired = n_unexec = 0
            for i in range(len(entries)):
                e = entries.iloc[i]
                key = (i, k, mm)
                if key in fires:
                    n_fired += 1
                    val = fires[key]["exit_val"]
                    cf = (val - e.cost) / e.cost
                    d_o = cf - e.ret
                    d_p = (cf - CONCESSION / e.cost) - e.ret_pess
                elif key in cond_met:
                    n_unexec += 1
                    d_o = d_p = 0.0   # unexecutable: realized stands
                else:
                    d_o = d_p = 0.0
                if d_o != 0.0 or d_p != 0.0:
                    cf_o.setdefault(e.event_slug, []).append(d_o)
                    cf_p.setdefault(e.event_slug, []).append(d_p)
            co = clustered_mean(cf_o)
            cp = clustered_mean(cf_p)
            COMPARISONS["n"] += sum(c is not None for c in (co, cp))

            def fmt(c):
                if c is None:
                    return "— (needs ≥2 games)"
                flag = " ◄" if c.hi < 0 else (" ▷" if c.lo > 0 else "")
                return (f"{c.mean * 100:+.1f} [{c.lo * 100:+.1f}, "
                        f"{c.hi * 100:+.1f}]{flag}")
            print(f"| {k * 100:.0f} | {mm:g} | {n_fired} | {n_unexec} | "
                  f"{fmt(co)} | {fmt(cp)} |")
    print("\nΔ > 0 means the cap would have beaten what actually happened "
          "for the entries it touched (paired). 'unexec' = condition met "
          "but no two-sided tick ever offered the exit — the bookless "
          "count, a finding in itself.")
    print("\nTrap 3, stated: this is exit-policy work. No cell here may be "
          "inherited by the flat-quintile analyses — a loss-cap changes "
          "the payoff structure and the ride-risk netting must be "
          "recomputed under it (dispositions-page correction).")


def run(exports: Path) -> int:
    entries = load_entries(exports)
    print("# Loss-cap counterfactual surface (O3)")
    print(f"\nSubstrate: A's ledger @ pins · {len(entries):,} filled "
          f"entries, {entries.event_slug.nunique()} games · tick pin "
          f"`{TICKS}` · taker-priced cap exits (touch + 0.06·p(1−p)).")
    scanned = scan(entries, exports / TICKS)
    surface(entries, scanned)
    print(f"\n**Comparisons: {COMPARISONS['n']} clustered intervals.**")
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    return 0


# --------------------------------------------------------------------------
# Mutation tests: the pipeline must find a cap that provably helps
# (monotone grind-down after going underwater) and must NOT invent one on
# a mean-reverting null (where a cap only pays the toll).
# --------------------------------------------------------------------------

def _paths_tape(rng, *, grinding: bool):
    """Synthetic single-market-per-entry tick paths + matching entries."""
    ticks, entries = [], []
    t0 = pd.Timestamp("2026-01-01 00:00:00")
    for i in range(300):
        slug = f"m{i}"
        game = f"g{i % 30}"
        L = 0.50
        mid = L
        path = []
        for s in range(1200):                     # 20 min of 1s ticks
            if grinding:
                mid -= 0.0004 if s > 60 else 0    # grinds down after 1m
                mid += rng.normal(0, 0.002)
            else:
                mid = L + 0.9 * (mid - L) + rng.normal(0, 0.004)
            mid = float(np.clip(mid, 0.02, 0.98))
            path.append(mid)
            ticks.append({"market_slug": slug,
                          "captured_at": t0 + pd.Timedelta(seconds=s),
                          "best_bid": mid - 0.01, "best_ask": mid + 0.01})
        final = path[-1]
        ret = (final - L) / L                     # realized ~ hold to end
        entries.append({"market_slug": slug, "event_slug": game,
                        "side": "yes", "entry_limit_price": L, "cost": L,
                        "ret": ret, "ret_pess": ret - CONCESSION / L,
                        "filled_at": t0, "exit_filled_at": pd.NaT,
                        "win_end": pd.NaT})
    e = pd.DataFrame(entries)
    return pd.DataFrame(ticks), e


def selftest() -> int:
    import tempfile
    rng = np.random.default_rng(20260902)
    ok = True
    for grinding, want in ((True, "cap helps"), (False, "cap ~toll only")):
        ticks, entries = _paths_tape(rng, grinding=grinding)
        with tempfile.NamedTemporaryFile(suffix=".csv.gz") as tf:
            ticks.to_csv(tf.name, index=False, compression="gzip")
            scanned = scan(entries, Path(tf.name))
        # score one representative cell (k=5c, m=1min)
        diffs = {}
        for i in range(len(entries)):
            e = entries.iloc[i]
            key = (i, 0.05, 1.0)
            if key in scanned["fires"]:
                cf = (scanned["fires"][key]["exit_val"] - e.cost) / e.cost
                diffs.setdefault(e.event_slug, []).append(cf - e.ret)
        c = clustered_mean(diffs)
        if grinding:
            good = c is not None and c.lo > 0
        else:
            good = c is None or c.hi < 0.02   # no invented benefit
        n = sum(len(v) for v in diffs.values())
        print(f"{'grind-down' if grinding else 'mean-revert null'}: "
              f"fired {n}, Δ {'' if c is None else f'{c.mean:+.3f} '}"
              f"[{'' if c is None else f'{c.lo:+.3f}, {c.hi:+.3f}'}] "
              f"-> {'OK' if good else 'FAIL'} ({want})")
        ok &= good
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exports", type=Path,
                    default=REPO / "backups/exports")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return selftest() if args.selftest else run(args.exports)


if __name__ == "__main__":
    raise SystemExit(main())
