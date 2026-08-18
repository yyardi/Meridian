"""ESPN publishes the season type in two places. Both must parse.

The outage this pins (2026-07-31 → 2026-08-18, ~51 games)
---------------------------------------------------------
`Event.season_type_id` read only `event["seasonType"]`. The **scoreboard**
endpoint — the one the daily incremental update calls — carries no such key. It
nests the same number as ``season: {"year": 2026, "type": 2, ...}``. So the
property returned None for every game, and `_rows_for_event` dropped every
event, because an unknown season type is a legitimate reason to refuse a row:
writing a preseason game into the regular-season record would corrupt every
feature built from it.

Nothing failed. `fetch_date` completed, wrote 0 rows, raised nothing, and the
scheduler wraps it in `_safe` and reports `rows_written: NULL` by design. Every
heartbeat stayed green while the pregame model predicted every 20 minutes on
team form frozen at 2026-07-31.

The lesson is the one the project keeps relearning in new costumes: **a guard
that returns "nothing to do" is indistinguishable from a guard that is broken,
unless something asserts on the output.** So these tests assert rows come back,
not that parsing did not raise.
"""

from __future__ import annotations

import pytest

from core.config import SEASON_TYPE_PRESEASON, SEASON_TYPE_REGULAR
from core.feeds.espn_schemas import Event
from core.feeds.espn_stats import ESPNStatsFetcher

#: The scoreboard shape, copied from the live payload for 2026-08-10. Note the
#: absence of `seasonType` — that absence IS the regression.
SCOREBOARD_EVENT = {
    "id": "401857132",
    "date": "2026-08-10T23:00Z",
    "season": {"year": 2026, "type": 2, "slug": "regular-season"},
    "competitions": [{
        "id": "401857132",
        "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
        "competitors": [
            {"homeAway": "home", "score": "107",
             "team": {"id": "20", "abbreviation": "ATL"}},
            {"homeAway": "away", "score": "95",
             "team": {"id": "3", "abbreviation": "DAL"}},
        ],
    }],
}

#: The schedule shape, which still uses the older spelling.
SCHEDULE_EVENT = {
    "id": "401857999",
    "date": "2026-08-10T23:00Z",
    "seasonType": {"id": "2", "name": "Regular Season"},
    "competitions": [{
        "id": "401857999",
        "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
        "competitors": [
            {"homeAway": "home", "score": "88",
             "team": {"id": "5", "abbreviation": "NY"}},
            {"homeAway": "away", "score": "80",
             "team": {"id": "9", "abbreviation": "PHX"}},
        ],
    }],
}


def test_scoreboard_shape_yields_a_season_type():
    """`season.type`, with no top-level `seasonType`. The failing case."""
    assert "seasonType" not in SCOREBOARD_EVENT, "fixture must reproduce the absence"
    assert Event.model_validate(SCOREBOARD_EVENT).season_type_id == SEASON_TYPE_REGULAR


def test_schedule_shape_still_yields_a_season_type():
    assert Event.model_validate(SCHEDULE_EVENT).season_type_id == SEASON_TYPE_REGULAR


@pytest.mark.parametrize("payload,label", [(SCOREBOARD_EVENT, "scoreboard"),
                                           (SCHEDULE_EVENT, "schedule")])
def test_a_completed_game_produces_two_rows(payload, label):
    """The assertion that would have caught the outage on day one: **rows**,
    not "did not raise". Two rows per game, one per team's perspective."""
    rows = ESPNStatsFetcher._rows_for_event(Event.model_validate(payload), 2026)
    assert len(rows) == 2, f"{label} shape produced no rows — the outage's signature"
    home = next(r for r in rows if r["is_home"])
    away = next(r for r in rows if not r["is_home"])
    assert home["points_scored"] == away["points_allowed"]
    assert away["points_scored"] == home["points_allowed"]
    assert home["season_type"] == SEASON_TYPE_REGULAR
    assert home["is_completed"] is True


def test_preseason_is_still_dropped():
    """The guard's real purpose must survive the fix. A preseason game in the
    regular-season record would corrupt every feature derived from it, so this
    is the one case where returning no rows is correct."""
    preseason = {**SCOREBOARD_EVENT,
                 "season": {"year": 2026, "type": SEASON_TYPE_PRESEASON}}
    assert Event.model_validate(preseason).season_type_id == SEASON_TYPE_PRESEASON
    assert ESPNStatsFetcher._rows_for_event(
        Event.model_validate(preseason), 2026) == []


def test_an_unknown_season_type_is_still_refused():
    """Neither spelling present -> None -> no rows. Still the right answer; the
    bug was that the payload HAD the value and we looked in one place."""
    unknown = {k: v for k, v in SCOREBOARD_EVENT.items() if k != "season"}
    assert Event.model_validate(unknown).season_type_id is None
    assert ESPNStatsFetcher._rows_for_event(Event.model_validate(unknown), 2026) == []
