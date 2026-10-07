"""The Kalshi liquidity-incentive paper scorer: the published rule on a worked example, books from
snapshot + deltas with sequence gaps, the per-second scoring and its hourly aggregates, and the
socket's subscribe / resubscribe behaviour -- all without a key or a venue."""
from __future__ import annotations

import json
import queue
import sqlite3
import threading

from core.kalshi.lip_scorer import (Books, BookSocket, Scorer, choose_programs, idle_status, our_share, reference_and_score, share_qualifying, subscribe_msgs, write_status, wait_for_programs)
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


def test_share_qualifying_follows_the_term_sheet_level_by_level():
    # Terms and Conditions (July 30, 2026): each price level's whole size is added and ALL bids at that
    # price qualify; the walk stops after the level that reaches the Target Size; reference = first level
    # whose cumulative reaches target/5. Coin Race XRP yes ladder 2026-10-03 19:04Z, target 1000, discount 0.5.
    yes = [(0.04, 301.0), (0.03, 1100.0), (0.01, 1000.0)]
    share, ref, inc = share_qualifying(yes, 1000.0, 1000.0, 0.5)              # we join the 4c level: 1301 >= 1000, stop
    assert ref == 0.04 and inc == 301.0 and abs(share - 1000 / 1301) < 1e-9  # the 3c and 1c thousands never qualify
    share, ref, inc = share_qualifying(yes, 1000.0, 1000.0, 0.5, improve=True)  # 5c alone reaches target/5 and the target
    assert ref == 0.05 and inc == 0.0 and share == 1.0
    # a 200 joining a 12k wall at the same price qualifies WITH it (all bids at the level), and the 5k below does not
    wall = [(0.40, 12000.0), (0.39, 5000.0)]
    share, ref, inc = share_qualifying(wall, 200.0, 1000.0, 0.5)
    assert ref == 0.40 and inc == 12000.0 and abs(share - 200 / 12200) < 1e-9
    # the registered estimator divides by the whole discounted ladder, so it is a lower bound on the venue's share
    assert our_share(200.0, reference_and_score(wall, 1000.0, 0.5)[1]) < share
    # one tick in front: our 200 sets the reference; the wall qualifies one tick worse (x0.5)
    share, ref, inc = share_qualifying(wall, 200.0, 1000.0, 0.5, improve=True)
    assert ref == 0.41 and inc == 6000.0 and abs(share - 200 / 6200) < 1e-9


def test_share_qualifying_is_zero_when_the_side_cannot_qualify():
    assert share_qualifying([(0.30, 50.0), (0.20, 40.0)], 100.0, 1000.0, 0.5)[0] == 0.0   # never reaches the target
    assert share_qualifying([(0.99, 5000.0), (0.98, 5000.0)], 1000.0, 1000.0, 0.5)[0] == 0.0  # highest bid at 99c: no qualifying bids
    share, ref, inc = share_qualifying([], 1000.0, 1000.0, 0.5)                          # an empty side: we are the whole book
    assert share == 1.0 and inc == 0.0


class _FakeHTTP:
    """incentive_programs pages by status, paginated with next_cursor like the venue."""

    def __init__(self, pages: dict[str, list[list[dict]]]) -> None:
        self.pages, self.calls = pages, []

    def get(self, url, params=None):
        self.calls.append(dict(params))
        st = params["status"]; cur = params.get("cursor"); pages = self.pages.get(st, [[]])
        i = int(cur[1:]) if cur else 0
        body = {"incentive_programs": pages[i]}
        if i + 1 < len(pages):
            body["next_cursor"] = f"c{i + 1}"
        class R:
            def raise_for_status(self): pass
            def json(self, b=body): return b
        return R()


