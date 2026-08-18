"""The account's real balance, read from the venue. **No constant anywhere.**

Why this module exists
----------------------
Every dollar figure the system computes is a fraction of a bankroll: the Kelly
stake, the ticket's size and stake columns, the per-order fat-finger cap. Until
2026-08-17 that bankroll was the literal ``35.68``, typed into
``core/scheduler.py`` on the day someone last looked at the app and passed
down through ``shadow_run``. The account was at **$23.82** by then — so every
size on the board was ~50% too large, and the error grew silently with every
fill and every withdrawal.

A number that decays without anybody noticing is not a parameter, it is a bug
with a decimal point. The venue knows the answer; ask it.

Read-only, structurally
-----------------------
The balance comes from :class:`core.polymarket.client.PolymarketAuthedClient`,
which exposes ``get`` and ``close`` and no other verb — there is no code path
from this module to an order. Credentials come from the environment via
``USCredentials.from_env`` and are never logged: the client logs only the
fingerprint (lengths and a truncated hash).

What "bankroll" means here
--------------------------
The venue answers ``/v1/account/balances`` with, observed live 2026-08-17::

    {"balances":[{"currentBalance":23.8204, "currency":"USD",
                  "buyingPower":23.8204, "assetNotional":0, "assetAvailable":0,
                  "pendingCredit":0, "openOrders":0, "unsettledFunds":0,
                  "pendingWithdrawals":[], "marginRequirement":0}]}

Kelly's ``f*`` is a fraction of *total wealth*, which argues for
``cash + assetNotional``. But every field except the first two was zero on
every observation so far, so **the arithmetic relating them is unverified**,
and Kelly is brutally asymmetric to over-betting (twice the optimal fraction
has zero expected growth — ``docs/math/kelly.md``). Under-betting costs growth
linearly; over-betting can cost the account. So:

    bankroll = min(currentBalance, buyingPower)

— the smallest defensible reading, and a strict lower bound on wealth under
any interpretation of the other fields. :func:`parse_balances` logs loudly the
first time any of ``assetNotional``, ``openOrders`` or ``unsettledFunds`` is
non-zero, because that is the observation which would let this definition be
tightened honestly.

Failure is a refusal, not a guess
---------------------------------
There is no default. If the venue cannot be reached and no stored reading is
fresh enough, :func:`current` raises :class:`BankrollUnavailable` and the
callers size nothing. A fallback constant is exactly the failure this module
was written to delete — it would be indistinguishable, on screen, from a real
balance.

Positions, and what "equity" means here (2026-08-18)
----------------------------------------------------
The operator held an open position while ``assetNotional`` read 0 — the
balances payload does not carry positions on this venue. They live at
``GET /v1/portfolio/positions`` (docs.polymarket.us): a **map** of market slug
to position, with ``netPositionDecimal`` (signed quantity), ``cost`` (basis)
and ``cashValue``. The docs disagreed with themselves about ``cashValue`` —
the REST page called it "unrealized PnL", the SDK page "current unrealized
value" — and **Polymarket support settled it (2026-08-18)**: ``cashValue`` is
the position's current market value, unrealized PnL is ``cashValue − cost``,
and ``assetNotional`` staying 0 while positions are open is *intended* —
position exposure is represented only through the positions endpoint. The
clamp to ±quantity stays (a binary contract is worth at most $1; it now
guards venue-side bugs rather than a doc reading), and
``verify_position_value`` stays as the empirical cross-check of what support
said — a confirmation in an email is not yet an observation in a log.

Two numbers now leave this module, deliberately distinct:

* ``bankroll`` — **sizing**. Unchanged: ``min(cash, buyingPower)``. Position
  value is not spendable on the next order, and Kelly is brutally asymmetric
  to over-betting.
* ``equity`` — **display**. ``bankroll`` plus the clamped position values:
  what the account is worth, which is what the operator watching a live trade
  actually asked for.

A positions read that fails does not fail the balance: the snapshot then says
``positions_read_ok = False`` and the pages render "positions unread" — an
unread position book is a different claim from an empty one.

    python -m core.bankroll            # print the current balance
    python -m core.bankroll --refresh  # poll the venue and store the reading
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

import structlog
from sqlalchemy import select

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc

#: Verified live 2026-08-17 (200, ~30ms at the venue). `/v1/balance` and
#: `/v1/portfolio` do **not** exist — they 404 once authenticated, which is how
#: the old 401s were finally diagnosed. See `scripts/probe_authed_read.py`.
BALANCES_PATH = "/v1/account/balances"

#: The venue's position book. Same signed-GET client, same read-only property.
POSITIONS_PATH = "/v1/portfolio/positions"

#: Pagination guard. The venue pages positions like activities (cursor/eof);
#: one page of 100 has always sufficed for this account.
POSITIONS_PAGE_LIMIT = 100
POSITIONS_MAX_PAGES = 10

#: How old a stored reading may be before a reader refuses to use it. The
#: scheduler's fast leg is 20 minutes and refreshes at the top of every cycle,
#: so anything older than this means the poller itself is not running.
DEFAULT_MAX_AGE_SECONDS = 1800.0

ZERO = Decimal("0")


class BankrollUnavailable(RuntimeError):
    """The real balance could not be established. **Never** substitute a guess.

    Raised rather than returning a default because the two are
    indistinguishable downstream: a fabricated bankroll produces a plausible
    stake on a plausible-looking ticket.
    """


def _dec(value, field: str) -> Decimal:
    if value is None:
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BankrollUnavailable(f"balance field {field!r} is not a number") from exc


def _amount(obj, field: str) -> Decimal:
    """The venue's Amount objects are ``{"value": "1.23", "currency": "USD"}``;
    a bare number is tolerated because the docs show both styles."""
    if obj is None:
        return ZERO
    if isinstance(obj, dict):
        return _dec(obj.get("value"), field)
    return _dec(obj, field)


@dataclass(frozen=True)
class Position:
    """One open position, in the venue's own fields.

    ``value`` is the equity contribution: ``cashValue``, confirmed by venue
    support (2026-08-18) as the position's current market value. Clamped to
    ±``quantity`` because a binary contract is worth at most $1 — the clamp
    now guards venue-side bugs, not a doc ambiguity.
    """

    market_slug: str
    quantity: Decimal            # netPositionDecimal; positive = long
    quantity_available: Decimal
    cost: Decimal
    cash_value: Decimal
    realized: Decimal
    expired: bool
    title: str | None = None
    outcome: str | None = None

    @property
    def value(self) -> Decimal:
        cap = abs(self.quantity)
        return max(-cap, min(self.cash_value, cap))

    @property
    def unrealized(self) -> Decimal:
        """``cashValue − cost`` — support's definition, stated explicitly so
        no reader re-derives it wrong from the once-ambiguous docs."""
        return self.value - self.cost

    def to_dict(self) -> dict:
        return {
            "market_slug": self.market_slug,
            "quantity": float(self.quantity),
            "quantity_available": float(self.quantity_available),
            "cost": float(self.cost),
            "cash_value": float(self.cash_value),
            "value": float(self.value),
            "realized": float(self.realized),
            "unrealized": float(self.unrealized),
            "expired": self.expired,
            "title": self.title,
            "outcome": self.outcome,
        }


def parse_positions(body: dict) -> list[Position]:
    """Venue payload → positions. The map may be empty; that IS "no positions".

    Observed live 2026-08-18: ``{"positions": {}, "nextCursor": "", "eof":
    true, "availablePositions": []}`` on a flat account — a dict keyed by
    market slug, exactly as documented, and unlike ``activities`` (a list).
    ``availablePositions`` is deprecated per the docs and never read.
    """
    posmap = (body or {}).get("positions")
    if posmap is None:
        raise BankrollUnavailable(
            "positions payload carried no 'positions' key; refusing to read "
            "that as flat")
    if not isinstance(posmap, dict):
        raise BankrollUnavailable(
            f"positions was {type(posmap).__name__}, expected a map of slug "
            "to position")
    out = []
    for slug, p in posmap.items():
        if not isinstance(p, dict):
            continue
        meta = p.get("marketMetadata") or {}
        out.append(Position(
            market_slug=str(meta.get("slug") or slug),
            quantity=_dec(p.get("netPositionDecimal"), "netPositionDecimal"),
            quantity_available=_dec(p.get("qtyAvailableDecimal"), "qtyAvailableDecimal"),
            cost=_amount(p.get("cost"), "cost"),
            cash_value=_amount(p.get("cashValue"), "cashValue"),
            realized=_amount(p.get("realized"), "realized"),
            expired=bool(p.get("expired")),
            title=meta.get("title"),
            outcome=meta.get("outcome"),
        ))
    return out


@dataclass(frozen=True)
class AccountSnapshot:
    """One reading of the account, in the venue's own fields."""

    observed_at: dt.datetime
    currency: str
    cash: Decimal                 # currentBalance
    buying_power: Decimal
    asset_notional: Decimal
    open_orders: Decimal
    unsettled_funds: Decimal
    pending_credit: Decimal
    margin_requirement: Decimal
    raw: dict | None = None
    positions: tuple[Position, ...] = ()
    #: False when balances were read but the positions endpoint was not — an
    #: unread position book is a different claim from an empty one.
    positions_read_ok: bool = False

    @property
    def bankroll(self) -> Decimal:
        """The number sizing uses. See the module docstring for the choice.

        Deliberately does NOT include position value: it is not spendable on
        the next order, and this is the input to Kelly.
        """
        return min(self.cash, self.buying_power)

    @property
    def positions_value(self) -> Decimal:
        return sum((p.value for p in self.positions), ZERO)

    @property
    def equity(self) -> Decimal:
        """What the account is worth: cash plus the clamped position values.
        Display only — sizing keeps using ``bankroll``."""
        return self.bankroll + self.positions_value

    @property
    def has_unverified_components(self) -> bool:
        """True once a field whose relationship to the others is unverified is
        non-zero — the observation that would let `bankroll` be tightened."""
        return any(v != ZERO for v in
                   (self.asset_notional, self.open_orders, self.unsettled_funds))

    def age_seconds(self, now: dt.datetime | None = None) -> float:
        return ((now or dt.datetime.now(UTC)) - self.observed_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "bankroll": float(self.bankroll),
            "equity": float(self.equity),
            "positions_value": float(self.positions_value),
            "n_positions": len(self.positions),
            "positions_read_ok": self.positions_read_ok,
            "positions": [p.to_dict() for p in self.positions],
            "currency": self.currency,
            "cash": float(self.cash),
            "buying_power": float(self.buying_power),
            "asset_notional": float(self.asset_notional),
            "open_orders": float(self.open_orders),
            "unsettled_funds": float(self.unsettled_funds),
            "observed_at": self.observed_at.isoformat(),
            "age_seconds": round(self.age_seconds(), 1),
        }


