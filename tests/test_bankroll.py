"""The account balance is read, never assumed.

The bug this pins: `35.68` was typed into `core/scheduler.py` on the day
someone last looked at the app, passed into `shadow_run`, and multiplied
through every Kelly size on the board. The account was at $23.82 by
2026-08-17 — so every stake was ~50% too large, the error grew with every fill
and withdrawal, and nothing on any screen said so. A stale constant is
indistinguishable from a live reading unless something structurally forbids
the constant.

Two kinds of test here:

* arithmetic and failure modes of `core.bankroll` — chiefly that an unreadable
  balance **raises** rather than defaulting, because a default is exactly the
  failure being deleted;
* a source-level regression that greps the tree and fails if a bankroll-shaped
  dollar literal reappears anywhere sizing can reach.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest

from core import bankroll as bk

UTC = dt.timezone.utc

#: The payload observed live 2026-08-17 (200 in ~30ms at the venue).
LIVE_SHAPE = {
    "balances": [{
        "currentBalance": 23.8204, "currency": "USD", "lastUpdated": None,
        "buyingPower": 23.8204, "assetNotional": 0, "assetAvailable": 0,
        "pendingCredit": 0, "openOrders": 0, "unsettledFunds": 0,
        "pendingWithdrawals": [], "marginRequirement": 0,
    }]
}


class _Resp:
    def __init__(self, status_code, body_text):
        self.status_code = status_code
        self.body_text = body_text


class _Client:
    """Stands in for PolymarketAuthedClient — `get` and nothing else, which is
    the point: a client that could place an order would not typecheck here."""

    def __init__(self, resp, expect_path=bk.BALANCES_PATH):
        self._resp, self._expect = resp, expect_path
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append(path)
        assert path == self._expect
        return self._resp

    def close(self):
        pass


# ------------------------------------------------------------------ #
# Parsing the venue's shape
# ------------------------------------------------------------------ #


def test_parses_the_live_payload():
    snap = bk.parse_balances(LIVE_SHAPE)
    assert snap.cash == Decimal("23.8204")
    assert snap.buying_power == Decimal("23.8204")
    assert snap.currency == "USD"
    assert snap.bankroll == Decimal("23.8204")


def test_bankroll_is_the_conservative_reading():
    """Kelly is brutally asymmetric to over-betting, so the smaller number
    wins. Under-betting costs growth linearly; over-betting can cost the
    account."""
    body = {"balances": [{"currency": "USD", "currentBalance": 40,
                          "buyingPower": 12, "assetNotional": 100}]}
    assert bk.parse_balances(body).bankroll == Decimal("12")


def test_picks_the_usd_entry_not_the_first_one():
    body = {"balances": [
        {"currency": "EUR", "currentBalance": 999, "buyingPower": 999},
        {"currency": "USD", "currentBalance": 23.82, "buyingPower": 23.82},
    ]}
    snap = bk.parse_balances(body)
    assert snap.currency == "USD"
    assert snap.bankroll == Decimal("23.82")


def test_empty_balances_is_an_error_not_zero():
    """"No answer" and "$0" are different facts. Reading the first as the
    second would silently stop all sizing and look like a broke account."""
    with pytest.raises(bk.BankrollUnavailable):
        bk.parse_balances({"balances": []})
    with pytest.raises(bk.BankrollUnavailable):
        bk.parse_balances({})


def test_unverified_components_are_flagged_not_swallowed():
    body = {"balances": [{"currency": "USD", "currentBalance": 30,
                          "buyingPower": 25, "assetNotional": 5}]}
    snap = bk.parse_balances(body)
    assert snap.has_unverified_components
    # Still a lower bound on wealth under any reading of the other fields.
    assert snap.bankroll == Decimal("25")


def test_non_numeric_field_raises():
    body = {"balances": [{"currency": "USD", "currentBalance": "lots",
                          "buyingPower": 1}]}
    with pytest.raises(bk.BankrollUnavailable):
        bk.parse_balances(body)


# ------------------------------------------------------------------ #
# Fetching
# ------------------------------------------------------------------ #


def test_fetch_uses_the_verified_path():
    import json
    client = _Client(_Resp(200, json.dumps(LIVE_SHAPE)))
    snap = bk.fetch(client)
    assert client.calls == ["/v1/account/balances"]
    assert snap.bankroll == Decimal("23.8204")


def test_non_200_is_unavailable_never_a_number():
    client = _Client(_Resp(401, '{"message":"Invalid API key signature"}'))
    with pytest.raises(bk.BankrollUnavailable):
        bk.fetch(client)


def test_unparseable_body_is_unavailable():
    client = _Client(_Resp(200, "<html>gateway</html>"))
    with pytest.raises(bk.BankrollUnavailable):
        bk.fetch(client)


# ------------------------------------------------------------------ #
# Staleness — the actual bug, in miniature
# ------------------------------------------------------------------ #


def _snap(age_seconds: float, amount="23.82") -> bk.AccountSnapshot:
    return bk.AccountSnapshot(
        observed_at=dt.datetime.now(UTC) - dt.timedelta(seconds=age_seconds),
        currency="USD", cash=Decimal(amount), buying_power=Decimal(amount),
        asset_notional=Decimal("0"), open_orders=Decimal("0"),
        unsettled_funds=Decimal("0"), pending_credit=Decimal("0"),
        margin_requirement=Decimal("0"),
    )


def test_fresh_stored_reading_is_used_without_touching_the_venue(monkeypatch):
    monkeypatch.setattr(bk, "latest", lambda Session=None: _snap(60))
    monkeypatch.setattr(bk, "refresh", lambda *a, **k: pytest.fail("should not fetch"))
    assert bk.current(max_age_seconds=1800).bankroll == Decimal("23.82")


def test_stale_stored_reading_is_refreshed_not_served(monkeypatch):
    """A balance that used to be true is the whole bug. It is never returned
    as if it were current."""
    monkeypatch.setattr(bk, "latest", lambda Session=None: _snap(9999, "35.68"))
    monkeypatch.setattr(bk, "refresh", lambda *a, **k: _snap(0, "23.82"))
    assert bk.current(max_age_seconds=1800).bankroll == Decimal("23.82")


def test_stale_and_unfetchable_raises_rather_than_serving_the_old_number(monkeypatch):
    monkeypatch.setattr(bk, "latest", lambda Session=None: _snap(9999, "35.68"))
    with pytest.raises(bk.BankrollUnavailable):
        bk.current(max_age_seconds=1800, allow_fetch=False)


def test_never_read_and_unreachable_raises(monkeypatch):
    monkeypatch.setattr(bk, "latest", lambda Session=None: None)

    def _boom(*a, **k):
        raise bk.BankrollUnavailable("venue down")

    monkeypatch.setattr(bk, "refresh", _boom)
    with pytest.raises(bk.BankrollUnavailable):
        bk.current()


def test_shadow_run_writes_nothing_without_a_bankroll(monkeypatch):
    """The consuming end of the same rule: no balance, no sizes. Not a
    fallback bankroll, not a zero-dollar board — nothing written at all."""
    from core import shadow_run

    def _boom(**kwargs):
        raise bk.BankrollUnavailable("venue down")

    monkeypatch.setattr(shadow_run, "current_bankroll", _boom)
    monkeypatch.setattr(
        shadow_run, "get_sessionmaker",
        lambda *a, **k: pytest.fail("must not open a session without a bankroll"),
    )
    assert shadow_run.run() == 0


# ------------------------------------------------------------------ #
# The regression: no bankroll-shaped constant, anywhere sizing can reach
# ------------------------------------------------------------------ #

_REPO = Path(__file__).resolve().parent.parent

#: Where a hardcoded bankroll would actually do damage: the code that sizes,
#: displays or orders. Tests and docs are excluded — this file quotes `35.68`
#: on purpose, and the docs describe the bug in prose.
_SCANNED = ("core", "scripts", "static", "strategies")

#: `35.68` by name. It was the real balance once, which is exactly why it is
#: the string most likely to be pasted back in by someone "restoring" a
#: default. Any spelling of it, anywhere in the scanned tree, is a failure.
_DEAD_CONSTANT = re.compile(r"\b35\.68\b")

#: A bankroll being *assigned* from a literal, rather than read. Catches
#: `bankroll=35.68`, `bankroll = 100.0`, `BANKROLL: float = 42` and the
#: `starting_balance`/`account_balance` spellings of the same idea.
_LITERAL_BANKROLL = re.compile(
    r"\b(bankroll|account_balance|starting_balance|account_value)\b"
    r"\s*(?::\s*[A-Za-z_\[\]|. ]+)?\s*=\s*\(?\s*(?:Decimal\(\s*[\"'])?\d",
    re.IGNORECASE,
)

#: One deliberate exception, and it is not a bankroll. A walk-forward backtest
#: starts from a stated hypothetical so its equity curve is reproducible; tying
#: it to today's balance would make last month's backtest un-rerunnable. It is
#: never used to size a live order — `core/backtest/` imports nothing from the
#: order path.
_ALLOWED = {
    ("core/backtest/engine.py", "starting_bankroll"),
}


# Comments and docstrings are blanked before scanning, and that is not a
# loophole — it is what makes the test usable. Every file that fixed this bug
# *describes* it, this one included ("the literal 35.68"), so a scanner that
# cannot tell prose from code is one that stays red until somebody weakens it
# into a rubber stamp. Blanking happens in place, so an offender's line number
# still points at the real line.


def _blank(grid: list[list[str]], start: tuple[int, int], end: tuple[int, int]) -> None:
    (r0, c0), (r1, c1) = start, end
    for row in range(r0, min(r1, len(grid)) + 1):
        line = grid[row - 1]
        lo = c0 if row == r0 else 0
        hi = c1 if row == r1 else len(line)
        for col in range(lo, min(hi, len(line))):
            line[col] = " "


def _code_only_python(src: str) -> str:
    """Source with comments and docstrings blanked out, line numbers intact."""
    import ast
    import io
    import tokenize

    grid = [list(line) for line in src.splitlines()]
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            _blank(grid, tok.start, tok.end)

    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            c = first.value
            _blank(grid, (c.lineno, c.col_offset), (c.end_lineno, c.end_col_offset))
    return "\n".join("".join(row) for row in grid)


_WEB_COMMENT = re.compile(r"<!--.*?-->|/\*.*?\*/", re.DOTALL)
_JS_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")


def _code_only_web(src: str) -> str:
    def _keep_newlines(match: re.Match) -> str:
        return "\n" * match.group(0).count("\n")

    return _JS_LINE_COMMENT.sub("", _WEB_COMMENT.sub(_keep_newlines, src))


def _code_sources():
    """(relative path, code-only text) for everything sizing can reach."""
    for folder in _SCANNED:
        root = _REPO / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in (".py", ".html", ".js"):
                continue
            if "__pycache__" in path.parts:
                continue
            src = path.read_text()
            code = (_code_only_python(src) if path.suffix == ".py"
                    else _code_only_web(src))
            yield path.relative_to(_REPO).as_posix(), code


def _hits(pattern: re.Pattern, *, skip_allowed: bool = False) -> list[str]:
    out = []
    for rel, code in _code_sources():
        for i, line in enumerate(code.splitlines(), start=1):
            if not pattern.search(line):
                continue
            if skip_allowed and any(rel == f and name in line
                                    for f, name in _ALLOWED):
                continue
            out.append(f"{rel}:{i}: {line.strip()[:90]}")
    return out


def test_the_dead_bankroll_constant_is_gone():
    offenders = _hits(_DEAD_CONSTANT)
    assert not offenders, (
        "35.68 is the stale balance this module exists to delete. The bankroll "
        "comes from `core.bankroll`, which asks the venue. Found:\n  "
        + "\n  ".join(offenders)
    )


def test_no_bankroll_is_assigned_from_a_literal():
    offenders = _hits(_LITERAL_BANKROLL, skip_allowed=True)
    assert not offenders, (
        "A bankroll assigned from a literal is a number that was true once. "
        "Read it with `core.bankroll.current()`; if the venue cannot answer, "
        "size nothing rather than guessing. Found:\n  " + "\n  ".join(offenders)
    )


def test_the_scanner_can_still_see_a_constant_in_real_code():
    """The stripping above is the part most likely to rot: a scanner that
    blanks too much passes forever and protects nothing."""
    src = ('"""A docstring mentioning bankroll = 35.68."""\n'
           "# a comment mentioning bankroll = 35.68\n"
           "bankroll = 35.68\n")
    code = _code_only_python(src)
    assert len(_DEAD_CONSTANT.findall(code)) == 1, "prose and code not separated"
    assert _LITERAL_BANKROLL.search(code)

    web = "<!-- bankroll = 35.68 -->\nconst bankroll = 35.68;\n"
    assert len(_DEAD_CONSTANT.findall(_code_only_web(web))) == 1


def test_the_allowlist_still_describes_something_real():
    """An allowlist that has drifted off its target silently re-permits the
    thing it was narrowed around."""
    for rel, name in _ALLOWED:
        path = _REPO / rel
        assert path.is_file(), f"allowlisted file {rel} no longer exists"
        assert name in path.read_text(), f"allowlisted symbol {name} gone from {rel}"


# ------------------------------------------------------------------ #
# The API contract: `bankroll` is always present, never merely usual
# ------------------------------------------------------------------ #


def test_picks_carries_bankroll_even_with_an_empty_board(monkeypatch):
    """`/api/picks` has an early return for "no predictions at all", and it
    used to skip the bankroll block.

    The balance is perfectly knowable on a night with no predictions, so a
    missing key there is the endpoint's own bug from the other side: a
    consumer doing `d.bankroll.bankroll` throws, and one doing
    `d.bankroll?.bankroll` renders nothing at all. Absent-with-no-explanation
    is the same failure as quietly-wrong — which is what the block exists to
    prevent.

    Pinned as a **contract**, not as one branch: every documented shape of the
    payload carries the key.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import delete

    from core.api import app
    from core.storage import Prediction, get_engine, get_sessionmaker

    monkeypatch.setattr(
        "core.bankroll.current",
        lambda **kw: _snap(0, "23.82"),
    )

    Session = get_sessionmaker(get_engine())
    with Session() as s:                       # the empty-board shape
        s.execute(delete(Prediction))
        s.commit()

    body = TestClient(app).get("/api/picks").json()
    assert body["predicted_at"] is None and body["picks"] == []
    assert "bankroll" in body, (
        "the empty-board early return dropped the bankroll key; consumers "
        "cannot tell 'no balance' from 'no board'"
    )
    assert body["bankroll"]["bankroll"] == 23.82


