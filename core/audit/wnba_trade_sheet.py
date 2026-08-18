"""One row per WNBA fill on the operator's account, for hand annotation.

**DESCRIPTIVE, like its neighbour :mod:`core.audit.hand_trades`.** This module
reports what was traded and what it returned. It draws no conclusion; the
conclusions are the three empty columns the operator fills in by hand.

Two venue facts this module depends on, both verified live against
``api.polymarket.us`` on 2026-08-17 over the full account history (681
activities, 455 trades). Neither was taken from a doc or an adjacent module.

**1. Which execution is ours: ``trade.isAggressor``.**
Every ``ACTIVITY_TYPE_TRADE`` carries BOTH ``aggressorExecution`` and
``passiveExecution`` — 455 of 455, neither ever null — and the two are the two
counterparties of a single trade: same price, opposite order side, in 455 of
455. Exactly one is ours, and ``isAggressor`` says which (397 True / 58 False).
Confirmed independently against our own ``orders`` table: of the five venue
order ids this system has placed, three appear on the ``isAggressor``-selected
side and **zero** on the other. Taking both sides would book a phantom
offsetting fill against every real one.

.. warning::
   ``hand_trades.parse_activity`` still walks both keys, on the belief that
   "the feed nulls the side that is not ours". That is not true of the live
   feed. Its numbers are affected; this module does not share the code path.

**2. Which side of the market we took: YES is the first slug team, or Over.**
``market.marketSides`` marks the YES outcome with ``long: true``, and
``order.marketMetadata.outcome`` labels *the side our own order took*. Against
those two fields, the derivation below reproduced the venue's own label for
**94 of 94** WNBA fills — 51 totals/spreads matched exactly, and all 43
moneylines matched the venue's ``team.abbreviation``:

* totals (``tsc``)     — YES = Over, NO = Under;
* spreads (``asc``)    — YES = first slug team at the slug's signed line,
  NO = the other team at the negated line;
* moneyline (``aec``)  — YES = first slug team, NO = the other team.

``market.outcomes`` is NOT usable: its array order flips between markets
(``["Under","Over"]`` and ``["Over","Under"]`` both occur). ``marketSides``
and ``marketMetadata.outcome`` are consistent.

Money, and where P&L is booked
------------------------------
Costs follow C11, the same frame as :mod:`core.audit.hand_trades`: a YES
contract costs the price paid, a NO contract costs ``1 - price``, because the
venue quotes every price in the YES frame (V14/V19).

P&L is booked on **entry rows only**, matched FIFO. A fill that opens exposure
carries ``dollars_in``; whatever that lot later returns — from closing trades,
from settlement, or both — lands in ``dollars_out`` on that same row, and
``pnl`` is the difference. A fill that only closes earlier exposure carries no
money of its own; its proceeds are already credited to the entry it closed.
So the three money columns sum without double counting, and the operator's
"why I made this trade" note sits on the row that has the P&L.

An unknown settlement leaves the lot OPEN and unscored rather than guessing a
payout — an unscored row is honest, a guessed one is not.

The contract traded is not always the position held
--------------------------------------------------
Selling the Under contract is being long the Over. So the sheet carries both:
``market`` names the contract as the venue labels it, and ``position`` names
the exposure the fill actually put on. Without the second column, the operator
sold the Under on ATL/DAL 181.5 on 2026-07-29, the total came in under the
line, and the row shows a $4.90 loss — which, read from the contract alone,
looks like a bet that won and lost money.

Slug team order is POSITIONAL ONLY. It is not home/away (see
:mod:`core.team_mapping`), so the ``game`` column never claims to be.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from core.team_mapping import ParsedSlug, UnknownTeamError, parse_market_slug

UTC = dt.timezone.utc
CENTRAL = ZoneInfo("America/Chicago")

ZERO = Decimal("0")
ONE = Decimal("1")

ACTIVITY_TRADE = "ACTIVITY_TYPE_TRADE"
ACTIVITY_RESOLUTION = "ACTIVITY_TYPE_POSITION_RESOLUTION"

#: Slug suffixes carrying the line: ``-neg-10pt5`` / ``-pos-13pt5`` (spreads,
#: signed) and ``-164pt5`` (totals, unsigned). Checked signed-first, because a
#: bare ``\d+pt\d`` also matches the tail of a spread slug.
_SIGNED_LINE = re.compile(r"-(neg|pos)-(\d+)pt(\d)$")
_PLAIN_LINE = re.compile(r"-(\d+)pt(\d)$")


def line_from_slug(slug: str) -> Decimal | None:
    """The market's line, signed, recovered from the slug alone.

    From the slug and not from ``market.line`` so the sheet covers markets the
    local recorder never saw — the operator traded before the recorder ran.
    """
    m = _SIGNED_LINE.search(slug or "")
    if m:
        value = Decimal(f"{m.group(2)}.{m.group(3)}")
        return -value if m.group(1) == "neg" else value
    m = _PLAIN_LINE.search(slug or "")
    if m:
        return Decimal(f"{m.group(1)}.{m.group(2)}")
    return None


def market_label(parsed: ParsedSlug, slug: str, outcome_yes: bool) -> str:
    """The position taken, as a human reads it: ``OVER 164.5``, ``CHI -10.5``.

    Reproduces the venue's own ``marketMetadata.outcome`` for every fill on
    the account (94/94); see the module docstring.
    """
    line = line_from_slug(slug)
    if parsed.market_type == "tsc":
        side = "OVER" if outcome_yes else "UNDER"
        return f"{side} {line:g}" if line is not None else side
    try:
        team = parsed.first_espn if outcome_yes else parsed.second_espn
    except UnknownTeamError:
        team = (parsed.first_polymarket if outcome_yes
                else parsed.second_polymarket).upper()
    if parsed.market_type == "asc":
        if line is None:
            return f"{team} spread"
        signed = line if outcome_yes else -line
        return f"{team} {signed:+g}"
    return f"{team} to win"


def game_label(parsed: ParsedSlug) -> str:
    """``GSV / PHX 2026-07-29``. A slash, not "vs" or "@": the slug's team
    order is positional and does NOT encode home/away, so the label must not
    imply one (see :mod:`core.team_mapping`)."""
    try:
        first, second = parsed.first_espn, parsed.second_espn
    except UnknownTeamError:
        first, second = parsed.first_polymarket.upper(), parsed.second_polymarket.upper()
    return f"{first} / {second} {parsed.local_date.isoformat()}"


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WnbaFill:
    """One of OUR executions on a WNBA market, in the venue's YES frame."""

    market_slug: str
    parsed: ParsedSlug
    at: dt.datetime
    venue_order_id: str
    is_buy: bool
    outcome_yes: bool
    yes_price: Decimal
    shares: Decimal
    commission: Decimal

    @property
    def yes_delta(self) -> Decimal:
        """Signed YES exposure: buying YES or selling NO is +, else −."""
        return (ONE if self.is_buy == self.outcome_yes else -ONE) * self.shares

    @property
    def game(self) -> str:
        return game_label(self.parsed)

    @property
    def market(self) -> str:
        """The contract traded, as the VENUE labels it — this reproduces
        ``order.marketMetadata.outcome`` exactly (94/94)."""
        return market_label(self.parsed, self.market_slug, self.outcome_yes)

    @property
    def exposure(self) -> str:
        """The position this fill actually puts on, which is NOT always the
        contract named in :attr:`market`.

        Selling the Under contract is being long the Over. A sheet that showed
        only ``UNDER 181.5 / SELL`` for such a fill reads, when that total
        comes in under the line and the row shows a loss, as a bet that won
        and lost money. This column states the exposure directly so the two
        cannot be confused.
        """
        return market_label(self.parsed, self.market_slug, self.yes_delta > 0)


