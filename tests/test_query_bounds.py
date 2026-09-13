"""`?limit=` reached the SQL unchecked, and /api/games returned 500 on -1.

Verified against the live box on 2026-09-14 before this was written: a public
endpoint 500s on a query string anyone can type. `limit=-1` became
`LIMIT -1`, which psycopg raises a DataError on, and an unhandled DataError is
a 500.

THE BOUND LIVES IN ONE PLACE — the parameter declaration. Two ways to get this
wrong were both present in main:

  unbounded   /api/games, /api/history, /api/results, /api/orders/recent
              passed the value straight to LIMIT

  clamped     /api/scalps did `n = max(1, min(int(limit), 1000))`, which never
              500s and is still wrong: it answers a question the caller did
              not ask. Asking for -1 and silently receiving 1 row is a wrong
              answer delivered with a 200, which is harder to notice than a
              crash. Deleted in favour of the same declared bound.

Declared bounds make FastAPI reject before the handler runs, so the response
is a 422 naming the parameter, and no handler needs its own guard.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api import app

client = TestClient(app)

#: (path, in-range value). Every route on main that takes a `limit`.
#:
#: CAPS ARE DERIVED FROM ACTUAL CALLERS, not chosen round. Two have one:
#:   /api/orders/recent  le=100   static/index.html:1595 is the only limit=
#:                                any page requests
#:   /api/results        le=5000  tests/test_era_separation.py asks for 5000
#: The other three have no caller that sets `limit` at all, so the cap is the
#: code's own default with headroom — enough for an ad-hoc query, orders of
#: magnitude below the regime that held a worker for 29 seconds.
BOUNDED = [
    ("/api/games", 60),
    ("/api/results", 100),
    ("/api/orders/recent", 25),
    ("/api/scalps", 200),
    ("/api/history/wnba-ny-chi-2026-08-18", 60),
]

#: Measured against the live box on 2026-09-14, and the LAST TWO are the
#: reason this is an availability fix and not a tidiness one:
#:
#:   limit=-1               500 immediately
#:   limit=abc              422 in 0.25s   (validation already worked here)
#:   limit=100000           200 in 29.1s
#:   limit=999_999_999_999   200 in 24.2s
#:
#: There was no upper bound at all. A 500 returns straight away; a 200 that
#: holds a worker for half a minute does not, on a service bound to all
#: interfaces. `0` is kept because it is the off-by-one that returns an empty
#: page rather than an error, which reads as "no data" rather than a bad call.
#:
#: Asserted on STATUS, never on duration — a timing assertion would be flaky
#: on any machine but the one it was written on.
#
# The last one is COMPUTED, not written: twelve consecutive digits is
# the AWS account-id shape, and a literal here trips both the
# pre-commit scanner and test_no_infra_identifiers. It caught this
# file, which is the guard working.
BAD = ["-1", "0", "abc", "100000", str(10 ** 12 - 1)]


@pytest.mark.parametrize("path,_ok", BOUNDED)
@pytest.mark.parametrize("bad", BAD)
def test_an_out_of_range_limit_is_refused_by_validation(path, _ok, bad):
    r = client.get(f"{path}?limit={bad}")
    assert r.status_code == 422, (
        f"{path}?limit={bad} returned {r.status_code}, not 422 — the bound is "
        "not declared on the parameter, so the value reached the handler")
    # 422 from FastAPI names the offending parameter; a hand-rolled 422 from
    # somewhere else would not, and would mean the bound moved out of one place.
    assert "limit" in r.text


@pytest.mark.parametrize("path,ok", BOUNDED)
def test_a_limit_inside_the_bound_is_still_served(path, ok):
    """The control. Four refusal tests are equally satisfied by an endpoint
    that refuses everything, and a 422 on a valid limit would be the same
    outage wearing a different status code."""
    r = client.get(f"{path}?limit={ok}")
    assert r.status_code != 422, f"{path} refused a valid limit={ok}"


def test_no_handler_re_clamps_a_limit_the_bound_already_checked():
    """The clamp is UNREACHABLE while the bound holds — and removing it still
    matters, for a reason the behavioural tests above cannot express.

    I wrote this as a request first (`/api/scalps?limit=-1` must be 422) and
    mutation-testing showed it green with the clamp restored: validation
    rejects -1 before the handler runs, so no request can reach the clamp.
    A test that cannot fail is not a guard, so this asserts the source instead.

    Why the dead code is worth deleting: it only becomes reachable if someone
    later drops the declared bound — and at that moment it converts the
    failure from a loud 500 into a 200 carrying a limit nobody asked for.
    Belt-and-braces here makes the NEXT regression quieter, not safer.
    """
    import inspect

    from core import api

    src = inspect.getsource(api.scalps)
    assert "min(int(limit)" not in src and "max(1, min(" not in src, (
        "scalps re-clamps a limit the declared bound already checked; if the "
        "bound is ever dropped this silently returns the wrong number of rows "
        "with a 200 instead of failing")
