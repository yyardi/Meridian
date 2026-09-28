"""BTC15: the money is exact, the $10 drawdown cannot be breached, and a window is decided and filled once.

    pytest --noconftest tests/test_btc15.py

No database server, no network: the ledger is SQLite on a temp path, Kalshi
and the model are fakes that behave as the verified venue does.
"""
from __future__ import annotations

import json
import pathlib
import random
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.btc15 import features as F  # noqa: E402
from core.btc15.harness import Harness, PaperBroker, Settings  # noqa: E402
from core.btc15.kalshi import normalize, to_units  # noqa: E402
from core.btc15.ledger import DEFAULT_LIMIT_U, UNIT, Ledger, fee_units, payout_units  # noqa: E402
from core.btc15.model import ModelConfig, ModelError, side_of, validate  # noqa: E402
from core.btc15.polymarket import PolymarketBTC, result_of, slug_at  # noqa: E402
from core.btc15.polymarket import normalize as pm_normalize  # noqa: E402
from core.btc15.prices import Quote, candles_ascending, composite  # noqa: E402


@pytest.fixture
def led(tmp_path):
    return Ledger(str(tmp_path / "b.sqlite"))


# ------------------------------------------------------------------ money
def test_units_come_from_the_venue_strings_exactly():
    assert to_units("0.8200") == 8200 and to_units("0.0010") == 10 and to_units(None) is None


@pytest.mark.parametrize("price_u, cents", [(5000, 2), (8200, 2), (9900, 1), (100, 1), (9990, 1), (2500, 2), (1500, 1)])
def test_the_fee_is_kalshis_quadratic_rounded_up_to_the_cent(price_u, cents):
    # 0.07 * P * (1 - P): 0.50 -> 1.75c -> 2c; 0.82 -> 1.03c -> 2c; 0.99 -> 0.07c -> 1c; 0.15 -> 0.89c -> 1c
    assert fee_units(price_u) == cents * 100
    assert fee_units(price_u) % 100 == 0


def test_the_fee_scales_with_the_series_multiplier():
    assert fee_units(5000, 1, Decimal("0.5")) == 100          # 0.875c -> 1c


def test_payout_is_a_dollar_on_the_winning_side_and_nothing_otherwise():
    assert payout_units("YES", "yes", 6000) == UNIT and payout_units("YES", "no", 6000) == 0
    assert payout_units("NO", "no", 4000) == UNIT and payout_units("NO", "yes", 4000) == 0
    assert payout_units("YES", "void", 6000) == 6000


def test_a_win_and_a_loss_settle_to_the_exact_units(led):
    fid, _ = led.record_fill("paper", "T1", "YES", 5500, 200)
    assert led.settle(fid, "yes") is True
    fid2, _ = led.record_fill("paper", "T2", "NO", 3000, 200)
    assert led.settle(fid2, "yes") is True
    a = led.account("paper")
    assert a["realized_u"] == (10000 - 5500 - 200) + (0 - 3000 - 200) == 1100
    assert a["peak_u"] == 4300 and a["drawdown_u"] == 3200 and a["wins"] == 1 and a["open"] == 0


# ------------------------------------------------------------------ what the database refuses
def test_one_fill_per_window_per_mode_and_one_contract_only(led):
    fid, why = led.record_fill("paper", "T1", "YES", 5000, 200)
    assert fid and why == "filled"
    again, why = led.record_fill("paper", "T1", "NO", 5000, 200)
    assert again is None and "refused by the ledger" in why
    with pytest.raises(Exception):
        led._conn.execute("INSERT INTO fills(mode,epoch,ticker,side,qty,price_u,fee_u,filled_at) "
                          "VALUES('paper',1,'T9','YES',2,5000,200,'x')")
    with pytest.raises(Exception):
        led._conn.execute("INSERT INTO fills(mode,epoch,ticker,side,qty,price_u,fee_u,filled_at) "
                          "VALUES('paper',1,'T8','YES',1,10000,200,'x')")


def test_a_fill_settles_once(led):
    fid, _ = led.record_fill("paper", "T1", "YES", 5000, 200)
    assert led.settle(fid, "no") is True and led.settle(fid, "no") is False
    assert led.account("paper")["realized_u"] == -5200


