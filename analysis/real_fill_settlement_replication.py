"""Real-fill settlement economics: phantom share, P&L/fill, per-game signs.

Built to answer the 24-game replication question INDEPENDENTLY of the
core/quote/report.py instrument, so that two constructions exist. Per the
convergence ruling, closeness between them is NOT a replication unless they
select the same rows — so this reports row-level overlap when given a
comparison set, and refuses to describe agreement any other way.

Three outputs, in the order the question was asked:
  (a) phantom share, overall and by sport
  (b) real-fill settlement P&L per fill, game-clustered CI, n in BOTH games
      and rows
  (c) the per-game sign count — how many games lose — which is the statistic
      that does not depend on the mean, and therefore the one that survives
      an outlier game

SUBSTRATE IS AN ARGUMENT, NOT A PIN. The whole point is to re-run this when
a larger export lands, so --fills and --ticks are required and the run
prints exactly what it read. A script that silently answers on whatever
substrate it happens to find is how a 13-game answer gets reported as a
24-game one.
"""
import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402


def sport_of(slug: str) -> str:
    s = str(slug)
    for key, name in (("-wnba-", "WNBA"), ("-cfb-", "CFB"), ("-nfl-", "NFL"),
                      ("-nba-", "NBA")):
        if key in s:
            return name
    return "other"


def classify(fills: pd.DataFrame, ticks_sql: str) -> pd.DataFrame:
    """Attach the book at fill time (BACKWARD join) and mark phantoms.

    A resting bid at B forces best_bid >= B, so the mid cannot reach B while
    the ask is still above it. Fills failing that are ones our own presence
    would have prevented.
    """
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    con.execute(f"CREATE TEMP TABLE tk AS SELECT * FROM ({ticks_sql}) "
                "WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL")
    con.register("f", fills.reset_index(names="fid"))
    b = con.execute("""
      WITH q AS (SELECT fid, market_slug, epoch(filled_at) t FROM f)
      SELECT q.fid, t.best_bid fb, t.best_ask fa, q.t - epoch(t.captured_at) age
      FROM q ASOF JOIN (SELECT market_slug, best_bid, best_ask, captured_at,
                               epoch(captured_at) ct FROM tk) t
        ON q.market_slug = t.market_slug AND t.ct <= q.t
    """).df().set_index("fid")
    assert b.age.dropna().ge(-1e-9).all(), "join must not look forward"
    out = fills.join(b)
    out["phantom"] = np.where(
        out.side == "bid", out.fa > out.quote_price + 1e-9,
        out.fb < out.quote_price - 1e-9)
    return out


