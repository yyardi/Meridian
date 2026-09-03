"""Placement curve re-derived on REAL fills — replaces a retracted result.

WHAT THIS RETIRES
-----------------
An earlier version of this measurement (the M2 cell of mm_control_variables)
reported that ">10c is the only non-negative cell per cycle quoted", and that
finding propagated: it is the premise under the GRIDIRON placement arm and
under the three-way width cell discussed with research. I retracted it once
the phantom-fill artifact was found. This script is the replacement, and it
reverses the sign of the conclusion.

The original had TWO independent defects, and it matters that they are two,
because fixing only the first still leaves a metric that cannot answer the
question.

DEFECT 1 — phantom contamination, correlated with the axis being measured.
The shadow fill model books a fill when the MID crosses the quote. A resting
bid at B forces best_bid >= B, so a real book cannot have mid <= B while
ask > B; those fills are ones our own presence would have prevented. Their
share is not constant across the width axis — it climbs from 42% in the
tightest band to 79% in the 5-10c band. Any curve drawn through those cells
is partly a curve through the artifact's own gradient.

DEFECT 2 — the normalisation ranks inactivity, on a losing book.
Per cycle quoted = (fill rate) x (P&L per fill). Every per-fill cell here is
negative. That does not force the per-cycle ordering to equal the fill-rate
ordering — a high-rate mild loser can beat a low-rate severe one — but it
does put a ceiling of zero on the metric, approached only as the fill rate
goes to zero. The argmax of "P&L per cycle quoted" on a losing book is
"do not quote". A band can therefore top this table by being economically
the WORST place to stand, provided it stands there rarely enough. That is
what >10c was doing: it has the worst per-fill P&L on the board.

Per-cycle is still the right unit for comparing policies that all trade;
it is not a safe unit for ranking cells when the per-fill mean is negative
everywhere. Report it alongside the fill rate and the per-fill mean, never
alone.

SCORING is settlement, not capture-vs-mid: capture is a marking convention,
and marking a maker's edge against the mid it just crossed flatters it.
CIs are game-clustered via the blessed clustered_mean.
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402


def _exports_dir():
    """Locate the pinned exports.

    backups/ is untracked, so it exists only in the main checkout and never
    inside a git worktree. Walk up until it is found rather than hardcoding
    either location, and fail loudly instead of silently reading a partial
    or absent substrate.
    """
    for base in [REPO, *Path(__file__).resolve().parents]:
        cand = base / "backups/exports"
        if cand.is_dir():
            return cand
    raise FileNotFoundError(
        "backups/exports not found above this file — the pinned exports live "
        "in the main checkout only. Run from there.")


EX = _exports_dir()
FILLS = EX / "quote_fills_v1_20260902T161223Z.csv"
TICKS = EX / "live_ticks_pulse_games_20260901T195202Z.csv.gz"

# live_ticks_pulse_games covers only 147 of the 209 markets that have fills
# (62 markets, 4,412 fills, 25% of the population, absent entirely). Both
# the fill-side book lookup and the cycle denominator need the full
# substrate, or the numerator and denominator describe different boards.
TICK_SOURCES = f"""
    SELECT market_slug, captured_at, best_bid, best_ask
      FROM read_csv('{TICKS}')
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/eval_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/delta_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT market_slug, captured_at, best_bid, best_ask
      FROM read_csv('{EX}/live_snapshots_since0820.csv.gz')"""

BANDS = [(0.0, 0.02, "<=2c"), (0.02, 0.05, "2-5c"),
         (0.05, 0.10, "5-10c"), (0.10, 1.01, ">10c")]
BOOK_MAX_AGE_S = 5.0
CYCLE = "5 seconds"


def band_of(s):
    for lo, hi, name in BANDS:
        if lo <= s < hi:
            return name
    return ">10c"


def per_cycle_table(fills, ncyc):
    """fills: one row per REAL fill with .band and .pnl. ncyc: band -> cycles.

    Returns a row per band carrying the three numbers that must travel
    together — fill rate, per-fill mean, and their product.
    """
    out = []
    for _, _, band in BANDS:
        nc = int(ncyc.get(band, 0))
        r = fills[fills.band == band]
        if nc == 0 and len(r) == 0:
            continue
        rate = len(r) / nc if nc else float("nan")
        # a band that was quoted but never filled earned exactly nothing --
        # per_fill is undefined, but per_cycle is 0.0, and that zero is the
        # do-nothing limit this metric maximises. Keep it visible.
        per_fill = r.pnl.mean() if len(r) else float("nan")
        per_cycle = (rate * per_fill) if len(r) else 0.0
        out.append({"band": band, "cycles": nc, "n": len(r), "rate": rate,
                    "per_fill": per_fill, "per_cycle": per_cycle})
    return pd.DataFrame(out)


def _selftest():
    """Encode the false positive the retracted version produced.

    Two bands. WIDE is economically terrible (-8c a fill) but almost never
    trades; TIGHT loses less per fill and trades often. Ranking by per-cycle
    alone crowns WIDE — the exact inversion that put ">10c" at the top of
    the original table. The test asserts the inversion HAPPENS, so that the
    guard against it cannot be quietly removed.
    """
    fills = pd.DataFrame(
        {"band": ["<=2c"] * 100 + [">10c"] * 2,
         "pnl": [-0.01] * 100 + [-0.08] * 2})
    t = per_cycle_table(fills, pd.Series({"<=2c": 1000, ">10c": 1000}))
    tight = t[t.band == "<=2c"].iloc[0]
    wide = t[t.band == ">10c"].iloc[0]

    assert wide.per_fill < tight.per_fill, "fixture: wide must be worse/fill"
    assert wide.per_cycle > tight.per_cycle, (
        "fixture must reproduce the inversion the retracted metric made")
    # the ceiling that makes the metric's argmax 'do not quote'
    assert (t.per_cycle < 0).all(), "all-negative per-fill => per-cycle < 0"

    # ...and the limit itself: a band quoted 1000 times that never filled
    # scores 0.000, beating every band that actually traded. If this ever
    # stops being the top row, the all-negative premise has changed.
    lim = per_cycle_table(fills[fills.band == "<=2c"],
                          pd.Series({"<=2c": 1000, ">10c": 1000}))
    never = lim[lim.band == ">10c"].iloc[0]
    assert never.n == 0 and never.rate == 0.0
    assert never.per_cycle == 0.0, "quoted-but-never-filled earns exactly 0"
    assert np.isnan(never.per_fill), "per-fill is undefined with no fills"
    assert never.per_cycle == lim.per_cycle.max(), (
        "the do-nothing row must win this metric outright")

    # identity: per_cycle is exactly rate x per_fill, no hidden weighting
    assert np.allclose(t.per_cycle, t.rate * t.per_fill)
    print("selftest OK — inversion reproduced, do-nothing row wins outright, "
          "identity exact")


def main():
    d = pd.read_csv(FILLS, parse_dates=["quoted_at", "filled_at"])
    d = d[(d.regime == "ingame") & d.settlement.notna()].copy()
    d["pnl"] = np.where(d.side == "bid", d.settlement - d.quote_price,
                        d.quote_price - d.settlement)

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    con.execute(f"""CREATE TEMP TABLE tk AS SELECT * FROM ({TICK_SOURCES})
        WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL""")
    con.register("f", d.reset_index(names="fid"))
    # BACKWARD join: the classifying book must be the one that existed at
    # or before the fill. An earlier version of this negated the timestamps
    # to work around DuckDB's ASOF direction and got `captured_at >=
    # filled_at` instead -- a forward join whose one-sided age filter then
    # admitted unbounded lookahead. It bit 123 fills (worst: a book from
    # 25 hours later) on the partial substrate. age is now >= 0 by
    # construction, so the cap means what it says.
    book = con.execute("""
      WITH q AS (SELECT fid, market_slug, epoch(filled_at) t FROM f)
      SELECT q.fid, t.best_bid fb, t.best_ask fa,
             q.t - epoch(t.captured_at) age
      FROM q ASOF JOIN (SELECT market_slug, best_bid, best_ask, captured_at,
                               epoch(captured_at) ct FROM tk) t
        ON q.market_slug = t.market_slug AND t.ct <= q.t
    """).df().set_index("fid")
    assert (book.age >= 0).all(), "join must not look forward"
    d = d.join(book[book.age <= BOOK_MAX_AGE_S]).dropna(subset=["fa", "fb"])

    # phantom: the model's mid-cross fired while the far touch was still
    # outside our price, i.e. our own resting order would have blocked it
    d["phantom"] = np.where(d.side == "bid", d.fa > d.quote_price + 1e-9,
                            d.fb < d.quote_price - 1e-9)
    d["band"] = d.spread_at_quote.map(band_of)

    cyc = con.execute(f"""
      SELECT market_slug, time_bucket(INTERVAL '{CYCLE}', captured_at) bk,
             arg_max(best_ask - best_bid, captured_at) spread
      FROM tk GROUP BY 1, 2
    """).df()
    ncyc = cyc.assign(band=cyc.spread.map(band_of)).groupby("band").size()

    real = d[~d.phantom]
    t = per_cycle_table(real, ncyc)

    print(f"settled in-game fills with a book within {BOOK_MAX_AGE_S:.0f}s: "
          f"{len(d)}  (phantom {d.phantom.mean():.1%})")
    print("\n=== PLACEMENT CURVE ON REAL FILLS (settlement basis) ===")
    print(f"{'band':7s} {'cycles':>9s} {'all':>7s} {'phantom%':>9s} "
          f"{'REAL':>6s} {'fill rate':>10s} {'P&L/fill (clustered)':>26s} "
          f"{'P&L/cycle':>10s}")
    for r in t.itertuples():
        g = d[d.band == r.band]
        rr = real[real.band == r.band]
        cm = clustered_mean({k: list(v)
                             for k, v in rr.groupby("game_id").pnl})
        ci = (f"{cm.mean*100:+.2f} [{cm.lo*100:+.2f},{cm.hi*100:+.2f}]c"
              if cm else "n/a")
        print(f"{r.band:7s} {r.cycles:>9d} {len(g):>7d} "
              f"{g.phantom.mean():>8.1%} {r.n:>6d} {r.rate:>10.4f} "
              f"{ci:>26s} {r.per_cycle*100:>+9.3f}c")

    print("\n=== THE TWO DEFECTS, SHOWN ===")
    print(f"1. phantom share across the width axis: "
          f"{' -> '.join(f'{d[d.band==b].phantom.mean():.0%}' for b in t.band)}"
          "  (not constant: the artifact has its own gradient along the very"
          " axis being measured)")
    worst = t.loc[t.per_fill.idxmin()]
    best_cyc = t.loc[t.per_cycle.idxmax()]
    print(f"2. per-cycle argmax is {best_cyc.band!r} at "
          f"{best_cyc.per_cycle*100:+.3f}c/cycle, and the worst per-fill cell "
          f"on the board is {worst.band!r} at {worst.per_fill*100:+.2f}c/fill")
    if best_cyc.band == worst.band:
        print("   -> SAME BAND. The per-cycle winner is the per-fill loser;")
        print("      it wins by trading at a rate of "
              f"{best_cyc.rate:.4f} fills per cycle, i.e. by barely standing")
        print("      in the market at all. This is the inactivity artifact.")
    print(f"   every per-fill cell negative: {bool((t.per_fill < 0).all())}"
          "  -> per-cycle is capped at 0 and maximised by not quoting")

    print("\nCONCLUSION: on real fills there is no width at which quoting was")
    print("profitable, and the wide end is not the good end. The placement")
    print("premise inherited by the GRIDIRON arm does not survive; width")
    print("should not be carried forward as a P&L lever on this evidence.")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    _selftest()
    main()
