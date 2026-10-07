"""The Coin Race live paper farming arm (core/kalshi/farm_paper.py): the registered quote policy, the fill
rule from prints, settlement, the per-second reward on valid seconds, accumulators across reloads and
restarts, the socket-print audit, the registered read -- and a control that must fail. No key, no venue."""
from __future__ import annotations

import queue
import sqlite3
import threading

from core.kalshi.farm_paper import (
    CHANNELS,
    Farm,
    FarmBooks,
    cluster_mean_ci,
    fill_pnl,
    fills_us,
    front_quote,
    nearest_rank,
    registered_read,
    settlement_value,
    side_hit,
)
from core.kalshi.lip_scorer import BookSocket, share_qualifying, subscribe_msgs
from core.polymarket.ws_min import ConnectionClosed

T0 = 1_791_000_000.0                       # a window opening (any quarter hour)
TK = "KXCRYPTOLEAD15M-26OCT070130-XRP"


def _prog(start=T0, end=T0 + 900):
    return {"series": "KXCRYPTOLEAD15M", "per_day_usd": 20.0 / (900 / 86400), "target": 1000.0, "discount": 0.5, "start_ts": start, "end_ts": end}


def _snap(tk, yes, no, sid=1, seq=1):
    return {"type": "orderbook_snapshot", "sid": sid, "seq": seq,
            "msg": {"market_ticker": tk, "yes_dollars_fp": [[f"{p:.4f}", f"{q:.2f}"] for p, q in yes], "no_dollars_fp": [[f"{p:.4f}", f"{q:.2f}"] for p, q in no]}}


def _delta(tk, side, price, delta, seq, sid=1):
    return {"type": "orderbook_delta", "sid": sid, "seq": seq, "msg": {"market_ticker": tk, "side": side, "price_dollars": f"{price:.4f}", "delta_fp": f"{delta:.2f}"}}


_N = [0]


