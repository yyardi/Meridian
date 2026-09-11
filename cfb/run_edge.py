"""THE SCORING RUN. Model vs the contemporaneous market, on a LIVE market.

PRE-REGISTERED READING, fixed before the number exists: a positive result here
is NOT a go-live. The state is BACKFILLED (ESPN's corrected finished-game
data) while serving would use provisional live state. Measured divergence on
the 19 games captured both ways: possession 0.00%, period 0.00%, down 0.25%,
yards_to_goal 0.25%, distance 0.89%, score 2.22%. Small, non-zero, and in the
flattering direction. So whatever this prints is an UPPER BOUND and a reason
to re-run on live-recorded state -- never a decision.

THE THREE THINGS THAT MAKE IT HONEST:
  * FEED LAG APPLIED. We act at wall_clock + 30s, never at wall_clock. The
    measured lag from ESPN's stamp to our observation is ~30s; acting at the
    play instant would claim a speed we do not have.
  * FRESHNESS REQUIRED. A quote counts only if that market's (bid,ask)
    actually changed in the 10 minutes before. A frozen mid cannot move, so
    every play reads as a disagreement and the edge is an artefact that looks
    like caution. Stale and unknown-freshness rows are EXCLUDED AND COUNTED.
  * COST CHARGED. Crossing costs theta*p*(1-p) with theta=0.06 -- 1.5c at 50c,
    less at the wings. Quoted net, never gross.
"""
import os
import sys

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, build_features  # noqa: E402
from cfb_train import REG_FEATURES  # noqa: E402

import xgboost as xgb  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

FEED_LAG = 30
FRESH_MIN = 10
TAKER_THETA = 0.06
EDGE_THRESHOLDS = (0.03, 0.05, 0.08, 0.12)

booster = xgb.Booster()
booster.load_model("/app/artifacts/cfb_wp_regulation.json")
eng = create_engine(os.environ["DATABASE_URL"])

SQL = """
-- SETTLEMENT DERIVED FROM THE GAME OUTCOME, not from shadow_quote_fills.
-- The fill-table join limited the sample to 7 games because settlement is only
-- populated where our simulator happened to fill. The outcome is a fact about
-- the game and is known for every backfilled game, so the sample is bounded by
-- game state and price coverage rather than by our own simulated activity --
-- which was a selection on our own behaviour sitting inside an edge estimate.
--
-- YES = P(FIRST TEAM WINS) and the slug's first team is the AWAY team,
-- verified 50/55 with 0 contradicting and 5 ambiguous. So settlement = 1 iff
-- the away team won.
WITH play AS (
  SELECT b.game_id espn_game, b.play_id, b.wall_clock, b.period,
         b.clock_minutes, b.clock_seconds, b.down, b.distance, b.yards_to_goal,
         b.pos_team_score, b.def_pos_team_score, b.drive_is_home_offense,
         b.is_overtime, m.venue_game_id, m.division, g.spread,
         m.event_slug, m.home_espn_name, m.away_espn_name,
         (CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END)::int AS settlement
  FROM espn_cfb_backfill_plays b
  JOIN cfb_game_map m ON m.espn_game_id = b.game_id
  JOIN espn_cfb_backfill_games g ON g.game_id = b.game_id
  WHERE b.wall_clock IS NOT NULL
    AND b.down IS NOT NULL AND b.down > 0      -- down=0 is ESPN's end-of-game sentinel
    AND b.period IS NOT NULL AND NOT b.is_overtime
    AND g.spread IS NOT NULL
    AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    AND g.home_score <> g.away_score           -- a tie has no winner to price
)
SELECT play.*, q.market_slug, q.best_bid::float bid, q.best_ask::float ask,
       q.captured_at,
       EXTRACT(EPOCH FROM (q.captured_at - play.wall_clock)) AS quote_lag_s,
       (SELECT count(DISTINCT (m2.best_bid, m2.best_ask)) > 1
        FROM market_snapshots m2
        WHERE m2.market_slug = q.market_slug
          AND m2.captured_at BETWEEN q.captured_at - INTERVAL '10 minutes'
                                 AND q.captured_at) AS market_fresh
FROM play
CROSS JOIN LATERAL (
  SELECT ms.market_slug, ms.best_bid, ms.best_ask, ms.captured_at
  FROM market_snapshots ms
  WHERE ms.game_id = play.venue_game_id
    AND ms.sports_market_type LIKE '%winner'
    AND ms.best_bid IS NOT NULL AND ms.best_ask IS NOT NULL
    AND ms.captured_at >= play.wall_clock + INTERVAL '30 seconds'
    AND ms.captured_at <= play.wall_clock + INTERVAL '5 minutes'
  ORDER BY ms.captured_at
  LIMIT 1) q
"""

with eng.connect() as c:
    rows = [dict(r._mapping) for r in c.execute(text(SQL))]
print(f"candidate (play, quote, settlement) triples: {len(rows):,}"
      f"   games: {len({r['espn_game'] for r in rows}):,}")

considered = stale = unknown = 0
usable = []
for r in rows:
    considered += 1
    fresh = r.get("market_fresh")
    if fresh is None:
        unknown += 1            # "we did not check" is not "it was fresh"
        continue
    if not fresh:
        stale += 1
        continue
    usable.append(r)
