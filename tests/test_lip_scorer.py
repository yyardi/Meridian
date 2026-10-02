"""The Kalshi liquidity-incentive paper scorer: the published rule on a worked example, books from
snapshot + deltas with sequence gaps, the per-second scoring and its hourly aggregates, and the
socket's subscribe / resubscribe behaviour -- all without a key or a venue."""
from __future__ import annotations

import json
import queue
import sqlite3
import threading

from core.kalshi.lip_scorer import (Books, BookSocket, Scorer, choose_programs, idle_status, our_share, reference_and_score, subscribe_msgs, write_status, wait_for_programs)
from core.polymarket.ws_min import ConnectionClosed


def test_the_reference_is_the_first_level_reaching_a_fifth_of_target_and_worse_levels_are_discounted():
    # target 1000 -> threshold 200; best bid 0.40 has 150, next 0.39 has 100 -> reference 0.39
    levels = [(0.40, 150.0), (0.39, 100.0), (0.37, 1000.0), (0.30, 5000.0)]
    ref, score, depth = reference_and_score(levels, target=1000, discount=0.5)
    assert ref == 0.39 and depth == 6250.0
    # 0.40 and 0.39 full credit (250); 0.37 is 2 ticks worse -> x0.25 (250); 0.30 is 9 ticks -> x0.5^9 (~9.8)
    assert abs(score - (250 + 250 + 5000 * 0.5 ** 9)) < 1e-6
    assert reference_and_score([], 1000, 0.5) == (None, 0.0, 0.0)
    ref2, score2, _ = reference_and_score([(0.40, 50.0)], 1000, 0.5)       # never reaches a fifth: the last level
    assert ref2 == 0.40 and score2 == 50.0
    assert abs(our_share(200, 800) - 0.2) < 1e-9 and our_share(0, 800) == 0.0


def _snap(tk, yes, no, sid=1, seq=1):
    return {"type": "orderbook_snapshot", "sid": sid, "seq": seq,
            "msg": {"market_ticker": tk, "yes_dollars_fp": [[str(p), f"{q:.2f}"] for p, q in yes], "no_dollars_fp": [[str(p), f"{q:.2f}"] for p, q in no]}}


def _delta(tk, side, price, delta, sid=1, seq=2):
    return {"type": "orderbook_delta", "sid": sid, "seq": seq, "msg": {"market_ticker": tk, "side": side, "price_dollars": str(price), "delta_fp": f"{delta:.2f}"}}


def test_books_apply_snapshot_then_deltas_remove_empty_levels_and_flag_a_sequence_gap():
    b = Books()
    assert b.handle(_snap("M1", [(0.40, 150.0), (0.39, 100.0)], [(0.59, 300.0)]), now=1.0) is None
    assert b.side("M1", "yes") == [(0.40, 150.0), (0.39, 100.0)] and b.side("M1", "no") == [(0.59, 300.0)]
    assert b.handle(_delta("M1", "yes", 0.40, -150.0, seq=2), now=2.0) is None          # the level empties and leaves
    assert b.side("M1", "yes") == [(0.39, 100.0)]
    assert b.handle(_delta("M1", "no", 0.60, 50.0, seq=3), now=3.0) is None             # a new best no bid
    assert b.side("M1", "no") == [(0.60, 50.0), (0.59, 300.0)]
    assert b.handle(_delta("M1", "no", 0.60, 1.0, seq=5), now=4.0) == "gap"              # 4 skipped
    assert b.gaps == [(4.0, 1, 4, 5)] and b.snapshots == 1 and b.deltas == 2         # the gapped delta is not applied
    assert b.handle({"type": "subscribed", "msg": {}}, now=5.0) is None


def test_the_scorer_accumulates_valid_seconds_and_shares_and_flushes_hourly_rows(tmp_path):
    progs = {"M1": {"series": "S", "per_day_usd": 1000.0, "target": 1000.0, "discount": 0.5, "start_ts": 0.0, "end_ts": 9e9}}
    books = Books()
    clock = [3600.0 * 1000 + 5]
    sc = Scorer(str(tmp_path / "lip.sqlite"), progs, [200.0, 500.0], books, clock=lambda: clock[0])
    assert sc.tick(clock[0]) == 0 and sc.acc["M1"]["seconds"] == 1 and sc.acc["M1"]["valid"] == 0    # no book: a second, not valid
    books.handle(_snap("M1", [(0.40, 800.0), (0.39, 400.0)], [(0.59, 800.0), (0.58, 400.0)]), clock[0])
    clock[0] += 1
    assert sc.tick(clock[0]) == 1
    a = sc.acc["M1"]
    assert a["seconds"] == 2 and a["valid"] == 1
    # each side: reference = best (800 >= 200), incumbent score 800 + 400*0.5 = 1000 -> share 200/1200 and 500/1500
    assert abs(a["sum"]["200"] - 200 / 1200) < 1e-9 and abs(a["sum"]["500"] - 500 / 1500) < 1e-9
    imp = sc.implied_per_day()
    assert abs(imp["total"]["200"] - (200 / 1200 / 2) * 1000.0) < 1e-6                 # one valid second of two
    clock[0] += 3600                                                                   # the next hour flushes the row
    sc.tick(clock[0])
    rows = sqlite3.connect(sc.db_path).execute("SELECT hour_ts, ticker, seconds, valid, sum_share, inc_yes_med FROM lip_hourly").fetchall()
    assert len(rows) == 1 and rows[0][2] == 2 and rows[0][3] == 1 and json.loads(rows[0][4])["200"] > 0 and rows[0][5] == 1000.0
    s = sqlite3.connect(sc.db_path).execute("SELECT COUNT(*), MIN(valid) FROM lip_sample").fetchone()
    assert s[0] >= 1
    # the depth test: a book thinner than target on one side is a second that does not count
    books.handle(_snap("M1", [(0.40, 100.0)], [(0.59, 5000.0)], seq=1), clock[0])
    before = sc.acc["M1"]["valid"]
    sc.tick(clock[0] + 1)
    assert sc.acc["M1"]["valid"] == before