def _trade(tk, taker_side, yes_c, count, ts=None):
    """The venue's trade message, shaped like the 2026-10-02 Kalshi tape (core/kalshi/book_recorder.py writes it raw)."""
    _N[0] += 1
    ts_ms = int(((T0 + 100) if ts is None else ts) * 1000)
    return {"type": "trade", "sid": 2, "seq": _N[0],
            "msg": {"trade_id": f"t{_N[0]}", "market_ticker": tk, "yes_price_dollars": f"{yes_c / 100:.4f}", "no_price_dollars": f"{(100 - yes_c) / 100:.4f}",
                    "count_fp": f"{count:.2f}", "taker_side": taker_side, "taker_outcome_side": taker_side, "taker_book_side": "bid",
                    "is_block_trade": False, "ts": int(ts_ms // 1000), "ts_ms": ts_ms}}


def _farm(tmp_path, programs=None, **kw):
    books = FarmBooks()
    farm = Farm(str(tmp_path / "farm_paper.sqlite"), books, **kw)
    books.farm = farm
    farm.set_programs(programs or {TK: _prog()}, T0 - 600)
    return farm, books


# ------------------------------------------------------------------ the quote
def test_the_quote_is_one_tick_in_front_capped_never_crossing_and_pulled_at_t_minus_60():
    end = T0 + 900
    assert front_quote(3, 50, 1000, T0, end) == (4, "front")
    assert front_quote(9, 50, 1000, T0, end) == (10, "front")                  # 10c is inside the cap
    assert front_quote(10, 50, 1000, T0, end) == (None, "above_cap")          # one tick in front would be 11c
    assert front_quote(5, 93, 1000, T0, end) == (6, "front")                   # 6 + 93 = 99 < 100
    assert front_quote(5, 94, 1000, T0, end) == (None, "would_cross")         # 6 + 94 = 100: our bid would take their bid
    assert front_quote(None, 50, 1000, T0, end) == (None, "no_bid")
    assert front_quote(3, 50, 0, T0, end) == (None, "filled")                  # no refill
    assert front_quote(3, 50, 1000, end - 61, end) == (4, "front")
    assert front_quote(3, 50, 1000, end - 60, end) == (None, "pulled")


def test_the_farm_re_prices_on_every_book_change_and_skips_sides_whose_reference_is_above_10c(tmp_path):
    farm, books = _farm(tmp_path)
    now = T0 + 10
    books.handle(_snap(TK, [(0.03, 1100.0), (0.01, 1000.0)], [(0.93, 2000.0)]), now)
    mw = farm.mw[TK]
    assert mw.quote == {"yes": 4, "no": None} and mw.why["no"] == "above_cap"      # the 93c NO side carries no quote
    books.handle(_delta(TK, "yes", 0.05, 120.0, seq=2), now + 1)                   # an incumbent bid reaches above our 4c
    assert mw.quote["yes"] == 6 and mw.at_us["yes"] == 1                           # we step back in front; counted, not a response to us
    books.handle(_delta(TK, "yes", 0.05, -120.0, seq=3), now + 2)                  # it leaves: we follow the best down
    assert mw.quote["yes"] == 4 and mw.reprices["yes"] == 3                        # None->4, 4->6, 6->4
    # a thin top above the cap: the incumbents' reference is 5c (50 < 200 at 12c) but one tick in front of the best is
    # 13c, and with our 1,000 there the side's reference would be 13c -- so no quote
    books.handle(_delta(TK, "yes", 0.12, 50.0, seq=4), now + 3)
    assert mw.quote["yes"] is None and mw.why["yes"] == "above_cap"
    books.handle(_delta(TK, "yes", 0.12, -50.0, seq=5), now + 4)
    assert mw.quote["yes"] == 4
    farm.tick(T0 + 900 - 60)                                                       # T-60: both sides pulled
    assert mw.quote == {"yes": None, "no": None} and mw.why["yes"] == "pulled"
    # a market outside its program period is never quoted
    farm2, books2 = _farm(tmp_path / "b", programs={TK: _prog(T0 + 900, T0 + 1800)})
    books2.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0 + 10)
    assert TK not in farm2.mw


# ------------------------------------------------------------------ fills
def test_a_sell_print_at_or_below_our_bid_fills_us_first_up_to_the_remaining_size_and_a_print_above_does_not(tmp_path):
    farm, books = _farm(tmp_path)
    now = T0 + 100
    books.handle(_snap(TK, [(0.03, 1100.0), (0.01, 1000.0)], [(0.95, 2000.0)]), now)
    mw = farm.mw[TK]
    assert mw.quote["yes"] == 4
    books.handle(_trade(TK, "no", 3, 300.0), now + 5)                 # a taker sells YES at 3c: we are hit first, at OUR 4c
    assert mw.remaining["yes"] == 700.0 and mw.fill_qty["yes"] == 300.0
    books.handle(_trade(TK, "no", 5, 500.0), now + 6)                 # a sale at 5c met a bid above ours: not us
    books.handle(_trade(TK, "yes", 3, 400.0), now + 6.5)              # a taker BUYING YES hits the NO bids, not ours
    assert mw.remaining["yes"] == 700.0
    dup = _trade(TK, "no", 4, 1000.0)
    books.handle(dup, now + 7)                                        # at our price: fills the remaining 700 only
    books.handle(dup, now + 7.1)                                      # the same trade id twice is one print
    assert mw.remaining["yes"] == 0.0 and mw.fill_qty["yes"] == 1000.0
    assert mw.quote["yes"] is None and mw.why["yes"] == "filled"     # no refill
    books.handle(_trade(TK, "no", 1, 100.0), now + 8)
    assert mw.fill_qty["yes"] == 1000.0
    assert farm.write_fills() == 2
    rows = sqlite3.connect(farm.db_path).execute("SELECT side, price_c, qty, print_c, print_qty, via_lookback FROM fills ORDER BY t").fetchall()
    assert rows == [("yes", 4, 300.0, 3, 300.0, 0), ("yes", 4, 700.0, 4, 1000.0, 0)]
    assert mw.prints == 5 and abs(mw.fill_cost - 40.0) < 1e-9
    # the NO side: a taker buying YES sells into the NO bids at no_price
    farm2, books2 = _farm(tmp_path / "b")
    books2.handle(_snap(TK, [(0.90, 2000.0)], [(0.05, 1100.0)]), now)
    assert farm2.mw[TK].quote == {"yes": None, "no": 6}
    books2.handle(_trade(TK, "yes", 95, 250.0), now + 1)             # yes 95c = no 5c <= our 6c NO bid
    assert farm2.mw[TK].fill_qty == {"yes": 0.0, "no": 250.0}
    assert side_hit("no") == "yes" and side_hit("yes") == "no" and side_hit(None) is None


def test_a_print_whose_book_delta_arrived_first_is_tested_against_the_quote_it_moved(tmp_path):
    # the venue's trade and book channels are separate: the delta that removes the hit level can land before
    # the print, moving our quote down; without the lookback the print would miss us and flatter the arm
    for lookback, filled, price in ((1.0, 300.0, 6), (0.0, 0.0, None)):
        farm, books = _farm(tmp_path / f"lb{lookback}", lookback_s=lookback)
        now = T0 + 200
        books.handle(_snap(TK, [(0.05, 300.0), (0.03, 1100.0)], [(0.93, 2000.0)]), now)
        assert farm.mw[TK].quote["yes"] == 6
        books.handle(_delta(TK, "yes", 0.05, -300.0, seq=2), now + 0.010)       # the 5c level is taken ...
        assert farm.mw[TK].quote["yes"] == 4
        books.handle(_trade(TK, "no", 5, 300.0), now + 0.012)                    # ... and the print that took it arrives
        assert farm.mw[TK].fill_qty["yes"] == filled
        farm.write_fills()
        r = sqlite3.connect(farm.db_path).execute("SELECT price_c, via_lookback FROM fills").fetchall()
        assert r == ([(price, 1)] if price else [])
    # a print executed after our T-60 cancel does not fill, even when it is received inside the lookback
    farm, books = _farm(tmp_path / "pull")
    books.handle(_snap(TK, [(0.03, 1100.0)], [(0.93, 2000.0)]), T0 + 839)
    books.handle(_trade(TK, "no", 2, 100.0, ts=T0 + 840.2), T0 + 840.3)
    assert farm.mw[TK].fill_qty["yes"] == 0.0
    books.handle(_trade(TK, "no", 2, 100.0, ts=T0 + 839.8), T0 + 840.3)        # executed before it: fills
    assert farm.mw[TK].fill_qty["yes"] == 100.0


# ------------------------------------------------------------------ settlement
def test_settlement_pnl_both_ways_and_the_ledger_rows(tmp_path):
    assert fill_pnl("yes", 4, 1000, 1.0) == 960.0 and fill_pnl("yes", 4, 1000, 0.0) == -40.0
    assert fill_pnl("no", 6, 1000, 1.0) == -60.0 and abs(fill_pnl("no", 6, 1000, 0.0) - 940.0) < 1e-9
    assert abs(fill_pnl("yes", 4, 1000, 0.5) - 460.0) < 1e-9                    # a two-coin tie settles 0.5
    assert settlement_value({"status": "active", "result": ""}) is None
    assert settlement_value({"status": "closed", "settlement_value_dollars": "1.0000"}) is None
    assert settlement_value({"status": "finalized", "result": "no", "settlement_value_dollars": "0.0000"}) == 0.0
    assert settlement_value({"status": "settled", "result": "yes"}) == 1.0
    assert settlement_value({"status": "finalized", "settlement_value_dollars": "0.5000"}) == 0.5
    for result, value, expect in (("no", "0.0000", -40.0 + 940.0 * 0.25), ("yes", "1.0000", 960.0 - 60.0 * 0.25)):
        farm, books = _farm(tmp_path / result)
        books.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0 + 10)
        books.handle(_trade(TK, "no", 3, 1000.0), T0 + 20)                       # YES 1,000 at 4c
        books.handle(_trade(TK, "yes", 95, 250.0), T0 + 21)                      # NO 250 at 6c
        farm.tick(T0 + 900)                                                      # the window closes
        assert farm.mw[TK].status == "closed" and farm.settle_due[TK][0] == T0 + 945
        assert farm.settle(TK, {"status": "closed"}, [], T0 + 950) is None      # not settled yet: retried
        assert farm.settle_due[TK][0] == T0 + 1010
        pnl = farm.settle(TK, {"status": "finalized", "result": result, "settlement_value_dollars": value}, [], T0 + 1010)
        assert abs(pnl - expect) < 1e-9
        db = sqlite3.connect(farm.db_path)
        w = db.execute("SELECT status, result, settlement_value, fill_pnl, fill_qty_yes, fill_qty_no FROM windows").fetchone()
        assert w[:2] == ("settled", result) and abs(w[3] - expect) < 1e-9 and w[4:] == (1000.0, 250.0)
        st = {s: (q, round(a, 4), round(p, 4)) for s, q, a, p in db.execute("SELECT side, qty, avg_price, pnl_usd FROM settlements")}
        assert st["yes"][:2] == (1000.0, 0.04) and st["no"][:2] == (250.0, 0.06)
        assert TK not in farm.mw and TK not in farm.settle_due and books.side(TK, "yes") == []


def test_a_window_the_venue_never_settles_is_recorded_unsettled_after_six_hours(tmp_path):
    farm, books = _farm(tmp_path)
    books.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0 + 10)
    farm.tick(T0 + 10); farm.tick(T0 + 900)
    assert farm.due_settlements(T0 + 900) == [] and farm.due_settlements(T0 + 945) == [TK]
    assert farm.due_settlements(T0 + 946) == []                                   # in flight: not twice
    farm.retry_settle(TK, T0 + 950)
    assert farm.due_settlements(T0 + 900 + 6 * 3600 + 1) == []
    assert sqlite3.connect(farm.db_path).execute("SELECT status FROM windows").fetchone() == ("unsettled",)


