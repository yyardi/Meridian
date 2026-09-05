"""`?limit=` is user input, and it reached the SQL unchecked.

2026-09-05, found by fuzzing every declared query parameter on every GET
route: `?limit=-1` returned 500 on four endpoints —

    psycopg.errors.InvalidRowCountInLimitClause: LIMIT must not be negative

A 500 is the server saying "I crashed"; the honest answer to a nonsensical
limit is 422, "that is not a limit". The same declaration also puts a ceiling
on the value, which matters more than the floor: `market_snapshots` is 16M
rows and `/api/history?limit=99999999` was a 200 that promised to serve all
of them.

Bounds are declarative (`Query(ge=…, le=…)`) rather than hand-checked in each
handler, so the four endpoints cannot drift apart and the ceiling shows up in
the OpenAPI schema.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.api import app

#: (path, default, ceiling) — the ceiling each endpoint advertises.
BOUNDED = [
    ("/api/history/wnba-x-y-2026-09-05", 60, 2000),
    ("/api/results", 2000, 20000),
    ("/api/orders/recent", 25, 500),
    ("/api/games", 60, 500),
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("path,default,ceiling", BOUNDED)
def test_a_negative_limit_is_rejected_not_crashed(client, path, default, ceiling):
    r = client.get(path, params={"limit": -1})
    assert r.status_code == 422, (
        f"{path} answered {r.status_code} to limit=-1; a negative limit is bad "
        f"input, not a server fault.\n{r.text[:200]}")


@pytest.mark.parametrize("path,default,ceiling", BOUNDED)
def test_zero_is_rejected_too(client, path, default, ceiling):
    """`LIMIT 0` is legal SQL and always returns nothing, which reads as "no
    data" rather than as the bad request it is."""
    assert client.get(path, params={"limit": 0}).status_code == 422


@pytest.mark.parametrize("path,default,ceiling", BOUNDED)
def test_the_ceiling_is_enforced(client, path, default, ceiling):
    assert client.get(path, params={"limit": ceiling + 1}).status_code == 422
    assert client.get(path, params={"limit": ceiling}).status_code == 200


@pytest.mark.parametrize("path,default,ceiling", BOUNDED)
def test_the_default_still_answers(client, path, default, ceiling):
    """The bounds must not have moved the default out of range."""
    assert default >= 1 and default <= ceiling
    assert client.get(path).status_code == 200


def test_the_callers_in_the_repo_stay_inside_the_bounds(client):
    """The page asks /api/orders/recent for 100 and the era tests ask
    /api/results for 5000. A ceiling that broke a live caller would be a
    worse bug than the one it fixes."""
    assert client.get("/api/orders/recent", params={"limit": 100}).status_code == 200
    assert client.get("/api/results", params={"limit": 5000}).status_code == 200


def test_the_bounds_are_visible_in_the_schema():
    """Declared, not hand-checked — so they document themselves and cannot
    drift between the four handlers."""
    spec = app.openapi()
    for path, _default, ceiling in BOUNDED:
        key = path.replace("wnba-x-y-2026-09-05", "{market_slug}")
        params = {p["name"]: p for p in spec["paths"][key]["get"]["parameters"]}
        schema = params["limit"]["schema"]
        assert schema.get("minimum") == 1, (path, schema)
        assert schema.get("maximum") == ceiling, (path, schema)
