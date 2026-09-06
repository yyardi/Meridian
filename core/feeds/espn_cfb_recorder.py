"""The COLLEGE FOOTBALL signal-side poller.

    python -m core.feeds.espn_cfb_recorder            # the service
    python -m core.feeds.espn_cfb_recorder --once     # one cycle, then exit
    python -m core.feeds.espn_cfb_recorder --probe    # read-only, writes nothing

Why this exists, stated plainly: on 2026-09-05 Meridian held **56,948 college
football shadow fills across 48 games** and **zero rows of college football
game state**. We were recording the market and not the game. The existing
`espn_live_recorder` cannot cover it — its `SUMMARY_URL` is a module constant
pinned to `basketball/wnba`, and `espn_live_storage` is basketball-shaped.

THE FOOTBALL PAYLOAD IS NOT THE BASKETBALL PAYLOAD
---------------------------------------------------
Verified against the venue on a live game (401856658, 2026-09-05):
**`summary.plays` is EMPTY for football.** Plays live under
``drives.current.plays`` and ``drives.previous[].plays``. A basketball-shaped
parser pointed at football finds zero plays and writes nothing — while every
heartbeat stays green and the log reads `rows_written=0`, which overnight is
indistinguishable from "no games". That is the failure this recorder is
written to make loud rather than silent (see `--probe` and the empty-payload
alarm below).

Everything the published nflfastR recipe needs is in that one call:
``start.down``, ``start.distance``, ``start.yardsToEndzone`` (this is
``yardline_100``), ``start.team.id`` for possession, ``clock``, ``period``,
both scores, and a real per-play ``wallclock``. Game-level, the same call
carries ``competitors[].timeoutsUsed`` and ``pickcenter[0].spread`` /
``overUnder`` — so the live line needs no second request.

CADENCE
-------
Scoreboard every 60s to find live games; one summary per live game every 20s.
A 68-game Saturday with ~20 concurrent live games is ~1.0 req/s against an
ESPN_RPS=3 budget. Plays are append-only and deduped on (game_id, play_id),
so a slow cycle costs resolution, never rows.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.feeds.espn_client import ESPNClient
from core.feeds.espn_cfb_storage import CfbGameState, CfbLivePlay, CfbWinProbability

log = structlog.get_logger(__name__)

#: The ONLY league-specific value in this module. The payload shape, the
#: parser and the tables are all FOOTBALL, not college football -- NFL plays
#: carry the same down/distance/yards-to-goal/possession. Verified against the
#: venue: `eventState` is GAME-STATE gated, not league gated, so NFL grows one
#: at kickoff and the parser needs no NFL-specific branch.
LEAGUE_PATHS = {
    "cfb": "football/college-football",
    "nfl": "football/nfl",
}
#: ESPN's CFB scoreboard DEFAULTS to groups=80 (FBS) and silently drops FCS --
#: measured, it dropped every live game on 2026-09-06. NFL has one division and
#: no groups gate (verified: 1 event with and without the parameter), so the
#: union is CFB-only and is applied by league rather than unconditionally.
SCOREBOARD_GROUPS = {"cfb": (80, 81), "nfl": (None,)}
CFB_LEAGUE_PATH = LEAGUE_PATHS["cfb"]
SCOREBOARD_INTERVAL = 60.0
SUMMARY_INTERVAL = 20.0
IDLE_INTERVAL = 300.0

#: US Eastern offset for scoreboard date math — ESPN scoreboards are keyed by
#: the US-local date, so a late kickoff lands on the previous UTC day.
_ET = dt.timezone(dt.timedelta(hours=-4))


# ------------------------------------------------------------------ parsing #
def _clock_parts(display: str | None) -> tuple[int | None, int | None]:
    """"12:34" -> (12, 34). Football clocks are mm:ss; OT plays carry none."""
    if not display or ":" not in display:
        return None, None
    m, _, s = display.partition(":")
    try:
        return int(m), int(s)
    except ValueError:
        return None, None


def _parse_wallclock(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_plays(payload: dict, game_id: str, home: str | None,
                away: str | None) -> list[dict]:
    """Flatten `drives.current` + `drives.previous[]` into play rows.

    Returns raw columns only — no derived features. `game_seconds_remaining`,
    `spread_time` and friends are computed in shared code imported by both the
    trainer and the server, so the two can never drift.
    """
    drives = payload.get("drives") or {}
    buckets = list(drives.get("previous") or [])
    if drives.get("current"):
        buckets.append(drives["current"])

    rows: list[dict] = []
    for drive in buckets:
        drive_id = str(drive.get("id") or "") or None
        # ESPN marks the offense per drive; the recipe's posteam-is-home flag.
        d_team = ((drive.get("team") or {}).get("id"))
        is_home_off = None if (d_team is None or home is None) else (str(d_team) == str(home))

        for p in (drive.get("plays") or []):
            pid = str(p.get("id") or "")
            if not pid:
                continue
            start = p.get("start") or {}
            period = ((p.get("period") or {}).get("number"))
            mins, secs = _clock_parts((p.get("clock") or {}).get("displayValue"))
            pos = (start.get("team") or {}).get("id")
            pos = str(pos) if pos is not None else None
            # Regulation is periods 1-4; 5+ is overtime, which has NO CLOCK.
            is_ot = bool(period and period >= 5)

            hs, as_ = p.get("homeScore"), p.get("awayScore")
            if pos is not None and home is not None and str(pos) == str(home):
                pts, dts = hs, as_
                defteam = away
            elif pos is not None:
                pts, dts = as_, hs
                defteam = home
            else:
                pts = dts = defteam = None

            rows.append({
                "game_id": game_id,
                "play_id": pid,
                "drive_id": drive_id,
                "sequence_number": str(p.get("sequenceNumber") or "") or None,
                "wall_clock": _parse_wallclock(p.get("wallclock")),
                "period": period,
                "half": (None if not period else (1 if period <= 2 else 2)),
                "clock_minutes": mins,
                "clock_seconds": secs,
                "is_overtime": is_ot,
                "ot_possession_number": (period - 4) if is_ot else None,
                "down": start.get("down"),
                "distance": start.get("distance"),
                "yards_to_goal": start.get("yardsToEndzone"),
                "pos_team": pos,
                "def_pos_team": defteam,
                "home": home,
                "away": away,
                "drive_is_home_offense": is_home_off,
                "pos_team_score": pts,
                "def_pos_team_score": dts,
                "home_score": hs,
                "away_score": as_,
                "play_type": ((p.get("type") or {}).get("text")),
                "play_text": p.get("text"),
                "scoring_play": p.get("scoringPlay"),
                "score_value": p.get("scoreValue"),
                "is_turnover": p.get("isTurnover"),
                "is_penalty": p.get("isPenalty"),
                "raw": p,
            })
    return rows


def parse_game_state(payload: dict, game_id: str) -> dict | None:
    header = payload.get("header") or {}
    comps = header.get("competitions") or []
    if not comps:
        return None
    c = comps[0]
    status = c.get("status") or {}
    def _i(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    home = away = None
    ht = at = None
    hs = as_ = None
    for side in (c.get("competitors") or []):
        if side.get("homeAway") == "home":
            home, ht, hs = str(side.get("id")), side.get("timeoutsUsed"), side.get("score")
        else:
            away, at, as_ = str(side.get("id")), side.get("timeoutsUsed"), side.get("score")

    pc = (payload.get("pickcenter") or [{}])[0]
    wp = payload.get("winprobability") or []

    return {
        "game_id": game_id,
        "state": ((status.get("type") or {}).get("state")),
        "period": status.get("period"),
        "display_clock": status.get("displayClock"),
        "home": home, "away": away,
        "home_score": _i(hs), "away_score": _i(as_),
        "home_timeouts_used": ht, "away_timeouts_used": at,
        "live_spread": pc.get("spread"),
        "live_over_under": pc.get("overUnder"),
        "line_provider": ((pc.get("provider") or {}).get("name")),
        "espn_home_win_pct": (wp[-1].get("homeWinPercentage") if wp else None),
    }


def parse_win_probability(payload: dict, game_id: str) -> list[dict]:
    out = []
    for w in (payload.get("winprobability") or []):
        pid = str(w.get("playId") or "")
        if pid:
            out.append({"game_id": game_id, "play_id": pid,
                        "home_win_pct": w.get("homeWinPercentage")})
    return out


# ------------------------------------------------------------------ writing #
def _write(session, rows: list[dict], model, conflict: list[str]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(model.__table__).values(rows).on_conflict_do_nothing(
        index_elements=conflict)
    return session.execute(stmt).rowcount or 0


class CfbLiveRecorder:
    def __init__(self, client: ESPNClient, session_factory, league: str = "cfb"):
        self._client = client
        self._sf = session_factory
        self.league = league
        self._live: set[str] = set()
        self._last_board = float("-inf")

    def _board_dates(self, now: dt.datetime) -> list[str]:
        et = now.astimezone(_ET)
        return sorted({et.strftime("%Y%m%d"),
                       (et - dt.timedelta(days=1)).strftime("%Y%m%d")})

    def refresh_live(self, now: dt.datetime) -> set[str]:
        if time.monotonic() - self._last_board < SCOREBOARD_INTERVAL:
            return self._live
        self._last_board = time.monotonic()
        live: set[str] = set()
        for date_str in self._board_dates(now):
            # UNION OVER GROUPS. ESPN's CFB scoreboard defaults to groups=80
            # (FBS) and silently drops FCS -- measured, that was every live
            # game on 2026-09-06 and this recorder saw zero for three hours.
            # NFL has no groups gate, so its tuple is (None,).
            for grp in SCOREBOARD_GROUPS.get(self.league, (None,)):
                params = {"dates": date_str, "limit": 200}
                if grp is not None:
                    params["groups"] = grp
                try:
                    board = self._client.get(
                        self._client._site("scoreboard"), params=params)
                except Exception as exc:
                    log.warning("espn_scoreboard_failed", league=self.league,
                                date=date_str, groups=grp, error=str(exc))
                    continue
                for ev in (board.get("events") or []):
                    st = ((ev.get("status") or {}).get("type") or {})
                    if st.get("state") == "in":
                        live.add(str(ev["id"]))
        self._live = live
        return live

    def poll_game(self, game_id: str) -> tuple[int, int, int]:
        payload = self._client.get(self._client._site("summary"),
                                   params={"event": game_id})
        state = parse_game_state(payload, game_id)
        home = state.get("home") if state else None
        away = state.get("away") if state else None
        plays = parse_plays(payload, game_id, home, away)
        wp = parse_win_probability(payload, game_id)

        # LOUD, not silent: a live game whose summary parsed no plays is the
        # exact shape of the basketball-parser-on-football failure.
        if not plays:
            log.error("cfb_empty_payload", game_id=game_id,
                      has_drives=bool(payload.get("drives")))

        with self._sf() as s:
            for r in plays:
                r["league"] = self.league
            for r in wp:
                r["league"] = self.league
            np = _write(s, plays, CfbLivePlay, ["game_id", "play_id"])
            nw = _write(s, wp, CfbWinProbability, ["game_id", "play_id"])
            ns = 0
            if state:
                s.add(CfbGameState(league=self.league, **state))
                ns = 1
            s.commit()
        return np, nw, ns

    def cycle(self) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        live = self.refresh_live(now)
        tot_p = tot_w = tot_s = 0
        for gid in sorted(live):
            try:
                p, w, st = self.poll_game(gid)
                tot_p += p; tot_w += w; tot_s += st
            except Exception as exc:
                log.warning("cfb_summary_failed", game_id=gid, error=str(exc))
        log.info("cfb_cycle", live_games=len(live), plays=tot_p,
                 wp_rows=tot_w, state_rows=tot_s)
        return {"live": len(live), "plays": tot_p, "wp": tot_w, "state": tot_s}


def _make_client(league: str = "cfb") -> ESPNClient:
    """A CFB-scoped client.

    `ESPNConfig.league_path` defaults to `basketball/wnba` and drives
    `ESPNClient._site()`, so overriding it here is the whole league switch —
    the client was already general; only the module constants were pinned.
    """
    import dataclasses

    from core.config import ESPN

    return ESPNClient(dataclasses.replace(ESPN, league_path=LEAGUE_PATHS[league]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ESPN college-football live recorder")
    ap.add_argument("--league", choices=sorted(LEAGUE_PATHS), default="cfb",
                    help="which football league to record")
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--probe", action="store_true",
                    help="read-only: parse a live game and print, write nothing")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    client = _make_client(a.league)

    if a.probe:
        now = dt.datetime.now(dt.timezone.utc)
        et = now.astimezone(_ET)
        # same groups union as the recording path -- a probe that queries a
        # narrower population than the recorder would under-report coverage
        # and read as healthy while the recorder saw more.
        evs, seen = [], set()
        for grp in SCOREBOARD_GROUPS.get(a.league, (None,)):
            params = {"dates": et.strftime("%Y%m%d"), "limit": 200}
            if grp is not None:
                params["groups"] = grp
            board = client.get(client._site("scoreboard"), params=params)
            for e in (board.get("events") or []):
                st = ((e.get("status") or {}).get("type") or {})
                if st.get("state") == "in" and e["id"] not in seen:
                    seen.add(e["id"])
                    evs.append(e)
        print(f"live games: {len(evs)}")
        if not evs:
            print("NO LIVE GAMES — this is an empty scoreboard, not a parse failure.")
            return 0
        gid = str(evs[0]["id"])
        payload = client.get(client._site("summary"), params={"event": gid})
        st = parse_game_state(payload, gid)
        plays = parse_plays(payload, gid, st.get("home"), st.get("away"))
        print(f"game {gid}: {len(plays)} plays parsed, "
              f"{len(parse_win_probability(payload, gid))} wp rows")
        print("state:", {k: st[k] for k in
                         ("state", "period", "display_clock", "home_score",
                          "away_score", "home_timeouts_used", "live_spread")})
        if plays:
            p = plays[-1]
            print("last play:", {k: p[k] for k in
                                 ("period", "clock_minutes", "clock_seconds", "down",
                                  "distance", "yards_to_goal", "pos_team",
                                  "pos_team_score", "def_pos_team_score",
                                  "is_overtime", "wall_clock")})
        return 0

    from core.storage import get_engine, get_sessionmaker
    rec = CfbLiveRecorder(client, get_sessionmaker(get_engine()),
                          league=a.league)
    if a.once:
        rec.cycle()
        return 0
    while True:
        out = rec.cycle()
        time.sleep(SUMMARY_INTERVAL if out["live"] else IDLE_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