# ------------------------------------------------------------------ the reward
def test_reward_accrues_only_on_valid_seconds_at_the_term_sheet_share_of_the_size_still_resting(tmp_path):
    farm, books = _farm(tmp_path)
    per_s = 20.0 / 900
    books.handle(_snap(TK, [(0.03, 1100.0), (0.01, 1000.0)], [(0.05, 1100.0)]), T0)
    mw = farm.mw[TK]
    assert mw.quote == {"yes": 4, "no": 6}                                        # 4 + 5 and 6 + 3 stay under 100
    assert farm.tick(T0 + 1) == 1
    assert abs(mw.reward - per_s) < 1e-12 and mw.valid == 1                       # 1/2 x (1 + 1) x $20/900: both sides whole
    books.handle(_delta(TK, "no", 0.05, -200.0, seq=2), T0 + 1.5)                  # NO depth 900 < the 1,000 target
    assert farm.tick(T0 + 2) == 0
    assert mw.seconds == 2 and mw.valid == 1 and abs(mw.reward - per_s) < 1e-12   # a second, not a valid one, nothing paid
    books.handle(_delta(TK, "no", 0.05, 200.0, seq=3), T0 + 2.5)
    books.handle(_trade(TK, "no", 3, 600.0), T0 + 2.6)                            # YES 600 filled: 400 still resting at 4c
    farm.tick(T0 + 3)
    # YES walk: 4c 400 (reference: >= 200), 3c 1,100 one tick below at x0.5 reaches 1,000 and stops -> 400 / (400 + 550)
    sy = 400 / 950
    assert abs(mw.rs["yes"] - (0.5 * per_s + 0.5 * sy * per_s)) < 1e-12 and abs(mw.rs["no"] - 1.0 * per_s) < 1e-12
    # the price= form is improve=True's walk whenever the best level alone holds a fifth of the target
    lv = [(0.03, 1100.0), (0.01, 1000.0)]
    assert share_qualifying(lv, 400.0, 1000.0, 0.5, price=0.04) == share_qualifying(lv, 400.0, 1000.0, 0.5, improve=True)
    assert share_qualifying(lv, 400.0, 1000.0, 0.5, price=0.04)[0] == sy
    # a whole window at full share both sides is the program's $20
    farm2, books2 = _farm(tmp_path / "w")
    books2.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0)
    for i in range(900):
        farm2.tick(T0 + i)
    m2 = farm2.mw[TK]
    assert m2.seconds == 900 and m2.quoted == {"yes": 840, "no": 840} and abs(m2.reward - 840 * per_s) < 1e-9   # pulled for the last 60 s
    assert dict(m2.reasons["yes"]) == {"pulled": 60}


