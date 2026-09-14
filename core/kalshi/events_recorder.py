"""Kalshi's NON-SPORTS board: the recording loop.

    KALSHI_SERIES=KXITFWMATCH,KXRAIN python -m core.kalshi.events --once

We record ~0.1% of this venue (14,018 series / 107,599 open markets, survey
2026-09-14). `core.kalshi.recorder` polls nine sports series and CANNOT be
widened to the rest — the three structural reasons are stated once, on
`core.storage.models.KalshiEvent`, which is the table they are about. So: a
sibling recorder over sibling tables, keyed on the venue's own
`event_ticker`/`market_ticker`, driven by a series allowlist from env.

`with_nested_markets=true` returns a whole series WITH prices in one request
(the survey pulled all 11,697 events and 107,599 markets in 15s), so there is
no discovery/poll split: every cycle sweeps the allowlist and writes the
markets inside the window. Writes are change-detected — KXBTC15M reopens
every fifteen minutes forever. What a payload MEANS, and why the window hangs
off `min(close_time, expected_expiration_time)` rather than close_time, is in
`core.kalshi.events_shape`.
"""

from __future__ import annotations

import datetime as dt
import signal
import time
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.heartbeat import Heartbeat
from core.kalshi.client import KalshiPublicClient
from core.kalshi.events_shape import (
    _PRICE_KEYS,
    _TERMS_KEYS,
    KalshiEventsConfig,
    changed,
    in_window,
    leg_bounds,
    poll_anchor,
    price_row,
    terms_row,
    ticker_suffix,
)
from core.storage import KalshiEvent, KalshiEventSnapshot, get_engine, get_sessionmaker

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc
SERVICE_KALSHI_EVENTS = "kalshi_events_recorder"


class EventStats:
    """Per-cycle counters. Every one is printed, including the zeros."""

    def __init__(self) -> None:
        self.events = self.markets = self.in_window = self.past_anchor = 0
        self.snapshots = self.terms = self.books = self.errors = 0
        self.legs_checked = self.leg_breaks = self.fee_changes = 0
        self.worst_leg_dev: Decimal | None = None


