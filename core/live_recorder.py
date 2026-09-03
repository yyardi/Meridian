"""High-cadence recorder for games in progress.

Why this is separate from the main recorder
-------------------------------------------
The main recorder runs an adaptive 15/60-minute cadence, which is right for
pregame: lines drift slowly and hourly sampling loses nothing. It is useless
for anything happening *inside* a game. A WNBA game is 40 minutes of clock and
roughly two hours of wall time, so at 15-minute spacing we capture perhaps
eight frames of it — and the measured in-game price travel is ~37 cents
peak-to-trough. We are photographing a hummingbird with a one-hour exposure.

Both of the unbuilt strategies depend on closing that gap:

* **In-game directional trading** needs to know whether prices *overreact* to
  scoring runs and then revert. A run lasts a couple of minutes; at 15-minute
  sampling the overreaction and the reversion land in the same frame, and the
  question is unanswerable by construction.
* **Market making** needs the spread and the quote lifetime, both of which are
  second-scale quantities.

**It records. It does not trade, predict, or decide anything.** The hypotheses
it exists to serve are unmeasured, and building a strategy before the
measurement is the mistake this project keeps not making.

Unrecoverable, like everything else on the market side: a game that finishes
unsampled is gone.


How it reaches one second
-------------------------
The first version of this file reused `Recorder.run_once`, which re-polls the
entire 131-market board and issues one order-book call per market. That costs
~132 requests and took 26-34 seconds a cycle, so the effective cadence was ~35s
and no amount of tuning inside that shape would have reached 1s: at the
documented 20 req/s ceiling, 132 requests *cannot* fit in a second.

The fix came from measuring the gateway rather than optimising the loop.
Three findings, all verified live on 2026-08-02:

1. **There is no push feed.** Websocket upgrades to `/ws`, `/v1/ws`, `/v2/ws`,
   `/websocket`, `/stream` and `/` all return 404, and every path returns
   `application/json` under `Accept: text/event-stream`. There is no SSE and no
   socket.io. Polling is the only option, so it has to be a *cheap* poll.
   (Re-check occasionally; a feed appearing would make this module obsolete,
   which would be good news.)

2. **The board call already carries top-of-book for every market.** Each market
   in `/v2/leagues/{league}/events` embeds `bestBidQuote` / `bestAskQuote`.
   Top-of-book for all 131 markets therefore costs **one request**, not 131.
   The 131 book calls were only ever buying *depth*.

3. **The board genuinely moves at 1s.** Polling it once a second for 45s during
   a live game, 43 of 44 consecutive frame-pairs differed and the live board
   took 44 distinct states in 45 seconds. The data is not cached upstream, so a
   1s poll is resolving real changes rather than re-reading the same payload.
   Median board latency was 194ms (p90 333ms), which leaves ample room.

So the cadence problem was never really a rate-limit problem — it was spending
131 requests on depth we mostly do not need. The loop now separates the two:

* **Price, every 200ms, one request.** One board call; top-of-book written for
  every market in a live game.
* **Depth, on a background thread.** Order-book calls only for the rungs
  nearest the money, concurrently, through the same token bucket. The deep
  rungs carry 22-26c spreads and do not trade, so they get a slow secondary
  loop instead of the request budget.

The depth sampler runs in its own thread precisely so it can never delay the
price loop: 36 book calls at 11 req/s is ~3.3s, which would blow the budget
many times over if it ran inline.

Why 200ms and not 1s (measured 2026-08-02)
------------------------------------------
Capture the live board at 200ms for three minutes, then subsample that one
capture to every candidate interval and count how many quote changes you
*detect per second*:

    interval   changes/sec   vs peak
      200ms       5.22         90%
      300ms       5.80        100%
      500ms       4.79         83%
        1s        3.47         60%
        2s        2.65         46%
        5s        1.80         31%

The rate saturates around 200-300ms and falls away above it. **A 1s loop was
seeing about 60% of the changes it could**; the rest superposed or reversed
inside a frame and were lost. Below 200ms nothing further is detected.

Beware the obvious statistic. "Fraction of consecutive frames that differ"
*rises* monotonically with the interval — 57% at 200ms, 91% at 1s, 100% at 5s —
because a longer gap has more chances to contain a change. It measures the
sampling interval, not the market, and cannot be used to choose a poll rate.
It also swings hard with game state: two windows on the same game gave 31% and
57% at the same 200ms. Changes-per-second is the scale-free version.

Budget, with a full four-game slate::

    price   1 board call / 200ms      = 5.0 req/s
    near    4 games x 9 rungs / 10s   = 3.6 req/s
    deep    4 games x 9 rungs / 120s  = 0.3 req/s
                                 total  8.9 req/s   (allowance: 12)

Note the near-depth cadence widened from 5s to 10s to pay for this; at the old
5s it would have been 12.5 req/s, over the allowance. Depth yields because its
own horizons are 30s and 60s, so 10s sampling costs it nothing measurable,
whereas price resolution was measured to matter at 200ms. `MERIDIAN_RPS` was
not raised.

What is deliberately *not* sampled at 200ms
-------------------------------------------
Deep rungs get a price snapshot every `deep_snapshot_seconds` (default 30s —
the cadence this recorder had before), not every cycle. They are the rungs
priced at 0.95/0.05 that do not trade, and writing 131 rows every 200ms to
capture a price that moves twice an hour is a storage bill, not a dataset.

Every row records `book_tier`, so that sparsity is auditable: a later analysis
can tell "no resting size" from "we did not look", which are otherwise the same
absence.

    python -m core.live_recorder                 # run until stopped
    python -m core.live_recorder --interval 0.2
    python -m core.live_recorder --once          # one cycle, then exit
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import queue
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import RECORDER, RecorderConfig
from core.heartbeat import SERVICE_LIVE, Heartbeat
from core.polymarket.client import PolymarketGatewayClient
from core.polymarket.schemas import Event, EventsResponse, Market
from core.recorder import _parse_ts
from core.storage import (BookLevel, MarketSnapshot, MarketTradeStat,
                          get_engine, get_sessionmaker)

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: 200ms, measured rather than chosen. Subsampling a 200ms capture of a live
#: board to every candidate interval, the number of quote changes *detected per
#: second* peaks at 5.8/s around 200-300ms and falls away above it — 3.5/s at
#: 1s, 1.8/s at 5s. A 1s loop was therefore seeing about 60% of the changes it
#: could. Below ~200ms nothing more is detected, and the loop cannot go there
#: anyway: see `_sleep_remaining`.
#:
#: Note the statistic. "Fraction of consecutive frames that differ" *rises*
#: with the interval by construction — a longer gap has more chances to contain
#: a change — so it cannot be used to pick a poll rate. It also swings hard with
#: game state: two windows on the same game measured 31% and 57% at 200ms.
#: Changes detected per second is the scale-free version and is what this
#: constant is set from.
DEFAULT_INTERVAL_SECONDS = 0.2

#: Floor on `--interval`. Not a rate-limit guard (the loop self-paces); purely
#: to stop a typo turning into a hot loop against the gateway.
MIN_INTERVAL_SECONDS = 0.1

#: Start early: the minutes either side of tip-off are when the pregame book
#: hands over to the live one, and that transition is itself worth having.
PRE_TIPOFF_MINUTES = 10.0

#: How long to keep polling after the last live market disappears, so the final
#: settlement-adjacent prices are captured rather than truncated.
GRACE_MINUTES = 5.0

#: When nothing is live, check back this often to see whether a game started.
IDLE_POLL_SECONDS = 120.0

#: How often the *plan* (which rungs count as near the money) is recomputed.
#: The board is fetched every cycle regardless — it is the price source — but
#: re-deriving the rung ranking every second is wasted CPU for a set that
#: changes on the timescale of the score, not the tick.
PLAN_REFRESH_SECONDS = 30.0

#: Rungs per (event, market type) that count as "near the money". Four is the
#: pre-existing judgement from the handoff brief: beyond that the spreads run
#: 22-26c and the rungs do not trade, so depth there buys nothing.
NEAR_MONEY_RUNGS = 4

#: Depth cadence for near-the-money rungs.
#:
#: Widened 5s -> 10s when the price loop went to 200ms, because the price loop's
#: share of the budget went 1 -> 5 req/s and 5 + 7.2 + 0.3 would have been 12.5
#: against a 12 req/s allowance. Depth is what yields, and it yields cheaply:
#: `core.quote.depth_signal` marks whale appearances at +30s and +60s, so 10s
#: sampling is still several observations inside its shortest horizon, whereas
#: price resolution was measured to matter at 200ms. Yielding the *measured*
#: requirement to protect the unmeasured one would have been the wrong way
#: round.
DEPTH_NEAR_SECONDS = 10.0

#: Depth cadence for everything else in a live game. Sparse on purpose.
DEPTH_DEEP_SECONDS = 120.0

#: Price cadence for rungs that are not near the money. They still get sampled
#: — just at the cadence this recorder used to run at, rather than every cycle.
DEEP_SNAPSHOT_SECONDS = 30.0

#: How often the full `raw` payload is retained for a given market.
#:
#: Measured: a snapshot row is 2,576 bytes, of which the `raw` JSONB is **1,599
#: — 62%**. At 200ms that is five near-identical copies a second of a blob whose
#: only moving fields (best bid/ask, score, period) are already stored in typed,
#: indexed columns. One live game was writing ~0.5 GB.
#:
#: The recorder's standing rule is "keep the raw payload; parsing can be fixed
#: later, unrecorded data cannot". That rule is about **schema drift** — being
#: able to reparse if the venue changes a field — and it is fully served by a
#: sample every 30s. It was never a claim that the same payload is worth storing
#: three hundred times a minute. Prices are not lost: they are in the typed
#: columns, at full 200ms resolution.
RAW_SNAPSHOT_SECONDS = 30.0

#: Concurrent order-book calls. The token bucket, not this, is what bounds the
#: request rate; this only bounds how many sockets are open at once.
DEPTH_CONCURRENCY = 8

TIER_NEAR = "near"
TIER_DEEP = "deep"


# --------------------------------------------------------------------- #
# Rung selection — pure functions, so the policy is testable without a
# network or a database
# --------------------------------------------------------------------- #


def _mid(market: Market) -> float | None:
    """Mid price, or the one side that exists, or None."""
    bid, ask = market.best_bid, market.best_ask
    if bid is not None and ask is not None:
        return (float(bid) + float(ask)) / 2.0
    if bid is not None:
        return float(bid)
    if ask is not None:
        return float(ask)
    return None


def moneyness(market: Market) -> float:
    """Distance from the money. 0.0 is a coin flip, 0.5 is a certainty.

    A rung priced near 0.50 is where the disagreement — and therefore the
    trading — is. A rung at 0.97 is a rung nobody argues about, and the
    measured 22-26c spreads out there say so. Markets with no quote at all
    sort last rather than crashing the ranking.
    """
    mid = _mid(market)
    if mid is None:
        return float("inf")
    return abs(mid - 0.5)


def select_near_money(
    markets: list[Market], *, per_type: int = NEAR_MONEY_RUNGS
) -> set[str]:
    """The `per_type` rungs closest to the money, per market type.

    Ranked independently within each `sports_market_type` because the ladders
    are different instruments: a totals ladder and a spread ladder each have
    their own at-the-money region, and ranking them together would let a
    tightly-priced spread ladder crowd out every totals rung.

    Moneyline is a single market rather than a ladder, so it is always
    included — it was also the most active market on the board when measured
    (29 changes in 45 seconds, more than any ladder rung).
    """
    by_type: dict[str, list[Market]] = {}
    for market in markets:
        key = market.sports_market_type or "unknown"
        by_type.setdefault(key, []).append(market)

    chosen: set[str] = set()
    for key, group in by_type.items():
        if len(group) <= per_type:
            # Not a ladder (moneyline), or a ladder short enough that ranking
            # it would exclude nothing. Take all of it.
            chosen.update(m.slug for m in group)
            continue
        ranked = sorted(group, key=moneyness)
        chosen.update(m.slug for m in ranked[:per_type])
    return chosen


def _start_time(value: str | None) -> dt.datetime | None:
    """Tip-off as an aware UTC datetime.

    The gateway is consistent about offsets today, but a naive timestamp
    compared against an aware `now` raises rather than misbehaving quietly, and
    this comparison decides whether we record a game at all.
    """
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def live_events(
    response: EventsResponse, *, now: dt.datetime, pre_tipoff_minutes: float = PRE_TIPOFF_MINUTES
) -> list[Event]:
    """Events that are live, or tip within `pre_tipoff_minutes`."""
    window = dt.timedelta(minutes=pre_tipoff_minutes)
    out: list[Event] = []
    for event in response.events:
        if event.is_live:
            out.append(event)
            continue
        start = _start_time(event.start_time)
        if start and now <= start <= now + window:
            out.append(event)
    return out


@dataclass
class SamplePlan:
    """Which markets are sampled how often, recomputed every ~30s."""

    near: set[str] = field(default_factory=set)
    #: Every market in a live event, near-money or not.
    all_live: set[str] = field(default_factory=set)
    computed_at: float = 0.0

    @property
    def deep(self) -> set[str]:
        return self.all_live - self.near

    def tier(self, slug: str) -> str | None:
        if slug in self.near:
            return TIER_NEAR
        if slug in self.all_live:
            return TIER_DEEP
        return None


def build_plan(
    response: EventsResponse,
    *,
    now: dt.datetime,
    per_type: int = NEAR_MONEY_RUNGS,
    pre_tipoff_minutes: float = PRE_TIPOFF_MINUTES,
) -> SamplePlan:
    """Derive the sampling plan from one board payload."""
    events = live_events(response, now=now, pre_tipoff_minutes=pre_tipoff_minutes)
    near: set[str] = set()
    all_live: set[str] = set()
    for event in events:
        tradable = [m for m in event.markets if not m.closed]
        all_live.update(m.slug for m in tradable)
        near |= select_near_money(tradable, per_type=per_type)
    return SamplePlan(near=near, all_live=all_live, computed_at=time.monotonic())


# --------------------------------------------------------------------- #
# Depth sampling — a background thread, so book calls can never delay the
# one-second price loop
# --------------------------------------------------------------------- #


class DepthSampler:
    """Fetches order-book depth for a rotating set of markets.

    Runs on its own thread. The price loop hands it the freshest snapshot ids
    after every cycle; it fetches books concurrently and hangs the levels off
    whichever snapshot was current when the call returned.

    Sharing the client's token bucket is what keeps the whole process under
    the rate ceiling: the bucket is thread-safe, so concurrency here raises
    utilisation without raising the rate.
    """

    def __init__(
        self,
        *,
        client: PolymarketGatewayClient,
        sessionmaker,
        max_book_levels: int,
        near_seconds: float = DEPTH_NEAR_SECONDS,
        deep_seconds: float = DEPTH_DEEP_SECONDS,
        concurrency: int = DEPTH_CONCURRENCY,
    ) -> None:
        self._client = client
        self._Session = sessionmaker
        self._max_levels = max_book_levels
        #: Trade-tape rows accumulated by _fetch during one depth cycle and
        #: flushed with that cycle's book levels (one DB round trip, not two).
        self._pending_stats: list[dict] = []
        self._near_seconds = near_seconds
        self._deep_seconds = deep_seconds
        self._concurrency = concurrency

        self._lock = threading.Lock()
        self._plan = SamplePlan()
        self._snapshot_ids: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.books_written = 0
        self.book_errors = 0

    # -- published state ------------------------------------------------ #

    def publish(self, plan: SamplePlan, snapshot_ids: dict[str, int]) -> None:
        """Called by the price loop after each cycle. Never blocks it."""
        with self._lock:
            self._plan = plan
            # Keep the previous ids for markets absent from this cycle: a deep
            # rung is only snapshotted every 30s, and its depth should still
            # attach to its most recent row rather than being dropped.
            self._snapshot_ids.update(snapshot_ids)

    def _current(self) -> tuple[SamplePlan, dict[str, int]]:
        with self._lock:
            return self._plan, dict(self._snapshot_ids)

    # -- the loop ------------------------------------------------------- #

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="depth-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)

    def _run(self) -> None:
        next_near = 0.0
        next_deep = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            plan, ids = self._current()

            try:
                if now >= next_near and plan.near:
                    self.sample(sorted(plan.near), ids, tier=TIER_NEAR)
                    next_near = time.monotonic() + self._near_seconds
                elif now >= next_deep and plan.deep:
                    self.sample(sorted(plan.deep), ids, tier=TIER_DEEP)
                    next_deep = time.monotonic() + self._deep_seconds
            except Exception as exc:
                # Depth is valuable but optional. Never let it kill the thread —
                # and never let it kill the price loop, which is why it is on a
                # thread at all.
                log.error("depth_cycle_failed", error=str(exc), exc_info=True)

            self._stop.wait(0.25)

    def sample(self, slugs: list[str], snapshot_ids: dict[str, int], *, tier: str) -> int:
        """Fetch depth for `slugs` concurrently and write it. Returns rows written."""
        targets = [(s, snapshot_ids[s]) for s in slugs if s in snapshot_ids]
        if not targets:
            return 0

        started = time.monotonic()
        rows: list[dict] = []
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            for levels in pool.map(lambda t: self._fetch(*t), targets):
                rows.extend(levels)

        written = 0
        stats_rows, self._pending_stats = self._pending_stats, []
        if rows or stats_rows:
            with self._Session() as session:
                if rows:
                    session.execute(
                        pg_insert(BookLevel)
                        .values(rows)
                        .on_conflict_do_nothing(constraint="uq_book_level")
                    )
                    written = len(rows)
                if stats_rows:
                    session.execute(
                        pg_insert(MarketTradeStat)
                        .values(stats_rows)
                        .on_conflict_do_nothing(
                            constraint="uq_market_trade_stat_snapshot")
                    )
                session.commit()
        self.books_written += written

        log.info(
            "depth_cycle",
            tier=tier,
            markets=len(targets),
            levels=written,
            errors=self.book_errors,
            duration_s=round(time.monotonic() - started, 2),
        )
        return written

    def _fetch(self, slug: str, snapshot_id: int) -> list[dict]:
        """One book call. Timestamped at the moment it returned, not the moment
        its parent snapshot was taken — depth runs on a slower loop than price,
        and the depth-signal question is about ordering."""
        try:
            book, _raw = self._client.get_book(slug)
        except Exception as exc:
            self.book_errors += 1
            log.warning("book_fetch_failed", market_slug=slug, error=str(exc))
            return []

        captured_at = dt.datetime.now(UTC)
        data = book.market_data
        if data is None:
            return []

        # The venue's trade tape rides free in this same response and was
        # discarded here on every poll until 2026-09-02 (findings V31/V32).
        # It is the ONLY flow observable this venue offers, and a poll that
        # goes unrecorded is print history that cannot be recovered.
        st = data.stats
        if st is not None:
            _v = lambda q: q.value if q is not None else None
            self._pending_stats.append({
                "snapshot_id": snapshot_id,
                "captured_at": captured_at,
                "last_trade_px": _v(st.last_trade_px),
                "last_trade_qty": st.last_trade_qty,
                "last_trade_at": st.last_trade_at,
                "shares_traded": st.shares_traded,
                "notional_traded": _v(st.notional_traded),
                "open_interest": st.open_interest,
                "high_px": _v(st.high_px),
                "low_px": _v(st.low_px),
            })

        rows: list[dict] = []
        for side, entries in (("bid", data.bids), ("offer", data.offers)):
            for idx, entry in enumerate(entries[: self._max_levels]):
                price = entry.px.value if entry.px else None
                if price is None or entry.qty is None:
                    continue
                rows.append(
                    {
                        "snapshot_id": snapshot_id,
                        "side": side,
                        "price": price,
                        "quantity": entry.qty,
                        "level_index": idx,
                        "captured_at": captured_at,
                    }
                )
        return rows


# --------------------------------------------------------------------- #
# The recorder
# --------------------------------------------------------------------- #


class SnapshotWriter:
    """Persists price rows, optionally off the poll loop's thread.

    Why this exists
    ---------------
    At a 200ms target the deployed recorder achieved **497ms**, and the reason
    was not the gateway: `work_ms_p50` was 492ms against a 158ms board call.
    The container writes to Supabase, and a single remote INSERT round trip is
    ~330ms — so the database, not the venue, had become the cadence.

    Polling and persisting are different problems and now run on different
    threads. The price loop hands rows over and immediately issues the next
    board call; this thread drains whatever has accumulated and writes it in
    **one** statement. If a write takes 400ms it simply picks up two cycles'
    worth next time, so DB latency changes the batch size rather than the
    sampling rate.

    The loss window, stated plainly
    -------------------------------
    Buffering means a hard kill (SIGKILL, power loss) drops whatever has not
    been written — typically well under a second, since the thread never sleeps
    while the queue is non-empty. That is a real cost against this project's
    first rule, that snapshots cannot be backfilled. It is accepted because the
    alternative was measured: writing inline discarded ~40% of observable quote
    changes *continuously*. A sub-second window on an abnormal exit is the
    smaller loss. `stop()` drains before returning, so an ordinary shutdown or
    redeploy loses nothing.

    In **synchronous mode** — the thread never started, which is how tests and
    `--once` run — `submit` writes immediately and returns the ids, so the
    idempotency and row-shape guarantees are testable without any concurrency.
    """

    #: Bounded so a database outage cannot exhaust memory. Sized for ~30s of
    #: backlog at 5 cycles/s; if it ever fills, the database has been unreachable
    #: for long enough that the loud error is the point.
    MAX_PENDING = 200

    def __init__(self, sessionmaker, on_ids=None) -> None:
        self._Session = sessionmaker
        self._on_ids = on_ids
        self._queue: queue.Queue[list[dict]] = queue.Queue(maxsize=self.MAX_PENDING)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.rows_written = 0
        self.batches = 0
        self.dropped = 0
        self.write_ms: list[float] = []

    @property
    def is_async(self) -> bool:
        return self._thread is not None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="snapshot-writer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Drain what is pending, then exit. An ordinary shutdown loses nothing."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30.0)
        self._drain_once(block=False)

    def submit(self, rows: list[dict]) -> dict[str, int]:
        """Queue rows (async) or write them now (sync). Returns ids in sync mode."""
        if not rows:
            return {}
        if not self.is_async:
            return self._write(rows)
        try:
            self._queue.put_nowait(rows)
        except queue.Full:
            # Never block the poll loop. Losing the newest cycle is bad; jamming
            # the recorder so it loses every future cycle is worse.
            self.dropped += len(rows)
            log.error("snapshot_queue_full", dropped_rows=len(rows),
                      pending=self._queue.qsize())
        return {}

    def _run(self) -> None:
        while not self._stop.is_set():
            self._drain_once(block=True)
        self._drain_once(block=False)

    def _drain_once(self, *, block: bool) -> None:
        batches: list[list[dict]] = []
        if block:
            try:
                batches.append(self._queue.get(timeout=0.25))
            except queue.Empty:
                return
        while True:
            try:
                batches.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if not batches:
            return

        rows = [row for batch in batches for row in batch]
        started = time.monotonic()
        ids = self._write(rows)
        self.write_ms.append((time.monotonic() - started) * 1000)
        self.batches += 1
        if ids and self._on_ids is not None:
            self._on_ids(ids)

    def _write(self, rows: list[dict]) -> dict[str, int]:
        """One statement for the whole batch. Returns {slug: snapshot_id}.

        ON CONFLICT DO NOTHING keeps a rerun idempotent, exactly as the pregame
        path does — a duplicate `captured_at` is a no-op rather than a
        half-written cycle. Only inserted rows come back from RETURNING, which
        is why the depth sampler retains ids across cycles rather than
        expecting a fresh one every time.
        """
        try:
            with self._Session() as session:
                result = session.execute(
                    pg_insert(MarketSnapshot)
                    .values(rows)
                    .on_conflict_do_nothing(constraint="uq_snapshot_market_time")
                    .returning(MarketSnapshot.id, MarketSnapshot.market_slug)
                )
                ids = {slug: sid for sid, slug in result.all()}
                session.commit()
                self.rows_written += len(ids)
                return ids
        except Exception as exc:
            log.error("snapshot_write_failed", rows=len(rows), error=str(exc),
                      exc_info=True)
            return {}


class LiveCycleStats:
    def __init__(self) -> None:
        self.markets_seen = 0
        self.snapshots_written = 0
        self.rows_queued = 0
        self.near = 0
        self.deep = 0


class LiveRecorder:
    """Polls only while a game is in progress (or about to be)."""

    def __init__(
        self,
        config: RecorderConfig | None = None,
        client: PolymarketGatewayClient | None = None,
        sessionmaker=None,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        *,
        near_money_rungs: int = NEAR_MONEY_RUNGS,
        deep_snapshot_seconds: float = DEEP_SNAPSHOT_SECONDS,
        plan_refresh_seconds: float = PLAN_REFRESH_SECONDS,
        raw_snapshot_seconds: float = RAW_SNAPSHOT_SECONDS,
        capture_depth: bool | None = None,
    ) -> None:
        self.config = config or RECORDER
        self._client = client or PolymarketGatewayClient(self.config)
        self.interval_seconds = interval_seconds
        self.near_money_rungs = near_money_rungs
        self.deep_snapshot_seconds = deep_snapshot_seconds
        self.plan_refresh_seconds = plan_refresh_seconds
        self.raw_snapshot_seconds = raw_snapshot_seconds
        self._Session = sessionmaker or get_sessionmaker(get_engine())

        self._plan = SamplePlan()
        #: When each slug was last given a price snapshot, so deep rungs can be
        #: throttled without throttling the near ones.
        self._last_snapshot: dict[str, float] = {}
        #: When each slug last had its full `raw` payload retained.
        self._last_raw: dict[str, float] = {}

        # The heartbeat gets its own single-connection engine when nothing was
        # injected: the shared pool is 2+1 and already serves the writer and
        # depth threads, so a beat competing there could block the price loop
        # behind a slow snapshot batch. Local Postgres has no connection budget
        # worth defending; the loop's 200ms budget is the scarce thing.
        self._heartbeat = Heartbeat(
            sessionmaker
            or get_sessionmaker(
                get_engine(pool_size=1, max_overflow=0, pool_timeout=2)
            ),
            (SERVICE_LIVE if self.config.league_slug == "wnba"
             else f"{SERVICE_LIVE}_{self.config.league_slug}"),  # B11: one row per process
        )
        self._rows_at_last_beat = 0

        want_depth = (
            self.config.capture_depth if capture_depth is None else capture_depth
        )
        self._depth: DepthSampler | None = None
        self._writer = SnapshotWriter(
            self._Session,
            on_ids=lambda ids: (
                self._depth.publish(self._plan, ids) if self._depth else None
            ),
        )
        if want_depth:
            self._depth = DepthSampler(
                client=self._client,
                sessionmaker=self._Session,
                max_book_levels=self.config.max_book_levels,
            )

    # ------------------------------------------------------------------ #
    # One cycle
    # ------------------------------------------------------------------ #

    def run_cycle(self, captured_at: dt.datetime | None = None) -> LiveCycleStats:
        """One board call; write top-of-book for everything live.

        Returns without writing anything if no game is live — the caller then
        sleeps at the idle cadence instead of the fast one.
        """
        captured_at = captured_at or dt.datetime.now(UTC)
        stats = LiveCycleStats()

        try:
            parsed, raw = self._client.get_league_events()
        except Exception as exc:
            # The board call is the only failure we cannot work around: it is
            # both the schedule and the price source. Log and let the loop
            # retry rather than dying.
            log.error("board_fetch_failed", error=str(exc), exc_info=True)
            return stats

        now = time.monotonic()
        if now - self._plan.computed_at >= self.plan_refresh_seconds or not self._plan.all_live:
            self._plan = build_plan(
                parsed, now=captured_at, per_type=self.near_money_rungs
            )

        plan = self._plan
        if not plan.all_live:
            return stats

        raw_events = {
            str(e.get("slug")): e for e in raw.get("events", []) if isinstance(e, dict)
        }

        rows: list[dict] = []
        for event in parsed.events:
            raw_event = raw_events.get(event.slug or "", {})
            raw_markets = {
                str(m.get("slug")): m
                for m in raw_event.get("markets", []) or []
                if isinstance(m, dict)
            }
            for market in event.markets:
                tier = plan.tier(market.slug)
                if tier is None:
                    continue
                stats.markets_seen += 1

                # Deep rungs stay on the 30s cadence. They are the 0.95/0.05
                # rungs that do not trade; at a 200ms price loop a row per
                # cycle there would be 150x the storage for a price that moves
                # a couple of times an hour.
                if tier == TIER_DEEP:
                    last = self._last_snapshot.get(market.slug, 0.0)
                    if now - last < self.deep_snapshot_seconds:
                        continue
                    stats.deep += 1
                else:
                    stats.near += 1

                self._last_snapshot[market.slug] = now

                # Retain the full payload periodically rather than every cycle:
                # it is 62% of the row and its moving fields are already typed.
                keep_raw = (
                    now - self._last_raw.get(market.slug, -1e9)
                    >= self.raw_snapshot_seconds
                )
                if keep_raw:
                    self._last_raw[market.slug] = now

                rows.append(
                    self._snapshot_values(
                        event=event,
                        market=market,
                        captured_at=captured_at,
                        raw_market=raw_markets.get(market.slug) if keep_raw else None,
                        tier=tier,
                    )
                )

        if not rows:
            return stats

        stats.rows_queued = len(rows)
        snapshot_ids = self._writer.submit(rows)
        stats.snapshots_written = len(snapshot_ids)

        if self._depth is not None:
            # In async mode the writer publishes ids itself as batches land;
            # this call still runs so the plan reaches the sampler every cycle.
            self._depth.publish(plan, snapshot_ids)

        return stats

    def _snapshot_values(
        self,
        *,
        event: Event,
        market: Market,
        captured_at: dt.datetime,
        raw_market: dict | None,
        tier: str,
    ) -> dict:
        """Identical row shape to the pregame recorder's, plus the tier.

        Deliberately mirrors `Recorder._record_market` so a live snapshot and a
        pregame one remain the same object — every downstream query treats them
        alike, and `is_live` is the only thing that distinguishes them.
        """
        state = event.event_state
        return {
            "captured_at": captured_at,
            "market_slug": market.slug,
            "market_id": market.id,
            "event_slug": event.slug,
            "event_id": event.id,
            "game_id": event.game_id,
            "sports_market_type": market.sports_market_type,
            "line": market.line,
            "best_bid": market.best_bid,
            "best_ask": market.best_ask,
            "min_tick_size": market.order_price_min_tick_size,
            "min_trade_qty": market.minimum_trade_qty,
            "fee_coefficient": market.fee_coefficient,
            "game_start_time": _parse_ts(market.game_start_time or event.start_time),
            "is_live": event.is_live,
            "event_score": state.score if state else None,
            "event_period": state.period if state else None,
            "book_tier": tier,
            "raw": raw_market,
        }

    # ------------------------------------------------------------------ #
    # Cadence
    # ------------------------------------------------------------------ #

    def should_be_running(self, now: dt.datetime | None = None) -> bool:
        """True when a game is live or tips within `PRE_TIPOFF_MINUTES`.

        Errs toward recording: if the board call fails we cannot tell what is
        happening, and over-sampling costs a few requests while under-sampling
        loses data permanently.
        """
        now = now or dt.datetime.now(UTC)
        try:
            parsed, _ = self._client.get_league_events()
        except Exception as exc:
            log.warning("live_check_failed", error=str(exc))
            return True
        return bool(live_events(parsed, now=now))

    def run_forever(self) -> None:
        """Poll fast while games are on, sleep cheaply when they are not."""
        stopping = {"flag": False}

        def _handle(signum, _frame):
            log.info("live_recorder_stopping", signal=signum)
            stopping["flag"] = True

        signal.signal(signal.SIGINT, _handle)
        signal.signal(signal.SIGTERM, _handle)

        log.info(
            "live_recorder_started",
            interval_seconds=self.interval_seconds,
            near_money_rungs=self.near_money_rungs,
            deep_snapshot_seconds=self.deep_snapshot_seconds,
            depth=self._depth is not None,
            rps=self.config.requests_per_second,
        )

        self._writer.start()
        if self._depth is not None:
            self._depth.start()

        last_active = 0.0
        cycles = 0
        work: list[float] = []
        gaps: list[float] = []
        previous_start: float | None = None
        reported = time.monotonic()
        try:
            while not stopping["flag"]:
                started = time.monotonic()
                if previous_start is not None:
                    gaps.append(started - previous_start)
                previous_start = started

                try:
                    stats = self.run_cycle()
                except Exception as exc:
                    # Absolute backstop. A recorder that dies unattended is the
                    # dominant failure mode and these snapshots cannot be
                    # backfilled from anywhere.
                    log.error("live_cycle_failed", error=str(exc), exc_info=True)
                    stats = LiveCycleStats()

                now = time.monotonic()
                if stats.markets_seen:
                    last_active = now
                in_grace = (now - last_active) < GRACE_MINUTES * 60

                if stats.markets_seen or in_grace:
                    wait = self.interval_seconds
                    cycles += 1
                    work.append(now - started)
                else:
                    wait = IDLE_POLL_SECONDS
                    gaps.clear()

                # Every cycle, game or no game. This is the B11 fix: the beat,
                # not the data, is what says "alive", so silence between games
                # stops being an excuse for silence during them.
                self._beat_cycle(stats, wait, now - started)

                # Five lines a second is unreadable; summarise instead. The
                # achieved cadence is reported here rather than only measurable
                # from a test harness — the 200ms target is a claim about the
                # deployed process, so the deployed process states it.
                if now - reported >= 60.0:
                    log.info(
                        "live_minute",
                        cycles=cycles,
                        near=stats.near,
                        deep_due=stats.deep,
                        depth_levels=self._depth.books_written if self._depth else 0,
                        book_errors=self._depth.book_errors if self._depth else 0,
                        rows_written=self._writer.rows_written,
                        write_batches=self._writer.batches,
                        dropped=self._writer.dropped,
                        **_latency_summary("work_ms", work),
                        **_latency_summary("cadence_ms", gaps),
                        **_latency_summary(
                            "db_ms", [v / 1000 for v in self._writer.write_ms]
                        ),
                    )
                    reported = now
                    cycles = 0
                    work.clear()
                    gaps.clear()
                    self._writer.write_ms.clear()

                self._sleep_remaining(started, wait, stopping)
        finally:
            if self._depth is not None:
                self._depth.stop()
            # Last, and always: drains the queue so an ordinary shutdown or a
            # redeploy loses nothing.
            self._writer.stop()

        log.info("live_recorder_stopped")

    def _beat_cycle(self, stats: LiveCycleStats, wait: float, cycle_seconds: float) -> None:
        """One heartbeat upsert, ~1ms against local Postgres.

        `rows_written` is the delta of rows the writer thread actually landed —
        an output, not a queue length. In async mode a batch can span cycles,
        so a single cycle legitimately reads 0; readers judge output over their
        own window (rows in 5 min), never a single beat's count.
        """
        delta = self._writer.rows_written - self._rows_at_last_beat
        self._rows_at_last_beat = self._writer.rows_written
        self._heartbeat.beat(
            interval_seconds=wait,
            rows_written=delta,
            cycle_seconds=cycle_seconds,
            game_live=bool(stats.markets_seen),
        )

    def _sleep_remaining(self, started: float, wait: float, stopping: dict) -> None:
        """Sleep until `started + wait`, or return immediately if already past.

        This is what makes the interval a *floor* rather than a promise, and it
        is why the loop cannot issue requests faster than they come back: the
        next board call is only made after the previous one has returned and
        been written. If a cycle takes longer than `wait` — p90 board latency is
        226ms against a 200ms target — the loop simply runs back-to-back at the
        speed the gateway allows instead of queueing requests on top of
        themselves. Overlap is unrepresentable, not merely avoided.

        The practical floor is therefore max(interval, round-trip), which
        measured ~175ms even when asked for 100ms.
        """
        deadline = started + wait
        while not stopping["flag"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.25, remaining))


def _latency_summary(prefix: str, values: list[float]) -> dict[str, float]:
    """median/p90 in milliseconds, for the per-minute log line."""
    if not values:
        return {}
    ordered = sorted(values)
    return {
        f"{prefix}_p50": round(ordered[len(ordered) // 2] * 1000, 1),
        f"{prefix}_p90": round(ordered[int(0.9 * (len(ordered) - 1))] * 1000, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-live-recorder")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--rungs", type=int, default=NEAR_MONEY_RUNGS,
                        help="rungs per market type sampled at full cadence")
    parser.add_argument("--no-depth", action="store_true",
                        help="skip order-book depth entirely (price only)")
    parser.add_argument("--once", action="store_true",
                        help="record a single cycle and exit")
    args = parser.parse_args()

    if args.interval < MIN_INTERVAL_SECONDS:
        parser.error(
            f"--interval {args.interval} is below the {MIN_INTERVAL_SECONDS}s floor. "
            "The loop self-paces to the round-trip time (~175ms measured), so a "
            "smaller number buys nothing and only risks a hot loop."
        )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    rec = LiveRecorder(
        interval_seconds=args.interval,
        near_money_rungs=args.rungs,
        capture_depth=not args.no_depth,
    )
    if args.once:
        stats = rec.run_cycle()
        log.info(
            "live_once",
            markets=stats.markets_seen,
            snapshots=stats.snapshots_written,
            near=stats.near,
            deep=stats.deep,
        )
        return 0
    rec.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
