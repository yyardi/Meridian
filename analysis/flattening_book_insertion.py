"""FLATTEN's k, re-hardened by INSERTING our order into the book.

WHY THIS EXISTS
---------------
I hardened FLATTEN's k=1c against the phantom artifact by EXCLUDING phantom
fills at scoring time. That is not the same operation as putting our order
into the book, and the difference is not cosmetic.

In flattening_policy_sim.simulate the inventory q is incremented by EVERY
model fill, phantoms included (it classifies them, then still counts them),
and q is the input to the inventory-conditional lean. So the simulated
policy was reacting to inventory it would never have held: a phantom bid
fill makes it "long", which leans the ask in, which changes every
subsequent quote and therefore every subsequent fill. Filtering phantoms
out of the P&L afterwards cannot undo a quote path that was chosen by them.

Two claims are then worth separating, because one is provable and one is
empirical.

PROVABLE — the per-fill test is unchanged by insertion. A resting bid at bp
forces best_bid >= bp, so the real fill condition is that the counterparty's
ask crosses it: ask <= bp. And ask <= bp implies mid = (bid+ask)/2 <= bp
since bid <= ask. So {mid <= bp} AND {ask <= bp} == {ask <= bp}: the
exclusion rule and the crossing rule select the SAME fills from the same
book. Symmetrically bid >= ap implies mid >= ap. Our own quotes also cannot
fill each other, since the post-only clamp keeps bp < ap. So insertion adds
nothing at the level of a single test.

EMPIRICAL — the PATH differs, because q differs, because the quotes differ.
That is what this script measures, and it is the only thing that can move
the registered parameter.

Scored on settlement, game-clustered CIs, same pinned substrate as the
k-curve it is checking.

WHAT k=0 IS, AND IS NOT. k=0 is a BASELINE ARM: the same procedure as
every other k, on the same grid, so differences BETWEEN k values are
meaningful. It is NOT a replication of what v1 did. This replay
re-derives quote placement from policy on a 5s grid; v1 ran on the raw
tick stream with move-triggered requoting. Checked at the row level, the
k=0 fill set and v1's recorded real fills overlap only ~41% on (market,
5s bucket, side, price) -- 2,462 shared out of 6,403 and 6,146. Their
totals land within 2.4% of each other, which is an aggregate coincidence
and not agreement. Do not quote this baseline as corroborating an
independent read of the recorded tape; they are different quantities.

THE CONSEQUENCE, STATED AS A PROHIBITION because it is the sentence
somebody will write by accident: this file's numbers are internally
valid and UNANCHORED to v1's measured economics. The k-curve figures
(+$10.10 at k=1c, -2.94c/fill at k=0, -2.20c/fill at k=1c) live inside
the replay's own world. They MUST NOT be placed beside the settlement
read on the recorded tape (-3.38c/fill over 6,255 real fills) as though
the pair described one board. Different procedures, different
populations, 41% overlap -- it is precisely the comparison withdrawn
above, and the numbers are close enough to look like they belong in one
sentence. They do not. Compare k values to each other; compare the tape
to itself.
"""
import importlib.util
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _exports_dir():
    """backups/ is untracked, so it exists only in the main checkout."""
    for base in [REPO, *Path(__file__).resolve().parents]:
        cand = base / "backups/exports"
        if cand.is_dir():
            return cand
    raise FileNotFoundError("backups/exports not found — run from the main "
                            "checkout, where the pinned exports live.")


EX = _exports_dir()
PIN = "20260901T195202Z"
FILLS = EX / "quote_fills_v1_20260902T161223Z.csv"
TICKS = EX / f"live_ticks_pulse_games_{PIN}.csv.gz"

# THE REPLAY GRID MUST COVER THE FILL POPULATION.
# live_ticks_pulse_games alone contains only 147 of the 209 markets that
# have fills — 62 markets, 4,412 fills (25%), are absent from it entirely.
# They are WHOLE MISSING MARKETS, not gaps inside covered markets (checked:
# zero fills in covered markets fail to join), so unioning the snapshot
# feeds extends coverage rather than splicing cadences inside a market.
# On the partial grid this k-curve reported a positive region of
# {1c, 2c, 3c}; on the full grid it is {1c} alone. Coverage was load-
# bearing for the conclusion, not a rounding detail.
TICK_SOURCES = f"""
    SELECT market_slug, captured_at, best_bid, best_ask
      FROM read_csv('{TICKS}')
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/eval_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT column00, column05, column06, column07
      FROM read_csv('{EX}/delta_market_snapshots.csv.gz', header=false)
    UNION ALL SELECT market_slug, captured_at, best_bid, best_ask
      FROM read_csv('{EX}/live_snapshots_since0820.csv.gz')"""