class KalshiEventsRecorder:
    def __init__(self, config=None, client=None, sessionmaker=None) -> None:
        self.config = config or KalshiEventsConfig()
        self._client = client or KalshiPublicClient()
        self._Session = sessionmaker or get_sessionmaker(get_engine())
        self._heartbeat = Heartbeat(self._Session, SERVICE_KALSHI_EVENTS)
        #: ticker -> last row written. NOT seeded from the database on
        #: purpose: reading a fingerprint back out of a stored row is a second
        #: implementation of it, and the two silently disagreeing writes
        #: NOTHING when the terms did change. The cost of not seeding is one
        #: extra row per in-window market per process restart.
        self._prices: dict[str, dict] = {}
        self._terms: dict[str, dict] = {}
        #: series -> last observed fee regime, for the CHANGE log only; the
        #: value written to a row is always this cycle's own fetch.
        self._fees: dict[str, dict] = {}

    def sweep(self, series: str) -> list[dict[str, Any]]:
        return list(self._client.iter_events(series, status="open", with_nested_markets=True))

    def run_once(self, now: dt.datetime | None = None) -> EventStats:
        """One sweep of the allowlist. All rows share `now` — a cycle is an instant."""
        now = now or dt.datetime.now(UTC)
        stats = EventStats()
        for series in self.config.series:
            try:
                self._record_series(series, now, stats)
            except Exception as exc:   # noqa: BLE001 - one series must not lose the sweep
                stats.errors += 1
                log.error("kalshi_events_series_failed", series=series, error=str(exc)[:300])
        log.info("kalshi_events_cycle", captured_at=now.isoformat(), series=len(self.config.series),
                 events=stats.events, markets=stats.markets, in_window=stats.in_window,
                 past_anchor=stats.past_anchor, snapshots=stats.snapshots, terms=stats.terms,
                 books=stats.books, legs_checked=stats.legs_checked, leg_breaks=stats.leg_breaks,
                 worst_leg_dev=str(stats.worst_leg_dev), fee_changes=stats.fee_changes,
                 errors=stats.errors)
        return stats

    def _record_series(self, series: str, now: dt.datetime, stats: EventStats) -> None:
        events = self.sweep(series)
        nested = [m for e in events for m in e.get("markets") or []]
        observed = len(nested)
        # `status=open` filters EVENTS, not their nested MARKETS: KXRAIN's open
        # event carried 8 `closed` legs alongside 36 `active` ones on
        # 2026-09-14. Measured across 10 series that day, the nested `active`
        # set is EXACTLY `/markets?status=open` (10/10), so that is the
        # comparable side; the closed legs are counted, not silently folded in.
        active = sum(1 for m in nested if m.get("status") == "active")
        stats.events += len(events)
        stats.markets += observed
        fees = self._series_fees(series, stats)

        due: list[tuple[dict, dict]] = []
        for event in events:
            markets = event.get("markets") or []
            legs = []
            for market in markets:
                anchor = poll_anchor(market)
                if in_window(anchor, now, self.config):
                    legs.append(market)
                elif anchor is not None and anchor < now:
                    stats.past_anchor += 1
            due += [(event, m) for m in legs]
            # Only a COMPLETE ladder can be summed: a partial sum is a
            # guaranteed break, which would fire the gate on our window rather
            # than on the venue.
            if event.get("mutually_exclusive") and legs and len(legs) == len(markets):
                self._leg_gate(event, legs, stats)
        stats.in_window += len(due)

        books = self._fetch_books([m.get("ticker") for _, m in due], stats)
        with self._Session() as session:
            for event, market in due:
                self._write(session, event, market, now, books, fees, stats)
            session.commit()
        self._coverage(series, observed, active, len(events), len(due), stats)

    def _series_fees(self, series: str, stats: EventStats) -> dict[str, Any]:
        """This cycle's `{fee_type, fee_multiplier}`, and a LOUD line on change."""
        try:
            meta = self._client.get_series(series)
        except Exception as exc:   # noqa: BLE001 - prices still land; the fee reads NULL
            stats.errors += 1
            log.error("kalshi_events_fee_unavailable", series=series, error=str(exc)[:200])
            return {}
        fees = {"fee_type": meta.get("fee_type"), "fee_multiplier": meta.get("fee_multiplier")}
        if self._fees.get(series) not in (None, fees):
            stats.fee_changes += 1
            log.error("kalshi_events_fee_changed", series=series,
                      was=self._fees.get(series), now=fees)
        self._fees[series] = fees
        return fees

    def _leg_gate(self, event: dict, legs: list[dict], stats: EventStats) -> None:
        """A mutually exclusive event's legs settle to 1 between them, so
        `bid_sum <= 1 <= ask_sum`. Breaking that is a venue error or free
        money; the mid sum is reported as a number, never tripped on (see
        `leg_bounds` for the board that settled which rule)."""
        bounds = leg_bounds(legs)
        if bounds is None:
            return
        bid_sum, ask_sum, mid_sum, tick = bounds
        stats.legs_checked += 1
        deviation = abs(mid_sum - 1)
        if stats.worst_leg_dev is None or deviation > stats.worst_leg_dev:
            stats.worst_leg_dev = deviation
        sell_arb, buy_arb = bid_sum > 1 + tick, ask_sum < 1 - tick
        if sell_arb or buy_arb:
            stats.leg_breaks += 1
            log.error("kalshi_events_leg_sum_break", event_ticker=event.get("event_ticker"),
                      legs=len(legs), bid_sum=str(bid_sum), ask_sum=str(ask_sum),
                      mid_sum=str(mid_sum), tick=str(tick),
                      side="sell_all" if sell_arb else "buy_all",
                      suffixes=[ticker_suffix(m.get("ticker"), event.get("event_ticker"))
                                for m in legs])

    def _fetch_books(self, tickers: list[str], stats: EventStats) -> dict[str, Any]:
        if not self.config.depth:
            return {}
        books: dict[str, Any] = {}
        live = [t for t in tickers if t]
        for i in range(0, len(live), 100):
            try:
                books.update(self._client.get_orderbooks(live[i:i + 100]))
            except Exception as exc:   # noqa: BLE001 - depth is additive; prices still land
                stats.errors += 1
                log.error("kalshi_events_orderbooks_failed", error=str(exc)[:200])
        stats.books += len(books)
        return books

    def _write(self, session, event: dict, market: dict, now: dt.datetime,
               books: dict[str, Any], fees: dict[str, Any], stats: EventStats) -> None:
        ticker = str(market.get("ticker") or "")
        if not ticker:
            return
        terms = terms_row(event, market, now)
        if changed(self._terms.get(ticker), terms, _TERMS_KEYS):
            session.execute(pg_insert(KalshiEvent).values(**terms)
                            .on_conflict_do_nothing(constraint="uq_kalshi_event_market_time"))
            self._terms[ticker] = terms
            stats.terms += 1
        prices = price_row(event, market, now, raw=self.config.snapshot_raw, fees=fees)
        if changed(self._prices.get(ticker), prices, _PRICE_KEYS):
            prices["book"] = books.get(ticker)
            session.execute(
                pg_insert(KalshiEventSnapshot).values(**prices)
                .on_conflict_do_nothing(constraint="uq_kalshi_event_snapshot_market_time"))
            self._prices[ticker] = prices
            stats.snapshots += 1

    def _coverage(self, series: str, observed: int, active: int, events: int, due: int,
                  stats: EventStats) -> None:
        """Expected-vs-observed, same shape as `core.recorder`'s board_coverage.

        `expected` comes from `/markets`, a DIFFERENT endpoint with its own
        pagination, so a nested-events cursor that ends early reads as a
        shortfall rather than as a small series. It is compared against
        `active`, not `observed`, because the two endpoints count different
        populations otherwise — see `_record_series`; comparing them raw made
        every weather cycle read as a disagreement, and a check that is red on
        a healthy board is a check nobody reads. The booleans are only the
        ones that cannot be anything but a defect; the rest are numbers.
        """
        expected = None
        if self.config.coverage:
            try:
                expected = self._client.count_series_markets(series)
            except Exception as exc:   # noqa: BLE001 - a check that kills the sweep is worse
                stats.errors += 1
                log.info("kalshi_events_coverage_unavailable", series=series, error=str(exc)[:200])
        log.info("kalshi_events_coverage", series=series, expected=expected, observed=observed,
                 active=active, closed=observed - active,
                 shortfall=(expected - active if expected is not None else None),
                 events=events, in_window=due,
                 # In the allowlist, nothing under it at the venue: a ticker
                 # typo, or a series gone dark.
                 swept_nothing=(observed == 0),
                 # Two endpoints disagree about the same population.
                 endpoints_disagree=(expected is not None and expected != active),
                 # Markets exist and NONE is in the window. Fine on a quiet
                 # day; permanent means the window is wrong.
                 none_in_window=(observed > 0 and due == 0))

    def run_forever(self) -> None:
        stopping = {"flag": False}

        def _handle(signum, _frame):
            log.info("shutdown_signal", signal=signum)
            stopping["flag"] = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)
        log.info("kalshi_events_recorder_started", series=list(self.config.series),
                 window_hours=self.config.window_hours, depth=self.config.depth)
        while not stopping["flag"]:
            started = time.monotonic()
            stats = EventStats()
            try:
                stats = self.run_once()
            except Exception as exc:   # nothing kills the loop
                log.exception("kalshi_events_cycle_failed", error=str(exc)[:300])
            self._heartbeat.beat(interval_seconds=self.config.interval_seconds,
                                 rows_written=stats.snapshots,
                                 cycle_seconds=time.monotonic() - started,
                                 game_live=bool(stats.in_window))
            waited = 0.0
            while waited < self.config.interval_seconds and not stopping["flag"]:
                step = min(5.0, self.config.interval_seconds - waited)
                time.sleep(step)
                waited += step
        log.info("kalshi_events_recorder_stopped")
