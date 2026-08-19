"""The signal-side poller: ESPN live boxscore + play-by-play, point-in-time.

    python -m core.feeds.espn_live_recorder                # the service
    python -m core.feeds.espn_live_recorder --once         # one cycle, then exit
    python -m core.feeds.espn_live_recorder --checklist    # feed-lag report

Design and endpoint receipts: docs/infra/signal-side.md. One endpoint does
everything: the WNBA summary call carries the team box, the player box, all
plays (each with a game clock and ESPN's own wallclock), ESPN's win
probability, and the injuries block. The scoreboard (already polled by the
live-odds-recorder at 15s) supplies live-game detection via its `state`
field — the house's authoritative live signal.

Budget: scoreboard every 30s (two ET dates, so games that straddle midnight
UTC are never missed) + one summary per live game every 10s ≈ 0.24 req/s of
the ESPN_RPS=3 budget with a two-game slate.

Point-in-time, restated because it is the point
-----------------------------------------------
Every row's ``first_seen_at`` is the instant THIS process observed it —
stamped once per cycle, before parsing. ESPN's per-play ``wallclock`` is
stored beside it as data; ``--checklist`` reports the (wallclock →
first_seen_at) lag distribution, which bounds how "live" any play-derived
signal may claim to be. Replays filter ``first_seen_at <= t`` and nothing
else.

What this writer is not
-----------------------
A reader of ESPN and a writer of its own five tables and one heartbeat row,
only. It never touches ``market_snapshots``, ``pulse_decisions``, or any
venue. There are no credentials because ESPN needs none.

The quiet-failure guard (#25's lesson, applied here on day one)
---------------------------------------------------------------
The season-type outage failed silently: fresh heartbeats, ``rows_written=0``
against real finished games, nobody alarmed. This recorder treats "a game is
live and a summary poll parsed nothing" as a LOUD condition
(``espn_live_empty_payload`` at error level), and the first-live-game
checklist pins it. The heartbeat beats every cycle regardless of work —
``rows_written=0, game_live=False`` overnight is IDLE, not DEAD, which keeps
the dashboard header truthful (the B11 rule: /api/status judges every
service that has ever beaten).
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import threading
import time

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core import heartbeat as hb
from core.feeds.espn_boxscores import SUMMARY_URL
from core.feeds.espn_client import ESPNClient
from core.feeds.espn_live_storage import (
    EspnLiveBoxSnapshot,
    EspnLiveInjuryObservation,
    EspnLivePlay,
    EspnLivePlayerSnapshot,
    EspnLiveWinProbability,
)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

SERVICE_ESPN_LIVE = "espn_live_recorder"

DEFAULT_SUMMARY_INTERVAL = 10.0     # per live game
DEFAULT_SCOREBOARD_INTERVAL = 30.0
DEFAULT_PLAYER_EVERY = 60.0         # player box cadence
#: One final summary after a game leaves 'in' — the completed box.
FINAL_SWEEP_STATES = ("post",)

#: US Eastern offset for scoreboard date math. ESPN scoreboards are keyed by
#: ET date; in-season (Apr-Oct) that is EDT = UTC-4. Games never tip within
#: hours of the ET date boundary, so DST edge weeks cannot misfile one.
ET_OFFSET = dt.timedelta(hours=-4)


# --------------------------------------------------------------------- #
# Parsers — pure, tested against a recorded payload
# --------------------------------------------------------------------- #


def parse_clock(display: str | None) -> float | None:
    """ESPN clock display -> seconds remaining in the period.

    Two observed formats: ``"3:36"`` and sub-minute ``"36.0"`` / ``"0.4"``.
    """
    if not display:
        return None
    try:
        if ":" in display:
            m, s = display.split(":", 1)
            return float(m) * 60.0 + float(s)
        return float(display)
    except ValueError:
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _made_attempted(value) -> tuple[int | None, int | None]:
    """``"29-64"`` -> (29, 64)."""
    if not value or "-" not in str(value):
        return None, None
    a, b = str(value).split("-", 1)
    return _int(a), _int(b)


def _wallclock(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_plays(payload: dict, *, espn_game_id: str, first_seen_at: dt.datetime,
                ) -> list[dict]:
    """Summary ``plays`` -> insertable rows. Transcription only."""
    out = []
    for p in payload.get("plays") or []:
        pid = p.get("id")
        if not pid:
            continue
        participants = p.get("participants") or []
        athlete = [
            (x.get("athlete") or {}).get("id") for x in participants[:2]
        ]
        athlete += [None, None]
        out.append({
            "first_seen_at": first_seen_at,
            "espn_game_id": espn_game_id,
            "play_id": str(pid),
            "sequence": _int(p.get("sequenceNumber")),
            "period": _int((p.get("period") or {}).get("number")),
            "clock_seconds": parse_clock((p.get("clock") or {}).get("displayValue")),
            "wallclock": _wallclock(p.get("wallclock")),
            "type_id": str((p.get("type") or {}).get("id") or "") or None,
            "type_text": ((p.get("type") or {}).get("text") or "")[:80] or None,
            "team_id": str((p.get("team") or {}).get("id") or "") or None,
            "athlete_id_1": str(athlete[0]) if athlete[0] else None,
            "athlete_id_2": str(athlete[1]) if athlete[1] else None,
            "shooting_play": p.get("shootingPlay"),
            "scoring_play": p.get("scoringPlay"),
            "points_attempted": _int(p.get("pointsAttempted")),
            "score_value": _int(p.get("scoreValue")),
            "home_score": _int(p.get("homeScore")),
            "away_score": _int(p.get("awayScore")),
            "text": (p.get("text") or "")[:300] or None,
            "raw": p,
        })
    return out


def parse_win_probability(payload: dict, *, espn_game_id: str,
                          first_seen_at: dt.datetime) -> list[dict]:
    out = []
    for w in payload.get("winprobability") or []:
        pid = w.get("playId")
        pct = w.get("homeWinPercentage")
        if not pid or pct is None:
            continue
        out.append({
            "first_seen_at": first_seen_at,
            "espn_game_id": espn_game_id,
            "play_id": str(pid),
            "home_win_pct": round(float(pct), 4),
        })
    return out


def parse_box(payload: dict, *, espn_game_id: str,
              first_seen_at: dt.datetime) -> dict | None:
    """Summary header + team boxscore -> one box-snapshot row."""
    header = payload.get("header") or {}
    comps = header.get("competitions") or [{}]
    comp = comps[0]
    status = comp.get("status") or {}
    state = ((status.get("type") or {}).get("state") or "")[:8] or None

    # The header status carries displayClock/period on live games (verified
    # on the scoreboard's shape; the live checklist confirms the summary's).
    # A finished game's header omits them — fall back to the newest play.
    clock = parse_clock(status.get("displayClock"))
    period = _int(status.get("period"))
    clock_source = "header" if clock is not None else None
    if clock is None or period is None:
        plays = payload.get("plays") or []
        if plays:
            last = plays[-1]
            if period is None:
                period = _int((last.get("period") or {}).get("number"))
            if clock is None:
                clock = parse_clock((last.get("clock") or {}).get("displayValue"))
                clock_source = "play"

    home = away = None
    for c in comp.get("competitors") or []:
        if c.get("homeAway") == "home":
            home = c
        elif c.get("homeAway") == "away":
            away = c
    if home is None or away is None:
        return None

    sides = {}
    for t in (payload.get("boxscore") or {}).get("teams") or []:
        tid = str((t.get("team") or {}).get("id") or "")
        stats = {s.get("name"): s.get("displayValue")
                 for s in t.get("statistics") or []}
        sides[tid] = stats

    def side_cols(team, prefix):
        tid = str((team.get("team") or {}).get("id") or "")
        stats = sides.get(tid, {})
        fgm, fga = _made_attempted(stats.get("fieldGoalsMade-fieldGoalsAttempted"))
        tpm, tpa = _made_attempted(
            stats.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
        ftm, fta = _made_attempted(stats.get("freeThrowsMade-freeThrowsAttempted"))
        return {
            f"{prefix}_team_id": tid or None,
            f"{prefix}_score": _int(team.get("score")),
            f"{prefix}_fgm": fgm, f"{prefix}_fga": fga,
            f"{prefix}_tpm": tpm, f"{prefix}_tpa": tpa,
            f"{prefix}_ftm": ftm, f"{prefix}_fta": fta,
            f"{prefix}_oreb": _int(stats.get("offensiveRebounds")),
            f"{prefix}_turnovers": _int(stats.get("totalTurnovers")
                                        or stats.get("turnovers")),
            f"{prefix}_stats": stats or None,
        }

    row = {
        "first_seen_at": first_seen_at,
        "espn_game_id": espn_game_id,
        "game_state": state,
        # NESTED spelling — the flat `seasonType` does not exist here (#25).
        "season_type": _int((header.get("season") or {}).get("type")),
        "period": period,
        "clock_seconds": clock,
        "clock_source": clock_source,
    }
    row.update(side_cols(home, "home"))
    row.update(side_cols(away, "away"))
    return row


def parse_players(payload: dict, *, espn_game_id: str,
                  first_seen_at: dt.datetime) -> list[dict]:
    out = []
    for team_block in (payload.get("boxscore") or {}).get("players") or []:
        tid = str((team_block.get("team") or {}).get("id") or "") or None
        for stat_block in team_block.get("statistics") or []:
            names = stat_block.get("names") or []
            idx = {n: i for i, n in enumerate(names)}

            def col(stats, name, i=idx):
                j = i.get(name)
                return stats[j] if j is not None and j < len(stats) else None

            for a in stat_block.get("athletes") or []:
                ath = a.get("athlete") or {}
                stats = a.get("stats") or []
                fgm, fga = _made_attempted(col(stats, "FG"))
                tpm, tpa = _made_attempted(col(stats, "3PT"))
                ftm, fta = _made_attempted(col(stats, "FT"))
                out.append({
                    "first_seen_at": first_seen_at,
                    "espn_game_id": espn_game_id,
                    "team_id": tid,
                    "athlete_id": str(ath.get("id") or ""),
                    "athlete_name": (ath.get("displayName") or "")[:80] or None,
                    "minutes": _int(col(stats, "MIN")),
                    "points": _int(col(stats, "PTS")),
                    "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa,
                    "ftm": ftm, "fta": fta,
                    "rebounds": _int(col(stats, "REB")),
                    "assists": _int(col(stats, "AST")),
                    "turnovers": _int(col(stats, "TO")),
                    "fouls": _int(col(stats, "PF")),
                    "plus_minus": _int(col(stats, "+/-")),
                    "starter": a.get("starter"),
                    "active": a.get("active"),
                    "ejected": a.get("ejected"),
                    "did_not_play": a.get("didNotPlay"),
                    "reason": (a.get("reason") or "")[:120] or None,
                })
    return [r for r in out if r["athlete_id"]]


def parse_injuries(payload: dict, *, espn_game_id: str,
                   first_seen_at: dt.datetime) -> list[dict]:
    out = []
    for team_block in payload.get("injuries") or []:
        tid = str((team_block.get("team") or {}).get("id") or "") or None
        for inj in team_block.get("injuries") or []:
            ath = inj.get("athlete") or {}
            aid = str(ath.get("id") or "")
            status = (inj.get("status") or "")[:40]
            if not aid or not status:
                continue
            out.append({
                "first_seen_at": first_seen_at,
                "espn_game_id": espn_game_id,
                "team_id": tid,
                "athlete_id": aid,
                "athlete_name": (ath.get("displayName") or "")[:80] or None,
                "status": status,
                "details": inj.get("details"),
            })
    return out


# --------------------------------------------------------------------- #
# The recorder
# --------------------------------------------------------------------- #


class EspnLiveRecorder:
    def __init__(
        self,
        sessionmaker,
        *,
        client: ESPNClient | None = None,
        summary_interval: float = DEFAULT_SUMMARY_INTERVAL,
        scoreboard_interval: float = DEFAULT_SCOREBOARD_INTERVAL,
        player_every: float = DEFAULT_PLAYER_EVERY,
    ) -> None:
        self._Session = sessionmaker
        self._client = client or ESPNClient()
        self.summary_interval = summary_interval
        self.scoreboard_interval = scoreboard_interval
        self.player_every = player_every
        self._live: set[str] = set()
        #: Games that left the live set and are owed one final summary.
        self._pending_final: set[str] = set()
        self._last_scoreboard = float("-inf")
        self._last_player_write: dict[str, float] = {}
        self._heartbeat = hb.Heartbeat(sessionmaker, SERVICE_ESPN_LIVE)
        self._stop = threading.Event()

    # ---- live detection --------------------------------------------------- #

    def _scoreboard_dates(self, now: dt.datetime) -> list[str]:
        """Today's and yesterday's ET dates — the pair covers every game that
        straddles midnight UTC (the 02:00Z tips)."""
        et_today = (now + ET_OFFSET).date()
        return [et_today.strftime("%Y%m%d"),
                (et_today - dt.timedelta(days=1)).strftime("%Y%m%d")]

    def refresh_live_set(self, now: dt.datetime) -> None:
        if time.monotonic() - self._last_scoreboard < self.scoreboard_interval:
            return
        self._last_scoreboard = time.monotonic()
        seen_live: set[str] = set()
        for date_str in self._scoreboard_dates(now):
            try:
                board = self._client.get_scoreboard(date_str)
            except Exception as exc:
                log.warning("espn_live_scoreboard_failed",
                            date=date_str, error=str(exc)[:150])
                continue
            for event in board.get("events") or []:
                state = ((((event.get("competitions") or [{}])[0]
                           .get("status") or {}).get("type") or {})
                         .get("state"))
                gid = str(event.get("id") or "")
                if not gid:
                    continue
                if state == "in":
                    seen_live.add(gid)
        # Games that just left the live set get one final summary sweep.
        self._pending_final |= self._live - seen_live
        self._live = seen_live

    # ---- one game, one poll ----------------------------------------------- #

    def record_game(self, espn_game_id: str, *, final: bool = False) -> int:
        first_seen_at = dt.datetime.now(UTC)
        try:
            payload = self._client.get(SUMMARY_URL, params={"event": espn_game_id})
        except Exception as exc:
            log.warning("espn_live_summary_failed",
                        game=espn_game_id, error=str(exc)[:150])
            return 0

        rows = 0
        with self._Session() as s:
            plays = parse_plays(payload, espn_game_id=espn_game_id,
                                first_seen_at=first_seen_at)
            if plays:
                result = s.execute(
                    pg_insert(EspnLivePlay).values(plays)
                    .on_conflict_do_nothing(index_elements=["play_id"]))
                rows += result.rowcount or 0

            wp = parse_win_probability(payload, espn_game_id=espn_game_id,
                                       first_seen_at=first_seen_at)
            if wp:
                result = s.execute(
                    pg_insert(EspnLiveWinProbability).values(wp)
                    .on_conflict_do_nothing(index_elements=["play_id"]))
                rows += result.rowcount or 0

            box = parse_box(payload, espn_game_id=espn_game_id,
                            first_seen_at=first_seen_at)
            if box is not None:
                s.add(EspnLiveBoxSnapshot(**box))
                rows += 1

            due = (final or time.monotonic()
                   - self._last_player_write.get(espn_game_id, float("-inf"))
                   >= self.player_every)
            if due:
                players = parse_players(payload, espn_game_id=espn_game_id,
                                        first_seen_at=first_seen_at)
                for p in players:
                    s.add(EspnLivePlayerSnapshot(**p))
                rows += len(players)
                if players:
                    self._last_player_write[espn_game_id] = time.monotonic()

            injuries = parse_injuries(payload, espn_game_id=espn_game_id,
                                      first_seen_at=first_seen_at)
            if injuries:
                result = s.execute(
                    pg_insert(EspnLiveInjuryObservation).values(injuries)
                    .on_conflict_do_nothing(
                        index_elements=["espn_game_id", "athlete_id", "status"]))
                rows += result.rowcount or 0

            s.commit()

        # The #25 shape, made loud: a live game whose summary parsed NOTHING
        # is a broken parser or a moved payload, not a quiet morning.
        if not final and box is None and not plays:
            log.error("espn_live_empty_payload", game=espn_game_id,
                      note="live game, zero rows parsed — the season-type "
                           "outage failed exactly this quietly (#25)")
        return rows

    # ---- cycle / lifecycle ------------------------------------------------ #

    def cycle(self) -> tuple[int, int]:
        """(games polled, rows written). Public so tests drive it."""
        now = dt.datetime.now(UTC)
        self.refresh_live_set(now)
        rows = 0
        polled = 0
        for gid in sorted(self._live):
            rows += self.record_game(gid)
            polled += 1
        for gid in sorted(self._pending_final):
            rows += self.record_game(gid, final=True)
            polled += 1
            self._pending_final.discard(gid)
            self._last_player_write.pop(gid, None)
        return polled, rows

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        log.info("espn_live_recorder_started",
                 summary_interval=self.summary_interval,
                 scoreboard_interval=self.scoreboard_interval)
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                _, rows = self.cycle()
                game_live = bool(self._live)
            except Exception as exc:   # one bad cycle must not kill the run
                log.error("espn_live_cycle_failed", error=str(exc)[:300])
                rows, game_live = 0, None
            # Beat EVERY cycle, work or none: rows_written=0 + game_live=False
            # overnight reads IDLE, not DEAD — the header depends on this.
            self._heartbeat.beat(
                interval_seconds=(self.summary_interval if self._live
                                  else self.scoreboard_interval),
                rows_written=rows,
                cycle_seconds=time.monotonic() - started,
                game_live=game_live,
            )
            wait = self.summary_interval if self._live else self.scoreboard_interval
            self._stop.wait(max(wait - (time.monotonic() - started), 0.5))


# --------------------------------------------------------------------- #
# The checklist report (first live game verification, question 4)
# --------------------------------------------------------------------- #


def checklist_report(session) -> str:
    """Feed-lag distribution + the loud conditions, from the recorded rows."""
    from sqlalchemy import text

    out = ["signal-side first-live-game checklist (docs/infra/signal-side.md)"]
    lag = session.execute(text("""
        SELECT count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY lag) AS p50,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY lag) AS p90,
               max(lag) AS mx
        FROM (
            SELECT extract(epoch FROM (first_seen_at - wallclock)) AS lag
            FROM espn_live_plays
            WHERE wallclock IS NOT NULL
              AND first_seen_at > wallclock
              AND first_seen_at - wallclock < interval '10 minutes'
        ) t
    """)).one()
    if lag.n:
        out.append(f"play feed lag (wallclock -> first_seen): n={lag.n:,}  "
                   f"p50={lag.p50:.1f}s  p90={lag.p90:.1f}s  max={lag.mx:.1f}s")
    else:
        out.append("play feed lag: NO DATA — no live game recorded yet")
    src = session.execute(text("""
        SELECT clock_source, count(*) FROM espn_live_box_snapshots
        WHERE game_state = 'in' GROUP BY clock_source
    """)).all()
    out.append(f"live clock source counts (header vs play): {dict(src) or 'NO DATA'}")
    empty = session.execute(text("""
        SELECT count(*) FROM espn_live_box_snapshots
        WHERE game_state = 'in' AND period IS NULL AND clock_seconds IS NULL
    """)).scalar()
    out.append(f"live snapshots with NO clock at all (loud if > 0): {empty}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(prog="espn-live-recorder")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--checklist", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)
    from core.storage import get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())
    if args.checklist:
        with Session() as s:
            print(checklist_report(s))
        return 0

    recorder = EspnLiveRecorder(Session)
    if args.once:
        polled, rows = recorder.cycle()
        print(f"polled {polled} games, wrote {rows} rows", file=sys.stderr)
        return 0
    recorder.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
