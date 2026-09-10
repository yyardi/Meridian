"""Reconcile core/quote/move_trigger.py against the harness's move count.

Two implementations of the H1c rule -- the harness's MOVE_STRATUM block and
the live MoveTrigger class -- fed the same tape must find the same number of
>=1c one-minute moves, under BOTH minute phases. They are written separately
and can disagree; that is the point. Run AFTER run_making_touch.py with
LEAGUE=both MOVE_STRATUM=1 (and MOVE_PHASE=utc) and pass its two totals:

    { sed '/^if __name__/,$d' core/quote/move_trigger.py; cat cfb/run_trigger_replay.py; } \\
      | ssh ubuntu@$H "$D -e HARNESS_KICKOFF=865 -e HARNESS_UTC=852 meridian-trainer python3 -"

The trigger class is prepended at pipe time because core/quote/move_trigger.py
is not in the prod image and the prod checkout is read-only.
"""
import datetime as dt
import os
from collections import defaultdict

from sqlalchemy import create_engine, text

try:
    MoveTrigger  # noqa: F821  -- prepended by the pipe
except NameError:  # local use
    from core.quote.move_trigger import MoveTrigger  # noqa: F401

FEED_LAG = 30   # the harness's window: snapshots in [p_lo+30s, p_hi+330s]

# Anchor population = the harness's `plays`: backfill games (spread known,
# settled, not tied, mapped) win; live games (cfb not in backfill, and nfl)
# are added. ko = the first joinable play's wall clock.
ANCHORS_SQL = """
WITH bf AS (
  SELECT b.game_id eg, m.venue_game_id vg, min(b.wall_clock) ko, max(b.wall_clock) hi, 'cfb' lg
  FROM espn_cfb_backfill_plays b
  JOIN cfb_game_map m ON m.espn_game_id = b.game_id
  JOIN espn_cfb_backfill_games g ON g.game_id = b.game_id
  WHERE b.wall_clock IS NOT NULL AND b.down IS NOT NULL AND b.down > 0
    AND b.period IS NOT NULL AND NOT b.is_overtime AND g.spread IS NOT NULL
    AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    AND g.home_score <> g.away_score AND m.venue_game_id IS NOT NULL
  GROUP BY 1, 2),
final AS (
  SELECT DISTINCT ON (game_id) game_id, home_score, away_score, league
  FROM espn_cfb_game_state WHERE home_score IS NOT NULL
  ORDER BY game_id, first_seen_at DESC),
lv AS (
  SELECT p.game_id eg, m.venue_game_id vg, min(p.wall_clock) ko, max(p.wall_clock) hi, p.league lg
  FROM espn_cfb_live_plays p
  JOIN cfb_game_map m ON m.espn_game_id = p.game_id
  JOIN final f ON f.game_id = p.game_id AND f.league = p.league
  WHERE p.league IN ('cfb', 'nfl') AND p.wall_clock IS NOT NULL AND p.down IS NOT NULL
    AND p.down > 0 AND p.period IS NOT NULL AND NOT p.is_overtime
    AND m.venue_game_id IS NOT NULL AND f.home_score <> f.away_score
  GROUP BY 1, 2, 5)
SELECT eg, vg, ko, hi, lg, 'backfill' src FROM bf
UNION ALL
SELECT eg, vg, ko, hi, lg, 'live' src FROM lv WHERE eg NOT IN (SELECT eg FROM bf)
"""

SNAPS_SQL = """
SELECT game_id, captured_at, best_bid::float bid, best_ask::float ask
FROM market_snapshots
WHERE game_id = ANY(:gids) AND sports_market_type LIKE '%winner'
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
  AND captured_at BETWEEN :t_lo AND :t_hi
ORDER BY game_id, captured_at
"""

eng = create_engine(os.environ["DATABASE_URL"])
with eng.connect() as c:
    c.execute(text("SET max_parallel_workers_per_gather = 0"))
    anchors = [dict(r._mapping) for r in c.execute(text(ANCHORS_SQL))]
    p_lo = min(a["ko"] for a in anchors); p_hi = max(a["hi"] for a in anchors)
    snaps = [dict(r._mapping) for r in c.execute(text(SNAPS_SQL), {
        "gids": sorted({a["vg"] for a in anchors}),
        "t_lo": p_lo + dt.timedelta(seconds=FEED_LAG),
        "t_hi": p_hi + dt.timedelta(seconds=FEED_LAG + 300)})]

by_lg = defaultdict(int)
for a in anchors: by_lg[a["lg"]] += 1
print(f"anchor games {len(anchors)}  " + "  ".join(f"{k} {v}" for k, v in sorted(by_lg.items()))
      + f"   winner snapshots {len(snaps):,}")
by_game = defaultdict(list)
for r in snaps: by_game[r["game_id"]].append(r)

for phase, env in (("kickoff", "HARNESS_KICKOFF"), ("utc", "HARNESS_UTC")):
    total, games_hit, sides, boundary = 0, 0, defaultdict(int), 0
    per_game = []
    for a in anchors:
        trig = MoveTrigger(a["ko"], phase=phase)
        n = 0
        for r in by_game.get(a["vg"], ()):
            s = trig.observe(r["captured_at"], r["bid"], r["ask"])
            if s is not None:
                n += 1; sides[s.side] += 1
                if abs(abs(s.dm) - 0.01) < 1e-6: boundary += 1
        total += n
        if n: games_hit += 1; per_game.append((n, a["lg"], a["vg"]))
    per_game.sort(reverse=True)
    want = os.environ.get(env)
    verdict = ("" if want is None else
               ("  RECONCILED with the harness" if int(want) == total else
                f"  DISAGREES with the harness ({want}) -- neither is trusted until this is explained"))
    print(f"phase={phase:<8} moves {total:,}  games with a move {games_hit}/{len(anchors)}  "
          f"bid {sides['bid']} ask {sides['ask']}  |dm| within 1e-6 of 1c: {boundary}{verdict}")
    print("   top games: " + ", ".join(f"{lg}:{vg} {n}" for n, lg, vg in per_game[:5]))
