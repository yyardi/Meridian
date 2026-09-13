"""cfb_data.py -- loads (play state, contemporaneous market) rows from prod.

Uses the join meridian-a1 verified end to end:
  espn_cfb_live_plays.game_id -> cfb_game_map.espn_game_id
  cfb_game_map.venue_game_id  -> market_snapshots.game_id, NEAREST captured_at
                                 to the play's own wall_clock (mean 1.4s).

FRESHNESS is computed here, not assumed: a market row counts as fresh only if
that market's (best_bid,best_ask) CHANGED within FRESH_MINUTES before the play.
The venue froze for 4.5h on 2026-09-05 while ticks kept arriving; a stale mid
cannot move, so every play looks like a disagreement and the edge estimate is
artefactual in a direction that reads as caution.

NO CFBD KEY: this returns our own recorded tape only. The key unlocks the
2014+ FBS backfill; its absence DEGRADES the training set, it does not fail.
"""
from __future__ import annotations
import os

FRESH_MINUTES = 10

SQL = """
with play as (
  select p.game_id espn_game_id, p.play_id, p.wall_clock, p.period, p.half,
         p.clock_minutes, p.clock_seconds, p.is_overtime, p.ot_possession_number,
         p.down, p.distance, p.yards_to_goal, p.pos_team_score, p.def_pos_team_score,
         p.drive_is_home_offense, m.venue_game_id, m.division, m.event_slug
  from espn_cfb_live_plays p
  join cfb_game_map m on m.espn_game_id = p.game_id
  where p.wall_clock is not null
),
px as (
  select play.*, q.market_slug, q.best_bid, q.best_ask, q.captured_at,
         abs(extract(epoch from (q.captured_at - play.wall_clock))) lag_s
  from play
  cross join lateral (
    select s.market_slug, s.best_bid, s.best_ask, s.captured_at
    from market_snapshots s
    where s.game_id = play.venue_game_id
      and s.sports_market_type like :mkt_type
      and s.best_bid is not null and s.best_ask is not null
      and s.captured_at between play.wall_clock - interval '5 minutes'
                            and play.wall_clock + interval '5 minutes'
    order by abs(extract(epoch from (s.captured_at - play.wall_clock)))
    limit 1) q
)
select px.*, (
  select count(distinct (s2.best_bid, s2.best_ask)) > 1
  from market_snapshots s2
  where s2.market_slug = px.market_slug
    and s2.captured_at between px.captured_at - (:fresh || ' minutes')::interval
                           and px.captured_at
) as market_fresh
from px
"""


def load(engine, market_type_like="%_winner", fresh_minutes=FRESH_MINUTES):
    from sqlalchemy import text
    with engine.connect() as c:
        rows = [dict(r._mapping) for r in c.execute(
            text(SQL), {"mkt_type": market_type_like, "fresh": str(fresh_minutes)})]
    return rows


def summarise(rows):
    if not rows: return "NO ROWS -- check cfb_game_map is populated and plays exist."
    fresh = sum(1 for r in rows if r.get("market_fresh"))
    games = len({r["espn_game_id"] for r in rows})
    lags = sorted(float(r["lag_s"]) for r in rows if r.get("lag_s") is not None)
    return (f"rows={len(rows)} games={games} fresh={fresh} ({100.0*fresh/len(rows):.1f}%) "
            f"stale={len(rows)-fresh}  median join lag={lags[len(lags)//2]:.1f}s")


if __name__ == "__main__":
    from sqlalchemy import create_engine
    eng = create_engine(os.environ["DATABASE_URL"])
    r = load(eng)
    print(summarise(r))