# ------------------------------------------------------------------ the $10 drawdown
def test_the_guard_counts_open_fills_as_lost_and_waits_without_latching(led):
    for i in range(10):                                     # ten open fills at 90c + 1c = $9.10 at risk
        fid, why = led.record_fill("paper", f"O{i}", "YES", 9000, 100)
        assert fid, why
    fid, why = led.record_fill("paper", "O10", "YES", 9000, 100)
    assert fid is None and why.startswith("waiting")         # $9.10 + $0.91 > $10
    assert led.halted("paper") is None


def test_the_guard_latches_when_the_next_trade_alone_could_breach_and_stays_latched(led):
    for i in range(18):                                     # lose 18 x (50c + 2c) = $9.36
        fid, _ = led.record_fill("paper", f"L{i}", "YES", 5000, 200)
        led.settle(fid, "no")
    assert led.account("paper")["drawdown_u"] == 18 * 5200
    fid, why = led.record_fill("paper", "L18", "YES", 6000, 200)    # $9.36 + $0.62 = $9.98 <= $10: allowed
    assert fid, why
    led.settle(fid, "no")
    fid, why = led.record_fill("paper", "L19", "YES", 1000, 100)    # $9.98 + $0.11 > $10
    assert fid is None and why.startswith("latched") and led.halted("paper")
    fid, why = led.record_fill("paper", "L20", "YES", 100, 100)     # even a 1c ticket, once latched
    assert fid is None and why == "halted"


def test_the_drawdown_is_from_the_peak_not_from_the_start(led):
    for i in range(10):                                     # win ten at 50c: +$4.80
        fid, _ = led.record_fill("paper", f"W{i}", "YES", 5000, 200)
        led.settle(fid, "yes")
    a = led.account("paper")
    assert a["peak_u"] == a["realized_u"] == 48000
    n = 0
    while True:
        fid, why = led.record_fill("paper", f"X{n}", "YES", 5000, 200)
        if fid is None:
            break
        led.settle(fid, "no")
        n += 1
    a = led.account("paper")
    assert a["peak_u"] - a["realized_u"] <= DEFAULT_LIMIT_U
    # a $10 drawdown from a +$4.80 peak stops at -$5.20 overall: the loss from the
    # start of the allocation is bounded by $10 too, because the peak starts at zero
    assert a["realized_u"] >= a["peak_u"] - DEFAULT_LIMIT_U >= -DEFAULT_LIMIT_U
    assert a["realized_u"] < 0 and led.halted("paper")


def test_no_sequence_of_trades_can_breach_ten_dollars(led):
    rng = random.Random(20260928)
    for i in range(3000):
        price = rng.randint(100, 9800)
        fee = fee_units(price)
        if price + fee > UNIT:
            continue
        fid, _ = led.record_fill("paper", f"R{i}", rng.choice(["YES", "NO"]), price, fee)
        if fid:
            led.settle(fid, rng.choice(["yes", "no"]))
        # the invariant, checked after every step from the rows themselves
        rows = led._conn.execute("SELECT pnl_u FROM settlements s JOIN fills f ON f.id=s.fill_id "
                                 "WHERE f.mode='paper' ORDER BY s.settled_at, f.id").fetchall()
        run = peak = worst = 0
        for r in rows:
            run += r[0]
            peak = max(peak, run)
            worst = max(worst, peak - run)
        assert worst <= DEFAULT_LIMIT_U
        if led.halted("paper"):
            break


def test_a_new_epoch_is_a_fresh_allocation_and_the_old_one_stays_halted(led):
    for i in range(30):
        fid, _ = led.record_fill("paper", f"E{i}", "YES", 5000, 200)
        if fid:
            led.settle(fid, "no")
    assert led.halted("paper")
    old = led.epoch("paper")
    assert led.new_epoch("paper") == old + 1 and led.halted("paper") is None
    assert led.account("paper")["realized_u"] == 0
    assert led.account("paper", old)["drawdown_u"] > 0


def test_paper_and_live_are_separate_allocations(led):
    for i in range(30):
        fid, _ = led.record_fill("paper", f"P{i}", "YES", 5000, 200)
        if fid:
            led.settle(fid, "no")
    assert led.halted("paper") and not led.halted("live")
    assert led.can_trade("live", 5200)[0] is True


