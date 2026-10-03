"""The Kalshi in-play recorder: date-tag discovery, raw lines per channel, the gap check kept."""
from __future__ import annotations

import json
import os

from core.kalshi.book_recorder import RecordingBooks, Tape, discover
from core.kalshi.lip_scorer import subscribe_msgs


class _Resp:
    def __init__(self, d): self._d = d
    def raise_for_status(self): pass
    def json(self): return self._d


class _Http:
    def __init__(self, pages): self.pages = pages; self.calls = []
    def get(self, url, params=None):
        self.calls.append(params)
        return _Resp(self.pages[params["series_ticker"]].pop(0))


def test_discover_matches_the_date_tag_at_the_ticker_position_only_and_pages():
    pages = {"KXNFLGAME": [
        {"markets": [{"ticker": "KXNFLGAME-26OCT04DETCAR-DET", "event_ticker": "KXNFLGAME-26OCT04DETCAR", "title": "Detroit wins"},
                     {"ticker": "KXNFLGAME-26OCT11DETCAR-DET"},
                     {"ticker": "KXNFLGAME-26OCT05ATLNO-NO"}], "cursor": "c1"},
        {"markets": [{"ticker": "KXNFLGAME-26OCT04DENSF-SF"}], "cursor": None}]}
    out = discover(["KXNFLGAME"], ["26OCT04", "26OCT05"], http=_Http(pages))
    assert [m["ticker"] for m in out] == ["KXNFLGAME-26OCT04DETCAR-DET", "KXNFLGAME-26OCT05ATLNO-NO", "KXNFLGAME-26OCT04DENSF-SF"]
    assert out[0]["date_tag"] == "26OCT04" and out[0]["teams"] == "DETCAR" and out[0]["title"] == "Detroit wins"


def test_recording_books_write_every_message_raw_per_channel_and_still_flag_a_gap(tmp_path):
    tape = Tape(str(tmp_path))
    b = RecordingBooks(tape)
    snap = {"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "10.00"]], "no_dollars_fp": [["0.59", "5.00"]]}}
    delta = {"type": "orderbook_delta", "sid": 1, "seq": 2, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "3.00"}}
    trade = {"type": "trade", "sid": 2, "seq": 1, "msg": {"market_ticker": "M1", "yes_price_dollars": "0.41", "count_fp": "2.00", "taker_side": "yes"}}
    gapped = {"type": "orderbook_delta", "sid": 1, "seq": 4, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "1.00"}}
    assert b.handle(snap, 1.0) is None and b.handle(delta, 1.5) is None and b.handle(trade, 1.6) is None
    assert b.handle(gapped, 2.0) == "gap"
    assert b.handle({"type": "subscribed", "sid": 1, "msg": {"channel": "orderbook_delta"}}, 2.1) is None
    tape.flush()
    books = [json.loads(l) for l in open(tmp_path / "books_M1.jsonl")]
    trades = [json.loads(l) for l in open(tmp_path / "trades_M1.jsonl")]
    assert [r["type"] for r in books] == ["orderbook_snapshot", "orderbook_delta", "orderbook_delta"]   # the gapped delta is on tape too
    assert books[0]["recv"].endswith("Z") and books[0]["msg"]["yes_dollars_fp"] == [["0.40", "10.00"]]
    assert len(trades) == 1 and trades[0]["msg"]["taker_side"] == "yes" and b.trades == 1
    assert b.side("M1", "yes") == [(0.41, 3.0), (0.40, 10.0)] and len(b.gaps) == 1
    assert tape.lines == 4 and tape.per_channel == {"book": 3, "trade": 1, "other": 0}
    assert not os.path.exists(tmp_path / "trades__unrouted.jsonl")


def test_subscribe_carries_both_channels_in_each_batch():
    msgs = subscribe_msgs([f"T{i}" for i in range(150)], ("orderbook_delta", "trade"))
    assert len(msgs) == 2 and all(m["params"]["channels"] == ["orderbook_delta", "trade"] for m in msgs)
    assert subscribe_msgs(["T1"])[0]["params"]["channels"] == ["orderbook_delta"]