def parse_balances(body: dict, *, observed_at: dt.datetime | None = None) -> AccountSnapshot:
    """Venue payload → snapshot. Raises rather than defaulting on any surprise.

    The response is a *list* of per-currency balances. The USD entry is the
    account; a sole entry in another currency is taken with a warning rather
    than silently treated as dollars, and no entries at all is an error — an
    empty list is not "zero money", it is "the question was not answered".
    """
    entries = (body or {}).get("balances")
    if not isinstance(entries, list) or not entries:
        raise BankrollUnavailable(
            "balances payload carried no entries; refusing to read that as $0"
        )
    usd = [e for e in entries if isinstance(e, dict)
           and str(e.get("currency") or "").upper() == "USD"]
    if usd:
        entry = usd[0]
        if len(usd) > 1:
            log.warning("bankroll_multiple_usd_balances", count=len(usd),
                        note="using the first; the venue has never returned more than one")
    else:
        entry = next((e for e in entries if isinstance(e, dict)), None)
        if entry is None:
            raise BankrollUnavailable("balances payload had no object entries")
        log.warning("bankroll_no_usd_balance",
                    currency=str(entry.get("currency")),
                    note="no USD entry; sizing this account in another currency is "
                         "not something this system has ever verified")

    snapshot = AccountSnapshot(
        observed_at=observed_at or dt.datetime.now(UTC),
        currency=str(entry.get("currency") or "USD"),
        cash=_dec(entry.get("currentBalance"), "currentBalance"),
        buying_power=_dec(entry.get("buyingPower"), "buyingPower"),
        asset_notional=_dec(entry.get("assetNotional"), "assetNotional"),
        open_orders=_dec(entry.get("openOrders"), "openOrders"),
        unsettled_funds=_dec(entry.get("unsettledFunds"), "unsettledFunds"),
        pending_credit=_dec(entry.get("pendingCredit"), "pendingCredit"),
        margin_requirement=_dec(entry.get("marginRequirement"), "marginRequirement"),
        raw=body,
    )
    if snapshot.has_unverified_components:
        # First sighting of a non-zero component is the whole reason the
        # conservative definition is provisional. Say so where it will be read.
        log.warning(
            "bankroll_components_nonzero",
            asset_notional=float(snapshot.asset_notional),
            open_orders=float(snapshot.open_orders),
            unsettled_funds=float(snapshot.unsettled_funds),
            bankroll=float(snapshot.bankroll),
            note="min(cash, buyingPower) is a lower bound; the fields' arithmetic "
                 "is now observable and docs/infra/bankroll.md can be tightened",
        )
    return snapshot


