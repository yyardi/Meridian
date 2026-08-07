"""Fill watcher: reconcile the `orders` table against venue truth, and submit
pre-authorized exits when their entries fill.

Why this exists (V17): "accepted" and "filled" are different events, and the
`orders` table only ever recorded the first. Orders #1–3 read `accepted=True`
while a human cancelled two of them in the venue's app — the table had no way
to know. This module is the missing read-back loop.

What it does, once every 60 seconds:

1. GET ``/v1/portfolio/activities`` and ``/v1/portfolio/positions`` — two
   read-only requests per minute, far inside the ~5 req/s throttle on the
   authenticated host (findings V12).
2. For every accepted order with a venue order id, derive its fill state from
   the activities: FILLED / PARTIAL / OPEN / CANCELLED / EXPIRED.
3. For every PENDING exit whose entry has reached a terminal state, act:
   submit it (filled), delete it (cancelled/expired unfilled), and nothing in
   between.
4. Upsert a ``fill_watcher`` heartbeat, so a dead watcher is loud (B11).

Attribution is by venue order id ONLY
-------------------------------------
The account also contains hand trades, sometimes in the same market at similar
prices. An activity that does not carry the venue order id of one of our rows
is **ignored** — never matched by market, price, size, or any similarity. The
positions endpoint is read for the heartbeat's context and for logging; it is
NEVER used to infer a fill, because a position delta cannot distinguish a
button order's fill from a hand trade.

The exit rules, each load-bearing
---------------------------------
1. The exit's market slug was copied from the entry row at click time; this
   module sends it as stored and never re-derives it.
2. The exit price is immutable — sent exactly as stored even if the market
   moved 30¢. No chasing, ever. A stale exit is the human's to cancel.
3. Exit quantity = the venue-reported FILLED quantity, never the ordered one.
   A partial fill exited at the ordered size would sell contracts we do not
   hold.
4. The exit sells the same outcome side the entry bought, and its stored
   ``limit_price`` is already the YES-frame ``price.value`` (V14: for a NO
   exit at cost X, price.value = 1 − X). No conversion happens here — it
   happened once, at click time, and is unit-tested in both frames.
5. Entry cancelled or expired unfilled → the pending exit is DELETED, with a
   log line.
6. One retry on submit failure, then FAILED loudly on the dashboard. An exit
   the human believes is protecting them must never silently not exist.
7. Nothing here reads ``is_live`` — in-game is the target use.

The payload schema is the OBSERVED one, and cancels are invisible
-----------------------------------------------------------------
Parsing is written against the schema read from the live venue on 2026-08-06
(findings V19), not against documentation — the first version of this module
guessed a flat shape and reconciled nothing. Activities that do not match the
observed shape are counted and logged (``fill_watcher_unparsed_activity``),
never guessed at.

One verified gap: a **zero-fill venue-side cancel emits no activity**, and no
order-status endpoint exists (``/v1/orders`` 501, ``/v1/orders/{id}`` 404).
A cancelled unfilled entry therefore stays OPEN here with its exit PENDING —
both visible on the dashboard, where the human who did the cancelling can see
and remove the exit. Market settlement (``ACTIVITY_TYPE_POSITION_RESOLUTION``)
does arrive, so orders on settled markets go EXPIRED and their unfilled exits
are deleted.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

import structlog

from core import heartbeat
from core.executor import ExecutionMode, OrderSide, OutcomeSide, build_order
from core.polymarket.client import (
    OrderSubmissionError,
    PolymarketAuthedClient,
    PolymarketOrderClient,
    USCredentials,
)
from core.storage import PendingExit, PlacedOrder

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Poll cadence. Two GETs per cycle = 1/30 req/s, ~1% of the V12 throttle.
POLL_INTERVAL_SECONDS = 60.0

ACTIVITIES_PATH = "/v1/portfolio/activities"
POSITIONS_PATH = "/v1/portfolio/positions"

# Fill states written to orders.fill_status. NULL means "never reconciled".
OPEN = "OPEN"
PARTIAL = "PARTIAL"
FILLED = "FILLED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"

#: States from which no further fills can arrive.
TERMINAL = frozenset({FILLED, CANCELLED, EXPIRED})


# --------------------------------------------------------------------------- #
# Activity parsing — against the OBSERVED schema, 2026-08-06 (findings V19)
# --------------------------------------------------------------------------- #
#
# The real response, read from the venue rather than assumed:
#
#     {"activities": [...], "nextCursor": "...", "eof": false}
#
# Each ACTIVITY_TYPE_TRADE carries `trade.aggressorExecution` and
# `trade.passiveExecution` (either may be null; our resting orders are the
# passive side). Each execution embeds the full order object, and that object
# is the authoritative record:
#
#     trade.<side>Execution.order.id            -> the venue order id
#     trade.<side>Execution.order.state         -> ORDER_STATE_FILLED / _PARTIALLY_FILLED
#     trade.<side>Execution.order.cumQuantity   -> cumulative filled, venue's number
#     trade.<side>Execution.transactTime        -> ordering key
#
# `cumQuantity` from the LATEST execution is used instead of summing per-fill
# shares, and `state` instead of comparing against our ordered quantity — the
# venue rounds quantities to 2dp (our 1.4645-contract order reports
# cumQuantity 1.46 with state FILLED), so "filled >= ordered" would read
# PARTIAL forever on any order with >2dp size.
#
# ACTIVITY_TYPE_POSITION_RESOLUTION (`positionResolution.marketSlug`) means
# the market settled; an order still open on a settled market can never fill
# again and is EXPIRED. This is market-level truth, not fill attribution —
# the venue-order-id-only rule applies to fills.
#
# **Cancels are invisible here.** A zero-fill cancel emits no activity
# (verified: two orders cancelled by hand in the app on 2026-08-05 appear
# nowhere in the feed, and no CANCEL activity or execution type has been
# observed). There is also no order-status endpoint (`/v1/orders` is 501,
# `/v1/orders/{id}` 404). So a venue-side cancel of an unfilled entry leaves
# the row OPEN and its exit PENDING — visible states, both, on the dashboard;
# the human who cancelled in the app can see and cancel the pending exit.

ACTIVITY_TRADE = "ACTIVITY_TYPE_TRADE"
ACTIVITY_RESOLUTION = "ACTIVITY_TYPE_POSITION_RESOLUTION"

#: Venue order states -> our fill_status. Substring match on the suffix so
#: e.g. a hypothetical ORDER_STATE_CANCELED maps sensibly if it ever appears.
def _status_from_state(state: str) -> str | None:
    up = (state or "").upper()
    if "PARTIALLY_FILLED" in up:
        return PARTIAL
    if "FILLED" in up:
        return FILLED
    if "CANCEL" in up:
        return CANCELLED
    if "EXPIR" in up:
        return EXPIRED
    if "NEW" in up or "OPEN" in up or "WORKING" in up:
        return OPEN
    return None


@dataclass(frozen=True)
class OrderEvent:
    """One execution's view of one order: the venue's own state and count."""

    venue_order_id: str
    state: str
    cum_quantity: Decimal
    transact_time: str      # RFC3339 with Z and 9-digit nanos — lexicographic
                            # compare orders correctly within this format


def extract_order_events(raw: dict) -> tuple[list[OrderEvent], str | None, bool]:
    """One raw activity → (order events, resolved market slug, parsed_ok).

    `parsed_ok` False means the activity was a shape this code does not
    recognise — the caller logs it loudly, because unknown must never be
    silently dropped (schema drift is exactly how the first version of this
    parser reconciled nothing for a day).
    """
    kind = raw.get("type")
    if kind == ACTIVITY_RESOLUTION:
        slug = (raw.get("positionResolution") or {}).get("marketSlug")
        return [], slug, slug is not None
    if kind != ACTIVITY_TRADE:
        # Other benign types exist (ACTIVITY_TYPE_TRANSFER); no order state
        # in them, nothing to extract, not an error.
        return [], None, True

    trade = raw.get("trade") or {}
    events: list[OrderEvent] = []
    saw_execution = False
    for side in ("aggressorExecution", "passiveExecution"):
        ex = trade.get(side)
        if not isinstance(ex, dict):
            continue
        saw_execution = True
        order = ex.get("order") or {}
        oid = order.get("id")
        state = order.get("state")
        cum = order.get("cumQuantity")
        if not oid or not state or cum is None:
            return events, None, False
        try:
            cum_qty = Decimal(str(cum))
        except (InvalidOperation, ValueError):
            return events, None, False
        events.append(OrderEvent(
            venue_order_id=str(oid),
            state=str(state),
            cum_quantity=cum_qty,
            transact_time=str(ex.get("transactTime") or ""),
        ))
    return events, None, saw_execution


def reconcile_order(events: list[OrderEvent]) -> tuple[str, Decimal] | None:
    """Venue-truth (fill_status, filled_quantity) for one order.

    The latest execution wins outright — its embedded order object carries the
    venue's own cumulative count and state, so nothing is summed or inferred.
    None means "no signal in the scanned activities": the caller then falls
    back to market resolution (EXPIRED) or leaves the row OPEN, and never
    touches the known fill count.
    """
    if not events:
        return None
    latest = max(events, key=lambda e: e.transact_time)
    status = _status_from_state(latest.state)
    if status is None:
        log.warning("fill_watcher_unknown_order_state", state=latest.state)
        return None
    return status, latest.cum_quantity


# --------------------------------------------------------------------------- #
# The watcher
# --------------------------------------------------------------------------- #


@dataclass
class PollResult:
    """What one cycle did — the watcher's output, assertable in tests."""

    tracked: int = 0
    updated: int = 0
    exits_submitted: int = 0
    exits_failed: int = 0
    exits_deleted: int = 0
    unparsed_activities: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)