# ------------------------------------------------------------------ model output
def test_the_side_is_derived_from_the_probability_not_asked_for():
    assert side_of(0.5) == "YES" and side_of(0.4999) == "NO" and side_of(0.9) == "YES"


@pytest.mark.parametrize("bad", [{"p_up": 1.2, "confidence": "low"}, {"p_up": "0.6", "confidence": "low"},
                                 {"p_up": 0.6, "confidence": "certain"}, {"confidence": "low"}])
def test_an_answer_outside_the_schema_is_an_error_not_a_trade(bad):
    with pytest.raises(ModelError):
        validate(bad)


# ------------------------------------------------------------------ features
def _bars(n, start=80000.0, step=1.0, t0=1_790_000_000.0, dt_s=60):
    out, px = [], start
    for i in range(n):
        o, px = px, px + step
        out.append((t0 + i * dt_s, min(o, px) - 2, max(o, px) + 2, o, px, 1.0))
    return out


def _market(now, strike=80100.0):
    return {"ticker": "KXBTC15M-X", "open_ts": now - 30, "close_ts": now + 870, "strike": strike,
            "yes_bid": 0.55, "yes_ask": 0.56, "no_bid": 0.44, "no_ask": 0.45}


def test_features_ignore_every_row_after_the_decision_instant():
    bars = _bars(400)
    now = bars[300][0] + 30
    secs = [(bars[0][0] + i, 80000.0 + i / 60.0) for i in range(0, 400 * 60, 10)]
    a = F.build(now=now, secs=[s for s in secs if s[0] <= now], c1m=[b for b in bars if b[0] <= now],
                c5m=[], c1h=[], market=_market(now), quotes={}, funding=None, recent_results=[])
    b = F.build(now=now, secs=secs, c1m=bars, c5m=[], c1h=[], market=_market(now), quotes={}, funding=None,
                recent_results=[])
    assert a == b, "rows after `now` must change nothing"


def test_the_random_walk_baseline_is_a_half_at_the_strike_and_monotone_in_distance():
    assert F.brownian_p_up(80000, 80000, 5.0, 600) == pytest.approx(0.5)
    ps = [F.brownian_p_up(80000 + d, 80000, 5.0, 600) for d in (-100, -10, 0, 10, 100)]
    assert ps == sorted(ps) and ps[0] < 0.5 < ps[-1]
    assert F.brownian_p_up(80010, 80000, 5.0, 0) == 1.0


def test_rsi_is_a_hundred_on_a_straight_climb_and_the_composite_is_a_median():
    assert F.rsi([float(i) for i in range(30)]) == 100.0
    q = {k: Quote(k, b, b + 2, b, 100.0) for k, b in (("a", 100.0), ("b", 104.0), ("c", 300.0))}
    px, n, disp = composite(q, now=101.0)
    assert (px, n) == (105.0, 3) and disp == 200.0
    assert composite(q, now=200.0) == (None, 0, 0.0), "stale quotes are not a price"
    assert candles_ascending([[2, 1, 3, 2, 2, 1], [1, 1, 3, 2, 2, 1]])[0][0] == 1.0


# ------------------------------------------------------------------ the loop, with fakes
class FakeFeed:
    def __init__(self, now):
        self.quotes = {k: Quote(k, 80099.0, 80101.0, 80100.0, now) for k in ("coinbase", "kraken", "gemini")}
        self._secs = [(now - 600 + i, 80100.0) for i in range(601)]
        self.c1m, self.c5m, self.c1h, self.funding = _bars(120, t0=now - 7200), [], [], None
        self.errors = {}

    def seconds(self):
        return self._secs

    def average(self, t0, t1):
        xs = [p for t, p in self._secs if t0 <= t < t1]
        return sum(xs) / len(xs) if xs else None


class FakeVenue:
    """The venue interface as the harness uses it, with Polymarket's fee rule."""
    venue = "fake"

    def owns(self, ticker):
        return True

    def __init__(self, m):
        self.m = dict(m)

    def current(self, now):
        return dict(self.m)

    def market(self, ticker):
        return dict(self.m)

    def outcome(self, ticker):
        return {"final": self.m.get("status") == "finalized" and self.m.get("result") in ("yes", "no"),
                "result": self.m.get("result"), "expiration_value": self.m.get("expiration_value")}

    def fee_units(self, price_u, market):
        return PolymarketBTC().fee_units(price_u, {**market, "fee_coefficient": "0.0695"})