@dataclass(frozen=True)
class Resolution:
    market_slug: str
    at: dt.datetime


def _parse_ts(value) -> dt.datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        # RFC3339 with nanoseconds — trim to microseconds for fromisoformat.
        if "." in text and text.endswith("Z"):
            head, frac = text[:-1].split(".", 1)
            text = f"{head}.{frac[:6]}Z"
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def our_execution(trade: dict) -> dict | None:
    """OUR side of a two-sided trade record — never the counterparty's.

    ``isAggressor`` is the discriminator; see the module docstring for the
    verification. Returns None when the selected side is absent.
    """
    key = "aggressorExecution" if trade.get("isAggressor") else "passiveExecution"
    execution = trade.get(key)
    return execution if isinstance(execution, dict) else None


def parse_activity(raw: dict) -> tuple[WnbaFill | None, Resolution | None, bool]:
    """One raw activity → (our WNBA fill, WNBA resolution, parsed_ok).

    Non-WNBA markets and non-trade activity types return ``(None, None, True)``
    — benign, nothing to score. ``ok=False`` marks a shape we expected to
    understand and did not, which the caller counts loudly rather than
    silently dropping.
    """
    kind = raw.get("type")
    if kind == ACTIVITY_RESOLUTION:
        pr = raw.get("positionResolution") or {}
        slug = pr.get("marketSlug") or ""
        if not parse_market_slug(slug):
            return None, None, True
        at = _parse_ts(pr.get("updateTime"))
        if at is None:
            return None, None, False
        return None, Resolution(market_slug=slug, at=at), True
    if kind != ACTIVITY_TRADE:
        return None, None, True

    trade = raw.get("trade") or {}
    execution = our_execution(trade)
    if execution is None:
        return None, None, False
    order = execution.get("order") or {}
    slug = str(trade.get("marketSlug") or order.get("marketSlug") or "")
    parsed = parse_market_slug(slug)
    if not parsed:
        return None, None, True          # another league — not this sheet

    price = _dec((execution.get("lastPx") or {}).get("value"))
    shares = _dec(execution.get("lastShares"))
    at = _parse_ts(execution.get("transactTime"))
    side = str(order.get("side") or "")
    outcome = str(order.get("outcomeSide") or "")
    oid = order.get("id")
    if (not oid or price is None or shares is None or at is None
            or "SIDE" not in side or "OUTCOME" not in outcome):
        return None, None, False
    return WnbaFill(
        market_slug=slug,
        parsed=parsed,
        at=at,
        venue_order_id=str(oid),
        is_buy="BUY" in side,
        outcome_yes=outcome.endswith("_YES"),
        yes_price=price,
        shares=shares,
        commission=_dec((execution.get("commissionNotionalCollected") or {})
                        .get("value")) or ZERO,
    ), None, True