def test_accumulators_survive_a_program_reload_and_a_restart(tmp_path):
    farm, books = _farm(tmp_path)
    books.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0)
    for i in range(10):
        farm.tick(T0 + i)
    mw = farm.mw[TK]
    books.handle(_trade(TK, "no", 3, 250.0), T0 + 10.5)
    nxt = "KXCRYPTOLEAD15M-26OCT070145-XRP"
    farm.set_programs({TK: _prog(), nxt: _prog(T0 + 900, T0 + 1800)}, T0 + 11)    # a reload adds the next window
    assert farm.mw[TK] is mw and mw.seconds == 10
    farm.set_programs({nxt: _prog(T0 + 900, T0 + 1800)}, T0 + 11.5)                # an answer that omits the live window
    assert TK in farm.programs and farm.mw[TK] is mw
    for i in range(11, 16):
        farm.tick(T0 + i)
    per_s = 20.0 / 900                                                              # 750 left at 4c: 750 / (750 + 1,100 x 0.5)
    assert mw.seconds == 15 and abs(mw.reward - (10 * per_s + 5 * 0.5 * (750 / 1300 + 1.0) * per_s)) < 1e-12
    farm.persist(T0 + 16)
    # the process restarts: the open window comes back from the ledger, not from zero
    books2 = FarmBooks()
    farm2 = Farm(farm.db_path, books2); books2.farm = farm2
    assert farm2.restore(T0 + 20) == 1
    m2 = farm2.mw[TK]
    assert (m2.seconds, m2.valid, round(m2.reward, 12), m2.remaining["yes"], m2.fill_qty["yes"]) == (15, 15, round(mw.reward, 12), 750.0, 250.0)
    farm2.set_programs({TK: _prog()}, T0 + 20)
    books2.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0 + 20)
    farm2.tick(T0 + 21); farm2.persist(T0 + 22)
    assert sqlite3.connect(farm.db_path).execute("SELECT seconds FROM windows WHERE ticker=?", (TK,)).fetchone() == (16,)


