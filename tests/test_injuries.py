"""Injury change-log tests.

This recorder has to be right the first time. ESPN publishes current status
only, so anything it fails to capture tonight is gone — there is no backfill to
run later. The two behaviours worth pinning down:

* an unchanged designation must not write a row (or the log stops being a log);
* a player who vanishes from the feed must write a `Cleared` row (or she stays
  "Out" forever and every later as_of query is wrong).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from core.feeds.espn_injuries import (
    STATUS_CLEARED,
    Designation,
    _athlete_id,
    parse_injuries,
    record_once,
)
from core.storage import InjuryPoll, InjuryReport, get_engine, get_sessionmaker

UTC = dt.timezone.utc
TEAM_ID = "9901"


class FakeClient:
    """Returns a queued payload instead of calling ESPN."""

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.calls = 0

    def get(self, url, params=None):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return payload


def _payload(*entries: tuple[str, str, str]) -> dict:
    """(athlete_id, name, status) -> an ESPN-shaped injuries payload."""
    return {
        "injuries": [
            {
                "id": TEAM_ID,
                "displayName": "Test Team",
                "injuries": [
                    {
                        "status": status,
                        "date": "2026-07-31T22:37Z",
                        "type": {"name": f"INJURY_STATUS_{status.upper()}"},
                        "details": {"type": "Knee", "returnDate": "2026-08-10"},
                        "athlete": {
                            "displayName": name,
                            "position": {"abbreviation": "G"},
                            "links": [
                                {"href": f"https://www.espn.com/wnba/player/_/id/{aid}/x"}
                            ],
                        },
                    }
                    for aid, name, status in entries
                ],
            }
        ]
    }


# ------------------------------------------------------------------ #
# Parsing
# ------------------------------------------------------------------ #


def test_athlete_id_recovered_from_player_link():
    """ESPN omits athlete.id from this feed but leaks it in every URL."""
    athlete = {"links": [{"href": "https://www.espn.com/wnba/player/_/id/4596309/liatu-king"}]}
    assert _athlete_id(athlete) == "4596309"


def test_athlete_id_recovered_from_headshot():
    athlete = {
        "headshot": {"href": "https://a.espncdn.com/i/headshots/wnba/players/full/3904577.png"}
    }
    assert _athlete_id(athlete) == "3904577"


def test_athlete_without_any_id_is_dropped():
    payload = {
        "injuries": [
            {"id": TEAM_ID, "displayName": "T", "injuries": [
                {"status": "Out", "athlete": {"displayName": "Nobody"}}
            ]}
        ]
    }
    designations, n_teams = parse_injuries(payload)
    assert designations == []
    assert n_teams == 1


def test_parse_extracts_the_fields_that_matter():
    designations, n_teams = parse_injuries(_payload(("1", "A Player", "Out")))
    assert n_teams == 1
    (d,) = designations
    assert (d.athlete_id, d.athlete_name, d.status) == ("1", "A Player", "Out")
    assert d.detail_type == "Knee"
    assert d.return_date == "2026-08-10"
    assert d.team_id == TEAM_ID


def test_comment_edits_are_not_status_changes():
    """`reported_at` is excluded from the change key on purpose."""
    a = Designation(
        athlete_id="1", athlete_name="A", position="G", team_id=TEAM_ID,
        team_name="T", status="Out", status_type="INJURY_STATUS_OUT",
        detail_type="Knee", return_date="2026-08-10",
        reported_at=dt.datetime(2026, 7, 31, tzinfo=UTC),
    )
    b = Designation(**{**a.__dict__, "reported_at": dt.datetime(2026, 8, 1, tzinfo=UTC)})
    assert a.state_key == b.state_key


# ------------------------------------------------------------------ #
# The change log (database)
# ------------------------------------------------------------------ #


#: Poll timestamps live in a fictional year, so nothing here can collide with a
#: real poll even if the source key were ever reused.
FAKE_YEAR = 1999

#: Own feed identity, so these rows are a separate state machine from the real
#: recorder's. The local database is a synced copy of the primary and holds
#: genuine designations; without this the test's empty payload would
#: "clear" every real player.
TEST_SOURCE = "test_injuries"


@pytest.fixture
def session():
    Session = get_sessionmaker(get_engine())
    lo = dt.datetime(FAKE_YEAR, 1, 1, tzinfo=UTC)
    hi = dt.datetime(FAKE_YEAR + 1, 1, 1, tzinfo=UTC)

    def _clean(s):
        s.execute(
            delete(InjuryReport)
            .where(InjuryReport.source == TEST_SOURCE)
        )
        s.execute(
            delete(InjuryPoll)
            .where(InjuryPoll.source == TEST_SOURCE)
        )
        s.commit()

    with Session() as s:
        _clean(s)
        yield s
        s.rollback()
        _clean(s)


def _statuses(session) -> list[tuple[str, str]]:
    """Rows this test wrote, in order. Scoped to the fictional year: the local
    database is a synced copy of the primary and holds real designations."""
    return [
        (r.athlete_id, r.status)
        for r in session.scalars(
            select(InjuryReport)
            .where(InjuryReport.source == TEST_SOURCE)
            .order_by(InjuryReport.captured_at, InjuryReport.athlete_id)
        ).all()
    ]


def test_unchanged_designation_writes_nothing_the_second_time(session):
    client = FakeClient([_payload(("1", "A", "Out"))])
    t1 = dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC)
    t2 = dt.datetime(FAKE_YEAR, 8, 1, 12, 20, tzinfo=UTC)

    assert record_once(session=session, client=client, source=TEST_SOURCE, captured_at=t1) == 1
    assert record_once(session=session, client=client, source=TEST_SOURCE, captured_at=t2) == 0
    assert _statuses(session) == [("1", "Out")]
    # But both polls are recorded, so the silence is not ambiguous.
    assert session.scalar(select(InjuryPoll.n_designations).where(
        InjuryPoll.captured_at == t2
    )) == 1


def test_status_change_writes_a_new_row(session):
    client = FakeClient([_payload(("1", "A", "Out")), _payload(("1", "A", "Day-To-Day"))])
    record_once(session=session, client=client, source=TEST_SOURCE,
                captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC))
    record_once(session=session, client=client, source=TEST_SOURCE,
                captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 20, tzinfo=UTC))
    assert _statuses(session) == [("1", "Out"), ("1", "Day-To-Day")]


def test_dropping_out_of_the_feed_writes_cleared(session):
    """Without this she stays 'Out' forever."""
    client = FakeClient([_payload(("1", "A", "Out")), _payload()])
    record_once(session=session, client=client, source=TEST_SOURCE,
                captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC))
    record_once(session=session, client=client, source=TEST_SOURCE,
                captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 20, tzinfo=UTC))
    assert _statuses(session) == [("1", "Out"), ("1", STATUS_CLEARED)]


def test_cleared_is_not_rewritten_every_poll(session):
    client = FakeClient([_payload(("1", "A", "Out")), _payload(), _payload()])
    for minute in (0, 20, 40):
        record_once(session=session, client=client, source=TEST_SOURCE,
                    captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, minute, tzinfo=UTC))
    assert _statuses(session) == [("1", "Out"), ("1", STATUS_CLEARED)]


def test_reinjury_after_clearing_is_recorded(session):
    client = FakeClient([
        _payload(("1", "A", "Out")), _payload(), _payload(("1", "A", "Out")),
    ])
    for minute in (0, 20, 40):
        record_once(session=session, client=client, source=TEST_SOURCE,
                    captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, minute, tzinfo=UTC))
    assert _statuses(session) == [("1", "Out"), ("1", STATUS_CLEARED), ("1", "Out")]


def test_a_poll_mixing_a_change_and_a_clearing_writes_both(session):
    """The production case, and the one that broke on the first live poll.

    A multi-VALUES insert compiles one statement for the batch, so rows with
    different key sets fail. Every earlier test happened to write one kind of
    row per poll and sailed past it.
    """
    client = FakeClient([
        _payload(("1", "A", "Out"), ("2", "B", "Out")),
        # Player 1 clears; player 2's status changes. Both in one poll.
        _payload(("2", "B", "Day-To-Day")),
    ])
    record_once(session=session, client=client, source=TEST_SOURCE,
                captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC))
    n = record_once(session=session, client=client, source=TEST_SOURCE,
                    captured_at=dt.datetime(FAKE_YEAR, 8, 1, 12, 20, tzinfo=UTC))
    assert n == 2
    assert _statuses(session) == [
        ("1", "Out"), ("2", "Out"), ("1", STATUS_CLEARED), ("2", "Day-To-Day"),
    ]


def test_cleared_rows_carry_the_team_forward(session):
    """Status is read back filtered by team, so a teamless row is invisible.

    Without the team on the `Cleared` row, the earlier `Out` is never
    overridden for that team and the player stays out forever.
    """
    from strategies.wnba_totals.model.availability import absent_from_injury_reports

    client = FakeClient([_payload(("1", "A", "Out")), _payload()])
    t1 = dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC)
    t2 = dt.datetime(FAKE_YEAR, 8, 1, 12, 20, tzinfo=UTC)
    record_once(session=session, client=client, source=TEST_SOURCE, captured_at=t1)
    record_once(session=session, client=client, source=TEST_SOURCE, captured_at=t2)

    cleared = session.scalars(
        select(InjuryReport)
        .where(InjuryReport.source == TEST_SOURCE)
        .where(InjuryReport.status == STATUS_CLEARED)
    ).one()
    assert cleared.team_id == TEAM_ID
    assert cleared.athlete_name == "A"

    after = dt.datetime(FAKE_YEAR, 8, 1, 12, 30, tzinfo=UTC)
    assert absent_from_injury_reports(
        team_id=TEAM_ID, as_of=t1 + dt.timedelta(minutes=5), session=session
    ) == {"1"}
    assert absent_from_injury_reports(
        team_id=TEAM_ID, as_of=after, session=session
    ) == set()


def test_rerunning_the_same_poll_is_idempotent(session):
    """A crashed-and-retried recorder must not duplicate a change."""
    t = dt.datetime(FAKE_YEAR, 8, 1, 12, 0, tzinfo=UTC)
    record_once(session=session, client=FakeClient([_payload(("1", "A", "Out"))]),
                source=TEST_SOURCE, captured_at=t)
    record_once(session=session, client=FakeClient([_payload(("1", "A", "Out"))]),
                source=TEST_SOURCE, captured_at=t)
    assert _statuses(session) == [("1", "Out")]
