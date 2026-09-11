"""The pregame line path: --days-ahead polls each day once per group, merges
the boards, and keeps change detection per (game, provider) across days."""
from __future__ import annotations

import datetime as dt

from core.feeds.live_odds_recorder import LiveOddsRecorder

UTC = dt.timezone.utc


def _odds(spread=-3.5, provider="DraftKings"):
    return {"provider": {"name": provider}, "spread": spread, "overUnder": 44.5,
            "homeTeamOdds": {"moneyLine": -170}, "awayTeamOdds": {"moneyLine": 142}}


def _event(game_id, start, odds):
    return {"id": game_id, "date": start,
            "competitions": [{"id": game_id, "status": {"type": {"state": "pre"}}, "odds": odds}]}


class _Client:
    """Serves a board per (date, group); records every call."""
    def __init__(self, boards):
        self.boards, self.calls = boards, []

    def get_scoreboard(self, date_yyyymmdd, *, groups=None, limit=None):
        self.calls.append((date_yyyymmdd, groups, limit))
        return self.boards.get((date_yyyymmdd, groups), {"events": []})


def _recorder(client, **kw):
    rec = LiveOddsRecorder(client=client, sessionmaker=lambda: None, **kw)
    rec.persisted = []
    rec._persist = lambda rows: (rec.persisted.extend(rows), len(rows))[1]
    return rec


def test_days_ahead_polls_every_day_and_group_once_and_merges():
    now = dt.datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
    boards = {
        ("20260911", 80): {"events": [_event("1", "2026-09-12T00:00:00Z", [_odds(-3.5)])]},
        ("20260912", 80): {"events": [_event("2", "2026-09-12T19:30:00Z", [_odds(-7.5)])]},
        ("20260912", 81): {"events": [_event("3", "2026-09-12T22:00:00Z", [_odds(+14.5)]),
                                      _event("2", "2026-09-12T19:30:00Z", [_odds(-7.5)])]},  # same game on both groups
    }
    client = _Client(boards)
    rec = _recorder(client, days_ahead=1, groups=(80, 81))
    stats = rec.poll_once(captured_at=now)
    # 2 days x 2 groups = 4 calls, each with the page cap lifted
    assert sorted(client.calls) == [("20260911", 80, 400), ("20260911", 81, 400),
                                    ("20260912", 80, 400), ("20260912", 81, 400)]
    # three distinct games, game 2 not double counted across groups
    assert stats.games_seen == 3 and stats.with_odds == 3
    assert sorted(r["espn_game_id"] for r in rec.persisted) == ["1", "2", "3"]


def test_change_detection_survives_the_wider_window():
    now = dt.datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
    boards = {("20260911", None): {"events": [_event("1", "2026-09-12T00:00:00Z", [_odds(-3.5)])]},
              ("20260912", None): {"events": []}}
    client = _Client(boards)
    rec = _recorder(client, days_ahead=1)
    rec.poll_once(captured_at=now)
    rec.poll_once(captured_at=now + dt.timedelta(minutes=5))       # unchanged -> no row
    assert len(rec.persisted) == 1
    boards[("20260911", None)]["events"][0]["competitions"][0]["odds"] = [_odds(-4.5)]
    rec.poll_once(captured_at=now + dt.timedelta(minutes=10))      # line moved -> one row
    assert len(rec.persisted) == 2 and rec.persisted[-1]["spread"] == -4.5


def test_one_bad_day_does_not_blind_the_rest():
    now = dt.datetime(2026, 9, 11, 18, 0, tzinfo=UTC)

    class _Flaky(_Client):
        def get_scoreboard(self, date_yyyymmdd, *, groups=None, limit=None):
            if date_yyyymmdd == "20260912":
                raise RuntimeError("503")
            return super().get_scoreboard(date_yyyymmdd, groups=groups, limit=limit)

    client = _Flaky({("20260911", None): {"events": [_event("1", "2026-09-12T00:00:00Z", [_odds()])]},
                     ("20260913", None): {"events": [_event("9", "2026-09-13T17:00:00Z", [_odds()])]}})
    rec = _recorder(client, days_ahead=2)
    stats = rec.poll_once(captured_at=now)
    assert stats.errors == 0 and stats.games_seen == 2


def test_days_ahead_zero_is_the_old_behaviour():
    now = dt.datetime(2026, 9, 11, 18, 0, tzinfo=UTC)
    client = _Client({("20260911", None): {"events": []}})
    rec = _recorder(client)
    rec.poll_once(captured_at=now)
    assert client.calls == [("20260911", None, 400)]
