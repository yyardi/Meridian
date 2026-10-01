"""The harness's background readers keep their contracts (2026-09-30).

Kalshi's order book moves to its own thread: the cache is stamped at the read's start, a read
older than KALSHI_FRESH_S is no price, and while the reader runs kalshi_quote never fetches.
Markouts record the venue's touch at fixed horizons after every fill, from the live book only.
The microtape hangs off the stream and the feed when the harness is built with a stream.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading

from core.btc15.arms import Arm, ArmSpec
from core.btc15.harness import Harness, PaperBroker, Settings, microtape_path
from core.btc15.kalshi import normalize
from core.btc15.ledger import UNIT, Ledger


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _market(now):
    return normalize({"ticker": "KXBTC15M-26SEP302015-15", "status": "active",
                      "open_time": _iso(now - 30), "close_time": _iso(now + 870), "floor_strike": 84000.0,
                      "yes_bid_dollars": "0.6100", "yes_ask_dollars": "0.6200", "no_bid_dollars": "0.3800",
                      "no_ask_dollars": "0.3900", "yes_bid_size_fp": "500", "yes_ask_size_fp": "400"})


class Feed:
    def __init__(self):
        self.quotes = {}
        self.c1m = self.c5m = self.c1h = []
        self.funding = None
        self.errors = {}

    def seconds(self):
        return []

    def average(self, a, b):
        return None

    def snapshot(self):
        return dict(self.quotes)


class Venue:
    venue = "polymarket"
    stream = None

    def __init__(self, m):
        self.m = m

    def current(self, now):
        return self.m

    def quote(self, slug):
        return dict(self.m, status="active", fee_coefficient="0.0695", book_source="stream") if slug == self.m["ticker"] else None

    def owns(self, t):
        return True


def _harness(now, reference=None):
    m = _market(now)
    led = Ledger(":memory:")
    h = Harness(Settings(db_path=":memory:", status_path="/dev/null", kalshi_every_s=0.01), led, Feed(), Venue(m), None,
                PaperBroker(), reference=reference, clock=lambda: now)
    h.market = m
    led.upsert_window(m)
    return h, m, led


def test_the_reader_thread_fills_the_cache_stamped_at_the_reads_start_and_kalshi_quote_never_fetches_meanwhile():
    now = 1_790_700_000.0
    reads = []
    gate = threading.Event()

    class K:
        def current(self, t):
            reads.append(t)
            gate.wait(0.5)
            return {"open_ts": None, "close_ts": None}
    h, m, _ = _harness(now, reference=K())
    h.reference.current = lambda t: (reads.append(t), {"open_ts": m["open_ts"], "close_ts": m["close_ts"],
                                                        "yes_bid": 0.60, "yes_ask": 0.61})[1]
    h.start_kalshi_reader()
    for _ in range(200):
        if h._kalshi_cache is not None:
            break
        threading.Event().wait(0.005)
    c = h._kalshi_cache
    assert c[0] == now and (c[1], c[2]) == (m["open_ts"], m["close_ts"]) and c[3] == {"yes_bid": 0.60, "yes_ask": 0.61}
    n = len(reads)
    assert h.kalshi_quote(now + 1.0, m, fetch=True) == {"yes_bid": 0.60, "yes_ask": 0.61}      # cached, fresh
    h.stop_kalshi_reader()
    threading.Event().wait(0.05)
    n = len(reads)
    h._kalshi_thread = object()                                                                # a reader "running"
    assert h.kalshi_quote(now + 3.0, m, fetch=True) is None and len(reads) == n               # stale: no price, NO fetch
    h._kalshi_thread = None
    assert h.kalshi_quote(now + 3.0, m, fetch=True) == {"yes_bid": 0.60, "yes_ask": 0.61} and len(reads) == n + 1   # no reader: inline read as before
    assert h._kalshi_cache[0] == now + 3.0


def test_a_failed_read_empties_the_cache_rather_than_keeping_a_stale_price():
    now = 1_790_700_000.0

    class K:
        def current(self, t):
            raise OSError("down")
    h, m, _ = _harness(now, reference=K())
    h._kalshi_cache = (now, m["open_ts"], m["close_ts"], {"yes_bid": 0.6, "yes_ask": 0.61}, id(h.reference))
    h._read_kalshi(now + 1, m["open_ts"], m["close_ts"])
    assert h._kalshi_cache is None and h.kalshi_quote(now + 1, m) is None


def test_markouts_record_the_live_touch_at_each_horizon_for_every_ledgers_fills(tmp_path):
    import time
    now = time.time()                       # the ledger stamps fills on the wall clock; the window must contain it
    h, m, led = _harness(now)
    arm_led = Ledger(str(tmp_path / "arm.sqlite"))
    h.arms = [Arm(ArmSpec("touch_maker", "mid", "join", 0.0), arm_led, 10 * UNIT)]
    arm_led.upsert_window(m)
    fid, _ = arm_led.record_fill("paper", m["ticker"], "YES", 6100, 0, 10 * UNIT)
    filled = dt.datetime.fromisoformat(arm_led._conn.execute("SELECT filled_at FROM fills").fetchone()[0]).timestamp()
    h.record_markouts(filled + 1)
    assert arm_led._conn.execute("SELECT COUNT(*) FROM markouts").fetchone()[0] == 0
    h.record_markouts(filled + 6)
    rows = arm_led._conn.execute("SELECT horizon_s, yes_bid, yes_ask FROM markouts").fetchall()
    assert [tuple(r) for r in rows] == [(5, 0.61, 0.62)]
    h.venue.m = dict(m, yes_bid=0.64, yes_ask=0.65)
    h.record_markouts(filled + 61)
    rows = arm_led._conn.execute("SELECT horizon_s, yes_bid FROM markouts ORDER BY horizon_s").fetchall()
    assert [tuple(r) for r in rows] == [(5, 0.61), (30, 0.64), (60, 0.64)]
    # a fill in a window that has closed unread is recorded empty once, and not asked again
    h.market = None
    arm_led._conn.execute("UPDATE windows SET close_ts=? WHERE ticker=?", (filled + 100, m["ticker"]))
    arm_led.upsert_window(dict(m, ticker="past-window", close_ts=filled + 200))
    fid2, _ = arm_led.record_fill("paper", "past-window", "NO", 3900, 0, 10 * UNIT)
    h.record_markouts(filled + 400)
    rows = arm_led._conn.execute("SELECT fill_id, horizon_s, yes_bid FROM markouts WHERE fill_id=? ORDER BY horizon_s", (fid2,)).fetchall()
    assert [tuple(r) for r in rows] == [(fid2, 5, None), (fid2, 30, None), (fid2, 60, None)]
    assert arm_led.markouts_due(filled + 400, arm_led.window_close_ts) == []


def test_build_hangs_the_microtape_off_the_stream_and_the_feed(tmp_path, monkeypatch):
    from core.btc15 import harness as H
    from core.btc15.stream_book import StreamBook
    monkeypatch.setenv("POLYMARKET_KEY_ID", "k")
    monkeypatch.setenv("POLYMARKET_SECRET", "s")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MERIDIAN_BTC15_MODEL", raising=False)
    monkeypatch.setattr(H, "KalshiBTC", lambda: None)
    s = Settings(db_path=str(tmp_path / "polymarket-15m.sqlite"), status_path="/dev/null", horizon="1h")
    h = H.build(s)
    assert h.microtape is not None and h.microtape.path == str(tmp_path / "polymarket-15m-microtape.sqlite")
    assert microtape_path("/data/polymarket-15m.sqlite") == "/data/polymarket-15m-microtape.sqlite"
    stream = h.venue.stream
    assert isinstance(stream, StreamBook) and stream.on_book == h.microtape.book and stream.on_trade == h.microtape.trade
    assert h.feed.on_spot is not None                                        # the fan-out: the tape and the spot trigger
    names = {a.spec.name for a in h.arms}
    assert {"touch_maker", "touch_maker_k", "touch_maker_t", "touch_maker_kt"} <= names and all(a.prints == stream.prints for a in h.arms)
    h.microtape.stop()
    assert sqlite3.connect(h.microtape.path).execute("SELECT COUNT(*) FROM spot").fetchone()[0] == 0
    s2 = Settings(db_path=str(tmp_path / "b.sqlite"), status_path="/dev/null", horizon="1h", microtape="none")
    assert H.build(s2).microtape is None


def test_one_ledger_connection_survives_two_threads_reading_and_writing_at_once(tmp_path):
    """2026-09-30 on prod: the stream thread's ledger.decision() and the main loop's collided on
    the model's ledger (sqlite3.InterfaceError: bad parameter or other API misuse), three times
    in forty minutes once the markout thread joined them. Every statement now runs under the
    ledger's lock; this hammers one Ledger from two threads for a moment and expects no error."""
    import time
    led = Ledger(str(tmp_path / "race.sqlite"))
    m = _market(time.time())
    led.upsert_window(m)
    errors = []
    stop = threading.Event()

    def reader():
        try:
            while not stop.is_set():
                led.decision(m["ticker"]); led.unsettled_fills(); led.account("paper"); led.spent()
                led.markouts_due(time.time(), led.window_close_ts); led.recent_results(3)
        except Exception as e:                                       # noqa: BLE001
            errors.append(repr(e))

    def writer():
        try:
            i = 0
            while not stop.is_set():
                led.add_quote(time.time() + i * 1e-3, {"ticker": m["ticker"], "yes_bid": 0.4, "yes_ask": 0.41}, None)
                led.put("k", str(i)); led.add_ticks([(time.time() + i * 1e-3, 1.0, 4, 0.0)])
                i += 1
        except Exception as e:                                       # noqa: BLE001
            errors.append(repr(e))
    ts = [threading.Thread(target=reader), threading.Thread(target=reader), threading.Thread(target=writer)]
    for t in ts:
        t.start()
    time.sleep(0.6)
    stop.set()
    for t in ts:
        t.join(5)
    assert errors == []