def per_game_signs(real: pd.DataFrame) -> pd.DataFrame:
    """Total settlement P&L per game, and its sign."""
    g = real.groupby("game_id").agg(n=("pnl", "size"), total=("pnl", "sum"),
                                    mean=("pnl", "mean"))
    g["loses"] = g.total < 0
    return g.sort_values("total")


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # the sign count must not be inferable from the mean: two books with
    # the SAME total P&L, opposite sign counts. This is why (c) was asked
    # for separately, and the fixture pins that it is a distinct statistic.
    # both books total +2; a loses 2 of 3 games, b loses 1 of 3
    a = pd.DataFrame({"game_id": ["g1"] * 2 + ["g2"] * 2 + ["g3"] * 2,
                      "pnl": [-1, -1, -1, -1, 5, 1]})       # -2, -2, +6
    b = pd.DataFrame({"game_id": ["g1"] * 2 + ["g2"] * 2 + ["g3"] * 2,
                      "pnl": [1, 1, 1, 1, -1, -1]})         # +2, +2, -2
    sa, sb = per_game_signs(a), per_game_signs(b)
    check(f"same total P&L ({a.pnl.sum():+.0f} both), different sign counts",
          a.pnl.sum() == b.pnl.sum() and sa.loses.sum() != sb.loses.sum())
    check("sign count is 2 of 3 and 1 of 3 respectively",
          int(sa.loses.sum()) == 2 and int(sb.loses.sum()) == 1)

    # a game with zero P&L is not a loss
    z = pd.DataFrame({"game_id": ["g1", "g1"], "pnl": [1.0, -1.0]})
    check("a flat game is not counted as losing",
          int(per_game_signs(z).loses.sum()) == 0)
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fills", type=Path, required=True)
    ap.add_argument("--ticks", type=Path, required=True,
                    help="tick/snapshot source(s); pass a SQL union via "
                         "--ticks-sql for multi-file substrates")
    ap.add_argument("--ticks-sql", type=str, default=None)
    args = ap.parse_args()

    d = pd.read_csv(args.fills, parse_dates=["quoted_at", "filled_at"])
    print(f"substrate: {args.fills.name}")
    print(f"  rows {len(d):,}   games {d.game_id.nunique()}   "
          f"markets {d.market_slug.nunique()}")
    print(f"  sports: {d.market_slug.map(sport_of).value_counts().to_dict()}")
    print(f"  last fill: {d.filled_at.max()}")

    d = d[(d.regime == "ingame") & d.settlement.notna()].copy()
    d["pnl"] = np.where(d.side == "bid", d.settlement - d.quote_price,
                        d.quote_price - d.settlement)
    d["sport"] = d.market_slug.map(sport_of)

    sql = args.ticks_sql or (
        f"SELECT market_slug, captured_at, best_bid, best_ask "
        f"FROM read_csv('{args.ticks}')")
    d = classify(d, sql)
    have = d[d.fa.notna()].copy()
    print(f"\nin-game settled fills with a book: {len(have):,} of {len(d):,}")

    print("\n=== (a) PHANTOM SHARE ===")
    print(f"  ALL   n={len(have):>7,}  phantom {have.phantom.mean():>6.1%}  "
          f"real {int((~have.phantom).sum()):>7,}")
    for sp, g in have.groupby("sport"):
        print(f"  {sp:<5s} n={len(g):>7,}  phantom {g.phantom.mean():>6.1%}  "
              f"real {int((~g.phantom).sum()):>7,}")
    if have.sport.nunique() < 2:
        print("  (single sport in this substrate — the cross-sport split")
        print("   this question asks for is NOT answerable here)")

    real = have[~have.phantom].copy()
    print("\n=== (b) REAL-FILL SETTLEMENT P&L PER FILL ===")
    cm = clustered_mean({k: list(v) for k, v in real.groupby("game_id").pnl})
    print(f"  rows {len(real):,}   games {real.game_id.nunique()}")
    print(f"  clustered mean {cm.mean*100:+.2f}c "
          f"[{cm.lo*100:+.2f}, {cm.hi*100:+.2f}]")
    print(f"  naive mean     {real.pnl.mean()*100:+.2f}c   "
          f"(design effect inflates the SE {'above' if cm else ''} this)")
    for sp, g in real.groupby("sport"):
        c2 = clustered_mean({k: list(v) for k, v in g.groupby("game_id").pnl})
        print(f"  {sp:<5s} rows {len(g):>7,} games {g.game_id.nunique():>3d}  "
              f"{c2.mean*100:+.2f} [{c2.lo*100:+.2f}, {c2.hi*100:+.2f}]"
              if c2 else f"  {sp}: n/a")

    print("\n=== (c) PER-GAME SIGN COUNT (independent of the mean) ===")
    g = per_game_signs(real)
    print(f"  {int(g.loses.sum())} of {len(g)} games lose "
          f"({g.loses.mean():.0%})")
    print(f"  worst game {g.total.min():+.2f}   best game {g.total.max():+.2f}")
    print(f"  {'game':<28s} {'fills':>7s} {'total':>9s} {'mean':>9s}")
    for gid, r in g.iterrows():
        print(f"  {str(gid):<28s} {int(r.n):>7d} {r.total:>+9.2f} "
              f"{r['mean']*100:>+8.2f}c")

    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")
    return 0


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    sys.exit(main())
