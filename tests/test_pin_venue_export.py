"""The one property that makes a pinned artifact trustworthy: it reached eof.

The live path guarantees completeness by walking the feed to `eof` and raising
if it never gets there. An ARTIFACT is read later by someone who was not there
and cannot re-derive that guarantee — so a truncated export must not be
pinnable in the first place. Refusing to write beats writing a file that looks
whole and is missing its oldest rows.
"""

from __future__ import annotations

import pytest

from scripts.pin_venue_export import build_envelope, page_is_last


def _page(n: int, *, eof: bool, cursor: str | None = None) -> dict:
    p: dict = {"activities": [{"type": "ACTIVITY_TYPE_TRADE"}] * n, "eof": eof}
    if cursor:
        p["nextCursor"] = cursor
    return p


@pytest.mark.parametrize(
    "body, expect, why",
    [
        ({"eof": True, "nextCursor": "c"}, True, "eof wins even with a cursor"),
        ({"eof": False}, True, "no cursor means nothing follows"),
        ({"eof": False, "nextCursor": "c"}, False, "more pages remain"),
    ],
)
def test_termination_rule_matches_the_live_walk(body, expect, why):
    assert page_is_last(body) is expect, why


def test_a_complete_walk_is_pinned_with_its_stamp():
    env = build_envelope([_page(100, eof=False, cursor="c1"), _page(39, eof=True)],
                         "20260826T040141Z")
    assert env["page_count"] == 2
    assert env["fetched_at"] == "20260826T040141Z"
    assert sum(len(p["activities"]) for p in env["pages"]) == 139


def test_a_truncated_walk_is_refused_and_nothing_is_written():
    """The failure this exists for: an export that stopped mid-feed still has a
    plausible page count and a plausible stamp, and is missing the oldest rows."""
    with pytest.raises(SystemExit, match="did not reach eof"):
        build_envelope([_page(100, eof=False, cursor="more")], "20260826T040141Z")


def test_no_pages_is_refused_rather_than_pinned_empty():
    with pytest.raises(SystemExit, match="no pages"):
        build_envelope([], "20260826T040141Z")
