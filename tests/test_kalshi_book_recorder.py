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


def test_recording_books_write_snapshots_and_prints_raw_and_the_best_level_coalesced_on_drain(tmp_path):
    tape = Tape(str(tmp_path))
    b = RecordingBooks(tape)
    snap = {"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "10.00"], ["0.39", "4.00"]], "no_dollars_fp": [["0.59", "5.00"]]}}
    deep = {"type": "orderbook_delta", "sid": 1, "seq": 2, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.01", "delta_fp": "1000.00"}}   # deep: best level unchanged
    improve = {"type": "orderbook_delta", "sid": 1, "seq": 3, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "3.00"}}
    more = {"type": "orderbook_delta", "sid": 1, "seq": 4, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "2.00"}}      # size at the best changes again
    trade = {"type": "trade", "sid": 2, "seq": 1, "msg": {"market_ticker": "M1", "yes_price_dollars": "0.41", "count_fp": "2.00", "taker_side": "yes"}}
    gapped = {"type": "orderbook_delta", "sid": 1, "seq": 6, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.41", "delta_fp": "1.00"}}
    assert b.handle(snap, 1.0) is None
    assert b.drain() == 1                                                                 # the snapshot's touch
    assert b.handle(deep, 1.2) is None and b.handle(improve, 1.5) is None and b.handle(more, 1.6) is None and b.handle(trade, 1.7) is None
    assert b.drain() == 1 and b.drain() == 0                                              # two changes, one coalesced line, then nothing
    assert b.handle(gapped, 2.0) == "gap" and b.drain() == 0                              # a gapped delta is neither applied nor written as a touch
    assert b.handle({"type": "subscribed", "sid": 1, "msg": {"channel": "orderbook_delta"}}, 2.1) is None
    tape.flush()
    books = [json.loads(l) for l in open(tmp_path / "books_M1.jsonl")]
    trades = [json.loads(l) for l in open(tmp_path / "trades_M1.jsonl")]
    assert [r["type"] for r in books] == ["orderbook_snapshot", "touch", "touch"]
    assert books[0]["msg"]["yes_dollars_fp"] == [["0.40", "10.00"], ["0.39", "4.00"]] and books[0]["recv"].endswith("Z")
    assert books[1] == {"recv": books[1]["recv"], "type": "touch", "yes_bid": 0.40, "yes_bid_size": 10.0, "no_bid": 0.59, "no_bid_size": 5.0, "changes": 1}
    assert books[2]["yes_bid"] == 0.41 and books[2]["yes_bid_size"] == 5.0 and books[2]["changes"] == 2 and books[2]["recv"].startswith("1970-01-01T00:00:01.600")
    assert len(trades) == 1 and trades[0]["msg"]["taker_side"] == "yes" and b.trades == 1
    assert b.touch_lines == 2 and b.touch_changes == 3 and len(b.gaps) == 1 and b.side("M1", "yes")[0] == (0.41, 5.0)
    assert tape.per_channel == {"book": 3, "trade": 1, "other": 0}
    assert not os.path.exists(tmp_path / "trades__unrouted.jsonl")


def test_raw_mode_also_keeps_every_delta(tmp_path):
    tape = Tape(str(tmp_path))
    b = RecordingBooks(tape, raw=True)
    b.handle({"type": "orderbook_snapshot", "sid": 1, "seq": 1, "msg": {"market_ticker": "M1", "yes_dollars_fp": [["0.40", "10.00"]], "no_dollars_fp": [["0.59", "5.00"]]}}, 1.0)
    b.handle({"type": "orderbook_delta", "sid": 1, "seq": 2, "msg": {"market_ticker": "M1", "side": "yes", "price_dollars": "0.01", "delta_fp": "1000.00"}}, 1.2)
    b.drain(); tape.flush()
    assert [json.loads(l)["type"] for l in open(tmp_path / "books_M1.jsonl")] == ["orderbook_snapshot", "orderbook_delta", "touch"]


def test_subscribe_carries_both_channels_in_each_batch():
    msgs = subscribe_msgs([f"T{i}" for i in range(150)], ("orderbook_delta", "trade"))
    assert len(msgs) == 2 and all(m["params"]["channels"] == ["orderbook_delta", "trade"] for m in msgs)
    assert subscribe_msgs(["T1"])[0]["params"]["channels"] == ["orderbook_delta"]