# ------------------------------------------------------------------ the control that must fail
def test_control_an_inverted_fill_rule_turns_the_same_sequence_to_the_opposite_sign(tmp_path):
    # YES rests at 4c and NO at 6c; a taker dumps YES at 2c (below our YES bid), another sells NO at 50c (above our
    # NO bid); YES wins. The rule fills the 2c dump (+$960); the inverted rule fills the 50c sale on NO (-$60).
    def run(rule, sub):
        farm, books = _farm(tmp_path / sub, fill_rule=rule)
        books.handle(_snap(TK, [(0.03, 1100.0)], [(0.05, 1100.0)]), T0 + 10)
        books.handle(_trade(TK, "no", 2, 1000.0), T0 + 20)
        books.handle(_trade(TK, "yes", 50, 1000.0), T0 + 30)
        farm.tick(T0 + 900)
        return farm.settle(TK, {"status": "finalized", "result": "yes", "settlement_value_dollars": "1.0000"}, [], T0 + 960)
    real = run(fills_us, "real")
    inverted = run(lambda print_c, quote_c: print_c > quote_c, "inverted")
    assert real == 960.0 and abs(inverted - (-60.0)) < 1e-9
    assert (real > 0) != (inverted > 0)


# ------------------------------------------------------------------ the socket, the quiet zone, the audit
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


