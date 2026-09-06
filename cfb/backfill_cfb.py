"""Backfill CFB game state for games played BEFORE the venue froze.

WHY. Edge must be scored against a market that can move. The venue froze at
17:40Z on 2026-09-05 and has read 0.0% since, so tonight's tape cannot score
anything. But Sept 3 through 5 16:00Z the CFB market was HEALTHY -- 35-58% of
markets moving per hour against a 26-41% healthy band -- and we hold that
tape. What we lacked was game state for those days, because the recorder only
started tonight. ESPN serves full play-by-play WITH wallclock for finished
games (verified: game 401856767, 175 plays, 175 wallclocks, real timestamps),
so the missing half is recoverable.

WHY A SEPARATE TABLE, and this is not bookkeeping fussiness.
`espn_cfb_live_plays.first_seen_at` means ONE thing: the instant OUR poller
observed the row. It is the only knowability stamp, and every replay filters
on it. These rows were never observed live -- writing them into that table
would either lie about first_seen_at or force every future reader to know
about an exception. A separate table cannot be confused with live tape.

THE LAG IS APPLIED, NOT ASSUMED. We measured ~30s from ESPN's own play stamp
to our observation. A backtest that acts at wall_clock would be claiming a
speed we do not have. `actionable_at = wall_clock + FEED_LAG_SECONDS`, and the
market quote is taken at or after that instant -- never before.
"""
import datetime as dt
import os
import sys

import httpx

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/cfb")

from sqlalchemy import create_engine, text  # noqa: E402

#: measured on the live probe, ESPN stamp -> our observation
FEED_LAG_SECONDS = 30

SUMMARY = ("https://site.api.espn.com/apis/site/v2/sports/football/"
           "college-football/summary")

DDL = """
CREATE TABLE IF NOT EXISTS espn_cfb_backfill_plays (
  id             bigserial PRIMARY KEY,
  backfilled_at  timestamptz NOT NULL DEFAULT now(),
  game_id        varchar(32) NOT NULL,
  play_id        varchar(48) NOT NULL,
  wall_clock     timestamptz,
  period         smallint,
  clock_minutes  smallint,
  clock_seconds  smallint,
  is_overtime    boolean NOT NULL DEFAULT false,
  down           smallint,
  distance       smallint,
  yards_to_goal  smallint,
  pos_team       varchar(32),
  home           varchar(32),
  away           varchar(32),
  drive_is_home_offense boolean,
  pos_team_score smallint,
  def_pos_team_score smallint,
  home_score     smallint,
  away_score     smallint,
  UNIQUE (game_id, play_id)
);
CREATE INDEX IF NOT EXISTS ix_cfb_bf_game_wall
  ON espn_cfb_backfill_plays (game_id, wall_clock);
CREATE TABLE IF NOT EXISTS espn_cfb_backfill_games (
  game_id     varchar(32) PRIMARY KEY,
  backfilled_at timestamptz NOT NULL DEFAULT now(),
  home        varchar(32),
  away        varchar(32),
  home_score  smallint,
  away_score  smallint,
  spread      numeric(6,2),
  provider    varchar(48)
);
"""