# --------------------------------------------------------------------------- #
# FIFO attribution — P&L is booked on the entry row
# --------------------------------------------------------------------------- #


ROLE_ENTRY = "ENTRY"
ROLE_EXIT = "EXIT"
ROLE_BOTH = "EXIT+ENTRY"


@dataclass
class SheetRow:
    """One fill, with the money its own exposure staked and returned.

    ``dollars_in``/``dollars_out``/``pnl`` describe ONLY the exposure this fill
    opened. A fill that merely closed an earlier lot carries no money here —
    those proceeds are credited to the entry row that staked them — so summing
    any money column over the sheet double-counts nothing.
    """

    fill: WnbaFill
    dollars_in: Decimal = ZERO
    dollars_out: Decimal = ZERO
    opened: Decimal = ZERO           # contracts this fill put on
    open_remaining: Decimal = ZERO   # of those, still not closed
    closed_a_lot: bool = False       # did this fill close someone else's lot?
    _exit_kinds: set[str] = field(default_factory=set)

    @property
    def role(self) -> str:
        if self.closed_a_lot and self.opened > 0:
            return ROLE_BOTH
        return ROLE_EXIT if self.closed_a_lot else ROLE_ENTRY

    @property
    def closed_by(self) -> str:
        """How the exposure THIS fill opened was closed."""
        if self.opened == 0:
            return ""                        # pure exit — nothing of its own
        if self.open_remaining > 0:
            return "partial" if self._exit_kinds else "open"
        if self._exit_kinds == {"trades", "settlement"}:
            return "mixed"
        return next(iter(self._exit_kinds), "open")

    @property
    def fully_closed(self) -> bool:
        return self.opened > 0 and self.open_remaining == 0

    @property
    def pnl(self) -> Decimal | None:
        """Blank until the lot is fully closed. A still-open lot has paid out
        nothing yet, and reporting cost-with-no-return as a loss would read as
        a result rather than an unfinished position."""
        return self.dollars_out - self.dollars_in if self.fully_closed else None

    @property
    def position(self) -> str:
        """What this fill put on. Blank for a pure exit, which puts on nothing
        — the same rule the money columns follow."""
        return self.fill.exposure if self.opened > 0 else ""

    @property
    def entry_cost(self) -> Decimal | None:
        """Cost per contract — this row's breakeven (C11)."""
        return None if self.opened == 0 else self.dollars_in / self.opened