def test_the_spot_socket_drives_the_trigger_from_the_coinbase_move_over_the_window(tmp_path):
    from core.btc15.arms import Arm, ArmSpec
    now = 1_790_700_000.0
    h, m, led = _harness(now)
    arm_led = Ledger(str(tmp_path / "p.sqlite"))
    arm = Arm(ArmSpec("touch_maker_p", "mid", "join", 0.0, spot_pull_usd=10, spot_pull_ms=250), arm_led, 10 * UNIT)
    h.arms = [arm]
    arm.tick(now, dict(m, status="active", fee_coefficient="0.0695"), {"mid": 0.615}, 0.0695, 90)
    h.on_spot_update("kraken", 84000.0, 84001.0, 84000.5, now + 1.0)          # not the trigger exchange
    h.on_spot_update("coinbase", 84000.0, 84001.0, 84000.5, now + 1.0)        # a fresh socket: nothing before the window, no trigger
    h.on_spot_update("coinbase", 84000.0, 84001.0, 84000.5, now + 1.5)
    h.on_spot_update("coinbase", 84004.0, 84005.0, 84004.5, now + 1.9)        # +$4 over the prior 250 ms: under the threshold
    r = json.loads(arm_led.decision(m["ticker"])["response"])
    assert r["offer"] == 0.62 and r["bid"] == 0.61
    h.on_spot_update("coinbase", 84012.0, 84013.0, 84012.5, now + 2.1)        # +$12 over the prior 250 ms (base: the 1.5 s quote): pull the offer
    r = json.loads(arm_led.decision(m["ticker"])["response"])
    assert r["offer"] is None and r["bid"] == 0.61 and r["pulled"]["offer"]["move"] == 12.0 and r["pulled"]["offer"]["mid"] == 0.615
    assert h.spot_trigger_counts == {"over_threshold": 1, "pulled": 1, "lock_missed": 0}
    h._arms_lock.acquire()                                                    # a pass holds the lock: the quote is skipped, never blocks, and counted
    try:
        h.on_spot_update("coinbase", 83980.0, 83981.0, 83980.5, now + 2.2)
    finally:
        h._arms_lock.release()
    assert json.loads(arm_led.decision(m["ticker"])["response"])["bid"] == 0.61
    assert h.spot_trigger_counts == {"over_threshold": 2, "pulled": 1, "lock_missed": 1}