class FillWatcher:
    """Background reconciliation loop. Read-mostly; its only write path to the
    venue is the pre-authorized exit, and the only exits it can submit are
    rows a human created on the ticket."""

    def __init__(
        self,
        sessionmaker,
        creds: USCredentials,
        *,
        interval_seconds: float = POLL_INTERVAL_SECONDS,
        read_client: PolymarketAuthedClient | None = None,
        order_client: PolymarketOrderClient | None = None,
    ) -> None:
        self._Session = sessionmaker
        self._creds = creds
        self.interval_seconds = interval_seconds
        # Injectable for tests; production builds real clients lazily.
        self._read_client = read_client
        self._order_client = order_client
        self._heartbeat = heartbeat.Heartbeat(
            sessionmaker, heartbeat.SERVICE_FILL_WATCHER
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle -------------------------------------------------------- #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="fill-watcher", daemon=True
        )
        self._thread.start()
        log.info("fill_watcher_started", interval_seconds=self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                result = self.poll_once()
            except Exception as exc:      # never let one bad cycle kill the loop
                log.error("fill_watcher_cycle_failed", error=str(exc)[:300])
                result = PollResult(error=str(exc)[:300])
            self._heartbeat.beat(
                interval_seconds=self.interval_seconds,
                rows_written=result.updated + result.exits_submitted,
                cycle_seconds=time.monotonic() - started,
            )
            self._stop.wait(self.interval_seconds)

    # ---- one cycle -------------------------------------------------------- #

    def poll_once(self) -> PollResult:
        """One reconciliation cycle. Public so tests can drive it directly."""
        result = PollResult()

        with self._Session() as s:
            tracked = s.query(PlacedOrder).filter(
                PlacedOrder.accepted.is_(True),
                PlacedOrder.venue_order_id.is_not(None),
                (PlacedOrder.fill_status.is_(None))
                | (PlacedOrder.fill_status.notin_(TERMINAL)),
            ).all()
            pending = s.query(PendingExit).filter(
                PendingExit.state == "PENDING"
            ).count()
        result.tracked = len(tracked)
        if not tracked and not pending:
            return result

        tracked_ids = {o.venue_order_id for o in tracked}
        activities = self._fetch_activities(result, tracked_ids)
        if activities is None:            # fetch failed; already logged loudly
            return result

        by_order: dict[str, list[OrderEvent]] = {}
        resolved_slugs: set[str] = set()
        for raw in activities:
            events, resolved_slug, ok = extract_order_events(raw)
            if not ok:
                result.unparsed_activities += 1
                log.warning(
                    "fill_watcher_unparsed_activity",
                    type=raw.get("type"),
                    keys=sorted(raw.keys())[:12],
                    note="schema drift? this activity was ignored, never "
                         "guessed at — compare against findings V19",
                )
            if resolved_slug:
                resolved_slugs.add(resolved_slug)
            for ev in events:
                by_order.setdefault(ev.venue_order_id, []).append(ev)

        now = dt.datetime.now(UTC)
        with self._Session() as s:
            for order in tracked:
                row = s.get(PlacedOrder, order.id)
                known_filled = row.filled_quantity or Decimal("0")
                outcome = reconcile_order(by_order.get(row.venue_order_id, []))
                if outcome is not None:
                    status, filled = outcome
                    if filled < known_filled:
                        # Fills can page out of the scanned window; venue
                        # truth never un-fills. Keep the larger count, loudly.
                        log.warning(
                            "fill_watcher_fill_count_regressed",
                            order_id=row.id, known=str(known_filled),
                            reported=str(filled),
                            note="scanned window no longer covers this "
                                 "order's fills; keeping the known count",
                        )
                        filled = known_filled
                elif row.market_slug in resolved_slugs:
                    # No execution in the window but the market settled: this
                    # order can never fill again. Market-level truth, not fill
                    # attribution — the fill count is left as known.
                    status, filled = EXPIRED, known_filled
                else:
                    status, filled = OPEN, known_filled
                changed = (status != row.fill_status
                           or filled != (row.filled_quantity or Decimal("0")))
                row.fill_status = status
                row.filled_quantity = filled
                row.fill_checked_at = now
                if changed:
                    result.updated += 1
                    log.info(
                        "fill_watcher_reconciled",
                        order_id=row.id, venue_order_id=row.venue_order_id,
                        market=row.market_slug, fill_status=status,
                        filled=str(filled), ordered=str(row.quantity),
                    )
            s.commit()

        self._act_on_pending_exits(result)
        return result

    #: Activities page size, and how many pages one cycle may walk. Three
    #: pages of 100 cover far more than a day of this account's activity; a
    #: fill older than that is caught by the monotonic guard never regressing
    #: what an earlier cycle already saw.
    PAGE_LIMIT = 100
    MAX_PAGES = 3

    def _fetch_activities(
        self, result: PollResult, tracked_ids: set[str] | None = None
    ) -> list[dict] | None:
        """All scanned activity dicts, or None on failure — **logged loudly**.

        The first version of this method recorded failures only on the
        PollResult, which nothing printed: the watcher ran for a day
        reconciling nothing in perfect silence, which is the exact B11 shape
        this module was built to prevent. Every failure path now logs at
        error level.

        Pagination follows the venue's `cursor`/`eof` contract and stops
        early once every tracked venue order id has been seen in the scan —
        the common case is one page.
        """
        import json as _json

        client = self._read_client or PolymarketAuthedClient(self._creds)
        owns = self._read_client is None
        remaining = set(tracked_ids or ())
        try:
            pages: list[dict] = []
            cursor: str | None = None
            for _ in range(self.MAX_PAGES):
                params: dict = {"limit": self.PAGE_LIMIT}
                if cursor:
                    params["cursor"] = cursor
                resp = client.get(ACTIVITIES_PATH, params=params)
                if resp.status_code != 200:
                    result.error = f"activities HTTP {resp.status_code}"
                    log.error("fill_watcher_activities_unavailable",
                              status=resp.status_code,
                              body=resp.body_text[:200])
                    return None
                try:
                    body = _json.loads(resp.body_text)
                except ValueError:
                    result.error = "activities body not JSON"
                    log.error("fill_watcher_activities_not_json",
                              body_prefix=resp.body_text[:120],
                              body_len=len(resp.body_text))
                    return None
                batch = body.get("activities") or []
                pages.extend(a for a in batch if isinstance(a, dict))

                for a in batch:
                    trade = a.get("trade") or {}
                    for side in ("aggressorExecution", "passiveExecution"):
                        oid = ((trade.get(side) or {}).get("order") or {}).get("id")
                        remaining.discard(str(oid))
                cursor = body.get("nextCursor")
                if body.get("eof") or not cursor or not remaining:
                    break

            # Positions: context only. Read so a human comparing the account
            # against the orders table has both in one log; NEVER used for
            # attribution.
            pos_resp = client.get(POSITIONS_PATH)
            if pos_resp.status_code == 200:
                result.notes.append("positions read ok")
            return pages
        except Exception as exc:
            result.error = f"fetch failed: {str(exc)[:200]}"
            log.error("fill_watcher_fetch_failed", error=str(exc)[:300])
            return None
        finally:
            if owns:
                client.close()

    # ---- pre-authorized exits --------------------------------------------- #

    def _act_on_pending_exits(self, result: PollResult) -> None:
        """Submit, delete, or wait — decided per exit from its ENTRY's state.

        The decision table (partial-then-still-open waits on purpose: fills
        may still arrive, and submitting per-slice would need amendment logic
        this system refuses to have):

            entry FILLED                        → submit, qty = filled
            entry CANCELLED/EXPIRED, filled > 0 → submit, qty = filled
            entry CANCELLED/EXPIRED, filled = 0 → DELETE, log line (rule 5)
            entry OPEN or PARTIAL               → wait
        """
        with self._Session() as s:
            rows = s.query(PendingExit).filter(PendingExit.state == "PENDING").all()
            plans: list[tuple[int, str]] = []      # (exit id, 'submit' | 'delete')
            for x in rows:
                entry = s.get(PlacedOrder, x.entry_order_id)
                if entry is None or entry.fill_status not in TERMINAL:
                    continue
                filled = entry.filled_quantity or Decimal("0")
                plans.append((x.id, "submit" if filled > 0 else "delete"))

        for exit_id, action in plans:
            if action == "delete":
                with self._Session() as s:
                    x = s.get(PendingExit, exit_id)
                    entry = s.get(PlacedOrder, x.entry_order_id)
                    x.state = "DELETED"
                    x.updated_at = dt.datetime.now(UTC)
                    s.commit()
                    result.exits_deleted += 1
                    log.info(
                        "pending_exit_deleted",
                        exit_id=exit_id, entry_order_id=x.entry_order_id,
                        market=x.market_slug,
                        reason=f"entry {entry.fill_status} with zero filled — "
                               "there is nothing to exit",
                    )
            else:
                self._submit_exit(exit_id, result)

    def _submit_exit(self, exit_id: int, result: PollResult) -> None:
        """Submit one pre-authorized exit, exactly as stored.

        One retry on failure (rule 6) — safe because the idempotency key is
        identical across attempts, so the venue and our UNIQUE constraint both
        refuse a duplicate. Then FAILED, loudly.
        """
        with self._Session() as s:
            x = s.get(PendingExit, exit_id)
            entry = s.get(PlacedOrder, x.entry_order_id)
            qty = entry.filled_quantity          # rule 3: filled, never ordered
            order = build_order(
                market_slug=x.market_slug,       # rule 1: copied at click time
                side=OrderSide.SELL,
                limit_price=x.limit_price,       # rule 2: immutable, YES-frame
                quantity=qty,
                decided_at=x.created_at,         # fixed → deterministic idem key
                outcome=OutcomeSide(x.outcome),  # rule 4: same side entry bought
            )
            row = PlacedOrder(
                submitted_at=dt.datetime.now(UTC),
                idempotency_key=order.idempotency_key,
                mode=ExecutionMode.HUMAN_CONFIRM.value,
                pre_authorized=True,
                market_slug=order.market_slug,
                event_slug=entry.event_slug,
                sports_market_type=entry.sports_market_type,
                side=f"sell_{x.outcome}".lower(),
                order_type=order.order_type,
                limit_price=order.limit_price,
                quantity=qty,
                accepted=False,
                would_rest=None,
                prediction_id=entry.prediction_id,
                notes=f"pre-authorized exit for order #{entry.id}",
            )
            s.add(row)
            try:
                s.commit()
            except Exception:
                # Key already reserved — a previous attempt got this far. Mark
                # FAILED rather than guessing at venue state.
                s.rollback()
                self._mark_exit_failed(
                    exit_id, result,
                    "idempotency key already reserved by an earlier attempt; "
                    "reconcile against the venue before retrying by hand",
                )
                return
            exit_order_row_id = row.id

        payload = order.to_payload()
        outcome_status, venue_answer = self._post_with_one_retry(payload)

        with self._Session() as s:
            row = s.get(PlacedOrder, exit_order_row_id)
            x = s.get(PendingExit, exit_id)
            x.updated_at = dt.datetime.now(UTC)
            x.submitted_order_id = exit_order_row_id
            if outcome_status == "accepted":
                row.accepted = True
                row.http_status = venue_answer.status_code
                body = venue_answer.body_text
                row.venue_order_id = _venue_order_id_from_body(body)
                row.submit_latency_ms = Decimal(str(round(venue_answer.elapsed_ms, 2)))
                x.state = "SUBMITTED"
                result.exits_submitted += 1
                log.info(
                    "pre_authorized_exit_submitted",
                    exit_id=exit_id, entry_order_id=x.entry_order_id,
                    market=x.market_slug, price=str(x.limit_price),
                    quantity=str(row.quantity),
                )
            else:
                if venue_answer is not None:
                    row.http_status = venue_answer.status_code
                    row.error = venue_answer.body_text[:1000]
                else:
                    row.error = outcome_status
                x.state = "FAILED"
                x.error = (row.error or outcome_status)[:1000]
                result.exits_failed += 1
                # Rule 6: FAILED must be loud. The dashboard reads this state;
                # this log line is the second alarm, not the only one.
                log.error(
                    "pre_authorized_exit_FAILED",
                    exit_id=exit_id, entry_order_id=x.entry_order_id,
                    market=x.market_slug, error=x.error[:200],
                    note="the human believes this position has an exit resting "
                         "and it does NOT — act on this",
                )
            s.commit()

    def _post_with_one_retry(self, payload: dict):
        """POST once; on failure, once more; never a third time (rule 6).

        Returns ('accepted', response) | ('rejected', response) | (error, None).
        Safe to retry because the idempotency key is identical on both
        attempts — the client class itself never retries, and the human-click
        path keeps that property; this is the one place a retry is mandated.
        """
        client = self._order_client or PolymarketOrderClient(self._creds)
        owns = self._order_client is None
        try:
            last_error = None
            for attempt in (1, 2):
                try:
                    resp = client.submit_limit_order(payload)
                except OrderSubmissionError as exc:
                    last_error = f"attempt {attempt}: {exc}"
                    log.warning("exit_submit_attempt_failed",
                                attempt=attempt, error=str(exc)[:200])
                    continue
                if resp.status_code in (200, 201):
                    return "accepted", resp
                # A definitive venue rejection: retrying the same order would
                # get the same answer, so surface it now.
                return "rejected", resp
            return last_error or "submit failed", None
        finally:
            if owns:
                client.close()

    def _mark_exit_failed(self, exit_id: int, result: PollResult, error: str) -> None:
        with self._Session() as s:
            x = s.get(PendingExit, exit_id)
            x.state = "FAILED"
            x.error = error[:1000]
            x.updated_at = dt.datetime.now(UTC)
            s.commit()
        result.exits_failed += 1
        log.error("pre_authorized_exit_FAILED", exit_id=exit_id, error=error[:200])


def _venue_order_id_from_body(body_text: str) -> str | None:
    import json as _json
    try:
        body = _json.loads(body_text)
    except (ValueError, TypeError):
        return None
    if isinstance(body, dict):
        value = body.get("orderId") or body.get("id")
        return str(value) if value else None
    return None
