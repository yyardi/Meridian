#!/usr/bin/env python3
"""THE SANDBOX — run a strategy on recorded tape and get a number. One command.

WHY THIS EXISTS (operator, 2026-09-04): *"the only thing which is called
progress is when u go out and test a strategy it works and we deploy it live
and it works."* We had 38 analysis scripts, four replay engines, and no front
door — so every strategy question became a bespoke query, and half our failures
were self-inflicted plumbing rather than strategy work.

This is the front door. Pick a sport, pick a strategy, pick a wallet size, get
a scored answer. No credentials, no deploy, no prod write, no engine restart.

    python3 scripts/sandbox.py --list
    python3 scripts/sandbox.py --sport cfb --strategy quote --wallet 10000
    python3 scripts/sandbox.py --sport wnba --strategy quote --wallet 1000 --since 2026-08-01

DESIGN RULES, so this stays simple:
  1. READ-ONLY. It never writes to the database and never places an order.
  2. It reports SETTLEMENT P&L, game-clustered, because that is the money and
     games are the independent unit (WAVE_STANDARD; capture-vs-mid is retired
     as an identity, not a measurement).
  3. It prints the numerator, denominator and per-event mean together — never a
     composite alone (rule 25: a metric that moves with activity ranks activity).
  4. A zero prints its provenance, never bare (rule 22).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --------------------------------------------------------------------------
# Strategies. Add one here and it appears in --list automatically.
# --------------------------------------------------------------------------

STRATEGIES: dict[str, str] = {
    "quote": "Shadow market maker — quotes both sides at the touch (the v1 engine).",
    "quote-guarded": "Same, but withdraws a side once fills go >=65% one-way "
                     "(the circuit breaker; measured -10.91c vs -1.68c balanced).",
}

SPORTS: dict[str, str] = {
    "wnba": "basketball · MERIDIAN",
    "nfl": "football · GRIDIRON",
    "cfb": "college football · GRIDIRON",
}


@dataclass
class Result:
    strategy: str
    sport: str
    wallet: float
    fills: int
    games: int
    settled: int
    pnl_per_fill_c: float
    ci_lo_c: float
    ci_hi_c: float
    wallet_end: float
    one_sided_fills: int
    note: str = ""


def _engine(url: str | None = None):
    from sqlalchemy import create_engine
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("set DATABASE_URL (or pass --db) — the sandbox reads the recorded tape")
    return create_engine(url, pool_pre_ping=True)


SQL = """
WITH f AS (
  SELECT game_id, market_slug, side, quote_price, settlement,
         (CASE WHEN side='bid' THEN settlement-quote_price
               ELSE quote_price-settlement END)::numeric AS pnl
  FROM shadow_quote_fills
  WHERE settlement IS NOT NULL
    AND market_slug LIKE :slug_like
    AND filled_at >= :since
),
sided AS (
  SELECT game_id, market_slug,
         greatest(count(*) FILTER (WHERE side='bid'),
                  count(*) FILTER (WHERE side='ask'))::float / count(*) AS onesided,
         count(*) AS n
  FROM f GROUP BY 1,2
),
kept AS (
  SELECT f.* FROM f JOIN sided s USING (game_id, market_slug)
  WHERE (:guard = 0) OR s.onesided < 0.65 OR s.n < 4
),
per_game AS (SELECT game_id, avg(pnl) m, count(*) n FROM kept GROUP BY 1)
SELECT (SELECT count(*) FROM kept)                                AS fills,
       (SELECT count(*) FROM per_game)                            AS games,
       (SELECT count(*) FROM f)                                   AS fills_before_guard,
       (SELECT coalesce(avg(m),0) FROM per_game)                  AS mean_pnl,
       (SELECT coalesce(stddev(m),0) FROM per_game)               AS sd_pnl,
       (SELECT coalesce(sum(pnl),0) FROM kept)                    AS total_pnl
"""


def run(sport: str, strategy: str, wallet: float, since: str, db: str | None) -> Result:
    from sqlalchemy import text
    guard = 1 if strategy == "quote-guarded" else 0
    eng = _engine(db)
    with eng.connect() as c:
        row = c.execute(text(SQL), {
            "slug_like": f"%-{sport}-%", "since": since, "guard": guard}).one()

    fills, games, before, mean, sd, total = row
    mean, sd, total = float(mean), float(sd), float(total)
    half = (1.96 * sd / (games ** 0.5)) if games > 1 else 0.0
    return Result(
        strategy=strategy, sport=sport, wallet=wallet,
        fills=int(fills), games=int(games), settled=int(fills),
        pnl_per_fill_c=mean * 100,
        ci_lo_c=(mean - half) * 100, ci_hi_c=(mean + half) * 100,
        wallet_end=wallet + total,
        one_sided_fills=int(before) - int(fills),
        note="" if fills else "no settled fills matched — check --sport and --since",
    )


def report(r: Result) -> None:
    w = 62
    print("=" * w)
    print(f" SANDBOX · {r.strategy} · {r.sport} · wallet ${r.wallet:,.0f}")
    print("=" * w)
    if not r.fills:
        # rule 22: a zero never prints bare.
        print(f"  NO SETTLED FILLS — {r.note}")
        print("  This is an EMPTY QUERY, not a measured zero.")
        print("=" * w)
        return

    # rule 25: numerator, denominator and per-event mean travel together.
    print(f"  fills (settled)      {r.fills:>12,}")
    print(f"  games                {r.games:>12,}   <- the independent unit")
    if r.one_sided_fills:
        print(f"  withdrawn by guard   {r.one_sided_fills:>12,}   (one-sided markets)")
    print()
    print(f"  P&L per fill         {r.pnl_per_fill_c:>+11.2f}c")
    print(f"  game-clustered CI    [{r.ci_lo_c:+.2f}c, {r.ci_hi_c:+.2f}c]"
          f"{'  EXCLUDES ZERO' if r.ci_lo_c * r.ci_hi_c > 0 else '  spans zero'}")
    print()
    print(f"  wallet  ${r.wallet:,.2f}  ->  ${r.wallet_end:,.2f}"
          f"   ({(r.wallet_end/r.wallet-1)*100:+.2f}%)")
    print("=" * w)
    print("  settlement P&L, game-clustered. Capture-vs-mid is retired (identity).")
    print("  In-sample on recorded tape. The forward test is the evidence.")
    print("=" * w)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a strategy on recorded tape.")
    ap.add_argument("--sport", choices=sorted(SPORTS))
    ap.add_argument("--strategy", choices=sorted(STRATEGIES))
    ap.add_argument("--wallet", type=float, default=1000.0)
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--db", default=None, help="DATABASE_URL override")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list or not (a.sport and a.strategy):
        print("\nSPORTS:")
        for k, v in SPORTS.items():
            print(f"  {k:<6} {v}")
        print("\nSTRATEGIES:")
        for k, v in STRATEGIES.items():
            print(f"  {k:<14} {v}")
        print("\n  python3 scripts/sandbox.py --sport cfb --strategy quote --wallet 10000\n")
        return 0

    report(run(a.sport, a.strategy, a.wallet, a.since, a.db))
    return 0


if __name__ == "__main__":
    sys.exit(main())
