"""ESPN cricket signal recorder: the toss, the innings state and the result.

    python -m core.feeds.espn_cricket_recorder

Read-only against ESPN; one table (espn_cricket_events) plus a heartbeat,
stamping WHEN the toss, each innings change and the result became visible.
Header (all series, today+tomorrow UTC) every 60 s; summary every 15 s for
matches 'in', 'pre' within 90 min of start (the toss lands ~30 min before
first ball) and once per 'post' match. A row is written ONLY on a CHANGE_KEYS
change; `raw` (~60 KB) only on a state/period/toss/winner change, since every
ball changes innings and commentary_count (300 x 60 KB = 20 MB a match).
Venue facts (2026-09-13): header and summary both carry notes[type=="toss"]
with IDENTICAL text; `winner` is a bool pre-match and the STRING "true" after;
`commentaries` is a dict keyed by id -- only the count and the latest are
kept. One worker, sequential GETs, 10 s timeout, one attempt, 60 s backoff.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import sys
import time

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import BIGINT, JSONB

from core import heartbeat as hb
from core.config import ESPNConfig
from core.feeds.espn_client import ESPNClient
from core.storage import Base, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)
UTC, SERVICE = dt.timezone.utc, "espn_cricket_recorder"
HEADER_URL = "https://site.web.api.espn.com/apis/v2/scoreboard/header"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/cricket/{series}/summary"
HEADER_INTERVAL, SUMMARY_INTERVAL, BACKOFF, PRE_WINDOW = 60.0, 15.0, 60.0, dt.timedelta(minutes=90)
CHANGE_KEYS = ("state", "period", "toss_text", "innings", "commentary_count", "winner_team")
RAW_KEYS = ("state", "period", "toss_text", "winner_team")   # result_text is a status line
LS_KEYS = ("period", "runs", "wickets", "overs", "isBatting", "target", "description")
TS = sa.DateTime(timezone=True)

EVENTS = sa.Table(
    "espn_cricket_events", Base.metadata,
    sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
    sa.Column("series_id", sa.String(16), nullable=False),
    sa.Column("event_id", sa.String(16), nullable=False, index=True),
    *[sa.Column(c, sa.Text) for c in ("name", "home_team", "away_team", "status_detail", "toss_text",
                                      "winner_team", "result_text", "commentary_latest")],
    sa.Column("scheduled_start", TS), sa.Column("toss_first_seen_at", TS),   # the latter: stamped once
    sa.Column("state", sa.String(8)), sa.Column("period", sa.SmallInteger),
    sa.Column("commentary_count", sa.Integer), sa.Column("captured_at", TS, nullable=False, index=True),
    sa.Column("innings", JSONB), sa.Column("raw", JSONB),   # innings: per competitor, homeAway verbatim
    sa.UniqueConstraint("event_id", "captured_at"),
)


def _ts(v) -> dt.datetime | None:
    with contextlib.suppress(AttributeError, ValueError):
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    return None


def _sides(competitors) -> dict:   # home/away by ESPN's homeAway field, never by position
    out = {"home_team": None, "away_team": None, "winner_team": None}
    for c in competitors:
        name = (c.get("team") or c).get("displayName")
        if c.get("homeAway") in ("home", "away"):
            out[f"{c['homeAway']}_team"] = name
        if str(c.get("winner")).lower() == "true":
            out["winner_team"] = name
    return out


def _row(series, ev_id, name, date, notes, status: dict, competitors) -> dict:
    return {"series_id": str(series), "event_id": str(ev_id), "name": name, "scheduled_start": _ts(date),
            "state": (status.get("type") or {}).get("state"), "period": status.get("period"),
            "status_detail": (status.get("type") or {}).get("detail"), "result_text": status.get("summary"),
            "toss_text": next((n.get("text") for n in notes or [] if n.get("type") == "toss"), None),
            **_sides(competitors or [])}


def parse_header(payload: dict) -> list[dict]:
    return [_row(lg.get("id"), ev.get("id"), ev.get("name"), ev.get("date"), ev.get("notes"),
                 ev.get("fullStatus") or {"type": {"state": ev.get("status")}}, ev.get("competitors"))
            for lg in (payload.get("sports") or [{}])[0].get("leagues") or [] for ev in lg.get("events") or []]


def parse_summary(payload: dict) -> dict:
    hd = payload.get("header") or {}
    comp = (hd.get("competitions") or [{}])[0]
    latest = max((comp.get("commentaries") or {}).values(), key=lambda c: c.get("sequence") or 0, default=None)
    return {**_row((hd.get("league") or {}).get("id"), hd.get("id"), hd.get("name"), comp.get("date"),
                   payload.get("notes"), comp.get("status") or {}, comp.get("competitors")),
            "innings": [{"team": (c.get("team") or {}).get("displayName"), "homeAway": c.get("homeAway"),
                         "score": c.get("score"),
                         "linescores": [{k: ls.get(k) for k in LS_KEYS} for ls in c.get("linescores") or []]}
                        for c in comp.get("competitors") or []],
            "commentary_count": comp.get("commentaryCount"),
            "commentary_latest": latest and f"{latest.get('sequence')} {latest.get('shortText')}" or None,
            "raw": {**{k: payload.get(k) for k in ("notes", "gameInfo", "situation", "meta")},
                    "header": {**hd, "competitions": [{k: v for k, v in comp.items() if k != "commentaries"}]}}}


def merge(prev: dict | None, row: dict, now: dt.datetime) -> dict | None:
    """The row to write, or None if nothing in CHANGE_KEYS changed. A later source never blanks an
    earlier fact (a header row has no innings, may lack the toss note); the toss is stamped once."""
    prev = prev or {}
    new = {**prev, **{k: v for k, v in row.items() if v is not None}}
    if new.get("toss_text") and not prev.get("toss_first_seen_at"):
        new["toss_first_seen_at"] = now
    if all(new.get(k) == prev.get(k) for k in CHANGE_KEYS):
        return None
    new["captured_at"] = now
    new["raw"] = row.get("raw") if any(new.get(k) != prev.get(k) for k in RAW_KEYS) else None
    return new


class CricketRecorder:
    def __init__(self, sessionmaker, *, client=None) -> None:
        self._Session = sessionmaker
        self._client = client or ESPNClient(ESPNConfig(http_timeout_seconds=10.0, max_retries=1))
        self._last, self._sched = {}, {}   # event_id -> last written row (seeded from the table) / header row
        self._last_header = self._backoff_until = float("-inf")
        self._heartbeat = hb.Heartbeat(sessionmaker, SERVICE)

    def _get(self, url: str, params: dict) -> dict | None:
        if time.monotonic() < self._backoff_until:
            return None
        try:
            return self._client.get(url, params=params)
        except Exception as exc:  # noqa: BLE001 - any failure backs off; the loop outlives ESPN
            self._backoff_until = time.monotonic() + BACKOFF
            log.warning("espn_cricket_get_failed", url=url, params=params, error=str(exc)[:150])
            return None

    def observe(self, row: dict, now: dt.datetime) -> int:
        eid = row["event_id"]
        if eid not in self._last:   # seed from the table: a restart neither re-writes nor re-stamps
            with self._Session() as s:
                r = s.execute(sa.select(EVENTS).where(EVENTS.c.event_id == eid)
                              .order_by(EVENTS.c.captured_at.desc()).limit(1)).mappings().first()
            self._last[eid] = {k: v for k, v in (r or {}).items() if k != "id"}
        new = merge(self._last[eid], row, now)
        if new is None:
            return 0
        with self._Session() as s:
            s.execute(sa.insert(EVENTS).values(**new))
            s.commit()
        self._last[eid] = {**new, "raw": None}
        return 1

    def poll_summary(self, eid: str, now: dt.datetime) -> int:
        payload = self._get(SUMMARY_URL.format(series=self._sched[eid]["series_id"]), {"event": eid})
        row = parse_summary(payload) if payload else None
        if not row or row["event_id"] != eid:   # never file a payload under another match
            log.error("espn_cricket_summary_unusable", event_id=eid, got=row and row["event_id"])
            return 0
        self._sched[eid]["state"] = row["state"] or self._sched[eid]["state"]
        return self.observe(row, now)

    def cycle(self, now: dt.datetime | None = None) -> tuple[int, int]:
        now, rows = now or dt.datetime.now(UTC), 0
        if time.monotonic() - self._last_header >= HEADER_INTERVAL:
            self._last_header = time.monotonic()
            for d in (now, now + dt.timedelta(days=1)):
                board = self._get(HEADER_URL, {"sport": "cricket", "dates": d.strftime("%Y%m%d")})
                for r in parse_header(board or {}):
                    self._sched[r["event_id"]] = r
                    rows += self.observe(r, now)
        # 'post' stays active until a summary (or the seeded prior) holds its innings: one final sweep
        active = sorted(e for e, r in self._sched.items() if r["state"] == "in" or (
            r["state"] == "pre" and r["scheduled_start"] and r["scheduled_start"] <= now + PRE_WINDOW) or (
            r["state"] == "post" and not self._last.get(e, {}).get("innings")))
        for eid in active:
            rows += self.poll_summary(eid, now)
        log.info("espn_cricket_cycle", scheduled=len(self._sched), active=len(active), rows_written=rows)
        return len(active), rows

    def run_forever(self) -> None:
        while True:
            started = time.monotonic()
            try:
                active, rows = self.cycle()
            except Exception as exc:  # noqa: BLE001 - one bad cycle must not kill the run
                log.error("espn_cricket_cycle_failed", error=str(exc)[:300])
                active = rows = 0
            self._heartbeat.beat(interval_seconds=SUMMARY_INTERVAL, rows_written=rows,
                                 cycle_seconds=time.monotonic() - started, game_live=bool(active))
            time.sleep(max(SUMMARY_INTERVAL - (time.monotonic() - started), 0.5))


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    CricketRecorder(get_sessionmaker(get_engine())).run_forever()
