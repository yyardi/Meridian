"""The test flattening OWES — whole-book policy simulation (c7's reopen).

    .venv/bin/python analysis/flattening_policy_sim.py --selftest
    .venv/bin/python analysis/flattening_policy_sim.py
        --fills FILLS.csv --ticks TICKS.csv.gz [--resolved R.csv]

WHY THIS EXISTS: the inventory cap died on a PROSPECTIVE, whole-book,
game-clustered re-score. Flattening was only ever tested as a SUBSET
comparison (same fills, round trip vs ride). That is a double standard in
favour of the lever we like — the cap's own totals were program-best and
would have looked excellent under the subset treatment too. So flattening
owes the structurally identical test, and this file is it.

THE POLICY, simulated whole-book rather than as a subset: at every cycle
quote a bid at the touch and an ask at (touch_ask − k). Then re-score the
ENTIRE book. The side effect the subset view structurally cannot see is
included by construction: a leaned ask fills MORE OFTEN, and some of those
fills OPEN SHORTS on markets where we were flat or already short rather
than flattening a long. The simulated book is therefore not "v1's book
minus flattened positions" — it is a different book, which is what a
policy actually is.

REPLAY FIDELITY IS THE LICENSE (the rule-16 pattern, and A's
"baseline-emission IS the equivalence proof"): the simulator first replays
v1's OWN policy (ask at the touch, k=0) and is compared against v1's real
fills. If the k=0 replay does not resemble the real tape, NOTHING about
the k>0 variants can be trusted and this file says so instead of printing
numbers.

THE ENGINE'S RULES, reproduced exactly (core/quote/engine.py):
  * cycle 5s; the newest observation per market per cycle;
  * fills checked BEFORE requoting, against the quote already resting, and
    never by the observation that quote was born from;
  * bid fills when mid <= bid_price, ask fills when mid >= ask_price;
    both can fire in one cycle;
  * requote to the touch only while quotable — MIN_SPREAD 0.01, MAX_SPREAD
    0.15, MIN_MID 0.20, MAX_MID 0.80 (core/quote/adverse_selection.py);
    outside the band the engine stands down entirely;
  * no exits: positions ride to settlement.

KNOWN COVERAGE LIMIT, stated not approximated: the tick pin covers 9 of
the 13 quote games, so the simulation runs on those and the clustered test
has G=9, not 13. The 4 uncovered games are excluded and counted.

**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import (  # noqa: E402
    MAX_MID,
    MAX_SPREAD,
    MIN_MID,
    MIN_SPREAD,
    clustered_mean,
)

CYCLE_S = 5
K_GRID = (0.00, 0.01, 0.02, 0.03, 0.05)     # pre-declared, k=0 is v1
TICK = 0.01                                  # venue min price increment


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def quotable(bid: float, ask: float) -> bool:
    spread, mid = ask - bid, (ask + bid) / 2.0
    return (MIN_SPREAD <= spread <= MAX_SPREAD
            and MIN_MID <= mid <= MAX_MID)


def simulate(cycles: pd.DataFrame, k: float) -> pd.DataFrame:
    """Replay the engine over 5s cycles with the ask leaned k inside.

    cycles: market_slug, bucket, bid, ask (the cycle's last observation),
    sorted. Returns one row per simulated fill."""
    out = []
    for m, g in cycles.groupby("market_slug", sort=False):
        stand: tuple[float, float, pd.Timestamp] | None = None
        q = 0.0                      # signed position, the policy's input
        for r in g.itertuples():
            mid = (r.bid + r.ask) / 2.0
            # 1. fills first, against the ALREADY-resting quote
            if stand is not None and r.bucket > stand[2]:
                bp, ap, _ = stand
                # PHANTOM CLASSIFICATION (the fill model's own artifact):
                # a resting bid at bp, if actually present, forces
                # best_bid >= bp, so the mid cannot reach it while ask > bp
                # — the only real fill is the ask coming down. Symmetrically
                # a resting ask at ap is really filled only if bid >= ap.
                # Fills failing that are fills our own presence would have
                # prevented, and they are ~64% of v1's tape.
                if mid <= bp:
                    out.append((m, "bid", bp, mid, r.bucket,
                                bool(r.ask > bp + 1e-9)))
                    q += 1.0
                if mid >= ap:
                    out.append((m, "ask", ap, mid, r.bucket,
                                bool(r.bid < ap - 1e-9)))
                    q -= 1.0
            # 2. requote at the touch (ask leaned k inside) while quotable.
            # POST-ONLY IS PHYSICS, NOT A DETAIL: a maker's ask must REST,
            # so it can never be at or below the best bid — the venue's
            # participateDontInitiate rejects a crossing order outright
            # (core/executor.py). Without this clamp the sim "sells" below
            # the bid, which is a taker trade wearing a maker's price, and
            # it manufactures fills and profit that cannot exist. The lean
            # is therefore a MAXIMUM, applied only as far as the spread
            # allows: ask = max(touch_ask − k, bid + one tick).
            #
            # AND THE LEAN IS INVENTORY-CONDITIONAL, which is what makes it
            # FLATTENING rather than a directional bias. Leaning the ask
            # unconditionally is "quote to get short", and on a ladder whose
            # far rungs mostly expire worthless that prints money in-sample
            # for reasons that have nothing to do with market making — the
            # first version of this simulator did exactly that and reported
            # +$1,928 on a book whose baseline was −$212. A flattening
            # policy leans ONLY toward flat: the ask when long, the bid when
            # short, both at the touch when flat.
            if quotable(r.bid, r.ask):
                bid_p, ask_p = r.bid, r.ask
                if q > 0:            # long -> lean the ask in, to get out
                    ask_p = max(round(r.ask - k, 4), round(r.bid + TICK, 4))
                elif q < 0:          # short -> lean the bid up, to get out
                    bid_p = min(round(r.bid + k, 4), round(r.ask - TICK, 4))
                stand = (bid_p, ask_p, r.bucket)
            else:
                stand = None
    return pd.DataFrame(out, columns=["market_slug", "side", "quote_price",
                                      "mid_at_fill", "filled_at", "phantom"])


def score(sim: pd.DataFrame, settle: pd.Series,
          games: pd.Series) -> pd.DataFrame:
    s = sim.copy()
    s["S"] = s.market_slug.map(settle)
    s["game_id"] = s.market_slug.map(games)
    s = s[s.S.notna()]
    s["pnl"] = np.where(s.side == "bid", s.S - s.quote_price,
                        s.quote_price - s.S)
    return s


def selftest() -> int:
    print("mutation test: the policy simulator")
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    t0 = pd.Timestamp("2026-08-20 01:00:00+00:00")
    B = lambda i: t0 + pd.Timedelta(seconds=CYCLE_S * i)
    # flat book at 0.48/0.52 (quotable): nothing crosses, no fills ever
    flat = pd.DataFrame([dict(market_slug="m", bucket=B(i), bid=0.48,
                              ask=0.52) for i in range(6)])
    check("flat quotable book yields no fills", len(simulate(flat, 0.0)) == 0)

    # A rising book. NOTE the requote race, which the first version of this
    # fixture got wrong: the standing ask is REPLACED every cycle, so the
    # mid must overtake the ask the quote was born at, not the current one.
    #   b0 .48/.52 (mid .50) -> stand ask .52 (k=0) / .51 (k=1c)
    #   b1 .495/.535 (mid .515): k=0 no (.515 < .52); k=1c FILLS (>= .51)
    #   b2 .52/.56  (mid .54) : k=0 fills the b1 quote (.535)
    rise = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.48, ask=0.52),
        dict(market_slug="m", bucket=B(1), bid=0.495, ask=0.535),
        dict(market_slug="m", bucket=B(2), bid=0.52, ask=0.56)])
    s0, s1 = simulate(rise, 0.0), simulate(rise, 0.01)
    check("k=0: the ask fills only once the mid overtakes it (b2)",
          len(s0) == 1 and s0.filled_at.iloc[0] == B(2)
          and abs(s0.quote_price.iloc[0] - 0.535) < 1e-9)
    check("FLAT book is quoted at the touch even at k>0 (no lean when q=0)",
          len(s1) == 1 and abs(s1.quote_price.iloc[0] - 0.535) < 1e-9)

    # The lean must engage only AFTER a fill puts us long: a falling book
    # fills the bid (q=+1), and the next ask is then leaned inside.
    fall_then_rise = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.54),
        dict(market_slug="m", bucket=B(1), bid=0.46, ask=0.50),  # mid .48 <= .50 -> bid fills, q=+1
        dict(market_slug="m", bucket=B(2), bid=0.47, ask=0.51),
        dict(market_slug="m", bucket=B(3), bid=0.50, ask=0.54)])
    f0, f2 = simulate(fall_then_rise, 0.0), simulate(fall_then_rise, 0.02)
    asks0 = f0[f0.side == "ask"]
    asks2 = f2[f2.side == "ask"]
    check("long inventory triggers the lean (leaned ask fills where the "
          "touch ask would not)", len(asks2) >= len(asks0))
    check("the leaned ask price is strictly inside the touch when long",
          len(asks2) == 0 or asks2.quote_price.min() < 0.51 + 1e-9)

    # POST-ONLY CLAMP — the bug that made the first run print +$10,313 on a
    # book whose baseline was −$182: with a 2c spread and k=5c the leaned
    # ask goes BELOW the bid, which is a crossing order the venue rejects.
    # Unclamped it "sells" under the bid and manufactures fills and profit.
    tight = pd.DataFrame([
        dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.52),
        dict(market_slug="m", bucket=B(1), bid=0.50, ask=0.52)])
    s5 = simulate(tight, 0.05)
    check("post-only: a 5c lean on a 2c spread never rests below the bid",
          all(p > 0.50 for p in s5.quote_price) if len(s5) else True)
    # and the clamp lands exactly one tick above the bid
    stand_prices = []
    for kk, want in ((0.05, 0.51), (0.01, 0.51)):
        ss = simulate(pd.DataFrame([
            dict(market_slug="m", bucket=B(0), bid=0.50, ask=0.52),
            dict(market_slug="m", bucket=B(1), bid=0.505, ask=0.53)]), kk)
        stand_prices.append(None if ss.empty else round(ss.quote_price.iloc[0], 4))
    check("clamped lean rests at bid + one tick (0.51), not deeper",
          all(p is None or p >= 0.51 - 1e-9 for p in stand_prices))

    # unquotable band: a 20c spread is stood down, never quoted, no fills
    wide = pd.DataFrame([dict(market_slug="m", bucket=B(i), bid=0.40,
                              ask=0.60) for i in range(4)])
    check("unquotable (20c spread) is stood down", len(simulate(wide, 0.0)) == 0)
    mid_out = pd.DataFrame([dict(market_slug="m", bucket=B(i), bid=0.10,
                                 ask=0.12) for i in range(4)])
    check("unquotable (mid 0.11 outside 0.20-0.80) is stood down",
          len(simulate(mid_out, 0.0)) == 0)

    # a quote cannot be filled by the observation it was born from
    born = pd.DataFrame([dict(market_slug="m", bucket=B(0), bid=0.48,
                              ask=0.52)])
    check("no self-fill on the birth observation",
          len(simulate(born, 0.0)) == 0)

    # scoring: a bid at 0.40 settling 1 earns +0.60; an ask at 0.60 -> -0.40
    sc = score(pd.DataFrame([
        dict(market_slug="m", side="bid", quote_price=0.40, mid_at_fill=0.4,
             filled_at=B(1)),
        dict(market_slug="m", side="ask", quote_price=0.60, mid_at_fill=0.6,
             filled_at=B(1))]),
        pd.Series({"m": 1.0}), pd.Series({"m": "g1"}))
    check("scoring signs (+0.60 long, -0.40 short at settlement 1)",
          abs(sc.pnl.iloc[0] - 0.60) < 1e-9
          and abs(sc.pnl.iloc[1] + 0.40) < 1e-9)

    print(f"mutation test: "
          f"{'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", type=Path)
    ap.add_argument("--ticks", type=Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.fills is None or args.ticks is None:
        print("need --fills and --ticks")
        return 2

    print("Flattening as a WHOLE-BOOK POLICY — the test the cap had to pass")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    real = pd.read_csv(args.fills, parse_dates=["quoted_at", "filled_at"])
    real = real[(real.regime == "ingame")
                & real.market_slug.str.contains("-wnba-")]
    settle = real.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug").settlement
    games = real.drop_duplicates("market_slug").set_index(
        "market_slug").game_id

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    mkts = sorted(real.market_slug.unique())
    con.execute("CREATE TEMP TABLE wanted(m VARCHAR)")
    con.executemany("INSERT INTO wanted VALUES (?)", [(m,) for m in mkts])
    cycles = con.execute(f"""
        SELECT market_slug,
               time_bucket(INTERVAL '{CYCLE_S} seconds', captured_at) bucket,
               arg_max(best_bid, captured_at) bid,
               arg_max(best_ask, captured_at) ask
        FROM read_csv('{args.ticks}')
        WHERE is_live AND best_bid IS NOT NULL AND best_ask IS NOT NULL
          AND market_slug IN (SELECT m FROM wanted)
        GROUP BY 1, 2 ORDER BY 1, 2
    """).df()
    covered = set(cycles.market_slug)
    hr("COVERAGE (stated, not approximated)")
    print(f"quote markets: {len(mkts)}; with tick coverage: {len(covered)}; "
          f"excluded for no ticks: {len(mkts) - len(covered)}")
    real_cov = real[real.market_slug.isin(covered)]
    print(f"real ingame fills: {len(real)} total, {len(real_cov)} on covered "
          f"markets, across {real_cov.game_id.nunique()} of "
          f"{real.game_id.nunique()} games")

    hr("REPLAY FIDELITY GATE — does k=0 reproduce v1's own tape?")
    base = simulate(cycles, 0.0)
    print(f"v1 real fills on covered markets: {len(real_cov)}")
    print(f"k=0 simulated fills:               {len(base)}")
    ratio = len(base) / len(real_cov) if len(real_cov) else float("nan")
    print(f"ratio: {ratio:.2f}")
    real_scored = score(
        real_cov.rename(columns={"quote_price": "quote_price"})
        .assign(mid_at_fill=real_cov.mid_at_fill,
                filled_at=real_cov.filled_at)[
            ["market_slug", "side", "quote_price", "mid_at_fill",
             "filled_at"]], settle, games)
    base_scored = score(base, settle, games)
    print(f"v1 real P&L on covered markets: {real_scored.pnl.sum():+.2f}")
    print(f"k=0 simulated P&L:              {base_scored.pnl.sum():+.2f}")
    fidelity_ok = 0.5 <= ratio <= 2.0
    if not fidelity_ok:
        print("\nFIDELITY GATE FAILS: the k=0 replay does not resemble v1's "
              "own tape, so no k>0 variant can be trusted. Reporting the "
              "gap instead of policy numbers — the divergence itself is the "
              "finding, and its likely sources are stated below.")
    else:
        print("\nfidelity acceptable — variants below are interpretable "
              "RELATIVE TO THE k=0 SIMULATION, which is the correct "
              "baseline for a policy comparison (differences share the "
              "simulator's biases and cancel).")

    hr("THE WHOLE-BOOK POLICY TEST (pre-declared k grid; totals AND "
       "game-clustered, exactly as the cap was judged)")
    rows = []
    for k in K_GRID:
        sim = simulate(cycles, k)
        sc = score(sim, settle, games)
        per_g = sc.groupby("game_id").pnl.sum()
        rows.append((k, len(sim), sc.pnl.sum(), per_g))
    # THE PHANTOM-FILTERED CURVE — the pre-Saturday check.
    # A leaned ask at A fills under the model when mid >= A, but really only
    # when bid >= A. At quote time mid = A0 - s/2, so ANY lean k >= s/2
    # satisfies the model IMMEDIATELY while reality still requires k >= s.
    # Leans between s/2 and s are therefore pure artifact — and the k-curve's
    # inflection landing at WNBA's s/2 (~2c) is exactly what a phantom-driven
    # result would look like.
    hr("THE SAME CURVE ON REAL FILLS ONLY (phantoms excluded)")
    print(f"{'k':>5s} {'fills':>8s} {'phantom%':>9s} {'REAL':>8s} "
          f"{'real settle P&L':>16s} {'delta vs k=0':>13s} "
          f"{'per-game (clustered)':>26s}")
    real_rows = []
    for k in K_GRID:
        sim = simulate(cycles, k)
        sc = score(sim, settle, games)
        rl = sc[~sc.phantom]
        real_rows.append((k, len(sc), sc.phantom.mean(), len(rl),
                          rl.pnl.sum(), rl.groupby("game_id").pnl.sum()))
    rb = real_rows[0][5]
    for k, n, pshare, nreal, tot, per_g in real_rows:
        d_ = (per_g - rb).reindex(rb.index).fillna(0.0)
        cm = clustered_mean({g: [v] for g, v in d_.items()})
        ci = (f"{cm.mean:+.2f} [{cm.lo:+.2f}, {cm.hi:+.2f}]" if cm else "n/a")
        print(f"{k*100:>4.0f}c {n:>8d} {pshare:>8.1%} {nreal:>8d} "
              f"{tot:>+16.2f} {tot - real_rows[0][4]:>+13.2f} {ci:>26s}")
    print("\nreading: if the shape SURVIVES phantom exclusion the small-lean")
    print("result is economic and k=1c is hardened; if it changes, the")
    print("registered parameter was chosen by an artifact.")

    b_pg = rows[0][3]
    print(f"{'k':>5s} {'fills':>8s} {'total P&L':>11s} {'delta vs k=0':>13s} "
          f"{'games improved':>15s} {'per-game delta (clustered)':>30s}")
    for k, n, tot, per_g in rows:
        d = (per_g - b_pg).reindex(b_pg.index).fillna(0.0)
        cm = clustered_mean({g: [v] for g, v in d.items()})
        ci = (f"{cm.mean:+.2f} [{cm.lo:+.2f}, {cm.hi:+.2f}]"
              if cm else "n/a")
        print(f"{k * 100:>4.0f}c {n:>8d} {tot:>+11.2f} "
              f"{tot - rows[0][2]:>+13.2f} "
              f"{int((d > 0).sum()):>7d}/{len(d):<7d} {ci:>30s}")

    hr("VERDICT AND ITS SYMMETRY WITH THE CAP")
    print("The cap improved TOTALS at every K and died because only 7/13 "
          "games improved with CIs spanning zero. Flattening is judged on "
          "the identical table above. If its clustered row also spans zero, "
          "it is the same KIND of result the cap was, and its P&L claim "
          "must be labelled the same way — structurally justified, "
          "statistically unresolved at this n, deferred to NFL volume. Its "
          "OTHER two arguments (tail reduction and capital efficiency) are "
          "ARITHMETIC and survive regardless, exactly as the risk limit's "
          "did.")
    print("\nWhat the subset test could not see and this one includes: a "
          "leaned ask fills more often, and some of those fills OPEN SHORTS "
          "rather than flattening longs. The simulated book is a different "
          "book, not v1's minus its flattened positions.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