def fetch_positions(client) -> list[Position]:
    """Signed GETs, paginated to ``eof``. Read-only, like everything here.

    Query parameters go through ``params=`` — the signature covers the bare
    path, and a query string embedded in the path signs the wrong message and
    401s (observed 2026-08-18).
    """
    out: list[Position] = []
    cursor: str | None = None
    for _ in range(POSITIONS_MAX_PAGES):
        params: dict = {"limit": POSITIONS_PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor
        resp = client.get(POSITIONS_PATH, params=params)
        if resp.status_code != 200:
            raise BankrollUnavailable(
                f"positions HTTP {resp.status_code}: {resp.body_text[:200]}")
        try:
            body = json.loads(resp.body_text)
        except ValueError as exc:
            raise BankrollUnavailable("positions body was not JSON") from exc
        out.extend(parse_positions(body))
        if body.get("eof") or not body.get("nextCursor"):
            return out
        cursor = body["nextCursor"]
    log.warning("bankroll_positions_pages_exhausted", pages=POSITIONS_MAX_PAGES,
                note="equity may under-count; raising the cap is safe")
    return out


def fetch(client=None) -> AccountSnapshot:
    """Two signed GETs. Read-only: the client has no verb but ``get``.

    A positions failure degrades rather than fails: the balance alone is
    still a true lower bound, and the snapshot says the position book went
    unread instead of pretending it was empty.
    """
    owned = client is None
    if owned:
        from core.polymarket.client import PolymarketAuthedClient, USCredentials
        client = PolymarketAuthedClient(USCredentials.from_env())
    try:
        resp = client.get(BALANCES_PATH)
        if resp.status_code != 200:
            raise BankrollUnavailable(
                f"balances HTTP {resp.status_code}: {resp.body_text[:200]}"
            )
        try:
            body = json.loads(resp.body_text)
        except ValueError as exc:
            raise BankrollUnavailable("balances body was not JSON") from exc
        snapshot = parse_balances(body)

        try:
            positions = tuple(fetch_positions(client))
            snapshot = replace(snapshot, positions=positions,
                               positions_read_ok=True)
            if positions:
                log.info("bankroll_positions",
                         n=len(positions),
                         positions_value=float(snapshot.positions_value),
                         equity=float(snapshot.equity))
        except Exception as exc:
            log.warning("bankroll_positions_unread", error=str(exc)[:200])
        return snapshot
    finally:
        if owned:
            client.close()


def verify_position_value(position: Position, mid: float) -> str:
    """Does ``cashValue`` behave the way support says it does?

    Support confirmed (2026-08-18) that ``cashValue`` is market value — the
    ``value`` verdict here. The check stays because a confirmation in an
    email is not an observation in a log: every position in a recorded market
    still gets compared against our own book, and a ``pnl`` verdict now means
    the venue's behaviour disagrees with its support's answer, which is worth
    knowing loudly. Observational only; nothing branches on it.
    """
    q = float(position.quantity)
    as_value = abs(float(position.cash_value) - q * mid)
    as_pnl = abs(float(position.cash_value) - (q * mid - float(position.cost)))
    margin = 0.05 * max(abs(q), 1.0)   # a nickel per contract of slack
    if as_value + margin < as_pnl:
        verdict = "value"
    elif as_pnl + margin < as_value:
        verdict = "pnl"
    else:
        verdict = "ambiguous"
    log.warning("bankroll_cashvalue_semantics",
                market_slug=position.market_slug, verdict=verdict,
                cash_value=float(position.cash_value), mid=mid,
                residual_as_value=round(as_value, 4),
                residual_as_pnl=round(as_pnl, 4),
                note="the docs give both readings; this observation is the "
                     "evidence that settles it — see the module docstring")
    return verdict


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


def _sessionmaker(Session=None):
    if Session is not None:
        return Session
    from core.storage import get_engine, get_sessionmaker
    return get_sessionmaker(get_engine())


def record(snapshot: AccountSnapshot, Session=None) -> int:
    """Append one reading. Returns the row id."""
    from core.storage import AccountBalance

    Session = _sessionmaker(Session)
    with Session() as session:
        row = AccountBalance(
            observed_at=snapshot.observed_at,
            currency=snapshot.currency,
            cash=snapshot.cash,
            buying_power=snapshot.buying_power,
            asset_notional=snapshot.asset_notional,
            open_orders=snapshot.open_orders,
            unsettled_funds=snapshot.unsettled_funds,
            pending_credit=snapshot.pending_credit,
            margin_requirement=snapshot.margin_requirement,
            bankroll=snapshot.bankroll,
            raw=snapshot.raw,
        )
        session.add(row)
        session.commit()
        return int(row.id)


def latest(Session=None) -> AccountSnapshot | None:
    """The newest stored reading, or None if the account has never been read."""
    from core.storage import AccountBalance

    Session = _sessionmaker(Session)
    with Session() as session:
        row = session.scalars(
            select(AccountBalance).order_by(AccountBalance.observed_at.desc()).limit(1)
        ).first()
        if row is None:
            return None
        observed = row.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        return AccountSnapshot(
            observed_at=observed,
            currency=row.currency,
            cash=row.cash,
            buying_power=row.buying_power,
            asset_notional=row.asset_notional,
            open_orders=row.open_orders,
            unsettled_funds=row.unsettled_funds,
            pending_credit=row.pending_credit,
            margin_requirement=row.margin_requirement,
            raw=row.raw,
        )


def refresh(Session=None, client=None) -> AccountSnapshot:
    """Poll the venue and store the reading. The poller's whole job."""
    snapshot = fetch(client)
    try:
        record(snapshot, Session)
    except Exception as exc:
        # A storage failure must not deny a caller a balance it already holds.
        log.error("bankroll_store_failed", error=str(exc)[:200])
    # Opportunistic, never fatal: any position in a market we record gets its
    # cashValue checked against our own book, which is the observation that
    # retires the docs' ambiguity about what the field means.
    for pos in snapshot.positions:
        try:
            mid = _recorded_mid(pos.market_slug, Session)
            if mid is not None:
                verify_position_value(pos, mid)
        except Exception as exc:
            log.debug("bankroll_semantics_check_skipped",
                      market_slug=pos.market_slug, error=str(exc)[:120])
    log.info("bankroll_refreshed", bankroll=float(snapshot.bankroll),
             equity=float(snapshot.equity), n_positions=len(snapshot.positions),
             currency=snapshot.currency)
    return snapshot


def _recorded_mid(market_slug: str, Session=None) -> float | None:
    """Our own newest two-sided quote for a market, or None. Only markets the
    recorder covers can answer; a hand trade on another sport returns None."""
    from core.storage import MarketSnapshot

    Session = _sessionmaker(Session)
    with Session() as session:
        row = session.scalars(
            select(MarketSnapshot)
            .where(MarketSnapshot.market_slug == market_slug)
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(1)
        ).first()
        if row is None or row.best_bid is None or row.best_ask is None:
            return None
        return (float(row.best_bid) + float(row.best_ask)) / 2


def current(
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    allow_fetch: bool = True,
    Session=None,
    client=None,
) -> AccountSnapshot:
    """The balance to size against, or :class:`BankrollUnavailable`.

    Reads the newest stored row; refreshes from the venue when there is none or
    it is staler than ``max_age_seconds``. A stale row is never returned as if
    it were current — the whole failure being fixed here is a dollar figure
    that used to be true.
    """
    stored = None
    try:
        stored = latest(Session)
    except Exception as exc:                      # database down: try the venue
        log.warning("bankroll_read_failed", error=str(exc)[:200])

    if stored is not None and stored.age_seconds() <= max_age_seconds:
        return stored

    if not allow_fetch:
        raise BankrollUnavailable(
            "no balance newer than "
            f"{max_age_seconds:.0f}s and fetching is disabled"
            + (f" (newest is {stored.age_seconds():.0f}s old)" if stored else "")
        )

    try:
        return refresh(Session, client)
    except BankrollUnavailable:
        raise
    except Exception as exc:
        raise BankrollUnavailable(f"could not read the balance: {exc}") from exc


def current_bankroll(**kwargs) -> float:
    """Convenience for the sizing callers, which work in floats."""
    return float(current(**kwargs).bankroll)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-bankroll")
    parser.add_argument("--refresh", action="store_true",
                        help="poll the venue and store the reading")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--raw", action="store_true",
                        help="print the raw balances and positions bodies, "
                             "for reconciling fields with venue support")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.WARNING)
    import core.storage  # noqa: F401  loads .env, like every CLI here

    if args.raw:
        # The two bodies support asked to see side by side for one open
        # position. Nothing in either is a credential; the account id is the
        # only thing worth redacting before sending.
        from core.polymarket.client import PolymarketAuthedClient, USCredentials
        client = PolymarketAuthedClient(USCredentials.from_env())
        try:
            for label, path in (("balances", BALANCES_PATH),
                                ("positions", POSITIONS_PATH)):
                resp = client.get(path)
                print(f"--- GET {path} (HTTP {resp.status_code}) ---")
                try:
                    print(json.dumps(json.loads(resp.body_text), indent=2))
                except ValueError:
                    print(resp.body_text[:2000])
        finally:
            client.close()
        return 0

    try:
        snapshot = refresh() if args.refresh else current()
    except BankrollUnavailable as exc:
        print(f"bankroll unavailable: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2))
    else:
        print(f"bankroll  ${snapshot.bankroll:,.2f} {snapshot.currency}"
              f"   equity ${snapshot.equity:,.2f}")
        print(f"  cash          ${snapshot.cash:,.4f}")
        if snapshot.positions_read_ok:
            print(f"  positions     ${snapshot.positions_value:,.4f}"
                  f" ({len(snapshot.positions)} open)")
            for pos in snapshot.positions:
                print(f"    {pos.market_slug}  {pos.quantity} @ cost "
                      f"${pos.cost:,.4f} -> ${pos.value:,.4f}")
        else:
            print("  positions     unread")
        print(f"  buying power  ${snapshot.buying_power:,.4f}")
        print(f"  in positions  ${snapshot.asset_notional:,.4f}")
        print(f"  resting       ${snapshot.open_orders:,.4f}")
        print(f"  unsettled     ${snapshot.unsettled_funds:,.4f}")
        print(f"  observed      {snapshot.observed_at.isoformat()} "
              f"({snapshot.age_seconds():.0f}s ago)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