def test_one_socket_carries_books_and_prints_and_a_print_fills_through_it(tmp_path):
    farm, books = _farm(tmp_path)
    now = [T0 + 50]
    ws = FakeWS([_snap(TK, [(0.03, 1100.0)], [(0.93, 2000.0)]), _trade(TK, "no", 3, 120.0)])
    s = BookSocket([TK], books, open_socket=lambda: ws, clock=lambda: now[0], sleep=lambda x: None, channels=CHANNELS).start()
    for _ in range(300):
        if books.trades >= 1:
            break
        threading.Event().wait(0.01)
    s.request_stop()
    assert ws.sent == subscribe_msgs([TK], CHANNELS) and ws.sent[0]["params"]["channels"] == ["orderbook_delta", "trade"]
    assert farm.mw[TK].fill_qty["yes"] == 120.0 and books.trades == 1


def test_socket_restarts_wait_for_the_dead_zone_between_t_minus_60_and_the_next_window():
    farm = Farm.__new__(Farm)
    farm.lock = threading.RLock(); farm.pull_s = 60.0
    farm.programs = {"W1": _prog(T0, T0 + 900), "W2": _prog(T0 + 900, T0 + 1800)}
    assert not farm.quiet(T0 + 100) and not farm.quiet(T0 + 839)                  # W1 can be quoted
    assert farm.quiet(T0 + 840) and farm.quiet(T0 + 879)                          # everything pulled, W2 > 20 s away
    assert not farm.quiet(T0 + 880)                                               # W2 opens within 20 s


