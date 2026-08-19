"""The served bankroll block must equal what the poller actually read.

The bug (B13)
-------------
`AccountSnapshot` grew `positions` and `positions_read_ok` when equity display
was added. `record()` never persisted them and `latest()` never reconstructed
them, so a stored snapshot came back with `positions=()` and
`positions_read_ok=False` — the dataclass defaults.

`positions_read_ok=False` does not mean "no positions". It means **the read
failed**. And `current()` prefers a fresh stored row over a live fetch, so the
serving path returned the degraded copy while the poller logged the truth. In
one minute, live:

    poller  : bankroll_positions equity=23.2204 n=1 positions_value=3.6
    served  : equity 19.6204, positions_read_ok false, positions [], n 0

The operator's page said "positions unread" in red against a real open
position, and `equity` silently degraded to sizing-cash.

Why the round-trip test is the one that matters
-----------------------------------------------
The specific fix is two columns. The *class* of bug is a serialisation pair
that disagrees: any future field added to `AccountSnapshot` will default
silently on the read path in exactly the same way, and default to the
wrong-and-alarming value if it is a boolean like this one. So the guard here
asserts **every field survives the round trip**, discovered by reflection
rather than by a hand-written list that the next person forgets to extend.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal

import pytest

from core import bankroll as bk

UTC = dt.timezone.utc


@pytest.fixture(autouse=True)
def _isolate_account_balances():
    """Delete the rows this module writes, before and after each test.

    These tests exercise the REAL `record()`/`latest()`, so they leave a fresh
    `account_balances` row behind — and a fresh row is global state: `current()`
    prefers it, and `_stake_cap()` in `core.api` caps every order at
    `min($25, bankroll)`. Left in place, a $19.62 snapshot from here silently
    re-caps an unrelated stake test in the same run. It passed alone and failed
    in the suite, which is the signature.

    Safe to delete: conftest gives each pytest run its own `meridian_test_<pid>`
    database, so nothing here can reach the analysis mirror (B6).
    """
    from sqlalchemy import delete

    from core.storage import AccountBalance, get_engine, get_sessionmaker

    Session = get_sessionmaker(get_engine())

    def _clear():
        with Session() as s:
            s.execute(delete(AccountBalance))
            s.commit()

    _clear()
    yield
    _clear()


def _position(slug="tsc-wnba-ny-phx-2026-08-18-168pt5", qty="12", cash="3.60"):
    return bk.Position(
        market_slug=slug,
        quantity=Decimal(qty),
        quantity_available=Decimal(qty),
        cost=Decimal("3.00"),
        cash_value=Decimal(cash),
        realized=Decimal("0"),
        expired=False,
        title="Total 168.5",
        outcome="YES",
    )


def _snapshot(*, positions=(), read_ok=True) -> bk.AccountSnapshot:
    """The live shape from the incident: $19.62 sizing-cash, one $3.60 position."""
    return bk.AccountSnapshot(
        observed_at=dt.datetime(2026, 8, 19, 2, 30, 34, tzinfo=UTC),
        currency="USD",
        cash=Decimal("19.6204"),
        buying_power=Decimal("19.6204"),
        asset_notional=Decimal("0"),
        open_orders=Decimal("0"),
        unsettled_funds=Decimal("0"),
        pending_credit=Decimal("0"),
        margin_requirement=Decimal("0"),
        raw={"balances": []},
        positions=tuple(positions),
        positions_read_ok=read_ok,
    )


# ------------------------------------------------------------------ #
# The incident, reproduced
# ------------------------------------------------------------------ #


def test_position_survives_the_storage_round_trip():
    """The regression itself: store a snapshot with a position, read it back,
    and the position is still there."""
    live = _snapshot(positions=[_position()], read_ok=True)
    stored = bk.position_from_dict(live.positions[0].to_dict())
    assert stored == live.positions[0]


def test_served_block_equals_what_the_poller_read():
    """The assertion the bug report asked for: same cycle, same numbers.

    This goes through the REAL `record()` and `latest()` against the per-run
    test database. An earlier version of this test monkeypatched both with
    fakes and passed happily with the bug re-introduced — it was exercising the
    stub, not the code. A guard that cannot fail is the bug it is guarding
    against, one level up.
    """
    live = _snapshot(positions=[_position()], read_ok=True)
    bk.record(live)

    served = bk.latest().to_dict()
    polled = live.to_dict()

    for key in ("equity", "positions_value", "n_positions", "positions_read_ok"):
        assert served[key] == polled[key], (
            f"served {key}={served[key]!r} but the poller read {polled[key]!r} "
            "— the serving path and the poller disagree about the same cycle"
        )
    assert served["equity"] == pytest.approx(23.2204)
    assert served["n_positions"] == 1
    assert served["positions_read_ok"] is True
    assert served["positions"][0]["market_slug"] == live.positions[0].market_slug


def test_unread_and_empty_are_different_facts():
    """`positions_read_ok` is stored, not derived from `len(positions)`. An
    empty book and an unread book render differently and must not collapse."""
    empty_but_read = _snapshot(positions=[], read_ok=True).to_dict()
    never_read = _snapshot(positions=[], read_ok=False).to_dict()

    assert empty_but_read["n_positions"] == never_read["n_positions"] == 0
    assert empty_but_read["positions_read_ok"] is True
    assert never_read["positions_read_ok"] is False


def test_equity_degrades_to_bankroll_only_when_the_read_actually_failed():
    """The old bug made every stored snapshot look like a failed read, so
    equity silently became sizing-cash. Equity may only equal bankroll when
    there is genuinely nothing to add."""
    with_position = _snapshot(positions=[_position()], read_ok=True)
    assert with_position.equity == with_position.bankroll + Decimal("3.60")

    failed = _snapshot(positions=[], read_ok=False)
    assert failed.equity == failed.bankroll


# ------------------------------------------------------------------ #
# The class, not the instance
# ------------------------------------------------------------------ #


def test_every_snapshot_field_survives_persistence():
    """Reflection over the dataclass, through the REAL storage path.

    A hand-written list of fields is the same bug one level up: it passes until
    someone adds a field and forgets to extend it, which is exactly how
    `positions` came to be dropped. Comparing the dataclass to itself after a
    real write and read catches any future field for free.

    `raw` is excluded only because JSONB round-trips dict key order, not
    identity; every other field must come back equal.
    """
    live = _snapshot(positions=[_position()], read_ok=True)
    bk.record(live)
    back = bk.latest()

    differing = []
    for f in dataclasses.fields(live):
        if f.name in {"raw", "observed_at"}:
            continue
        if getattr(back, f.name) != getattr(live, f.name):
            differing.append(
                f"{f.name}: stored {getattr(live, f.name)!r} -> read back "
                f"{getattr(back, f.name)!r}"
            )
    assert not differing, (
        "AccountSnapshot fields did not survive storage:\n  "
        + "\n  ".join(differing)
        + "\nA field the write path drops comes back as its dataclass default, "
        "which for a boolean flag means silently asserting the wrong thing."
    )