def _cost_per_contract(long: bool, yes_price: Decimal) -> Decimal:
    """C11: a YES contract costs the price paid, a NO contract costs 1 − price."""
    return yes_price if long else ONE - yes_price


@dataclass
class _Lot:
    qty: Decimal
    long: bool
    row: SheetRow


def build_rows(
    fills: list[WnbaFill],
    resolutions: list[Resolution],
    settlement_lookup,
) -> tuple[list[SheetRow], list[str]]:
    """(rows in time order, markets left unscored).

    ``settlement_lookup(market_slug) -> Decimal | None`` gives the YES payout
    (0 or 1) for a settled market, None when unknown. Unknown leaves the lot
    open and the market named in the second return value — never guessed.
    """
    # Keyed by position in `fills`, never by the fill itself: two fills can be
    # field-for-field equal (same market, instant, price and size) and would
    # collide as dict keys, silently merging two real trades into one row.
    rows: dict[int, SheetRow] = {i: SheetRow(fill=f) for i, f in enumerate(fills)}
    by_market: dict[str, list] = {}
    for i, f in enumerate(fills):
        by_market.setdefault(f.market_slug, []).append((f.at, 0, i, f))
    for r in resolutions:
        by_market.setdefault(r.market_slug, []).append((r.at, 1, -1, r))

    unscored: list[str] = []

    for slug, events in sorted(by_market.items()):
        # Fills before resolutions at the same instant: a position must be on
        # the books before settlement can close it.
        events.sort(key=lambda e: (e[0], e[1], e[2]))
        lots: deque[_Lot] = deque()

        for _, _, index, event in events:
            if isinstance(event, Resolution):
                if not lots:
                    continue
                payout = settlement_lookup(slug)
                if payout is None:
                    unscored.append(slug)
                    continue                 # left open, reported, not guessed
                while lots:
                    lot = lots.popleft()
                    per = payout if lot.long else ONE - payout
                    lot.row.dollars_out += lot.qty * per
                    lot.row.open_remaining -= lot.qty
                    lot.row._exit_kinds.add("settlement")
                continue

            fill: WnbaFill = event
            row = rows[index]
            delta = fill.yes_delta

            # Closing part: whatever of this fill reduces the open position.
            while lots and delta != 0 and (delta > 0) != lots[0].long:
                lot = lots[0]
                take = min(abs(delta), lot.qty)
                per = _cost_per_contract(lot.long, fill.yes_price)
                lot.row.dollars_out += take * per
                lot.row.open_remaining -= take
                lot.row._exit_kinds.add("trades")
                lot.qty -= take
                if lot.qty == 0:
                    lots.popleft()
                delta += take if delta < 0 else -take
                row.closed_a_lot = True

            # Opening part: whatever remains puts on new exposure.
            if delta != 0:
                long = delta > 0
                qty = abs(delta)
                per = _cost_per_contract(long, fill.yes_price)
                row.dollars_in += qty * per
                row.opened += qty
                row.open_remaining += qty
                lots.append(_Lot(qty=qty, long=long, row=row))

    ordered = sorted(rows.values(), key=lambda r: (r.fill.at, r.fill.market_slug))
    return ordered, sorted(set(unscored))