def load_cycles(markets, sources=None):
    """The 5s cycle grid, over the full tick substrate by default."""
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    con.execute("CREATE TEMP TABLE wanted(m VARCHAR)")
    con.executemany("INSERT INTO wanted VALUES (?)", [(m,) for m in markets])
    return con.execute(f"""
        SELECT market_slug,
               time_bucket(INTERVAL '{fps.CYCLE_S} seconds', captured_at)
                   AS bucket,
               arg_max(best_bid, captured_at) AS bid,
               arg_max(best_ask, captured_at) AS ask
        FROM ({sources or TICK_SOURCES})
        WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND market_slug IN (SELECT m FROM wanted)
        GROUP BY 1, 2 ORDER BY 1, 2
    """).df()


def _load_sim():
    spec = importlib.util.spec_from_file_location(
        "fps", Path(__file__).resolve().parent / "flattening_policy_sim.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fps = _load_sim()
from core.quote.adverse_selection import clustered_mean  # noqa: E402

K_GRID = (0.0, 0.01, 0.02, 0.03, 0.05)


def simulate_inserted(cycles: pd.DataFrame, k: float) -> pd.DataFrame:
    """Replay with our quotes actually resting in the book.

    Identical to flattening_policy_sim.simulate except:
      - a fill requires the COUNTERPARTY to cross (ask <= bp / bid >= ap),
        which is what a resting order actually needs, and
      - only those fills move q, so the lean is driven by inventory we
        would really be holding.
    """
    out = []
    for m, g in cycles.groupby("market_slug", sort=False):
        stand = None
        q = 0.0
        for r in g.itertuples():
            if stand is not None and r.bucket > stand[2]:
                bp, ap, _ = stand
                # our bid is filled only by an offer coming down to it; our
                # own resting ask is never the counterparty (bp < ap always)
                if r.ask <= bp + 1e-9:
                    out.append((m, "bid", bp, (r.bid + r.ask) / 2.0, r.bucket))
                    q += 1.0
                if r.bid >= ap - 1e-9:
                    out.append((m, "ask", ap, (r.bid + r.ask) / 2.0, r.bucket))
                    q -= 1.0
            if fps.quotable(r.bid, r.ask):
                bid_p, ask_p = r.bid, r.ask
                if q > 0:
                    ask_p = max(round(r.ask - k, 4), round(r.bid + fps.TICK, 4))
                elif q < 0:
                    bid_p = min(round(r.bid + k, 4), round(r.ask - fps.TICK, 4))
                stand = (bid_p, ask_p, r.bucket)
            else:
                stand = None
    return pd.DataFrame(out, columns=["market_slug", "side", "quote_price",
                                      "mid_at_fill", "filled_at"])


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    t0 = pd.Timestamp("2026-08-20 01:00:00+00:00")
    B = lambda i: t0 + pd.Timedelta(seconds=fps.CYCLE_S * i)

    # 1. the provable claim, on a book built to separate the two rules:
    #    mid crosses our bid while the ask stays above it -> the model fills,
    #    insertion does not. This is the phantom, isolated.
    phantom = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.54),
        dict(market_slug="m", bucket=B(1), bid=0.40, ask=0.52)])
    #   stand bid .50; b1 mid = .46 <= .50 (model fills) but ask .52 > .50
    old = fps.simulate(phantom, 0.0)
    new = simulate_inserted(phantom, 0.0)
    check("model books the phantom bid fill", len(old) == 1
          and bool(old.phantom.iloc[0]))
    check("insertion refuses it (ask never crossed)", len(new) == 0)

    # 2. and where the ask DOES cross, both agree
    real = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.54),
        dict(market_slug="m", bucket=B(1), bid=0.44, ask=0.48)])
    o2, n2 = fps.simulate(real, 0.0), simulate_inserted(real, 0.0)
    check("a genuine cross is booked by both",
          len(o2) == 1 and len(n2) == 1
          and not bool(o2.phantom.iloc[0])
          and abs(n2.quote_price.iloc[0] - 0.50) < 1e-9)

    # 3. THE POINT: a phantom fill steers the later quote path. Here the
    #    phantom makes the old sim think it is long, so it leans its ask in
    #    and books a second fill that the inserted book never reaches.
    steer = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.54),
        dict(market_slug="m", bucket=B(1), bid=0.40, ask=0.52),  # phantom
        dict(market_slug="m", bucket=B(2), bid=0.50, ask=0.54),
        dict(market_slug="m", bucket=B(3), bid=0.52, ask=0.56)])
    o3 = fps.simulate(steer, 0.02)
    n3 = simulate_inserted(steer, 0.02)
    o3_real = o3[~o3.phantom]
    check("phantom-excluded scoring and insertion DISAGREE on the path "
          f"(excluded n={len(o3_real)}, inserted n={len(n3)})",
          len(o3_real) != len(n3) or not np.allclose(
              sorted(o3_real.quote_price), sorted(n3.quote_price)))
    print(f"    excluded keeps {list(zip(o3_real.side, o3_real.quote_price))}")
    print(f"    inserted keeps {list(zip(n3.side, n3.quote_price))}")

    # 4. KNOWN ANSWER, and the check that validates this whole file against
    #    the reviewed simulator: at k=0 there is no lean, so inventory
    #    cannot steer the quote path, so phantom-driven q is inert and the
    #    two methods MUST select the identical fill set. If this ever fails,
    #    simulate_inserted has a bug that is not about phantoms at all.
    rng = np.random.default_rng(7)
    walk, p = [], 0.50
    for i in range(400):
        # volatile enough that the touch genuinely crosses our resting
        # quotes: a quiet walk yields ~3 fills and tests nothing
        p = float(np.clip(p + rng.normal(0, 0.02), 0.05, 0.95))
        s = float(rng.choice([0.01, 0.02, 0.03, 0.06]))
        walk.append(dict(market_slug="w", bucket=B(i),
                         bid=round(p - s / 2, 4), ask=round(p + s / 2, 4)))
    w = pd.DataFrame(walk)
    a = fps.simulate(w, 0.0)
    a = a[~a.phantom].reset_index(drop=True)
    b = simulate_inserted(w, 0.0).reset_index(drop=True)
    same = (len(a) == len(b) and len(a) > 20
            and np.allclose(a.quote_price.values, b.quote_price.values)
            and list(a.side) == list(b.side))
    check(f"k=0: exclusion and insertion select the SAME fills "
          f"(n={len(a)} vs {len(b)})", same)
    return fails