def test_status_carries_bankroll(monkeypatch):
    from fastapi.testclient import TestClient

    from core import api
    from core.api import app

    monkeypatch.setattr("core.bankroll.current", lambda **kw: _snap(0, "23.82"))
    # /api/status caches for STATUS_CACHE_SECONDS; a warm cache from another
    # test would answer instead of the code under test.
    api._status_cache["value"] = None

    body = TestClient(app).get("/api/status").json()
    assert "bankroll" in body
    assert body["bankroll"]["bankroll"] == 23.82


def test_an_unreadable_balance_is_a_stated_null_not_a_missing_key(monkeypatch):
    """The null branch still carries the key AND says why — the page renders
    'unknown' rather than silently omitting a number it could not read."""
    from fastapi.testclient import TestClient

    from core import api
    from core.api import app

    def _boom(**kwargs):
        raise bk.BankrollUnavailable("venue down")

    monkeypatch.setattr("core.bankroll.current", _boom)
    api._status_cache["value"] = None

    body = TestClient(app).get("/api/status").json()
    assert body["bankroll"]["bankroll"] is None
    assert "venue down" in body["bankroll"]["unavailable"]


def test_picks_carries_bankroll_on_an_unrecorded_league(monkeypatch):
    """Every return path of `/api/picks` carries the key — including the ones
    added by other people's branches.

    This is a **cross-PR guard**, and it is aimed at a class rather than a
    line. `picks()` has several returns and each one is a place the contract
    can be broken by someone who does not know it exists: the empty-board path
    already dropped the key once. A league-scoped short-circuit — return early
    for a league we do not record, rather than walking every prediction to
    discard them all — is an obvious and correct optimisation, and it is
    exactly the shape that omits the key again.

    Textual merge checks cannot see this. Two branches can edit `picks()` three
    lines apart, merge clean, and produce a response missing a field neither
    author knew the other depended on. So it is pinned by behaviour: ask for
    the unrecorded league and require the key, whatever route the answer took.
    """
    from fastapi.testclient import TestClient

    from core.api import app
    from core.leagues import LEAGUES

    unrecorded = [lg.slug for lg in LEAGUES.values() if not lg.recorded]
    if not unrecorded:
        pytest.skip("every league is recorded; nothing to short-circuit")

    monkeypatch.setattr("core.bankroll.current", lambda **kw: _snap(0, "23.82"))

    body = TestClient(app).get(f"/api/picks?league={unrecorded[0]}").json()
    assert body["recorded"] is False, "fixture assumption: this league is unrecorded"
    assert "bankroll" in body, (
        f"/api/picks?league={unrecorded[0]} dropped the bankroll key. The "
        "balance is a fact about the ACCOUNT and is knowable on a league we do "
        "not record — an early return that omits it makes the page say "
        "'unknown' about a number we have."
    )
    assert body["bankroll"]["bankroll"] == 23.82
