"""ESPN cricket recorder: parsers against real (trimmed) payloads, the
change rule, the once-only toss stamp, and the recorder's own active-set
predicate driven with a stub session and client. No DB, no network:

    pytest --noconftest tests/test_espn_cricket_recorder.py

Fixtures are trimmed copies of the venue's own 2026-09-13 payloads: header
(three events: post 1549533, in 1540218, pre 1534213 at 23:00Z) and two
summaries (1549533 finished with toss+innings+result, 1534213 not started).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import ClassVar

import pytest
import sqlalchemy as sa
from sqlalchemy import Insert
from sqlalchemy.dialects import postgresql

from core.feeds import espn_cricket_recorder as rec

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 13, 14, 0, tzinfo=UTC)
TOSS = "Namibia , elected to bat first"


def _load(name: str) -> dict:
    with open(os.path.join(FIX, name)) as f:
        return json.load(f)


def _post() -> dict:
    return rec.parse_summary(_load("espn_cricket_summary_post.json"))


# ------------------------------------------------------------------ parsers #
def test_header_rows_state_teams_winner_toss():
    rows = {r["event_id"]: r for r in rec.parse_header(_load("espn_cricket_header.json"))}
    assert {r["state"] for r in rows.values()} == {"pre", "in", "post"}
    post = rows["1549533"]
    assert post["series_id"] == "24670"
    assert (post["home_team"], post["away_team"], post["winner_team"]) == (
        "Namibia", "South Africa", "South Africa")
    assert post["scheduled_start"] == dt.datetime(2026, 9, 13, 7, 30, tzinfo=UTC)
    assert (post["period"], post["status_detail"]) == (2, "Final")
    assert post["result_text"] == "South Africa won by 9 wkts (171b rem)"
    assert post["toss_text"] == TOSS
    live = rows["1540218"]
    assert live["toss_text"] == "Guyana Amazon Warriors Women , elected to field first"
    assert live["winner_team"] is None and live["period"] == 1
    assert rows["1534213"]["toss_text"] is None and rows["1534213"]["period"] == 0


def test_summary_post_toss_innings_result():
    row = _post()
    assert (row["event_id"], row["series_id"], row["state"]) == ("1549533", "24670", "post")
    assert row["toss_text"] == TOSS
    assert (row["winner_team"], row["period"], row["status_detail"]) == ("South Africa", 2, "Final")
    assert row["scheduled_start"] == dt.datetime(2026, 9, 13, 7, 30, tzinfo=UTC)
    assert row["commentary_count"] == 358
    assert row["commentary_latest"] == "202103 Heingo to Brevis, SIX"
    by_side = {i["homeAway"]: i for i in row["innings"]}
    assert (by_side["home"]["team"], by_side["away"]["team"]) == ("Namibia", "South Africa")
    assert by_side["home"]["linescores"][0]["runs"] == 156
    chase = by_side["away"]["linescores"][1]
    assert tuple(chase[k] for k in ("period", "runs", "wickets", "overs", "target", "isBatting")) == (
        2, 157, 1, 21.3, 157, True)
    assert "commentaries" not in row["raw"]["header"]["competitions"][0]
    assert "rosters" not in row["raw"] and row["raw"]["notes"]


def test_summary_pre_has_nothing_yet():
    row = rec.parse_summary(_load("espn_cricket_summary_pre.json"))
    assert (row["event_id"], row["state"]) == ("1534213", "pre")
    assert row["toss_text"] is None and row["winner_team"] is None and row["period"] == 0
    assert row["commentary_count"] == 1     # ESPN's "waiting for this match" placeholder
    assert all(i["linescores"] == [] for i in row["innings"])


# -------------------------------------------------------------- change rule #
def test_identical_payload_writes_nothing():
    first = rec.merge(None, _post(), NOW)
    assert first["captured_at"] == NOW and first["raw"] is not None
    assert rec.merge(first, _post(), NOW + dt.timedelta(seconds=15)) is None


def test_ball_changes_row_but_not_raw():
    first = rec.merge(None, _post(), NOW)
    nxt = rec.merge(first, {**_post(), "commentary_count": 359}, NOW + dt.timedelta(seconds=15))
    assert nxt["commentary_count"] == 359 and nxt["raw"] is None
    assert nxt["toss_first_seen_at"] == first["toss_first_seen_at"] == NOW


def test_toss_first_seen_stamped_once_and_never_blanked():
    pre = rec.parse_summary(_load("espn_cricket_summary_pre.json"))
    r0 = rec.merge(None, pre, NOW)
    assert r0.get("toss_first_seen_at") is None
    t1 = NOW + dt.timedelta(minutes=5)
    r1 = rec.merge(r0, {**pre, "toss_text": "Barbados Tridents , elected to bat first"}, t1)
    assert r1["toss_first_seen_at"] == t1
    r2 = rec.merge(r1, {**r1, "commentary_count": 5, "raw": None}, t1 + dt.timedelta(minutes=20))
    assert r2["toss_first_seen_at"] == t1 and r2["captured_at"] == t1 + dt.timedelta(minutes=20)
    # a header row carries no innings and, here, no toss note: it must not blank either
    hdr = next(r for r in rec.parse_header(_load("espn_cricket_header.json")) if r["event_id"] == "1534213")
    assert hdr["toss_text"] is None
    assert rec.merge(r2, hdr, t1 + dt.timedelta(minutes=21)) is None


# ---------------------------------------------------------------- dry run #
class _Session:
    """Enough session for the seed query (no prior row) and the insert; no database."""
    stmts: ClassVar[list] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt):
        self.stmts.append(stmt)
        return self

    def mappings(self):
        return self

    def first(self):
        return None

    def commit(self):
        pass


class _Client:
    def __init__(self):
        self.calls: list = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if "header" in url:
            return _load("espn_cricket_header.json")
        return _load("espn_cricket_summary_post.json")   # whatever the event asked


def _written() -> list[dict]:
    return [s.compile(dialect=postgresql.dialect()).params
            for s in _Session.stmts if isinstance(s, Insert)]


def test_recorder_writes_changes_then_nothing():
    _Session.stmts = []
    client = _Client()
    r = rec.CricketRecorder(_Session, client=client)
    active, rows = r.cycle(NOW)
    # header: two dates, three schedule rows. active: the live match (its
    # summary comes back as 1549533's -> refused, never filed under 1540218)
    # and the finished one (summary adds innings + count -> one more row).
    # 1534213 starts at 23:00Z, 9h out: not active.
    assert [p["dates"] for u, p in client.calls if "header" in u] == ["20260913", "20260914"]
    assert (active, rows) == (2, 4)
    written = _written()
    ids = [w["event_id"] for w in written]
    assert ids.count("1549533") == 2 and "1540218" in ids and "1534213" in ids
    assert written[-1]["innings"] and written[-1]["commentary_count"] == 358
    assert written[-1]["toss_first_seen_at"] == NOW and "id" not in written[-1]
    # second cycle: header is rate-gated, the finished match holds its innings,
    # the live one still refuses the mismatched payload -> nothing written.
    assert r.cycle(NOW + dt.timedelta(seconds=15)) == (1, 0)
    assert len(_written()) == 4


@pytest.mark.parametrize("minutes_before, active", [(91, 2), (89, 3)])
def test_pre_match_enters_the_active_set_90_minutes_out(minutes_before, active):
    _Session.stmts = []
    now = dt.datetime(2026, 9, 13, 23, 0, tzinfo=UTC) - dt.timedelta(minutes=minutes_before)
    assert rec.CricketRecorder(_Session, client=_Client()).cycle(now)[0] == active


# --------------------------------------------------------------------------- #
# A REAL database. Everything above this line runs against `_Session`, which
# collects statements and never sends them anywhere, so it cannot see a
# constraint. The defect of 2026-09-14 was a UniqueViolation, and nine green
# tests had no way to notice it: within one cycle the header sweep files a row
# and poll_summary files the richer view of the same match at the SAME `now`,
# and (event_id, captured_at) is unique. run_forever caught it, logged
# espn_cricket_cycle_failed and discarded the whole cycle -- on a match at the
# toss, that is the one observation that cannot be backfilled.
# --------------------------------------------------------------------------- #

@pytest.fixture()
def _clean_events():
    from core.storage import get_engine
    # create_all(checkfirst) rather than an alembic run: this table is newer than
    # most deploys and the suite's database may not carry it yet. The DDL comes
    # from the recorder's own metadata, so the UNIQUE(event_id, captured_at) under
    # test is the one the module declares, not one retyped into a fixture.
    rec.EVENTS.create(bind=get_engine(), checkfirst=True)
    with get_engine().begin() as c:
        c.execute(sa.text("DELETE FROM espn_cricket_events WHERE event_id = 'utest-1'"))
    yield
    with get_engine().begin() as c:
        c.execute(sa.text("DELETE FROM espn_cricket_events WHERE event_id = 'utest-1'"))


def _sessionmaker():
    from sqlalchemy.orm import sessionmaker
    from core.storage import get_engine
    return sessionmaker(bind=get_engine())


def test_two_views_of_one_instant_collapse_to_the_richer_row(_clean_events):
    """The header view then the summary view, same match, same `now`.

    Before the upsert this raised UniqueViolation and the caller threw the cycle
    away. The table's constraint is right -- an event has one state per instant --
    so the fix keeps one row and lets the later, richer write win."""
    from core.storage import get_engine
    now = dt.datetime(2026, 9, 14, 10, 51, tzinfo=dt.timezone.utc)
    r = rec.CricketRecorder(_sessionmaker(), client=_Client())
    thin = {"series_id": "24740", "event_id": "utest-1", "name": "A v B",
            "scheduled_start": now, "state": "in", "period": 1,
            "status_detail": None, "result_text": None, "toss_text": None,
            "home_team": "A", "away_team": "B", "home_score": None, "away_score": None}
    assert r.observe(dict(thin), now) == 1
    assert r.observe({**thin, "toss_text": "A won the toss"}, now) == 1
    with get_engine().connect() as c:
        rows = c.execute(sa.text(
            "SELECT toss_text FROM espn_cricket_events WHERE event_id='utest-1'")).all()
    assert len(rows) == 1, f"one event, one instant, one row -- got {len(rows)}"
    assert rows[0][0] == "A won the toss", "the richer view must win"


def test_a_later_instant_is_a_new_row(_clean_events):
    """Guards the guard: an upsert that collapsed everything onto one row would
    pass the test above and silently destroy the time series."""
    from core.storage import get_engine
    t0 = dt.datetime(2026, 9, 14, 10, 51, tzinfo=dt.timezone.utc)
    r = rec.CricketRecorder(_sessionmaker(), client=_Client())
    base = {"series_id": "24740", "event_id": "utest-1", "name": "A v B",
            "scheduled_start": t0, "state": "in", "period": 1,
            "status_detail": None, "result_text": None, "toss_text": None,
            "home_team": "A", "away_team": "B", "home_score": None, "away_score": None}
    r.observe(dict(base), t0)
    r.observe({**base, "state": "post"}, t0 + dt.timedelta(minutes=1))
    with get_engine().connect() as c:
        n = c.execute(sa.text(
            "SELECT count(*) FROM espn_cricket_events WHERE event_id='utest-1'")).scalar()
    assert n == 2
