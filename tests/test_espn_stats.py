"""ESPN stats fetcher: the parsing rules that silently corrupt data if wrong."""

from __future__ import annotations

import datetime as dt

from core.feeds.espn_schemas import Event, ScheduleResponse
from core.feeds.espn_stats import ESPNStatsFetcher


def _event(season_type: str, completed: bool = True, home_score=66, away_score=77) -> dict:
    return {
        "id": "401856953",
        "date": "2026-04-25T23:30Z",
        "seasonType": {"id": season_type, "name": "x"},
        "competitions": [
            {
                "status": {"type": {"completed": completed}},
                "competitors": [
                    {
                        "team": {"id": "16", "abbreviation": "WSH"},
                        "homeAway": "home",
                        "score": home_score,
                    },
                    {
                        "team": {"id": 8, "abbreviation": "MIN"},  # int id on purpose
                        "homeAway": "away",
                        "score": away_score,
                    },
                ],
            }
        ],
    }


def _rows(payload: dict, season: int = 2026):
    return ESPNStatsFetcher._rows_for_event(Event.model_validate(payload), season)


def test_preseason_is_never_written():
    """Exhibition rotations would corrupt both PPG and win-loss record."""
    assert _rows(_event("1")) == []


def test_regular_and_postseason_are_written():
    assert len(_rows(_event("2"))) == 2
    assert len(_rows(_event("3"))) == 2


def test_season_type_is_coerced_to_int():
    """ESPN sends "2" as a string; the column and all comparisons are int."""
    ev = Event.model_validate(_event("2"))
    assert ev.season_type_id == 2
    assert isinstance(ev.season_type_id, int)


def test_two_mirrored_rows_per_game():
    rows = _rows(_event("2", home_score=66, away_score=77))
    assert len(rows) == 2
    home = next(r for r in rows if r["is_home"])
    away = next(r for r in rows if not r["is_home"])

    assert (home["points_scored"], home["points_allowed"]) == (66, 77)
    assert (away["points_scored"], away["points_allowed"]) == (77, 66)
    # Perspectives must mirror exactly.
    assert home["points_scored"] == away["points_allowed"]
    assert home["team_id"] == away["opponent_id"]


def test_incomplete_games_are_skipped():
    """In-progress games get captured on a later run, not written half-formed."""
    assert _rows(_event("2", completed=False)) == []


def test_score_accepts_dict_or_bare_value():
    """ESPN returns {"value": 66.0} on some endpoints and 66 on others."""
    dict_form = _event("2")
    dict_form["competitions"][0]["competitors"][0]["score"] = {"value": 66.0}
    bare_form = _event("2")
    bare_form["competitions"][0]["competitors"][0]["score"] = 66

    a = next(r for r in _rows(dict_form) if r["is_home"])
    b = next(r for r in _rows(bare_form) if r["is_home"])
    assert a["points_scored"] == b["points_scored"] == 66


def test_missing_score_is_skipped_not_zeroed():
    """A null score must not become 0 — that would be a fabricated blowout."""
    payload = _event("2")
    payload["competitions"][0]["competitors"][0]["score"] = None
    assert _rows(payload) == []


def test_int_team_id_is_stringified():
    rows = _rows(_event("2"))
    assert all(isinstance(r["team_id"], str) for r in rows)


def test_missing_season_type_is_skipped():
    """Unknown season type is unsafe: it might be preseason."""
    payload = _event("2")
    del payload["seasonType"]
    assert _rows(payload) == []


def test_malformed_competitor_count_is_skipped():
    payload = _event("2")
    payload["competitions"][0]["competitors"] = payload["competitions"][0]["competitors"][:1]
    assert _rows(payload) == []


def test_schedule_response_parses_mixed_season_types():
    payload = {"events": [_event("1"), _event("2"), _event("3")]}
    parsed = ScheduleResponse.model_validate(payload)
    assert [e.season_type_id for e in parsed.events] == [1, 2, 3]


def test_game_date_is_timezone_aware():
    rows = _rows(_event("2"))
    assert rows[0]["game_date"].tzinfo is not None
    assert rows[0]["game_date"] == dt.datetime(2026, 4, 25, 23, 30, tzinfo=dt.timezone.utc)
