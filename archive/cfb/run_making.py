"""MARKET MAKING with the model as fair value. The actual strategy.

WHY THIS AND NOT run_edge.py. That script tested TAKING: cross the spread, pay
theta*p*(1-p) ~1.5c at mid prices, need edge above it. That is not the
strategy. A maker RECEIVES 0.31c and pays nothing to cross, so the two differ
by 1.81c per contract before anything else happens — and every prior making
result was measured on a quoter with NO VIEW, quoting at the touch, which
Glosten-Milgrom says must lose.

THE STRATEGY: quote a two-sided market around the model's fair value, at a
chosen half-width. We are filled only when the market comes to US. If the fair
value is better than the market's, the fills we get are the ones where the
market was wrong, and we are paid the rebate for providing them.

FILL RULE, and it is the conservative one. A resting bid at B is filled when
the market's ASK falls to B or below — someone was willing to sell at our
price. NOT when the mid crosses B, which is the engine's rule and is
arithmetically impossible with a positive spread except when the book moves
THROUGH us. That rule books only adverse fills and is why capture <= 0 by
construction there.

  bid at B filled  <=>  next ask <= B     (a seller reached our price)
  ask at A filled  <=>  next bid >= A     (a buyer reached our price)

WHAT IS CHARGED: nothing to cross, because we never cross. The maker rebate
theta*p*(1-p) with theta = -0.0125 is ADDED. Settlement P&L is the money.

WHAT IS NOT MODELLED, stated rather than buried: queue position. We assume we
are filled when the price reaches us, which is optimistic — real queue depth
means someone ahead may absorb the flow. The venue exposes no order count at
any level, so this cannot be corrected from tape (see docs/math/fill-rule-bias).
Treat the result as an UPPER BOUND on the making arm.
"""
import os
import sys

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, build_features  # noqa: E402
from cfb_train import REG_FEATURES  # noqa: E402

import xgboost as xgb  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

FEED_LAG = 30
MAKER_THETA = 0.0      # THERE IS NO MAKER REBATE. findings.md C7
# (RESOLVED 2026-08-25) and V24: the credits that looked like one were
# TAKER_FEE_REBATE, a 50% refund of our OWN taker fees, promo window
# 2026-03-29 -> 05-10, ended, nothing since. The advertised 25%-of-
# matched-taker-fee rebate has NEVER been observed in this account.
# The core code has defaulted theta_maker=0 everywhere since 08-05
# (wallet.py:143, fills.py:21, engine.py:179); these two CFB scripts
# were the last place still booking it as certain income.
HALF_WIDTHS = (0.01, 0.02, 0.03, 0.05)

booster = xgb.Booster()
booster.load_model("/app/artifacts/cfb_wp_regulation.json")
eng = create_engine(os.environ["DATABASE_URL"])

# One row per play: our quote instant, and the NEXT quote that could fill it.
SQL = """
WITH play AS (
  SELECT b.game_id espn_game, b.play_id, b.wall_clock, b.period,
         b.clock_minutes, b.clock_seconds, b.down, b.distance, b.yards_to_goal,
         b.pos_team_score, b.def_pos_team_score, b.drive_is_home_offense,
         m.venue_game_id, m.event_slug, m.home_espn_name, m.away_espn_name,
         g.spread,
         (CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END)::int AS settlement
  FROM espn_cfb_backfill_plays b
  JOIN cfb_game_map m ON m.espn_game_id = b.game_id
  JOIN espn_cfb_backfill_games g ON g.game_id = b.game_id
  WHERE b.wall_clock IS NOT NULL AND b.down IS NOT NULL AND b.down > 0
    AND b.period IS NOT NULL AND NOT b.is_overtime AND g.spread IS NOT NULL
    AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    AND g.home_score <> g.away_score
),
quoted AS (   -- the book when we would have posted
  SELECT play.*, q.market_slug, q.best_bid::float bid0, q.best_ask::float ask0,
         q.captured_at AS t0,
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
    ORDER BY ms.captured_at LIMIT 1) q
)
-- the book over the NEXT 2 minutes decides whether our quote is reached
SELECT quoted.*, f.min_ask, f.max_bid
FROM quoted
CROSS JOIN LATERAL (
  SELECT min(ms.best_ask)::float AS min_ask, max(ms.best_bid)::float AS max_bid
  FROM market_snapshots ms
  WHERE ms.market_slug = quoted.market_slug
    AND ms.captured_at > quoted.t0
    AND ms.captured_at <= quoted.t0 + INTERVAL '2 minutes'
) f
WHERE f.min_ask IS NOT NULL
"""

