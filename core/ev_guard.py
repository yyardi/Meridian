"""EV stop-loss guard: hypothesis #9 as an ALERT, never an execution path.

What it does
------------
For every open venue position this system placed (fill-watcher state:
accepted buys with a venue-confirmed filled quantity), continuously compare
the **live formula fair value** against the position's entry cost, in the
position's own cost frame:

* **EDGE GONE** — FV has fallen to or below entry. The reason for holding the
  position no longer exists *according to the formula*. Push an ntfy alert
  ("FV 0.18 < your 0.23: edge gone") and mark the row on /picks with the same
  urgency as a FAILED exit.
* **PRICE NOISE — FV INTACT** (the #11 mirror) — the market price has dropped
  below entry but FV has not. The drawdown is, per the formula, noise; the
  row says so, so averaging-down has an honest signal instead of a red number
  and an itchy finger.
* **EDGE INTACT** — neither. Quiet.
* **NO FORMULA FV** — the game is not live, the clock estimate has degraded
  past usefulness, or the market type has no live formula. Said outright
  rather than silently skipping the row: a guard that covers part of the book
  must say which part.

**Coverage, as of 2026-08-07:** live **moneylines** (win curve,
`core/live_fv.py`) and live **totals** (per-period totals model,
`core/live_totals_fv.py`). **Spreads are not priced live** and say so. Totals
coverage is the half that matters most here — the hand-trade audit's one
measured-positive pocket is the user's live-totals trading (+9.4%, n=31,
descriptive), and what was missing there was a number to hold a price
against.

What it deliberately is not
---------------------------
**NO automatic selling. NO order integration.** This module imports nothing
from `core.executor` or `core.polymarket.client` and has no code path to
either — pinned by test, same as the live-FV strip it builds on. It computes
verdicts and, at most, POSTs a notification to the user's ntfy topic. The
human acts on it from their phone — which is aimed at the one
measured-positive pocket in the hand-trade audit, their live-totals in-game
trading, where what was missing was a timely signal, not a button.

Every verdict is driven by the **UNVALIDATED formula FV** and carries the
same caption as the strip. The formula's one contact with a pre-registered
gate (hypothesis #16) passed and then inverted under a confound check —
that history rides along with every alert this module sends.

Frames, because every previous frame bug cost something
-------------------------------------------------------
`LiveFV.fair_value` is P(first team wins) in the YES frame (V20: the venue's
`event_score` and slug agree on who "first" is, 12/12 settled games).
A `buy_yes` position's entry cost is the stored YES-frame `limit_price`; a
`buy_no` position's cost is `1 − limit_price`, and its fair value is
`1 − FV`. All comparisons happen in the position's cost frame, unit-tested
in both directions.

Alert discipline
----------------
Transitions only, once per order per crossing: an alert that re-fires every
cycle while FV sits below entry is an alarm that gets muted. Recovery back
above entry re-arms the alert (and pushes a one-line all-clear, so a phone
that saw "edge gone" is not left believing it forever).
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx
import structlog

from core.live_fv import build_live_fv
from core.live_totals_fv import build_live_totals_fv
from core.storage import PlacedOrder

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Verdicts. String constants, not an enum — they go straight into JSON.
EDGE_GONE = "EDGE_GONE"
PRICE_NOISE = "PRICE_NOISE"
INTACT = "INTACT"
NO_FV = "NO_FV"

#: The caption every payload and push carries. Same wording family as the
#: live-FV strip: the number is unvalidated and nothing trades on it.
CAPTION = "formula FV — unvalidated; information only, nothing sells on this"

CYCLE_SECONDS = 60.0


# --------------------------------------------------------------------- #
# Pure logic — the part the tests pin
# --------------------------------------------------------------------- #


def position_frame(side: str, limit_price: Decimal | float) -> tuple[str, float]:
    """(outcome, entry cost per contract) in the position's own frame.

    `side` is the orders table's `buy_yes` / `buy_no`. The stored
    `limit_price` is ALWAYS the YES-frame price.value (V14), so a NO buy's
    cost is its complement — converted here, once, and nowhere else.
    """
    p = float(limit_price)
    if side == "buy_no":
        return "NO", 1.0 - p
    return "YES", p


def fv_in_position_frame(fair_value: float | None, outcome: str) -> float | None:
    """The formula FV (YES frame) seen from the position's side."""
    if fair_value is None:
        return None
    return 1.0 - fair_value if outcome == "NO" else fair_value