class FakeModel:
    def __init__(self, p=0.62, error=None):
        self.cfg = ModelConfig(api_key="k", model="fake-model")
        self.p, self.error, self.calls = p, error, 0

    def decide(self, features, experience):
        self.calls += 1
        assert "your_record" in experience and "features" not in experience
        if self.error:
            raise ModelError(self.error)
        return {"p_up": self.p, "confidence": "medium", "key_factors": ["x"], "rationale": "r"}, {"total_tokens": 1}, 2.0

    def lesson(self, decision, outcome):
        return f"lesson for {outcome['result']}"


def _live_market(now):
    return normalize({"ticker": "KXBTC15M-26SEP280015-15", "status": "active",
                      "open_time": _iso(now - 30), "close_time": _iso(now + 870), "floor_strike": 80000.0,
                      "yes_bid_dollars": "0.6100", "yes_ask_dollars": "0.6200", "no_bid_dollars": "0.3800",
                      "no_ask_dollars": "0.3900", "yes_bid_size_fp": "500", "yes_ask_size_fp": "400"})


def _iso(ts):
    import datetime as dt
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _harness(led, now, model, broker=True):
    m = _live_market(now)
    h = Harness(Settings(db_path=":memory:", status_path="/dev/null"), led, FakeFeed(now), FakeVenue(m), model,
                PaperBroker() if broker else None, clock=lambda: now)
    h.market = m
    led.upsert_window(m)
    return h, m


def test_a_window_is_decided_once_and_filled_once_at_the_ask(led):
    now = 1_790_600_000.0
    model = FakeModel(p=0.62)
    h, m = _harness(led, now, model)
    h.decide(m)
    h.decide(m)                                             # a restart or a second tick: no second call, no second fill
    assert model.calls == 1
    d = led.decision(m["ticker"])
    assert d["status"] == "filled" and d["side"] == "YES" and d["p_up"] == 0.62
    f = led._conn.execute("SELECT * FROM fills").fetchall()
    assert len(f) == 1 and f[0]["price_u"] == 6200 and f[0]["fee_u"] == 200 and f[0]["side"] == "YES"


def test_a_no_call_buys_the_no_ask(led):
    now = 1_790_600_000.0
    h, m = _harness(led, now, FakeModel(p=0.30))
    h.decide(m)
    f = led._conn.execute("SELECT * FROM fills").fetchone()
    assert f["side"] == "NO" and f["price_u"] == 3900


def test_a_model_error_or_a_late_answer_is_recorded_and_places_nothing(led):
    now = 1_790_600_000.0
    h, m = _harness(led, now, FakeModel(error="HTTP 500"))
    h.decide(m)
    assert led.decision(m["ticker"])["status"] == "model_error"
    assert led._conn.execute("SELECT count(*) FROM fills").fetchone()[0] == 0
    slow = FakeModel(p=0.7)
    h2, m2 = _harness(led, now, slow)
    m2 = dict(m2, ticker="KXBTC15M-LATE")
    h2.venue.m["ticker"] = "KXBTC15M-LATE"
    led.upsert_window(m2)
    clock = {"t": now}
    h2.clock = lambda: clock["t"]
    real = slow.decide

    def takes_too_long(features, experience):              # the answer lands inside the settlement average
        out = real(features, experience)
        clock["t"] = m2["close_ts"] - 60
        return out
    slow.decide = takes_too_long
    h2.decide(m2)
    assert led.decision("KXBTC15M-LATE")["status"] == "late"
    assert led._conn.execute("SELECT count(*) FROM fills").fetchone()[0] == 0


def test_without_a_model_the_window_is_still_recorded_for_the_dataset(led):
    now = 1_790_600_000.0
    h, m = _harness(led, now, None)
    h.decide(m)
    d = led.decision(m["ticker"])
    assert d["status"] == "no_model" and json.loads(d["features"])["baselines"]["market_p_up"] == 0.615