class FakeWS:
    def __init__(self, msgs):
        self.q = queue.Queue()
        for m in msgs:
            self.q.put(m)
        self.closed = threading.Event(); self.sent = []

    def send_json(self, obj):
        self.sent.append(obj)

    def recv_json(self):
        while not self.closed.is_set():
            try:
                return self.q.get(timeout=0.02)
            except queue.Empty:
                continue
        raise ConnectionClosed("closed")

    def close(self):
        self.closed.set()


def test_subscribe_batches_and_a_gap_opens_a_fresh_socket_whose_snapshot_replaces_the_book():
    tickers = [f"M{i}" for i in range(250)]
    msgs = subscribe_msgs(tickers)
    assert [len(m["params"]["market_tickers"]) for m in msgs] == [100, 100, 50]
    assert msgs[0]["params"]["channels"] == ["orderbook_delta"] and msgs[2]["id"] == 3
    books = Books()
    # socket 1: a snapshot, then a delta that skips seq 2 -> the book is wrong from here;
    # socket 2: the venue's fresh snapshot (a second subscribe on the same socket would be
    # answered with an error, not a snapshot, so the recovery is a new socket)
    ws1 = FakeWS([_snap("M1", [(0.4, 500.0)], [(0.59, 500.0)], seq=1), _delta("M1", "yes", 0.4, 10.0, seq=3)])
    ws2 = FakeWS([_snap("M1", [(0.4, 777.0)], [(0.59, 500.0)], seq=1)])
    sockets = [ws1, ws2]
    s = BookSocket(["M1"], books, open_socket=lambda: sockets.pop(0), clock=lambda: 7.0, sleep=lambda x: None)
    s.start()
    for _ in range(300):
        if s.resubscribes >= 1 and books.side("M1", "yes") == [(0.4, 777.0)]:
            break
        threading.Event().wait(0.01)
    assert s.resubscribes == 1 and s.reconnects == 0                   # a gap is a fresh socket, not an error
    assert len(ws1.sent) == 1 and len(ws2.sent) == 1 and ws2.sent[0]["cmd"] == "subscribe"   # one subscribe per socket
    assert ws1.closed.is_set() and books.side("M1", "yes") == [(0.4, 777.0)]                 # the gapped delta never applied
    assert s.counters()["seq_gaps"] == 1 and s.counters()["books"] == 1
    s.request_stop()


def test_an_empty_program_reload_keeps_live_programs_and_idles_only_when_they_all_ended():
    live = {"M1": {"series": "S", "end_ts": 2000.0}, "M2": {"series": "S", "end_ts": 2000.0}}
    assert choose_programs({}, live, now=1500.0) == (live, "empty")                   # the endpoint answered empty mid-period: keep
    assert choose_programs({}, live, now=2500.0) == ({}, "ended")                     # 03:59Z passed, nothing listed yet: idle
    assert choose_programs({"M1": live["M1"], "M2": live["M2"]}, live, now=1500.0) == (live, "same")
    new = {"M3": {"series": "S", "end_ts": 9000.0}}
    assert choose_programs(new, live, now=2500.0) == (new, "changed")


def test_the_idle_status_is_fresh_and_says_why(tmp_path):
    # 2026-10-02 04:08-12:00Z on prod: the scorer waited for programs without writing status, so the health
    # read saw a 5,269-s-old file from the last scored second and could not tell idle from dead
    p = str(tmp_path / "lip_status.json"); write_status(p, idle_status(1_700_000_000.0, ["KXAAAGASDGA", "KXAAAGASDFL"]))
    st = json.load(open(p))
    assert st["markets"] == 0 and st["scored_this_second"] == 0 and st["at"] == "2023-11-14T22:13:20+00:00"
    assert "no live liquidity programs" in st["idle"] and st["implied_per_day"]["total"] == {}


def test_the_startup_wait_survives_a_failed_fetch_and_an_empty_answer_and_writes_idle_status():
    answers = [RuntimeError("429 Too Many Requests"), {}, {"M1": {"series": "S"}}]
    slept, written = [], []

    def load(series):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    cfg = {"series": ["S"], "status": "unused"}
    out = wait_for_programs(cfg, load=load, sleep=slept.append, clock=lambda: 1.0, status=lambda path, st: written.append(st))
    assert out == {"M1": {"series": "S"}}
    assert slept == [600, 300]                                           # a failure waits longer than an empty answer
    assert len(written) == 2 and all(w["markets"] == 0 and w["idle"] for w in written)

