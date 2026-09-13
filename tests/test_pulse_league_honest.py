"""PULSE exists only for WNBA, and the dashboard must say so — not show a zero.

The operator's report: "the Pulse on the UI doesn't work for CFB, nor do the
numbers change from 1335". Both were the same defect from two sides.
`/api/pulse` took no league, counted `pulse_decisions` — a table the WNBA
engine stopped writing on 2026-08-31 when the regular season ended — and the
MODEL page rendered that count under whichever tab was selected, with its
first decision but never its last. So a WNBA count that legitimately stood
still appeared, unlabelled, under a CFB tab, and read as a broken CFB PULSE.

Now: a non-WNBA league gets one line and no numbers; WNBA gets the registered
view's counts beside the last decision's timestamp, for the same estimates
version as the counts. No database: `pytest --noconftest` this file.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from core import api
from core.api import PULSE_LEAGUE, app
from core.pulse import live_report
from core.pulse.live_report import LiveReport

UTC = dt.timezone.utc
STATIC = Path(__file__).resolve().parent.parent / "static"


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _fn(html: str, signature: str) -> str:
    """The body of one JS function, by brace matching (see test_landing_page)."""
    i = html.index(signature)
    depth, j = 0, html.index("{", i)
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise AssertionError(f"unbalanced braces after {signature!r}")


# ------------------------------------------------------------------ #
# /api/pulse
# ------------------------------------------------------------------ #


def test_pulse_is_registered_on_wnba_alone():
    assert PULSE_LEAGUE == "wnba"


@pytest.mark.parametrize("league", ["cfb", "nfl", "nba", "mlb"])
def test_a_non_wnba_league_gets_one_line_and_no_numbers(client, league):
    d = client.get(f"/api/pulse?league={league}").json()
    assert d["available"] is False
    assert d["league"] == league and d["pulse_league"] == "wnba"
    assert "WNBA" in d["note"] and "playoffs" in d["note"]
    assert "\n" not in d["note"], "one line"
    for k in ("n_decisions", "n_entries", "n_entry_fills", "n_games", "n_round_trips",
              "trip_roi", "ride_roi", "verdict", "floors", "first_decision", "last_decision"):
        assert k not in d, f"{k}: a zero here reads as 'PULSE ran on {league} and found this'"


def test_an_unknown_league_is_a_400_not_a_default(client):
    assert client.get("/api/pulse?league=xfl").status_code == 400


class _Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _FakeSession:
    """Stands in for `_Session` on the WNBA path: records the bounds query's
    parameters and answers it. `build_report` is patched separately."""
    calls: ClassVar[list] = []
    bounds: ClassVar[tuple] = (dt.datetime(2026, 5, 16, 23, 5, tzinfo=UTC),
                               dt.datetime(2026, 8, 31, 2, 41, tzinfo=UTC))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt, params=None):
        _FakeSession.calls.append((str(stmt), params))
        return _Result(_FakeSession.bounds)


def _report(version: str, n_decisions: int) -> LiveReport:
    return LiveReport(version=version, n_decisions=n_decisions, n_entries=40,
                      n_entry_fills=21, n_round_trips=6, n_rides_settled=9, n_games=7,
                      trip_staked=12.0, trip_pnl=-0.8, ride_staked=15.0, ride_returned=14.1,
                      trip_roi_clustered=None, ride_roi_clustered=None)


def test_wnba_counts_carry_the_last_decision_of_the_same_version(client, monkeypatch):
    monkeypatch.setattr(api, "_Session", _FakeSession)
    monkeypatch.setattr(live_report, "build_report",
                        lambda s, **kw: {"v1": _report("v1", 900), "v2": _report("v2", 1335)})
    _FakeSession.calls.clear()
    d = client.get("/api/pulse?league=wnba").json()
    assert d["available"] is True and d["league"] == "wnba"
    assert d["estimates_version"] == "v2", "the newest estimates version, as before"
    assert d["n_decisions"] == 1335
    assert d["last_decision"] == "2026-08-31T02:41:00+00:00"
    assert d["first_decision"] == "2026-05-16T23:05:00+00:00"
    assert d["at_floor"] is False and d["verdict"] == "NO DATA"
    # The timestamps must describe the population that was counted. The old
    # query took min/max over the whole table while the count was per version.
    (stmt, params), = _FakeSession.calls
    assert "estimates_version = :v" in stmt and params == {"v": "v2"}


def test_no_league_means_the_default_league_not_a_table_wide_count(client, monkeypatch):
    monkeypatch.setattr(api, "_Session", _FakeSession)
    monkeypatch.setattr(live_report, "build_report", lambda s, **kw: {})
    d = client.get("/api/pulse").json()
    assert d["available"] is False and d["league"] == "wnba"
    assert d["note"] == "no PULSE decisions recorded yet"


# ------------------------------------------------------------------ #
# /api/pulse/latest names its league so the board can say so
# ------------------------------------------------------------------ #


class _EmptyResult:
    def all(self):
        return []


class _EmptySession(_FakeSession):
    def execute(self, stmt, params=None):
        return _EmptyResult()


def test_the_board_feed_names_the_league_pulse_runs_on(client, monkeypatch):
    monkeypatch.setattr(api, "_Session", _EmptySession)
    d = client.get("/api/pulse/latest?league=cfb").json()
    assert d["league"] == "cfb" and d["pulse_league"] == "wnba"
    assert d["markets"] == {} and d["positions"] == {} and d["feed"] == []


# ------------------------------------------------------------------ #
# The pages
# ------------------------------------------------------------------ #


def test_model_page_asks_for_the_selected_league_and_shows_the_last_decision():
    html = (STATIC / "analytics.html").read_text()
    fn = _fn(html, "async function loadPulse(")
    assert "/api/pulse?league=" in fn, "the count must be for the tab you are on"
    assert "pulse_league" in fn and "d.note" in fn, "a non-WNBA tab renders the server's one line"
    assert "last_decision" in fn, "the count beside the date it stopped moving"
    # a league switch re-renders PULSE, not just ANCHOR
    paint = _fn(html, "const paint = () =>")
    assert "loadPulse()" in paint


def test_board_page_shows_one_line_and_no_pulse_numbers_off_wnba():
    html = (STATIC / "index.html").read_text()
    fn = _fn(html, "async function loadPulseLatest(")
    assert "d.pulse_league !== league" in fn
    assert "renderPulseAbsent(" in fn
    absent = _fn(html, "function renderPulseAbsent(")
    assert "playoffs" in absent and "exists only for" in absent