def test_stale_prices_record_the_window_and_ask_nothing(led):
    now = 1_790_600_000.0
    model = FakeModel()
    h, m = _harness(led, now, model)
    h.feed.quotes = {k: Quote(k, 1, 2, 1, now - 60) for k in ("a", "b")}
    h.decide(m)
    assert led.decision(m["ticker"])["status"] == "stale_data" and model.calls == 0


def test_settlement_comes_from_kalshis_result_and_writes_the_lesson(led):
    now = 1_790_600_000.0
    h, m = _harness(led, now, FakeModel(p=0.62))
    h.decide(m)
    h.venue.m.update(status="finalized", result="no", expiration_value=79990.0)
    h.settings.reflect = False
    h.settle_due(m["close_ts"] + 2)
    w = led._conn.execute("SELECT * FROM windows").fetchone()
    assert w["result"] == "no" and w["expiration_value"] == 79990.0
    a = led.account("paper")
    assert a["settled"] == 1 and a["realized_u"] == -(6200 + 200)
    h._lesson(dict(led._conn.execute(
        "SELECT d.ticker, d.p_up, d.side, d.confidence, d.rationale, d.features, d.status, w.result, "
        "w.expiration_value, w.strike FROM decisions d JOIN windows w ON w.ticker=d.ticker").fetchone()))
    assert led.decision(m["ticker"])["lesson"] == "lesson for no"


def test_predict_only_mode_records_the_call_and_places_nothing(led):
    now = 1_790_600_000.0
    h, m = _harness(led, now, FakeModel(p=0.8), broker=False)
    h.decide(m)
    assert led.decision(m["ticker"])["status"] == "predict_only"
    assert led._conn.execute("SELECT count(*) FROM fills").fetchone()[0] == 0


# ------------------------------------------------------------------ Polymarket US, the traded venue
# Payload shapes copied from the venue's own replies on 2026-09-28.
PM_META_OPEN = {
    "slug": "cpc-btc-updown-15m-2026-09-28-0015z", "status": "MARKET_STATUS_OPEN", "feeCoefficient": 0.0695,
    "outcomePrices": '["0","0"]',
    "assetPriceTerms": {"marketType": "ASSET_PRICE_MARKET_TYPE_UP_DOWN", "indexSymbol": "BRTI", "horizon": "15m",
                        "windowStart": "2026-09-28T00:15:00Z", "windowEnd": "2026-09-28T00:30:00Z",
                        "priceToBeat": {"value": "84414.77", "currency": "USD"}, "settlementPrice": None},
}
PM_BOOK = {"marketSlug": "cpc-btc-updown-15m-2026-09-28-0015z", "state": "MARKET_STATE_OPEN",
           "bids": [{"px": {"value": "0.9800", "currency": "USD"}, "qty": "956.1700"},
                    {"px": {"value": "0.9700", "currency": "USD"}, "qty": "5120.9900"}],
           "offers": [{"px": {"value": "0.9900", "currency": "USD"}, "qty": "533.0100"}],
           "stats": {"lastTradePx": {"value": "0.9800", "currency": "USD"}}}
PM_META_RESOLVED = {
    "slug": "cpc-btc-updown-15m-2026-09-27-2330z", "status": "MARKET_STATUS_RESOLVED", "feeCoefficient": 0.0695,
    "outcomePrices": '["0","1"]',
    "assetPriceTerms": {"windowStart": "2026-09-27T23:30:00Z", "windowEnd": "2026-09-27T23:45:00Z",
                        "priceToBeat": {"value": "84390.86", "currency": "USD"},
                        "settlementPrice": {"value": "84337.75", "currency": "USD"}},
}


def test_the_slug_names_the_window_start_in_utc_for_both_horizons():
    t = 1790554500.0 + 7 * 60                             # 2026-09-28 00:22Z
    assert slug_at(t) == "cpc-btc-updown-15m-2026-09-28-0015z"
    assert slug_at(t, "1h") == "cpc-btc-updown-1h-2026-09-28-0000z"
    with pytest.raises(ValueError):
        PolymarketBTC(horizon="5m")                        # the venue lists no 5-minute market


