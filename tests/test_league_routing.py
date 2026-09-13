"""Every consumer that routes by a league word in a slug.

    pytest --noconftest tests/test_league_routing.py

The venue names cricket and table tennis by COMPETITION -- `cplcr`, `county`,
`setkameua` -- and the league word never appears in a slug. Anything matching
on it returns nothing found, which is indistinguishable from a quiet night.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from core.leagues import LEAGUES, league_of_slug, venue_patterns

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("slug, want", [
    ("aec-cplcr-bra-gaw-2026-09-13", "cricket"),
    ("cplcr-bra-gaw-2026-09-13", "cricket"),
    ("aec-county-essex-war-2026-09-15", "cricket"),
    ("aec-t20icr-ind-aus-2026-09-14", "cricket"),
    ("aec-t20iwcr-eng-nz-2026-09-14", "cricket"),
    ("aec-odicr-sa-pak-2026-09-14", "cricket"),
    ("aec-setkameua-melval-tuzole-2026-09-13", "tabletennis"),
    ("aec-setkamemd-a-b-2026-09-13", "tabletennis"),
    ("aec-setkamecz-a-b-2026-09-13", "tabletennis"),
    ("aec-setkawoua-a-b-2026-09-13", "tabletennis"),
])
def test_a_competition_slug_resolves_to_its_league(slug, want):
    got = league_of_slug(slug)
    assert got is not None and got.slug == want


@pytest.mark.parametrize("slug, want", [
    ("wnba-ny-chi-2026-08-18", "wnba"),
    ("tsc-wnba-ny-chi-2026-08-18-191pt5", "wnba"),
    ("asc-nfl-a-b-2026-09-13-neg-3", "nfl"),
    ("asc-cfb-a-b-2026-09-13-pos-7", "cfb"),
    ("asc-mlb-col-det-2026-09-13-pos-1pt5", "mlb"),
])
def test_the_existing_leagues_are_unchanged(slug, want):
    assert league_of_slug(slug).slug == want


@pytest.mark.parametrize("slug", [None, "", "   ", "not-a-slug", "aec-unknownlg-a-b-2026-09-13"])
def test_a_slug_of_no_known_league_is_still_None(slug):
    assert league_of_slug(slug) is None


def test_every_venue_competition_is_routable():
    """Derived from the table, so adding a competition without routing it fails
    here rather than in an empty dashboard tab."""
    for lg in LEAGUES.values():
        for v in lg.venue_leagues:
            got = league_of_slug(f"aec-{v}-a-b-2026-09-13")
            assert got is not None and got.slug == lg.slug, f"{v} routes to {got}"


def test_no_competition_token_shadows_another():
    """`t20icr` must not swallow `t20iwcr`. Longest token first is what stops
    it; this is the assertion that would notice if that ordering were lost."""
    owner = {}
    for lg in LEAGUES.values():
        for t in {lg.slug, *lg.venue_leagues}:      # a one-competition league
            assert owner.setdefault(t, lg.slug) == lg.slug, \
                f"token {t!r} names both {owner[t]} and {lg.slug}"
    for t, want in owner.items():
        assert league_of_slug(f"aec-{t}-a-b-2026-09-13").slug == want


@pytest.mark.parametrize("lg, n", [("cricket", 5), ("tabletennis", 4), ("wnba", 1), ("nfl", 1)])
def test_venue_patterns_covers_every_competition(lg, n):
    pats = venue_patterns(lg)
    assert len(pats) == n and all(p.startswith("%-") and p.endswith("-%") for p in pats)


def test_the_league_word_itself_would_have_matched_nothing():
    """The defect being fixed, stated as a test: cricket's own name is not in
    any of its slugs, so the naive pattern is not merely narrow -- it is empty."""
    assert "%-cricket-%" not in venue_patterns("cricket")
    assert "%-tabletennis-%" not in venue_patterns("tabletennis")


def test_an_unknown_sport_falls_back_instead_of_raising():
    """These callers are read-only analyses; an unknown sport should find
    nothing, not traceback."""
    assert venue_patterns("quidditch") == ("%-quidditch-%",)


# ------------------------------------------------- the consumers, by source
def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", ["cfb/run_paper_book.py", "scripts/sandbox.py"])
def test_the_slug_matchers_go_through_venue_patterns(rel):
    """Neither may rebuild `f"%-{lg}-%"` on its own again."""
    s = _src(rel)
    assert "venue_patterns" in s
    assert not re.search(r'f"%-\{(lg|sport|league)\}-%"', s), f"{rel} still builds its own pattern"


@pytest.mark.parametrize("rel", ["cfb/run_ladder_calibration.py", "cfb/run_longshot_decomp.py"])
def test_the_ladder_studies_say_why_they_stay_football_only(rel):
    """Not a routing gap: cricket and table tennis have one lineless market per
    event, so there is no ladder. Marked in the file so the next sweep does not
    re-derive it."""
    assert "LADDER STUDY" in _src(rel)


def test_both_new_recorders_are_in_the_health_check():
    s = _src("scripts/health.py")
    assert "meridian-cricket-recorder" in s and "meridian-tt-recorder" in s