def main():
    real = pd.read_csv(FILLS, parse_dates=["quoted_at", "filled_at"])
    real = real[(real.regime == "ingame")
                & real.market_slug.str.contains("-wnba-")]
    settle = real.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug").settlement
    games = real.drop_duplicates("market_slug").set_index(
        "market_slug").game_id
    mkts = sorted(real.market_slug.unique())
    cycles = load_cycles(mkts)

    # COVERAGE GATE: a replay grid that omits markets silently answers a
    # different question than the one asked. Report it, always.
    covered = set(cycles.market_slug.unique())
    missing = [m for m in mkts if m not in covered]
    print(f"replay grid: {len(cycles):,} cycles over "
          f"{len(covered)}/{len(mkts)} markets with fills")
    if missing:
        n_lost = int(real.market_slug.isin(missing).sum())
        print(f"  WARNING: {len(missing)} markets absent from the grid "
              f"({n_lost} fills, {n_lost/len(real):.1%} of the population)")

    print("\n=== FLATTEN k-curve: phantom-EXCLUDED vs order-INSERTED ===")
    print("excluded = phantoms dropped from P&L but still driving inventory")
    print("inserted = phantoms never happen, so they never drive anything\n")
    print(f"{'k':>5s} {'excl fills':>11s} {'excl P&L':>10s} "
          f"{'ins fills':>10s} {'ins P&L':>9s} {'ins per-fill':>13s} "
          f"{'ins per-game (clustered)':>28s}")
    ins = {}
    for k in K_GRID:
        e = fps.score(fps.simulate(cycles, k), settle, games)
        e = e[~e.phantom]
        n = fps.score(simulate_inserted(cycles, k), settle, games)
        ins[k] = n
        pf = f"{n.pnl.mean()*100:+.2f}c" if len(n) else "n/a"
        print(f"{k*100:>4.0f}c {len(e):>11d} {e.pnl.sum():>+10.2f} "
              f"{len(n):>10d} {n.pnl.sum():>+9.2f} {pf:>13s}", end="")
        base = ins[0.0].groupby("game_id").pnl.sum()
        d = (n.groupby("game_id").pnl.sum() - base).reindex(
            base.index).fillna(0.0)
        cm = clustered_mean({g: [v] for g, v in d.items()})
        print(f" {f'{cm.mean:+.2f} [{cm.lo:+.2f}, {cm.hi:+.2f}]':>28s}"
              if cm else f" {'n/a':>28s}")

    tot = {k: v.pnl.sum() for k, v in ins.items()}
    pos = [k for k, v in tot.items() if v > tot[0.0]]
    best = max(tot, key=tot.get)
    print(f"\nk values beating k=0 on the inserted book: "
          f"{[f'{k*100:.0f}c' for k in pos] or 'NONE'}")
    print(f"best k on the inserted book: {best*100:.0f}c "
          f"({tot[best]:+.2f}); per-fill {ins[best].pnl.mean()*100:+.2f}c")
    print(f"every k negative per fill: "
          f"{all(v.pnl.mean() < 0 for v in ins.values() if len(v))}")
    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    main()