def test_an_open_market_normalizes_to_the_harness_shape():
    m = pm_normalize(PM_META_OPEN, PM_BOOK)
    assert m["status"] == "active" and m["strike"] == 84414.77
    assert (m["yes_bid_u"], m["yes_ask_u"], m["no_bid_u"], m["no_ask_u"]) == (9800, 9900, 100, 200)
    assert m["yes_bid_size"] == 956.17 and m["close_ts"] - m["open_ts"] == 900
    assert m["result"] is None, "an open market has no result, whatever outcomePrices says"


def test_a_resolved_market_reads_down_and_the_official_average():
    m = pm_normalize(PM_META_RESOLVED, None)
    assert m["status"] == "finalized" and m["result"] == "no" and m["expiration_value"] == 84337.75
    assert result_of('["1","0"]') == "yes" and result_of('["0","0"]') is None and result_of(None) is None


def test_the_polymarket_fee_is_the_markets_coefficient_rounded_up_to_the_cent():
    pm = PolymarketBTC()
    assert pm.fee_units(5000, {"fee_coefficient": 0.0695}) == 200   # 1.7375c -> 2c
    assert pm.fee_units(9800, {"fee_coefficient": 0.0695}) == 100   # 0.136c -> 1c
    assert pm.fee_units(5000, {"fee_coefficient": 0.06}) == 200     # 1.5c -> 2c
    with pytest.raises(ValueError):
        pm.fee_units(5000, {"ticker": "x"})


def test_the_reference_price_is_attached_only_for_the_same_window(led):
    now = 1_790_600_000.0
    model = FakeModel(p=0.6)
    h, m = _harness(led, now, model)

    class Ref:
        def __init__(self, r):
            self.r = r

        def current(self, t):
            return self.r
    h.reference = Ref({"open_ts": m["open_ts"], "close_ts": m["close_ts"], "yes_bid": 0.60, "yes_ask": 0.62, "strike": 80000.0})
    h.decide(m)
    f = json.loads(led.decision(m["ticker"])["features"])
    assert f["market"]["other_venue_p_up"] == 0.61 and f["market"]["other_venue_strike_usd"] == 80000.0
    m2 = dict(m, ticker="OTHER")
    h.venue.m["ticker"] = "OTHER"
    led.upsert_window(m2)
    h.reference = Ref({"open_ts": m["open_ts"] - 2700, "close_ts": m["close_ts"], "yes_bid": 0.1, "yes_ask": 0.2})
    h.decide(m2)
    assert json.loads(led.decision("OTHER")["features"])["market"]["other_venue_p_up"] is None, \
        "an hourly window that ends with a 15-minute one is a different contract"


def test_each_venue_owns_only_its_own_windows():
    assert PolymarketBTC().owns("cpc-btc-updown-15m-2026-09-28-0015z")
    assert not PolymarketBTC().owns("cpc-btc-updown-1h-2026-09-28-0000z")
    assert PolymarketBTC(horizon="1h").owns("cpc-btc-updown-1h-2026-09-28-0000z")
    from core.btc15.kalshi import KalshiBTC
    assert KalshiBTC().owns("KXBTC15M-26SEP272015-15") and not KalshiBTC().owns("cpc-btc-updown-15m-x")


def test_the_decision_waits_for_the_venues_book_and_records_a_window_that_never_gets_one(led, monkeypatch):
    now = 1_790_600_000.0
    model = FakeModel(p=0.6)
    h, m = _harness(led, now, model)
    started = []
    monkeypatch.setattr("core.btc15.harness.threading.Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: started.append(args)})())
    no_book = dict(m, yes_bid_u=None, yes_ask_u=None)
    h.market = no_book
    h.maybe_decide(m["open_ts"] + 60)                        # book not live yet: wait
    assert started == []
    h.maybe_decide(m["close_ts"] - 100)                      # still none inside the last 105 s: record it
    assert started and started[-1][1] is False
    h.decide(*started[-1])
    assert led.decision(m["ticker"])["status"] == "no_book" and model.calls == 0
    assert led._conn.execute("SELECT count(*) FROM fills").fetchone()[0] == 0
    h._inflight.clear()
    started.clear()
    h.market = dict(m, ticker="WITHBOOK")
    h.venue.m["ticker"] = "WITHBOOK"
    led.upsert_window(h.market)
    h.maybe_decide(m["open_ts"] + 45)                        # book live: decide now
    assert started and started[-1][1] is True
