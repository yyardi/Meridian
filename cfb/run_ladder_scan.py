"""Report the venue's CURRENT ladder self-contradictions. Places nothing.

    python cfb/run_ladder_scan.py [--since 2026-09-13] [--league cfb|nfl|mlb]

Reads the latest recorded snapshot per market and applies core.ladder.scan.
It is a REPORT, not a strategy: §0bj measured that these quotes are never
consumed (23 shrank / 33 grew / 41 flat, median +0 contracts), so whether one
would fill is unknown and cannot be learned by looking. Nothing here decides to
trade; it makes the state visible so a human can.

Prices for the two legs come from ONE snapshot timestamp -- which means ONE
SWEEP, not one instant. recorder.py stamps every row in a cycle with the time
the cycle STARTED; measured fetch spread inside a stamp is median 5s, p90 14s,
max 110s (STATUS 0bs). Pregame that is nothing. In-play a scoring play can
re-price the winner while the sweep is still walking the spread rungs, so an
in-play "violation" here may be two prices that never coexisted. Only a
genuinely simultaneous fetch (one get_book per rung inside a few seconds, or
the venue's board in one call) can say whether a live violation is real. A ladder assembled
across timestamps is not an arbitrage, it is two prices that never coexisted --
which is why the query keys on (game, captured_at) rather than taking each
market's own latest row.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import scan  # noqa: E402

SQL = """
SELECT ms.game_id, ms.sports_market_type, ms.market_slug, ms.best_bid, ms.best_ask,
       ms.captured_at,
       (SELECT max(quantity) FROM book_levels b
         WHERE b.snapshot_id = ms.id AND b.level_index = 0 AND b.side = 'bid'),
       (SELECT max(quantity) FROM book_levels b
         WHERE b.snapshot_id = ms.id AND b.level_index = 0 AND b.side = 'offer')
FROM market_snapshots ms
WHERE ms.captured_at >= CAST(:since AS timestamptz)
  AND ms.market_slug LIKE :pat
  AND ms.sports_market_type IN (:winner, :spread)
  AND ms.best_bid IS NOT NULL AND ms.best_ask > ms.best_bid
  AND ms.game_start_time IS NOT NULL AND {phase}
"""
# max(quantity), not a bare subquery: book_levels holds DUPLICATE level_index=0
# rows for some snapshots -- worst seen 27 on NFL, 12 on CFB, mean 1.00. A
# scalar subquery raises "more than one row returned", which is how it surfaced.

SPORT = {"cfb": ("football_team_full_game_winner", "football_team_full_game_spread"),
         "nfl": ("football_team_full_game_winner", "football_team_full_game_spread"),
         "mlb": ("baseball_team_full_game_winner", "baseball_team_full_game_spread")}


def line_of(slug: str) -> float | None:
    """`...-neg-10pt5` -> -10.5. Verified against settled outcomes, not assumed:
    84,646 pairs over 144 CFB and NFL ladders, zero cases where the harder rung
    paid and the easier one did not."""
    m = re.search(r"-(neg|pos)-(\d+)pt(\d)$", slug)
    if not m:
        return None
    return (-1.0 if m.group(1) == "neg" else 1.0) * (
        float(m.group(2)) + float(m.group(3)) / 10.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-09-13")
    ap.add_argument("--league", default="cfb", choices=sorted(SPORT))
    # IN-PLAY IS THE DEFAULT, and this flag exists because it was not. The job
    # shipped scanning pregame only -- where the measured value is $414 -- while
    # the same scan run in-play is $9,900 (STATUS 0bp). Ordering falls from 85.4%
    # pregame to 67-78% live: the winner market re-prices every possession while
    # deep spread rungs sit at their last quote, so the dislocation IS the game
    # being played. Scanning pregame by default was watching the quiet half.
    ap.add_argument("--phase", default="inplay",
                    choices=("inplay", "pregame", "both"))
    a = ap.parse_args()
    from sqlalchemy import create_engine, text

    win, spr = SPORT[a.league]
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        phase = {"inplay": "ms.captured_at > ms.game_start_time",
                 "pregame": "ms.game_start_time > ms.captured_at",
                 "both": "TRUE"}[a.phase]
        rows = c.execute(text(SQL.format(phase=phase)),
                         {"since": a.since, "pat": f"%-{a.league}-%",
                          "winner": win, "spread": spr}).all()

    snaps: dict[tuple, dict[float, tuple]] = defaultdict(dict)
    for gid, mt, slug, bid, ask, ts, qb, qo in rows:
        if qb is None or qo is None:
            continue
        key = 0.0 if mt == win else line_of(slug)
        if key is None:
            continue
        snaps[(gid, ts)][key] = (float(bid), float(ask), float(qb), float(qo))

    found = []
    for (gid, _ts), rungs in snaps.items():
        found += scan.scan_ladder(gid, rungs)

    best = scan.best_per_game(found)
    print(f"ladder scan  league={a.league}  phase={a.phase}  since={a.since}")
    print(f"  {len(snaps):,} simultaneous ladders, {len(found):,} self-contradictions")
    if not found:
        print("  no violations -- the board is internally consistent")
        return 0
    print(f"  best single trade per game, summed: ${sum(best.values()):,.2f} "
          f"over {len(best)} games")
    print(f"  {'$':>9} {'edge':>7} {'size':>9}  lines")
    for v in sorted(found, key=lambda x: -x.dollars)[:10]:
        print(f"  {v.dollars:9,.2f} {v.edge*100:+6.2f}c {v.size:9,.0f}  "
              f"{v.high_line:+.1f}/{v.low_line:+.1f}  game {v.game}")
    print("  SIZE IS QUOTED, NOT FILLED. These quotes are not consumed when they")
    print("  stand (§0bj), so executability is unknown. This report places nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