def test_build_fans_socket_quotes_out_to_the_tape_and_the_trigger(tmp_path, monkeypatch):
    from core.btc15 import harness as H
    monkeypatch.setenv("POLYMARKET_KEY_ID", "k")
    monkeypatch.setenv("POLYMARKET_SECRET", "s")
    for k in ("OPENAI_API_KEY", "MERIDIAN_BTC15_MODEL", "KALSHI_API_KEY_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(H, "KalshiBTC", lambda: None)
    h = H.build(H.Settings(db_path=str(tmp_path / "polymarket-15m.sqlite"), status_path="/dev/null", horizon="15m"))
    seen = []
    h.on_spot_update = lambda *a: seen.append(a)
    h.feed.on_spot("coinbase", 1.0, 2.0, 1.5, 5.0)
    h.microtape.drain()
    assert seen == [("coinbase", 1.0, 2.0, 1.5, 5.0)]
    assert sqlite3.connect(h.microtape.path).execute("SELECT COUNT(*) FROM spot").fetchone()[0] == 1
    h.microtape.stop()


def test_probabilities_carry_the_spot_move_over_each_window_from_the_ring():
    now = 1_790_700_000.0
    h, m, led = _harness(now)
    assert h.spot_moves(now) == {250: None, 500: None, 1000: None}                       # no socket quote yet
    for t, px in ((now - 1.2, 84000.0), (now - 0.6, 84003.0), (now - 0.2, 84010.0), (now - 0.05, 84012.0)):
        h._spot_ring.append((t, px))
    assert h.spot_moves(now) == {250: 84012.0 - 84003.0, 500: 84012.0 - 84003.0, 1000: 84012.0 - 84000.0}
    assert h.spot_moves(now + 6)[250] is None                                            # a socket silent 5 s is no move
    assert h.probabilities(now, dict(m, yes_bid=0.61, yes_ask=0.62))["spot_move"][250] == 9.0


def test_the_kalshi_reader_tapes_the_depth_it_read(tmp_path):
    from core.btc15.microtape import Microtape
    now = 1_790_700_000.0

    class K:
        def current(self, t):
            return {"ticker": "KXBTC15M-X", "open_ts": None, "close_ts": None, "yes_bid": 0.6, "yes_ask": 0.61,
                    "levels": {"yes": [(0.6, 10.0)], "no": [(0.39, 20.0)]}}
    h, m, _ = _harness(now, reference=K())
    h.reference.current = lambda t: {"ticker": "KXBTC15M-X", "open_ts": m["open_ts"], "close_ts": m["close_ts"], "yes_bid": 0.6, "yes_ask": 0.61,
                                     "levels": {"yes": [(0.6, 10.0)], "no": [(0.39, 20.0)]}}
    h.microtape = Microtape(str(tmp_path / "micro.sqlite"), clock=lambda: now)
    h._read_kalshi(now + 1, m["open_ts"], m["close_ts"])
    h.microtape.drain()
    rows = sqlite3.connect(h.microtape.path).execute("SELECT recv, ticker, side, price, size FROM kalshi_book ORDER BY side DESC").fetchall()
    assert rows == [(now + 1, "KXBTC15M-X", "yes", 0.6, 10.0), (now + 1, "KXBTC15M-X", "no", 0.39, 20.0)]
    assert h._kalshi_cache[3] == {"yes_bid": 0.6, "yes_ask": 0.61}                 # the cache contract is unchanged