print(f"  excluded_stale={stale:,}  excluded_unknown_freshness={unknown:,}  "
      f"usable={len(usable):,}")
if not usable:
    print("\nNO FRESH MARKET ROWS -- refusing to report an edge. "
          "This is an empty set, not a measured zero.")
    sys.exit(0)

# --- model probability per play ----------------------------------------- #
preds = []
for r in usable:
    st = GameState(period=r["period"], clock_minutes=r["clock_minutes"] or 0,
                   clock_seconds=r["clock_seconds"] or 0, down=r["down"],
                   distance=r["distance"], yards_to_goal=r["yards_to_goal"],
                   pos_team_score=r["pos_team_score"] or 0,
                   def_pos_team_score=r["def_pos_team_score"] or 0,
                   drive_is_home_offense=bool(r["drive_is_home_offense"]),
                   pos_team_timeouts=3, def_pos_team_timeouts=3,
                   is_overtime=False, ot_possession_number=None)
    f = build_features(st, float(r["spread"]))
    if f.get("spread_time") is None:
        continue
    vec = [float("nan") if f.get(c) is None else f.get(c) for c in REG_FEATURES]
    p_pos = float(booster.predict(xgb.DMatrix([vec], feature_names=REG_FEATURES,
                                              missing=float("nan")))[0])
    p_home = p_pos if r["drive_is_home_offense"] else 1.0 - p_pos
    preds.append((r, p_home))

# The 5 games whose slug token cannot be resolved to a side by fuzzy match
# (wmich/mich, txst/tx, utrgv/utsa, semst/iowast, umass/rutger -- c7's
# collision case). An unresolvable frame is EXCLUDED AND COUNTED, never
# guessed: a wrong orientation silently inverts that game's entire P&L.
import difflib as _dl
import re as _re


def _norm(x):
    return _re.sub(r"[^a-z0-9]", "", (x or "").lower())


def _sc(tok, name):
    n = _norm(name)
    if not tok or not n:
        return 0.0
    r = _dl.SequenceMatcher(None, tok, n).ratio()
    if n.startswith(tok) and len(tok) >= 3:
        r = max(r, 0.92)
    return r


resolved, ambiguous_games = [], set()
for r, p_home in preds:
    m = _re.match(r"^cfb-([a-z0-9]+)-", r.get("event_slug") or "")
    if not m:
        ambiguous_games.add(r["espn_game"])
        continue
    t = m.group(1)
    a, h = _sc(t, r.get("away_espn_name")), _sc(t, r.get("home_espn_name"))
    if abs(a - h) < 0.08 or h > a:
        ambiguous_games.add(r["espn_game"])
        continue
    resolved.append((r, p_home))
print(f"  scored {len(preds):,} plays; frame-resolved {len(resolved):,}; "
      f"EXCLUDED {len(preds) - len(resolved):,} plays from "
      f"{len(ambiguous_games)} games with an unresolvable YES frame")
preds = resolved


def cost(p):
    return TAKER_THETA * p * (1.0 - p)


print("\n=== EDGE: act on disagreement, score the outcome, charge the cost ===")
print("    (settlement derived from the game outcome; mid is the price we cross)")
for th in EDGE_THRESHOLDS:
    trades = []
    for r, p_home in preds:
        mid = (r["bid"] + r["ask"]) / 2.0
        y = float(r["settlement"])
        # THE VENUE'S YES FRAME IS P(FIRST TEAM WINS) -- core/live_fv.py:229
        # and core/quote/storage.py:70. Verified on our own board: the slug's
        # first token is the AWAY team in 50 of 55 games, 0 contradicting,
        # 5 refused as ambiguous and EXCLUDED above rather than guessed.
        # Comparing P(home) to the mid, as the first version of this script
        # did, inverted the sign on every market -- which is why 96% of plays
        # read as "disagreements".
        p_yes = 1.0 - p_home
        d = p_yes - mid
        if abs(d) < th:
            continue
        pnl = (y - mid) if d > 0 else (mid - y)
        trades.append((pnl - cost(mid), r["espn_game"]))
    if not trades:
        print(f"  |edge| > {th * 100:4.0f}c   NO TRADES")
        continue
    g = {}
    for pnl, gid in trades:
        g.setdefault(gid, []).append(pnl)
    per = [sum(v) / len(v) for v in g.values()]
    n = len(per)
    m = sum(per) / n
    sd = (sum((x - m) ** 2 for x in per) / (n - 1)) ** 0.5 if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
    verdict = ("UNDERPOWERED (<25 games)" if n < 25
               else "EXCLUDES ZERO" if (m - half) * (m + half) > 0 else "spans zero")
    print(f"  |edge| > {th * 100:4.0f}c   trades={len(trades):6,}  games={n:3d}  "
          f"net={m * 100:+7.2f}c  CI [{(m - half) * 100:+.2f}, {(m + half) * 100:+.2f}]  {verdict}")

print("\nUPPER BOUND: state is backfilled (corrected) while serving is "
      "provisional; measured divergence up to 2.22% of plays. Not a go-live.")