def mid_in_position_frame(mid: float | None, outcome: str) -> float | None:
    if mid is None:
        return None
    return 1.0 - mid if outcome == "NO" else mid


def evaluate(*, entry_cost: float, fv: float | None,
             mid: float | None) -> tuple[str, str]:
    """One position → (verdict, human sentence). All inputs position-frame.

    The order of the tests is the design:

    1. No FV → NO_FV. Without the formula there is no verdict, and pretending
       the market price alone is a verdict is exactly what the mirror guard
       exists to prevent.
    2. FV ≤ entry → EDGE_GONE, whatever the price is doing. The hypothesis-#9
       trigger is the *model's* number crossing the entry, not the market's —
       a position can be up money with the edge gone.
    3. Price below entry but FV above → PRICE_NOISE. The #11 mirror: the
       drawdown is real, the formula's reason to hold is intact.
    4. Otherwise INTACT.
    """
    if fv is None:
        return NO_FV, "no formula FV for this market/state"
    if fv <= entry_cost:
        return EDGE_GONE, (
            f"FV {fv:.2f} ≤ your {entry_cost:.2f}: edge gone"
        )
    if mid is not None and mid < entry_cost:
        return PRICE_NOISE, (
            f"price {mid:.2f} < your {entry_cost:.2f} but FV {fv:.2f} holds: "
            "price noise — FV intact"
        )
    return INTACT, f"FV {fv:.2f} vs your {entry_cost:.2f}: edge intact"


# --------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class GuardRow:
    order_id: int
    market_slug: str
    label: str
    outcome: str
    entry_cost: float
    filled_quantity: float
    fv: float | None            # position frame
    mid: float | None           # position frame
    verdict: str
    message: str

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "market_slug": self.market_slug,
            "label": self.label,
            "outcome": self.outcome,
            "entry_cost": round(self.entry_cost, 4),
            "filled_quantity": self.filled_quantity,
            "fv": None if self.fv is None else round(self.fv, 4),
            "mid": None if self.mid is None else round(self.mid, 4),
            "verdict": self.verdict,
            "message": self.message,
        }


def open_positions(session) -> list[PlacedOrder]:
    """Button-order positions that still exist: accepted buys with a
    venue-confirmed fill and no settlement behind them.

    Venue truth only — `filled_quantity` is the fill watcher's number, never
    inferred. EXPIRED rows are excluded because the watcher only marks
    EXPIRED at settlement, and a settled position has nothing left to guard.
    Positions opened by hand in the app are invisible here on purpose: this
    guard covers what the button bought.
    """
    cutoff = dt.datetime.now(UTC) - dt.timedelta(hours=24)
    return session.query(PlacedOrder).filter(
        PlacedOrder.accepted.is_(True),
        PlacedOrder.side.like("buy_%"),
        PlacedOrder.filled_quantity > 0,
        PlacedOrder.fill_status.in_(("FILLED", "PARTIAL", "CANCELLED")),
        # WNBA positions settle same-night; a FILLED row keeps its status
        # after settlement (terminal rows leave the watcher's tracking), so
        # without a time bound every historical position would sit in the
        # guard as NO_FV forever.
        PlacedOrder.submitted_at >= cutoff,
    ).all()


def build_guard_rows(session) -> list[GuardRow]:
    """Every open position, judged against the live formula FV."""
    positions = open_positions(session)
    if not positions:
        return []

    # Two formulas, one map. Moneylines are priced by the win curve
    # (`core/live_fv.py`); totals by the per-period totals model
    # (`core/live_totals_fv.py`). Both expose `.fair_value` in the YES frame
    # and `.mid`, so everything downstream is identical — and both are equally
    # UNVALIDATED, which is the caption every verdict carries.
    #
    # Totals coverage closed the gap this module used to name outright, and it
    # is the half that matters most: the hand-trade audit's one measured
    # positive pocket is the user's live-totals trading.
    fv_by_market: dict = {r.market_slug: r for r in build_live_fv(session)}
    fv_by_market.update({r.market_slug: r for r in build_live_totals_fv(session)})

    rows: list[GuardRow] = []
    for p in positions:
        outcome, entry_cost = position_frame(p.side, p.limit_price)
        live = fv_by_market.get(p.market_slug)
        if live is None:
            fv = mid = None
            # Spreads are the remaining uncovered type: nothing prices a
            # handicap live yet. Saying which half is uncovered beats a silent
            # gap.
            reason = (
                "formula FV covers live moneylines and totals; spreads are "
                "not priced live"
                if (p.sports_market_type or "").endswith("spread")
                else "market not live (or FV suppressed for clock/OT reasons)"
            )
        else:
            fv = fv_in_position_frame(live.fair_value, outcome)
            mid = mid_in_position_frame(live.mid, outcome)
            reason = None
        verdict, message = evaluate(entry_cost=entry_cost, fv=fv, mid=mid)
        if reason and verdict == NO_FV:
            message = reason
        rows.append(GuardRow(
            order_id=p.id,
            market_slug=p.market_slug,
            label=p.market_slug,
            outcome=outcome,
            entry_cost=entry_cost,
            filled_quantity=float(p.filled_quantity),
            fv=fv,
            mid=mid,
            verdict=verdict,
            message=message,
        ))
    return rows


