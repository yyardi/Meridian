"""The BTC15 loop: poll once a second, decide once per window, fill, settle, reflect.

The traded venue is Polymarket US ("BTC Up or Down", 15-minute by default,
MERIDIAN_BTC15_HORIZON=1h for the hourly market), the operator's account;
Kalshi's KXBTC15M settles on the same BRTI averages and is read as a reference
(its same-window price becomes a feature). MERIDIAN_BTC15_VENUE=kalshi trades
the Kalshi market instead.

    python -m core.btc15.harness                 # run forever (the service)
    python -m core.btc15.harness --check-openai  # list the models the key can use
    python -m core.btc15.harness --new-epoch paper   # operator: a fresh $10 allocation

One window, start to finish:

1. The venue opens the window at :00/:15/:30/:45 (or on the hour) with its strike set.
2. At open + DECIDE_AT_S (default 30 s) the harness builds the feature set from
   data at or before that instant and records it. If the price feed is stale
   (older than 5 s, or fewer than two exchanges) the window is recorded as
   ``stale_data`` and nothing is asked.
3. The model returns p_up; side = YES if p_up >= 0.5 else NO.
4. If the answer arrived with at least MIN_LEAD_S (default 90 s) left, the
   harness reads Kalshi's ask for that side NOW and buys one contract through
   the broker -- which checks the $10 drawdown guard and writes the fill in one
   locked step. A cost (price + fee) above $1.00 is refused.
5. After close the venue resolves the market. The harness records the result,
   its own 60-second proxy average beside the official settlement average,
   settles the fill, and asks the model for a one-line lesson.

Every step writes a row before it acts; a restart re-reads the ledger and never
decides or fills a window twice. Any exception in a step is logged and the
loop continues -- a bad second never takes the service down.

MODE: ``paper`` (default) fills at the displayed ask in the ledger. ``live``
is refused until the Kalshi order adapter exists; the service then records
features and predictions and places nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal

from core.btc15 import features as F
from core.btc15.kalshi import KalshiBTC
from core.btc15.ledger import DEFAULT_LIMIT_U, UNIT, Ledger
from core.btc15.polymarket import PolymarketBTC
from core.btc15.model import ModelConfig, ModelError, OpenAIModel, side_of
from core.btc15.prices import PriceFeed

log = logging.getLogger("btc15")


@dataclass
class Settings:
    db_path: str = "/data/btc15.sqlite"
    mode: str = "paper"
    decide_at_s: float = 30.0
    min_lead_s: float = 90.0
    limit_u: int = DEFAULT_LIMIT_U
    reflect: bool = True
    max_data_age_s: float = 5.0
    min_exchanges: int = 2
    status_path: str = "/data/status.json"
    venue: str = "polymarket"
    horizon: str = "15m"

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(
            db_path=e("MERIDIAN_BTC15_DB") or "/data/btc15.sqlite",
            mode=(e("MERIDIAN_BTC15_MODE") or "paper").lower(),
            decide_at_s=float(e("MERIDIAN_BTC15_DECIDE_AT_S") or 30),
            min_lead_s=float(e("MERIDIAN_BTC15_MIN_LEAD_S") or 90),
            limit_u=int(Decimal(e("MERIDIAN_BTC15_DRAWDOWN_USD") or "10") * UNIT),
            reflect=(e("MERIDIAN_BTC15_REFLECT") or "1") != "0",
            status_path=e("MERIDIAN_BTC15_STATUS") or "/data/status.json",
            venue=(e("MERIDIAN_BTC15_VENUE") or "polymarket").lower(),
            horizon=(e("MERIDIAN_BTC15_HORIZON") or "15m").lower(),
        )


class PaperBroker:
    """Fills at the displayed ask, in the ledger, behind the drawdown guard."""
    mode = "paper"

    def buy(self, ledger: Ledger, ticker: str, side: str, price_u: int, fee_u: int, limit_u: int,
            book: dict) -> tuple[int | None, str]:
        return ledger.record_fill("paper", ticker, side, price_u, fee_u, limit_u, book=book)


@dataclass
class Harness:
    settings: Settings
    ledger: Ledger
    feed: PriceFeed
    venue: object                      # PolymarketBTC or KalshiBTC: current / market / outcome / fee_units
    model: OpenAIModel | None
    broker: PaperBroker | None
    reference: object | None = None    # the other venue, read for its same-window price only
    clock: object = time.time
    market: dict | None = None
    _inflight: set = field(default_factory=set)
    _reflected: set = field(default_factory=set)
    _next: dict = field(default_factory=lambda: {"market": 0.0, "settle": 0.0, "status": 0.0, "flush": 0.0})
    _ticks: list = field(default_factory=list)
    _last_summary_day: str | None = None
    _pushed_halt: bool = False

    # ------------------------------------------------------------------ the second
    def step(self, now: float, px: float | None, n: int, disp: float) -> None:
        if px is not None:
            self._ticks.append((round(now, 3), px, n, disp))
        if now >= self._next["flush"]:
            self.ledger.add_ticks(self._ticks)
            self._ticks = []
            self._next["flush"] = now + 10
        if now >= self._next["market"]:
            self._refresh_market(now)
        self.maybe_decide(now)
        if now >= self._next["settle"]:
            self.settle_due(now)
            self._next["settle"] = now + 5
        if now >= self._next["status"]:
            self._status(now, px, n)
            self._next["status"] = now + 60

    def _refresh_market(self, now: float) -> None:
        try:
            m = self.venue.current(now)
        except Exception as e:                                   # noqa: BLE001
            log.warning("%s current market: %s", self.venue.venue, e)
            self._next["market"] = now + 5
            return
        self.market = m
        if m:
            self.ledger.upsert_window(m)
            if now >= m["open_ts"] + 1:
                self.ledger.set_proxy_open(m["ticker"], self.feed.average(m["open_ts"] - 60, m["open_ts"]))
        self._next["market"] = now + 10

    # ------------------------------------------------------------------ decide
    def maybe_decide(self, now: float) -> None:
        """Decide at the first second after open + DECIDE_AT_S at which the venue's
        book is live. Measured 2026-09-28: Polymarket US answers 404 on a
        15-minute window's book for a while after the window opens although the
        market is OPEN, and a decision without the book has no ask to fill at
        and no market price to read. A window whose book never appears before
        the last MIN_LEAD_S is recorded as ``no_book`` with its features."""
        m = self.market
        if not m or m.get("strike") is None:
            return
        if not (m["open_ts"] + self.settings.decide_at_s <= now < m["close_ts"] - self.settings.min_lead_s):
            return
        if m["ticker"] in self._inflight or self.ledger.decision(m["ticker"]) is not None:
            return
        has_book = m.get("yes_bid_u") is not None or m.get("yes_ask_u") is not None
        if not has_book and now < m["close_ts"] - self.settings.min_lead_s - 15:
            self._next["market"] = min(self._next["market"], now + 3)     # look again soon
            return
        self._inflight.add(m["ticker"])
        threading.Thread(target=self._decide_safely, args=(dict(m), has_book), daemon=True).start()

    def _decide_safely(self, m: dict, has_book: bool = True) -> None:
        try:
            self.decide(m, has_book)
        except Exception as e:                                   # noqa: BLE001
            log.exception("decide %s", m["ticker"])
            self.ledger.finish_decision(m["ticker"], status="harness_error", error=repr(e)[:500])
        finally:
            self._inflight.discard(m["ticker"])

    def decide(self, m: dict, has_book: bool = True) -> None:
        now = self.clock()
        secs = self.feed.seconds()
        m = dict(m)
        if self.reference is not None:
            try:
                r = self.reference.current(now)
                same = r and r.get("open_ts") == m["open_ts"] and r.get("close_ts") == m["close_ts"]
                if same and r.get("yes_bid") is not None and r.get("yes_ask") is not None:
                    m["reference_p_up"] = round((r["yes_bid"] + r["yes_ask"]) / 2, 4)
                    m["reference_strike"] = r.get("strike")
            except Exception as e:                               # noqa: BLE001 -- a reference is a feature, never a gate
                log.warning("reference read: %s", e)
        feats = F.build(now=now, secs=secs, c1m=self.feed.c1m, c5m=self.feed.c5m, c1h=self.feed.c1h,
                        market=m, quotes=self.feed.quotes, funding=self.feed.funding,
                        recent_results=self.ledger.recent_results(12))
        model_name = self.model.cfg.model if self.model else None
        if not self.ledger.start_decision(m["ticker"], model_name, feats):
            return
        if not has_book:
            self.ledger.finish_decision(m["ticker"], status="no_book",
                                        error="the venue's book was not live before the last decision second")
            return
        fresh = [q for q in self.feed.quotes.values() if now - q.t <= self.settings.max_data_age_s]
        if not secs or now - secs[-1][0] > self.settings.max_data_age_s or len(fresh) < self.settings.min_exchanges:
            self.ledger.finish_decision(m["ticker"], status="stale_data",
                                        error=f"{len(fresh)} fresh exchanges; last composite "
                                              f"{(now - secs[-1][0]) if secs else None} s old")
            return
        if not self.model or not self.model.cfg.ready:
            self.ledger.finish_decision(m["ticker"], status="no_model",
                                        error="set OPENAI_API_KEY and MERIDIAN_BTC15_MODEL to decide")
            return
        try:
            out, usage, took = self.model.decide(feats, self.ledger.experience(self.settings.mode))
        except ModelError as e:
            self.ledger.finish_decision(m["ticker"], status="model_error", error=str(e)[:800],
                                        answered_at=_iso(self.clock()))
            return
        side = side_of(out["p_up"])
        answered = self.clock()
        self.ledger.finish_decision(m["ticker"], answered_at=_iso(answered), response=json.dumps(out),
                                    p_up=out["p_up"], side=side, confidence=out["confidence"],
                                    rationale=out["rationale"], latency_s=round(took, 3),
                                    usage=json.dumps(usage), status="answered")
        self.trade(m, side, answered)

    # ------------------------------------------------------------------ trade
    def trade(self, m: dict, side: str, answered: float) -> None:
        t = m["ticker"]
        if self.broker is None:
            self.ledger.finish_decision(t, status="predict_only")
            return
        if answered >= m["close_ts"] - self.settings.min_lead_s:
            self.ledger.finish_decision(t, status="late")
            return
        live = self.venue.market(t)
        if live.get("status") != "active":
            self.ledger.finish_decision(t, status=f"market_{live.get('status')}")
            return
        ask_u = live["yes_ask_u"] if side == "YES" else live["no_ask_u"]
        if not ask_u or not (0 < ask_u < UNIT):
            self.ledger.finish_decision(t, status="no_ask")
            return
        try:
            fee_u = self.venue.fee_units(ask_u, live)
        except Exception as e:                                   # noqa: BLE001
            self.ledger.finish_decision(t, status="no_fee_schedule", error=str(e)[:300])
            return
        if ask_u + fee_u > UNIT:
            self.ledger.finish_decision(t, status="cost_over_one_dollar")
            return
        book = {k: live.get(k) for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u", "yes_bid_size", "yes_ask_size")}
        fill_id, why = self.broker.buy(self.ledger, t, side, ask_u, fee_u, self.settings.limit_u, book)
        self.ledger.finish_decision(t, status="filled" if fill_id else f"not_filled: {why}")
        if fill_id is None and why.startswith("latched") and not self._pushed_halt:
            self._pushed_halt = True
            _push("BTC15 halted", f"{self.settings.mode}: $10 drawdown limit reached; trading stopped, predictions continue.")

    # ------------------------------------------------------------------ settle
    def settle_due(self, now: float) -> None:
        for w in self.ledger.unfinalized_windows(now):
            if not self.venue.owns(w["ticker"]):
                continue                                         # another venue's window in a shared file
            try:
                o = self.venue.outcome(w["ticker"])
            except Exception as e:                               # noqa: BLE001
                log.warning("settle read %s: %s", w["ticker"], e)
                continue
            if not o["final"]:
                continue
            proxy = self.feed.average(w["close_ts"] - 60, w["close_ts"])
            self.ledger.finalize_window(w["ticker"], o["result"], o.get("expiration_value"), proxy)
        results = {r["ticker"]: r["result"] for r in self.ledger._conn.execute(
            "SELECT ticker, result FROM windows WHERE result IS NOT NULL").fetchall()}
        for f in self.ledger.unsettled_fills():
            if f["ticker"] in results:
                self.ledger.settle(f["id"], results[f["ticker"]])
        if self.settings.reflect and self.model and self.model.cfg.ready:
            self._reflect()

    def _reflect(self) -> None:
        rows = self.ledger._conn.execute(
            "SELECT d.ticker, d.p_up, d.side, d.confidence, d.rationale, d.features, d.status, w.result, "
            "w.expiration_value, w.strike FROM decisions d JOIN windows w ON w.ticker=d.ticker "
            "WHERE d.p_up IS NOT NULL AND d.lesson IS NULL AND w.result IN ('yes','no') "
            "ORDER BY w.close_ts DESC LIMIT 3").fetchall()
        for r in rows:
            if r["ticker"] in self._reflected:
                continue
            self._reflected.add(r["ticker"])
            threading.Thread(target=self._lesson, args=(dict(r),), daemon=True).start()

    def _lesson(self, r: dict) -> None:
        feats = json.loads(r["features"] or "{}")
        decision = {"p_up": r["p_up"], "side": r["side"], "confidence": r["confidence"], "rationale": r["rationale"],
                    "features_at_decision": feats}
        outcome = {"result": r["result"], "strike": r["strike"], "closing_average": r["expiration_value"],
                   "you_were": "right" if (r["p_up"] >= 0.5) == (r["result"] == "yes") else "wrong"}
        try:
            self.ledger.finish_decision(r["ticker"], lesson=self.model.lesson(decision, outcome))
        except Exception as e:                                   # noqa: BLE001
            log.warning("lesson %s: %s", r["ticker"], e)

    # ------------------------------------------------------------------ status
    def _status(self, now: float, px: float | None, n: int) -> None:
        a = self.ledger.account(self.settings.mode)
        s = {"at": _iso(now), "btc_usd": px, "exchanges": n, "window": (self.market or {}).get("ticker"),
             "venue": self.venue.venue, "mode": self.settings.mode, "model": self.model.cfg.model if self.model else None,
             "model_ready": bool(self.model and self.model.cfg.ready),
             "account": {k: (v / UNIT if k.endswith("_u") else v) for k, v in a.items()},
             "halted": self.ledger.halted(self.settings.mode), "feed_errors": dict(self.feed.errors)}
        try:
            with open(self.settings.status_path, "w") as fh:
                json.dump(s, fh, indent=1)
        except OSError:
            pass
        log.info("status %s", json.dumps(s))
        day = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y-%m-%d")
        if dt.datetime.fromtimestamp(now, dt.timezone.utc).hour == 12 and self._last_summary_day != day:
            self._last_summary_day = day
            _push("BTC15 daily", _summary(self.ledger, self.settings.mode))


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _summary(ledger: Ledger, mode: str) -> str:
    ex = ledger.experience(mode, n=0, n_lessons=0)["your_record"]
    a = ledger.account(mode)
    return (f"{mode}: {a['settled']} settled, {a['wins']} won, P&L ${a['realized_u'] / UNIT:+.2f}, "
            f"drawdown ${a['drawdown_u'] / UNIT:.2f}/$10. Brier you {ex['brier_you']} vs market {ex['brier_market_mid']} "
            f"over {ex['windows_scored']} windows.")


def _push(title: str, body: str) -> None:
    try:
        from core import notify
        notify.push("schedule", title, body[:450], tags="chart_with_upwards_trend", timeout=10)
    except Exception:                                            # noqa: BLE001
        pass


def build(settings: Settings) -> Harness:
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    ledger = Ledger(settings.db_path)
    cfg = ModelConfig.from_env()
    model = OpenAIModel(cfg) if cfg.ready else None
    if settings.mode == "paper":
        broker: PaperBroker | None = PaperBroker()
    else:
        log.error("MERIDIAN_BTC15_MODE=%s: live execution is not built yet; recording and predicting only, "
                  "nothing will be placed", settings.mode)
        broker = None
    if settings.venue == "polymarket":
        # Kalshi lists only the 15-minute contract; the hourly one has no reference.
        venue = PolymarketBTC(horizon=settings.horizon)
        reference = KalshiBTC() if settings.horizon == "15m" else None
    elif settings.venue == "kalshi":
        if settings.horizon != "15m":
            raise SystemExit("Kalshi's KXBTC15M is 15-minute only")
        venue, reference = KalshiBTC(), None
    else:
        raise SystemExit(f"MERIDIAN_BTC15_VENUE={settings.venue!r}: polymarket or kalshi")
    return Harness(settings, ledger, PriceFeed(), venue, model, broker, reference=reference)


def run(h: Harness) -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)       # four GETs a second is not news
    log.info("btc15 up: venue=%s mode=%s model=%s db=%s", h.venue.venue, h.settings.mode,
             h.model.cfg.model if h.model else None, h.settings.db_path)
    while True:
        t0 = time.time()
        try:
            now, px, n, disp = h.feed.tick()
            h.feed.refresh(now)
            h.step(now, px, n, disp)
        except Exception:                                        # noqa: BLE001
            log.exception("step")
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-openai", action="store_true")
    ap.add_argument("--new-epoch", choices=("paper", "live"))
    a = ap.parse_args(argv)
    settings = Settings.from_env()
    if a.check_openai:
        cfg = ModelConfig.from_env()
        if not cfg.api_key:
            print("OPENAI_API_KEY is not set")
            return 1
        print("\n".join(OpenAIModel(cfg).list_models()))
        print(f"\nconfigured MERIDIAN_BTC15_MODEL={cfg.model!r}")
        return 0
    if a.new_epoch:
        led = Ledger(settings.db_path)
        print(f"{a.new_epoch} epoch -> {led.new_epoch(a.new_epoch)}")
        return 0
    run(build(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
