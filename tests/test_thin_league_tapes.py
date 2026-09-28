"""The score tape and the Kalshi tape that ride the stream slate in the thin leagues.

The venue's websocket carries prices, not game state, so the speed question
("does the venue reprice late after a basket in a dead league?") needs the
venue's own score on a clock beside its book tape, and Kalshi's touch on the
same game as the anchor. These pin that each tape writes a line per CHANGE,
bounds when the change happened, leaves the rotation when a game ends, and
that the planner opens these leagues three hours before tip.
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.ladder.kalshi_tape import KALSHI_SERIES_BY_LEAGUE, KalshiTape  # noqa: E402
from core.ladder.scores import ScorePoller, state_of  # noqa: E402

SS = importlib.import_module("scripts.schedule_slate")

#: The shape of the venue's events/slug payload, trimmed from
#: lnbp-dia-ast-2026-09-27 as fetched on 2026-09-28.
EVENT = {"event": {"slug": "lnbp-dia-ast-2026-09-27", "live": True, "ended": False, "score": "62-78",
                   "period": "Q4", "elapsed": "03:05",
                   "eventState": {"type": "basketball", "updatedAt": "2026-09-28T00:08:01.123Z", "score": "62-78",
                                  "elapsed": "03:05", "period": "Q4", "live": True, "ended": False,
                                  "periodScores": [{"number": 1, "label": "Q1",
                                                    "scores": [{"competitorId": "1", "score": 15},
                                                               {"competitorId": "2", "score": 22}]}]}}}


class Clock:
    def __init__(self, t=1_790_600_000.0):
        self.t = t

    def __call__(self):
        return self.t


def _client(responses):
    """httpx client whose handler pops the next canned JSON (or raises for an int status)."""
    seq = list(responses)

    def handler(request):
        body = seq.pop(0) if seq else seq_last[0]
        seq_last[0] = body
        if isinstance(body, int):
            return httpx.Response(body, json={})
        return httpx.Response(200, json=body)
    seq_last = [responses[-1]]
    return httpx.Client(transport=httpx.MockTransport(handler))


def _event(score, *, live=True, ended=False, updated="2026-09-28T00:08:01Z"):
    e = json.loads(json.dumps(EVENT))
    st = e["event"]["eventState"]
    st.update(score=score, live=live, ended=ended, updatedAt=updated)
    return e


def _lines(path):
    return [json.loads(x) for x in pathlib.Path(path).read_text().splitlines()] if pathlib.Path(path).exists() else []


def test_state_of_reads_the_event_state_and_its_stamp():
    st = state_of(EVENT)
    assert st["score"] == "62-78" and st["period"] == "Q4" and st["elapsed"] == "03:05"
    assert st["live"] is True and st["ended"] is False
    assert st["state_updated_at"] == "2026-09-28T00:08:01.123Z"
    assert st["period_scores"] == [["Q1", [15, 22]]]


def test_a_line_per_change_bounded_by_the_poll_before(tmp_path):
    clock = Clock()
    p = ScorePoller({"g": "g"}, str(tmp_path), client=_client([_event("10-8"), _event("10-8"), _event("12-8")]),
                    clock=clock)
    assert p.poll("g") is True               # first sight is a change
    clock.t += 4
    assert p.poll("g") is False              # same state: nothing written
    clock.t += 4
    assert p.poll("g") is True
    rows = _lines(tmp_path / "slate_scores_g.jsonl")
    assert [r["score"] for r in rows] == ["10-8", "12-8"]
    assert rows[0]["prev_recv"] is None
    # the basket happened after the second poll (which still saw 10-8) and by the third
    assert rows[1]["prev_recv"] < rows[1]["recv"] and rows[1]["polls"] == 3


def test_an_ended_game_leaves_the_rotation_and_pregame_is_polled_slowly(tmp_path):
    clock = Clock()
    p = ScorePoller({"a": "a", "b": "b"}, str(tmp_path), interval_s=4, pregame_interval_s=30, clock=clock,
                    client=_client([_event("", live=False), _event("80-70", live=False, ended=True)]))
    assert p.due() == "a"
    p.poll("a")                              # pregame
    assert p.due() == "b"
    p.poll("b")                              # ended
    clock.t += 5
    assert p.due() is None, "a is pregame (30 s), b has ended"
    clock.t += 30
    assert p.due() == "a"


def test_a_venue_error_is_counted_and_writes_nothing(tmp_path):
    p = ScorePoller({"g": "g"}, str(tmp_path), client=_client([503]), clock=Clock())
    assert p.poll("g") is False and p.errors == 1
    assert not (tmp_path / "slate_scores_g.jsonl").exists()


def _mkt(ticker, bid, ask, vol="10.00"):
    return {"ticker": ticker, "event_ticker": ticker.rsplit("-", 1)[0], "yes_sub_title": ticker[-3:],
            "yes_bid_dollars": bid, "yes_ask_dollars": ask, "yes_bid_size_fp": "100.00", "yes_ask_size_fp": "50.00",
            "last_price_dollars": bid, "volume_fp": vol, "open_interest_fp": "5.00", "status": "active",
            "result": "", "updated_time": "2026-09-28T01:00:00Z"}


def test_the_kalshi_tape_writes_changed_touches_only(tmp_path):
    clock = Clock()
    a1 = {"markets": [_mkt("KXLNBPGAME-X-MIN", "0.5500", "0.5600"), _mkt("KXLNBPGAME-X-LOB", "0.4400", "0.4500")]}
    a2 = {"markets": [_mkt("KXLNBPGAME-X-MIN", "0.5500", "0.5600"), _mkt("KXLNBPGAME-X-LOB", "0.4300", "0.4500")]}
    t = KalshiTape("lnbp", str(tmp_path), client=_client([a1, a2]), clock=clock)
    assert t.poll_once() == 2
    clock.t += 10
    assert t.poll_once() == 1
    rows = _lines(tmp_path / "kalshi_lnbp.jsonl")
    assert [(r["ticker"][-3:], r["yes_bid"]) for r in rows] == [("MIN", "0.5500"), ("LOB", "0.4400"), ("LOB", "0.4300")]
    assert rows[2]["prev_recv"] is not None and rows[2]["team"] == "LOB"


def test_every_kalshi_series_is_a_basketball_game_series_and_denbl_hunbl_have_none():
    assert "denbl" not in KALSHI_SERIES_BY_LEAGUE and "hunbl" not in KALSHI_SERIES_BY_LEAGUE
    for lg, series in KALSHI_SERIES_BY_LEAGUE.items():
        assert all(s.startswith("KX") and s.endswith("GAME") for s in series), lg


def test_thin_basketball_opens_three_hours_before_tip_and_others_ten_minutes():
    now = dt.datetime(2026, 9, 28, 12, 10, tzinfo=dt.timezone.utc)
    tip = dt.datetime(2026, 9, 29, 18, 0, tzinfo=dt.timezone.utc)
    games = [{"game": "eurolg-aaa-bbb-2026-09-29", "league": "eurolg", "tip": tip, "rungs": 1},
             {"game": "nfl-ccc-ddd-2026-09-29", "league": "nfl", "tip": tip, "rungs": 42}]
    p = SS.plan(games, now)
    rec = {l.args.split()[0]: l for l in p.launches if l.script == "launch_stream_slate.sh"}
    assert rec["eurolg"].at == tip - dt.timedelta(minutes=180)
    assert int(rec["eurolg"].args.split()[1]) == 180 + 150
    assert rec["nfl"].at == tip - dt.timedelta(minutes=SS.RECORDER_LEAD_MIN)