def test_settlement_audits_the_socket_prints_against_the_public_tape(tmp_path):
    farm, books = _farm(tmp_path)
    books.handle(_snap(TK, [(0.03, 1100.0)], [(0.93, 2000.0)]), T0 + 10)
    seen = _trade(TK, "no", 3, 100.0, ts=T0 + 20)
    books.handle(seen, T0 + 20)
    iso = lambda t: __import__("datetime").datetime.fromtimestamp(t, __import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
    rest = [{"trade_id": seen["msg"]["trade_id"], "created_time": iso(T0 + 20), "taker_side": "no", "yes_price_dollars": "0.0300",
             "no_price_dollars": "0.9700", "count_fp": "100.00"},
            {"trade_id": "lost-1", "created_time": iso(T0 + 30), "taker_side": "no", "yes_price_dollars": "0.0200",       # the socket never
             "no_price_dollars": "0.9800", "count_fp": "75.00"},                                                          # delivered it; it hits us
            {"trade_id": "lost-2", "created_time": iso(T0 + 31), "taker_side": "no", "yes_price_dollars": "0.0900",
             "no_price_dollars": "0.9100", "count_fp": "40.00"},                                                          # above our bid
            {"trade_id": "before", "created_time": iso(T0 - 5), "taker_side": "no", "yes_price_dollars": "0.0100",
             "no_price_dollars": "0.9900", "count_fp": "999.00"}]                                                         # before the window
    farm.tick(T0 + 900)
    farm.settle(TK, {"status": "finalized", "result": "no", "settlement_value_dollars": "0.0000"}, rest, T0 + 960)
    row = sqlite3.connect(farm.db_path).execute("SELECT prints_socket, prints_rest, prints_missed, missed_fillable, audit, fill_pnl FROM windows").fetchone()
    assert row == (1, 3, 2, 75.0, "full", -4.0)                                    # the lost print is counted, not added


# ------------------------------------------------------------------ the registered read
def test_the_registered_read_clusters_by_window_and_applies_the_decision_rule(tmp_path):
    assert cluster_mean_ci([[1.0, 1.0], [3.0, 3.0]])[:3] == (2.0, 2.0 - 1.96, 2.0 + 1.96)    # var = 2/1 x (4 + 4)/16 = 1
    assert nearest_rank([5.0, 1.0, 3.0, 2.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0], 0.9) == 9.0
    farm, _ = _farm(tmp_path)
    db = farm.conn
    for w in range(4):                                         # four windows x five coins; every coin earns $8, fills cost $1 each,
        for i, coin in enumerate(("BTC", "ETH", "SOL", "XRP", "HYPE")):        # except window 3 where BTC lost $60 on a fill
            t = f"KXCRYPTOLEAD15M-W{w}-{coin}"
            pnl = -60.0 if (w == 3 and coin == "BTC") else -1.0
            db.execute("INSERT INTO windows(ticker, series, coin, start_ts, end_ts, reward_per_s, target, discount, first_tick, seconds, valid,"
                       " reward_usd, quoted_yes, quoted_no, book_at_us_yes, book_at_us_no, status, settlement_value, fill_pnl, prints_rest,"
                       " prints_missed, missed_fillable, audit) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (t, "KXCRYPTOLEAD15M", coin, T0 + 900 * w, T0 + 900 * (w + 1), 20 / 900, 1000, 0.5, T0 + 900 * w + 1, 900, 810,
                        8.0, 840, 0, 0, 0, "settled", 0.0, pnl, 10, 0, 0.0, "full"))
    r = registered_read(db, days=4 * 900 / 86400)
    assert r["settled"] == 20 and r["windows"] == 4 and r["expected_market_windows"] == 20
    # net per market-window: (19 x 7 + 1 x -52) / 20 = 4.05; per-window sums 35, 35, 35, -24
    assert abs(r["net"][0] - 4.05) < 1e-12 and abs(r["reward"][0] - 8.0) < 1e-12 and abs(r["fill_pnl"][0] - (-3.95)) < 1e-12
    assert r["loss_per_window_p90"] == 64.0 and r["loss_per_window_max"] == 64.0   # four windows: the 90th percentile is the worst
    assert abs(r["valid_fraction"] - 0.9) < 1e-12
    assert r["decision"].startswith("FAIL")                                        # p90 loss $64 > $50
    db.execute("UPDATE windows SET fill_pnl = -1.0")
    r2 = registered_read(db, days=4 * 900 / 86400)
    assert r2["net"][1] > 0 and r2["loss_per_window_p90"] == 5.0 and r2["decision"].startswith("PASS")
    db.execute("UPDATE windows SET reward_usd = 0.5")                              # net -0.5 every market-window: closes
    assert registered_read(db, days=4 * 900 / 86400)["decision"].startswith("FAIL")
    # an instrument that missed the prints is not read in either direction
    db.execute("UPDATE windows SET reward_usd = 8.0, prints_missed = 1")           # 20 of 200 prints missed: 10% > 5%
    r3 = registered_read(db, days=4 * 900 / 86400)
    assert not r3["instrument_valid"] and r3["decision"].startswith("INVALID") and "socket missed" in r3["decision"]
    assert registered_read(db, days=5 * 900 / 86400)["decision"].startswith("INVALID")   # 20 of 25 expected market-windows
    from core.kalshi.farm_paper import format_read
    txt = format_read(r2)
    assert "PAPER: fills are inferred" in txt and "decision" in txt and "PASS" in txt