# --------------------------------------------------------------------- #
# The alert loop
# --------------------------------------------------------------------- #


def _push_ntfy(topic: str, title: str, body: str, *, priority: int,
               tags: str, server: str | None = None) -> bool:
    """One ntfy JSON publish. Self-contained on purpose: `core.alerter` is a
    separate service with its own lifecycle, and this in-process guard must
    not couple the API's import graph to it. JSON publish, not headers —
    headers are ascii-only and titles here carry ≤/¢."""
    base = (server or os.environ.get("MERIDIAN_NTFY_SERVER")
            or "https://ntfy.sh").rstrip("/")
    try:
        r = httpx.post(base, json={
            "topic": topic, "title": title, "message": body,
            "priority": priority, "tags": tags.split(",") if tags else [],
        }, timeout=20)
        r.raise_for_status()
        log.info("ev_guard_push_sent", title=title)
        return True
    except Exception as exc:
        log.error("ev_guard_push_failed", title=title, error=str(exc)[:200])
        return False


class EVGuard:
    """Background loop: build rows, push transitions, remember state.

    Read-only against the database; its only side effect is an ntfy POST.
    There is no code path from here to an order, and a test pins that.
    """

    def __init__(self, sessionmaker, *, topic: str | None = None,
                 cycle_seconds: float = CYCLE_SECONDS, pusher=None):
        self._Session = sessionmaker
        self._topic = topic
        self.cycle_seconds = cycle_seconds
        self._pusher = pusher or _push_ntfy
        #: order_id -> last verdict, for transition detection.
        self._last: dict[int, str] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ev-guard", daemon=True)
        self._thread.start()
        log.info("ev_guard_started", cycle_seconds=self.cycle_seconds,
                 pushes_enabled=bool(self._topic))

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception as exc:
                log.error("ev_guard_cycle_failed", error=str(exc)[:300])
            self._stop.wait(self.cycle_seconds)

    def check_once(self) -> list[GuardRow]:
        """One evaluation. Public so tests drive it directly."""
        with self._Session() as s:
            rows = build_guard_rows(s)

        for row in rows:
            prev = self._last.get(row.order_id)
            self._last[row.order_id] = row.verdict

            if row.verdict == EDGE_GONE and prev != EDGE_GONE:
                log.warning("ev_guard_edge_gone", order_id=row.order_id,
                            market=row.market_slug, message=row.message)
                if self._topic:
                    self._pusher(
                        self._topic,
                        f"EDGE GONE — {row.label}",
                        f"{row.message}\n"
                        f"position: {row.filled_quantity:g} @ "
                        f"{row.entry_cost:.2f} ({row.outcome})\n"
                        f"{CAPTION}",
                        priority=5, tags="rotating_light",
                    )
            elif prev == EDGE_GONE and row.verdict in (INTACT, PRICE_NOISE):
                # The all-clear, once: a phone that saw "edge gone" must not
                # be left believing it after FV recovers.
                log.info("ev_guard_edge_recovered", order_id=row.order_id)
                if self._topic:
                    self._pusher(
                        self._topic,
                        f"FV recovered — {row.label}",
                        f"{row.message}\n{CAPTION}",
                        priority=3, tags="white_check_mark",
                    )
        # Positions that vanished (settled/closed) drop out of the state map
        # so a future position reusing nothing re-alerts cleanly.
        seen = {r.order_id for r in rows}
        for oid in list(self._last):
            if oid not in seen:
                del self._last[oid]
        return rows