def _prog(ticker, start, end, reward=200000, target=1000):
    iso = lambda t: __import__("datetime").datetime.fromtimestamp(t, __import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
    return {"market_ticker": ticker, "start_date": iso(start), "end_date": iso(end), "period_reward": reward,
            "target_size_fp": str(target), "discount_factor_bps": 5000}


def test_load_programs_takes_live_windows_and_upcoming_ones_inside_the_horizon_across_pages():
    from core.kalshi.lip_scorer import load_programs
    now = 1_000_000.0
    http = _FakeHTTP({"active": [[_prog("KXA-1", now - 600, now + 300), _prog("KXZ-1", now - 600, now + 300)],      # page 1: a live window and an ignored series
                                 [_prog("KXA-0", now - 1800, now - 900)]],                                           # page 2: already ended (listed as active by the venue)
                      "upcoming": [[_prog("KXA-2", now + 300, now + 1200), _prog("KXA-9", now + 7200 + 1, now + 8100)]]})
    got = load_programs(["KXA"], http, now=now, horizon_s=7200)
    assert sorted(got) == ["KXA-1", "KXA-2"]                                 # live + upcoming within 2 h; not the ended, not the far, not the other series
    assert got["KXA-1"]["per_day_usd"] == 20.0 / (900 / 86400) and got["KXA-2"]["start_ts"] == now + 300
    assert [c["status"] for c in http.calls] == ["active", "active", "upcoming"] and http.calls[1]["cursor"] == "c1"
    assert sorted(load_programs(["KXA"], http, now=now)) == ["KXA-1"]       # no horizon: the live window only, one status


def test_the_scorer_scores_a_market_only_inside_its_period_and_reports_the_front_policy(tmp_path):
    now = 3600.0 * 2000 + 10
    progs = {"W1": {"series": "S", "per_day_usd": 1920.0, "target": 1000.0, "discount": 0.5, "start_ts": now - 100, "end_ts": now + 800},
             "W2": {"series": "S", "per_day_usd": 1920.0, "target": 1000.0, "discount": 0.5, "start_ts": now + 800, "end_ts": now + 1700}}
    books = Books()
    for t in ("W1", "W2"):                                                  # Coin Race XRP late in a window: yes 1c-4c ladder, no best 93c
        books.handle(_snap(t, [(0.04, 301.0), (0.03, 1100.0), (0.01, 1000.0)], [(0.93, 340.0), (0.89, 120.0), (0.86, 1000.0)]), now)
    sc = Scorer(str(tmp_path / "farm.sqlite"), progs, [200.0], books, clock=lambda: now, front_sizes=[1000.0, 300.0], front_cap=0.10)
    assert sc.tick(now) == 1 and "W2" not in sc.acc                           # the future window is not a second, scored or not
    r = sc.score_market("W1", now)
    assert set(r["shares"]) == {"200", "f1000", "f1000c", "f300", "f300c"}
    # a full-target lot one tick in front reaches the target alone on either side: by construction 100% before anyone responds
    assert r["shares"]["f1000"] == 1.0
    assert r["shares"]["f1000c"] == 0.5                                       # the capped policy skips the 93c side
    # 300 in front: yes 5c -> 300 (x1) + 301 @ 4c (x0.5) + 1100 @ 3c (x0.25) reaches 1000; no 94c -> 300 + 340 (x0.5) + 120 (x0.5^5) + 1000 (x0.5^8)
    assert abs(r["shares"]["f300"] - 0.5 * (300 / (300 + 150.5 + 275) + 300 / (300 + 170 + 3.75 + 3.90625))) < 1e-9
    assert abs(r["shares"]["f300c"] - 0.5 * (300 / 725.5)) < 1e-9
    assert r["disq_yes"] == 0 and r["disq_no"] == 0
    imp = sc.implied_per_day()
    assert set(imp["total"]) == {"200", "f1000", "f1000c", "f300", "f300c"} and abs(imp["total"]["f1000c"] - 0.5 * 1920.0) < 1e-9
    # a 99c best bid is a disqualified side and is counted per hour
    books.handle(_snap("W1", [(0.99, 2000.0)], [(0.01, 2000.0)], seq=1), now)
    sc.tick(now + 1)
    assert sc.acc["W1"]["disq_yes"] == 1 and sc.acc["W1"]["disq_no"] == 0
    sc.flush_all()
    assert sqlite3.connect(sc.db_path).execute("SELECT disq_yes, disq_no FROM lip_disq WHERE ticker='W1'").fetchone() == (1, 0)


def test_the_startup_wait_survives_a_failed_fetch_and_an_empty_answer_and_writes_idle_status():
    answers = [RuntimeError("429 Too Many Requests"), {}, {"M1": {"series": "S"}}]
    slept, written = [], []

    def load(series, horizon_s=0.0):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    cfg = {"series": ["S"], "status": "unused", "horizon_s": 0.0}
    out = wait_for_programs(cfg, load=load, sleep=slept.append, clock=lambda: 1.0, status=lambda path, st: written.append(st))
    assert out == {"M1": {"series": "S"}}
    assert slept == [600, 300]                                           # a failure waits longer than an empty answer
    assert len(written) == 2 and all(w["markets"] == 0 and w["idle"] for w in written)



def test_ws_close_is_idempotent_and_safe_from_a_second_thread():
    # prod 2026-10-04 14:03Z: request_stop() and the session's finally both closed the same WSClient;
    # the second saw _sock become None between its check and its call and raised AttributeError
    from core.polymarket.ws_min import WSClient

    class Sock:
        def __init__(self): self.closed = 0; self.sent = []
        def sendall(self, b): self.sent.append(b)
        def close(self): self.closed += 1

    ws = WSClient.__new__(WSClient); ws._sock = Sock(); ws._buf = b""
    first = ws._sock
    ws.close(); ws.close()                                               # twice, sequentially
    assert first.closed == 1 and len(first.sent) == 1 and ws._sock is None
    ws._sock = s2 = Sock()
    s2.close = lambda: (_ for _ in ()).throw(OSError("already"))            # the OS refusing the close is swallowed too
    ws.close()
    assert ws._sock is None
    # two threads closing at once: exactly one close frame, no exception from either
    ws._sock = s3 = Sock(); errs = []
    def closer():
        try: ws.close()
        except Exception as e: errs.append(e)                             # noqa: BLE001
    ts = [threading.Thread(target=closer) for _ in range(8)]
    [th.start() for th in ts]; [th.join() for th in ts]
    assert errs == [] and s3.closed == 1 and len(s3.sent) == 1


def test_a_reader_on_a_closed_client_gets_connection_closed_not_attribute_error():
    from core.polymarket.ws_min import WSClient
    import pytest
    c = WSClient("wss://example.invalid/x", {}, timeout=1.0)
    c._sock = None
    with pytest.raises(ConnectionClosed):
        c.recv_json()
    c.close(); c.close()                                                  # idempotent on a client never opened



def test_a_program_reload_carries_each_markets_hour_instead_of_overwriting_it(tmp_path):
    # the farm scorer reloads every 15 min; before adopt() the new Scorer rewrote each (hour, ticker) row
    # from zero, so a 900-s market-window kept only the seconds after the last reload
    progs = {"M1": {"series": "S", "per_day_usd": 1920.0, "target": 1000.0, "discount": 0.5, "start_ts": 0.0, "end_ts": 9e9}}
    books = Books()
    books.handle(_snap("M1", [(0.40, 800.0), (0.39, 400.0)], [(0.59, 800.0), (0.58, 400.0)]), 0.0)
    t0 = 3600.0 * 1000 + 5
    old = Scorer(str(tmp_path / "lip.sqlite"), progs, [200.0], books)
    for i in range(10):
        old.tick(t0 + i)
    new = Scorer(str(tmp_path / "lip.sqlite"), dict(progs), [200.0], books)
    new.adopt(old)
    for i in range(10, 25):
        new.tick(t0 + i)
    new.tick(t0 + 3600)                                                  # the next hour flushes the row
    row = sqlite3.connect(str(tmp_path / "lip.sqlite")).execute("SELECT seconds, valid FROM lip_hourly WHERE ticker='M1'").fetchone()
    assert row == (25, 25)                                               # all 25 seconds, not the last 15
    # a market that left the program set at the reload is flushed, not dropped
    old2 = Scorer(str(tmp_path / "lip2.sqlite"), progs, [200.0], books)
    for i in range(7):
        old2.tick(t0 + i)
    gone = Scorer(str(tmp_path / "lip2.sqlite"), {}, [200.0], books)
    gone.adopt(old2)
    assert sqlite3.connect(str(tmp_path / "lip2.sqlite")).execute("SELECT seconds FROM lip_hourly WHERE ticker='M1'").fetchone() == (7,)


def test_a_fully_cancelled_large_level_leaves_the_book_instead_of_staying_as_a_phantom_best():
    # the 2026-10-04 NFL tape: seven-figure levels built from float deltas and then cancelled to zero
    # stayed as the best price with ~2e-9 contracts and crossed the book; this exact sequence leaves
    # 1.86e-9 under plain float addition, above the old 1e-9 floor
    b = Books()
    b.handle(_snap("M1", [(0.46, 4895.33)], [(0.53, 100.0)], seq=1), 1.0)
    seq = 2
    for d in (898829.49, 1451235.58, 1498197.28, 474083.27, 1831599.06, -6153944.68):
        b.handle(_delta("M1", "no", 0.55, d, seq=seq), 1.0); seq += 1
    assert b.side("M1", "no") == [(0.53, 100.0)]                         # the 0.55 level is gone
    yes, no = b.side("M1", "yes"), b.side("M1", "no")
    assert yes[0][0] + no[0][0] <= 1.0                                   # not crossed