def parse(payload, game_id):
    header = payload.get("header") or {}
    comps = header.get("competitions") or []
    home = away = None
    hs = as_ = None
    for c in (comps[0].get("competitors") if comps else []) or []:
        if c.get("homeAway") == "home":
            home, hs = str(c.get("id")), c.get("score")
        else:
            away, as_ = str(c.get("id")), c.get("score")

    def _i(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    pc = (payload.get("pickcenter") or [{}])[0]
    game = {"game_id": game_id, "home": home, "away": away,
            "home_score": _i(hs), "away_score": _i(as_),
            "spread": pc.get("spread"),
            "provider": ((pc.get("provider") or {}).get("name"))}

    drives = payload.get("drives") or {}
    buckets = list(drives.get("previous") or [])
    if drives.get("current"):
        buckets.append(drives["current"])
    rows = []
    for d in buckets:
        dteam = ((d.get("team") or {}).get("id"))
        is_home_off = (None if (dteam is None or home is None)
                       else str(dteam) == str(home))
        for p in (d.get("plays") or []):
            pid = str(p.get("id") or "")
            if not pid:
                continue
            start = p.get("start") or {}
            period = ((p.get("period") or {}).get("number"))
            disp = (p.get("clock") or {}).get("displayValue") or ""
            mins = secs = None
            if ":" in disp:
                a, _, b = disp.partition(":")
                try:
                    mins, secs = int(a), int(b)
                except ValueError:
                    pass
            wc = p.get("wallclock")
            try:
                wc = dt.datetime.fromisoformat(wc.replace("Z", "+00:00")) if wc else None
            except ValueError:
                wc = None
            pos = (start.get("team") or {}).get("id")
            pos = str(pos) if pos is not None else None
            phs, pas = p.get("homeScore"), p.get("awayScore")
            if pos is not None and home is not None and pos == home:
                pts, dts = phs, pas
            elif pos is not None:
                pts, dts = pas, phs
            else:
                pts = dts = None
            rows.append({
                "game_id": game_id, "play_id": pid, "wall_clock": wc,
                "period": period, "clock_minutes": mins, "clock_seconds": secs,
                "is_overtime": bool(period and period >= 5),
                "down": start.get("down"), "distance": start.get("distance"),
                "yards_to_goal": start.get("yardsToEndzone"),
                "pos_team": pos, "home": home, "away": away,
                "drive_is_home_offense": is_home_off,
                "pos_team_score": pts, "def_pos_team_score": dts,
                "home_score": phs, "away_score": pas,
            })
    return game, rows


def main():
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.begin() as c:
        for stmt in DDL.split(";"):
            if stmt.strip():
                c.execute(text(stmt))

    # ALL mapped games, deliberately. The pre-freeze ones are the scoring
    # set; the Sept-5 ones OVERLAP games our live recorder captured, and that
    # overlap is the only way to measure whether ESPN's corrected
    # finished-game data differs from the provisional data we saw live. A
    # backfill validated against corrected state but served on provisional
    # state would be train-clean/serve-dirty and would flatter us invisibly.
    with eng.connect() as c:
        targets = [dict(r._mapping) for r in c.execute(text("""
            SELECT espn_game_id, venue_game_id, espn_date
            FROM cfb_game_map
            ORDER BY espn_date
        """))]
    print(f"games to backfill (pre-freeze, mapped to a venue game): {len(targets)}")

    ok = plays_total = 0
    empty = []
    with httpx.Client(timeout=60.0) as h, eng.begin() as c:
        for t in targets:
            gid = t["espn_game_id"]
            try:
                r = h.get(SUMMARY, params={"event": gid})
                r.raise_for_status()
            except Exception as exc:
                print(f"  ! {gid}: {type(exc).__name__}")
                continue
            game, rows = parse(r.json(), gid)
            if not rows:
                empty.append(gid)          # rule 22: counted, never silent
                continue
            c.execute(text("""
                INSERT INTO espn_cfb_backfill_games
                  (game_id,home,away,home_score,away_score,spread,provider)
                VALUES (:game_id,:home,:away,:home_score,:away_score,:spread,:provider)
                ON CONFLICT (game_id) DO UPDATE SET
                  home_score=EXCLUDED.home_score, away_score=EXCLUDED.away_score,
                  spread=EXCLUDED.spread, provider=EXCLUDED.provider
            """), game)
            for row in rows:
                c.execute(text("""
                    INSERT INTO espn_cfb_backfill_plays
                      (game_id,play_id,wall_clock,period,clock_minutes,clock_seconds,
                       is_overtime,down,distance,yards_to_goal,pos_team,home,away,
                       drive_is_home_offense,pos_team_score,def_pos_team_score,
                       home_score,away_score)
                    VALUES
                      (:game_id,:play_id,:wall_clock,:period,:clock_minutes,:clock_seconds,
                       :is_overtime,:down,:distance,:yards_to_goal,:pos_team,:home,:away,
                       :drive_is_home_offense,:pos_team_score,:def_pos_team_score,
                       :home_score,:away_score)
                    ON CONFLICT (game_id,play_id) DO NOTHING
                """), row)
            ok += 1
            plays_total += len(rows)

    print(f"backfilled {ok} games, {plays_total:,} plays")
    if empty:
        print(f"EMPTY payloads: {len(empty)} games -> {empty[:5]}"
              " (counted, not silently dropped)")

    with eng.connect() as c:
        n = c.execute(text("""
            SELECT count(*) FROM espn_cfb_backfill_plays
            WHERE wall_clock IS NOT NULL AND down IS NOT NULL
        """)).scalar()
        g = c.execute(text("SELECT count(DISTINCT game_id) FROM espn_cfb_backfill_plays")).scalar()
        sp = c.execute(text("SELECT count(*) FROM espn_cfb_backfill_games WHERE spread IS NOT NULL")).scalar()
    print(f"usable plays (wallclock + down): {n:,} across {g} games; "
          f"{sp} games carry a spread")
    print(f"\nfeed lag to apply when scoring: +{FEED_LAG_SECONDS}s "
          f"(we cannot act at wall_clock; we did not see it then)")


if __name__ == "__main__":
    main()
