"""Every GET route answers, and every URL the pages fetch is a real route.

Why this file exists
--------------------
`/api/pulse` returned 500 on every request for two weeks (2026-08-22 →
2026-09-05). `build_report` changed shape — one report per estimates version
— and the endpoint kept reading `r.n_decisions` off the dict. 1,370 tests
were green the whole time, because no test had ever CALLED the endpoint, and
the page's `catch(e)` rendered "unavailable", which reads like "no data yet".

Nothing subtle was needed to find it. Asking each route for a response found
it in one pass. This file is that pass, kept.

It is deliberately shallow: a 4xx is a fine answer, an empty payload is a
fine answer, and no assertion is made about content — the per-endpoint tests
own that. The only thing asserted is that the handler runs, which is exactly
the property that was missing.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from core.api import app

#: Filled into templated paths. Neither needs to exist — a 404 passes.
SAMPLE = {"{market_slug}": "tsc-smoke-does-not-exist",
          "{event_slug}": "wnba-smoke-aaa-bbb-2026-09-05"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def no_venue_calls(monkeypatch):
    """`/api/bankroll` polls the venue when the stored reading is over 1800s
    old. A smoke test must not make a network call, so the read is stubbed
    unavailable — which is itself a real state the handler must survive."""
    import core.bankroll as bk

    def _unavailable(*_a, **_k):
        raise bk.BankrollUnavailable("stubbed for the route smoke test")

    monkeypatch.setattr(bk, "current", _unavailable)


def _get_paths() -> list[str]:
    return sorted(
        r.path for r in app.routes
        if hasattr(r, "methods") and "GET" in r.methods
        and not r.path.startswith("/openapi")
    )


@pytest.mark.parametrize("path", _get_paths())
def test_the_route_answers_without_a_server_error(client, path, no_venue_calls):
    url = path
    for token, value in SAMPLE.items():
        url = url.replace(token, value)
    r = client.get(url)
    assert r.status_code < 500, (
        f"GET {url} -> {r.status_code}. A 4xx is an answer; a 5xx is the "
        f"handler crashing.\n{r.text[:400]}")


def test_the_smoke_test_covers_every_get_route():
    """A route added tomorrow is covered without anyone remembering to add
    it — asserted, so the parametrize source cannot be narrowed by accident."""
    declared = {r.path for r in app.routes
                if hasattr(r, "methods") and "GET" in r.methods}
    assert declared - set(_get_paths()) <= {"/openapi.json"}


_FETCH = re.compile(r"""fetch\(\s*[`'"]([^`'"?]+)""")


def test_every_url_the_pages_fetch_is_a_real_route():
    """The other half of the same failure: a page can also point at a route
    that no longer exists, and `catch(e)` will render that as "unavailable"
    too."""
    routes = {r.path for r in app.routes if hasattr(r, "methods")}
    prefixes = tuple(r.split("{")[0] for r in routes if "{" in r)
    missing = []
    for page in sorted(pathlib.Path("static").glob("*.html")):
        for m in _FETCH.finditer(page.read_text()):
            url = m.group(1)
            if not url.startswith("/"):
                continue
            if url in routes or url.split("${")[0].rstrip("/") in routes:
                continue
            if url.startswith(prefixes):
                continue
            missing.append(f"{page.name}: {url}")
    assert not missing, f"pages fetch routes that do not exist: {missing}"
