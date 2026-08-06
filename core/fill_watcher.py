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

Venue payload shapes are treated as unverified
----------------------------------------------
The activities response schema has not been observed at volume (the venue's
docs have been wrong for this repo before — findings C10). Parsing is
therefore defensive: an activity that cannot be normalised is counted and
logged, never guessed at. If the counters on ``/api/status`` disagree with the
venue's app, the first thing to read is a ``fill_watcher_unparsed_activity``
log line.
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
# Activity normalisation — defensive by design
# --------------------------------------------------------------------------- #

#: Keys that may carry the VENUE's order id. Deliberately does not include
#: bare "id" (that is the activity's own id) or "clientOrderId" (ours, but the
#: rule is venue id only, and one rule beats two).
_ORDER_ID_KEYS = ("orderId", "order_id", "orderID")

#: Keys that may carry a fill quantity, tried in order — most specific first,
#: so a payload carrying both "filledQuantity" and a total "quantity" reads
#: the fill, not the order size.
_QTY_KEYS = ("filledQuantity", "filled_quantity", "fillQuantity", "matchedQuantity",
             "quantity", "size", "shares")

#: Keys that may say what kind of event this is.
_KIND_KEYS = ("type", "activityType", "activity_type", "eventType", "event_type",
              "status", "state")


@dataclass(frozen=True)
class Activity:
    """One venue activity, normalised. `kind` is 'fill' | 'cancel' | 'expire'."""

    venue_order_id: str
    kind: str
    quantity: Decimal = Decimal("0")


def _classify(label: str) -> str | None:
    """Map a venue label onto fill/cancel/expire, or None for anything else.

    Substring matching on purpose: 'FILL', 'FILLED', 'ORDER_FILL',
    'ACTIVITY_TYPE_FILL' and 'trade' should all read as fills without this
    module having to know the venue's exact vocabulary. 'MATCH' is a fill in
    exchange vocabulary ('matched'). Anything unrecognised returns None and is
    logged by the caller — unknown must be loud, not silently dropped.
    """
    up = label.upper()
    if "CANCEL" in up:
        return "cancel"
    if "EXPIR" in up:
        return "expire"
    if "FILL" in up or "TRADE" in up or "MATCH" in up:
        return "fill"
    return None


def normalize_activity(raw: dict) -> Activity | None:
    """One raw activity → an :class:`Activity`, or None if unparseable.

    None is a signal, not a shrug: the caller logs it with the raw keys so a
    schema drift shows up in the log the first time it happens, instead of as
    counters that quietly stop moving.
    """
    order_id = next(
        (str(raw[k]) for k in _ORDER_ID_KEYS if raw.get(k) not in (None, "")), None
    )
    if order_id is None:
        return None

    kind = None
    for key in _KIND_KEYS:
        value = raw.get(key)
        if isinstance(value, str):
            kind = _classify(value)
            if kind is not None:
                break
    if kind is None:
        return None

    qty = Decimal("0")
    if kind == "fill":
        for key in _QTY_KEYS:
            value = raw.get(key)
            if value in (None, ""):
                continue
            try:
                qty = abs(Decimal(str(value)))
                break
            except (InvalidOperation, ValueError):
                continue
        if qty == 0:
            return None            # a fill without a quantity is not usable
    return Activity(venue_order_id=order_id, kind=kind, quantity=qty)


def _extract_activity_list(body) -> list[dict]:
    """The venue may wrap the list ({"activities": [...]}, {"data": [...]}) or
    serve it bare. Take the first list of dicts found at the top level."""
    if isinstance(body, list):
        return [a for a in body if isinstance(a, dict)]
    if isinstance(body, dict):
        for key in ("activities", "data", "items", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return [a for a in value if isinstance(a, dict)]
    return []


def reconcile_order(order_quantity: Decimal, acts: list[Activity]) -> tuple[str, Decimal]:
    """Venue-truth state for one order from its own activities.

    Returns (fill_status, filled_quantity). Cancel/expire beat OPEN but do not
    erase fills — a partially-filled-then-cancelled order is CANCELLED with a
    non-zero filled quantity, and its exit covers exactly that quantity.
    """
    filled = sum((a.quantity for a in acts if a.kind == "fill"), Decimal("0"))
    if filled >= order_quantity and order_quantity > 0:
        return FILLED, filled
    if any(a.kind == "cancel" for a in acts):
        return CANCELLED, filled
    if any(a.kind == "expire" for a in acts):
        return EXPIRED, filled
    if filled > 0:
        return PARTIAL, filled
    return OPEN, filled


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

        activities = self._fetch_activities(result)
        if activities is None:            # fetch failed; error already recorded
            return result

        by_order: dict[str, list[Activity]] = {}
        for raw in activities:
            act = normalize_activity(raw)
            if act is None:
                result.unparsed_activities += 1
                log.warning(
                    "fill_watcher_unparsed_activity",
                    keys=sorted(raw.keys())[:12],
                    note="schema drift? attribution needs a venue order id and "
                         "a recognisable type — this activity was ignored, "
                         "never guessed at",
                )
                continue
            by_order.setdefault(act.venue_order_id, []).append(act)

        now = dt.datetime.now(UTC)
        with self._Session() as s:
            for order in tracked:
                row = s.get(PlacedOrder, order.id)
                acts = by_order.get(row.venue_order_id, [])
                status, filled = reconcile_order(row.quantity, acts)
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

    def _fetch_activities(self, result: PollResult) -> list[dict] | None:
        client = self._read_client or PolymarketAuthedClient(self._creds)
        owns = self._read_client is None
        try:
            acts_resp = client.get(ACTIVITIES_PATH)
            if acts_resp.status_code != 200:
                result.error = f"activities HTTP {acts_resp.status_code}"
                log.warning("fill_watcher_activities_unavailable",
                            status=acts_resp.status_code)
                return None
            import json as _json
            try:
                body = _json.loads(acts_resp.body_text)
            except ValueError:
                result.error = "activities body not JSON"
                return None

            # Positions: context only. Logged so a human can eyeball the
            # account against the orders table; NEVER used for attribution.
            pos_resp = client.get(POSITIONS_PATH)
            if pos_resp.status_code == 200:
                result.notes.append("positions read ok")
            return _extract_activity_list(body)
        except Exception as exc:
            result.error = f"fetch failed: {str(exc)[:200]}"
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