with eng.connect() as c:
    rows = [dict(r._mapping) for r in c.execute(text(SQL))]
print(f"play/quote/fill-window triples: {len(rows):,}  "
      f"games: {len({r['espn_game'] for r in rows}):,}")

fresh = [r for r in rows if r.get("market_fresh")]
print(f"  excluded_stale={len(rows) - len(fresh):,}  usable={len(fresh):,}")
if not fresh:
    print("NO FRESH ROWS — refusing. Empty set, not a measured zero.")
    sys.exit(0)


def rebate(p):
    return -MAKER_THETA * p * (1.0 - p)


import difflib  # noqa: E402
import re  # noqa: E402


def _sc(tok, name):
    n = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if not tok or not n:
        return 0.0
    r = difflib.SequenceMatcher(None, tok, n).ratio()
    return max(r, 0.92) if (n.startswith(tok) and len(tok) >= 3) else r


scored, skipped_frame = [], set()
for r in fresh:
    m = re.match(r"^cfb-([a-z0-9]+)-", r.get("event_slug") or "")
    if not m:
        skipped_frame.add(r["espn_game"])
        continue
    t = m.group(1)
    a, h = _sc(t, r.get("away_espn_name")), _sc(t, r.get("home_espn_name"))
    if abs(a - h) < 0.08 or h > a:
        skipped_frame.add(r["espn_game"])
        continue
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
    # venue YES = first team = away team (verified 50/55)
    fv = 1.0 - (p_pos if r["drive_is_home_offense"] else 1.0 - p_pos)
    scored.append((r, fv))

print(f"  frame-resolved {len(scored):,}; excluded {len(skipped_frame)} games "
      f"with an unresolvable YES frame")

print("\n=== MARKET MAKING: quote around model FV, never cross, collect rebate ===")
print("    fill = the market REACHED our price (ask<=our bid / bid>=our ask)")
for hw in HALF_WIDTHS:
    trades, by_game = [], {}
    for r, fv in scored:
        y = float(r["settlement"])
        our_bid, our_ask = fv - hw, fv + hw
        # only quote inside the tradable band
        if not (0.02 < our_bid and our_ask < 0.98):
            continue
        for side, price, reached in (
                ("bid", our_bid, r["min_ask"] is not None and r["min_ask"] <= our_bid),
                ("ask", our_ask, r["max_bid"] is not None and r["max_bid"] >= our_ask)):
            if not reached:
                continue
            pnl = (y - price) if side == "bid" else (price - y)
            pnl += rebate(price)
            trades.append(pnl)
            by_game.setdefault(r["espn_game"], []).append(pnl)
    if not trades:
        print(f"  half-width {hw*100:4.1f}c   NO FILLS")
        continue
    per = [sum(v) / len(v) for v in by_game.values()]
    n = len(per)
    mu = sum(per) / n
    sd = (sum((x - mu) ** 2 for x in per) / (n - 1)) ** 0.5 if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
    verdict = ("UNDERPOWERED (<25 games)" if n < 25
               else "EXCLUDES ZERO" if (mu - half) * (mu + half) > 0 else "spans zero")
    print(f"  half-width {hw*100:4.1f}c   fills={len(trades):6,}  games={n:3d}  "
          f"net={mu*100:+7.2f}c  CI [{(mu-half)*100:+.2f}, {(mu+half)*100:+.2f}]  {verdict}")

print("\nUPPER BOUND: queue position is not modelled -- we assume a fill when the")
print("price reaches us. The venue exposes no order count at any level, so this")
print("cannot be corrected from tape. State is also backfilled (corrected).")
