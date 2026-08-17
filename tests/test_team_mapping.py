"""Polymarket <-> ESPN join hazards.

Each of these was found against live data, and each fails *silently* — wrong
sign or missing rows, never an exception. That is why they are pinned.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.storage import get_engine, get_sessionmaker
from core.team_mapping import (
    POLYMARKET_TO_ESPN,
    GameOrientation,
    UnknownTeamError,
    orient_for_slug,
    parse_market_slug,
    resolve_orientation,
    to_espn_abbrev,
    utc_window,
)

UTC = dt.timezone.utc


# ---------------------------------------------------------------- #
# Hazard 1: abbreviations
# ---------------------------------------------------------------- #

def test_the_two_teams_that_differ():
    """`.upper()` would silently drop every Golden State and Connecticut game."""
    assert to_espn_abbrev("gsv") == "GS"
    assert to_espn_abbrev("conn") == "CON"
    assert "gsv".upper() != "GS"
    assert "conn".upper() != "CON"


def test_all_other_teams_are_a_case_change():
    for pm, espn in POLYMARKET_TO_ESPN.items():
        if pm in {"gsv", "conn"}:
            continue
        assert pm.upper() == espn, (pm, espn)


def test_unknown_team_raises_loudly():
    """A new franchise must fail visibly, not vanish from predictions."""
    with pytest.raises(UnknownTeamError):
        to_espn_abbrev("xyz")


# ---------------------------------------------------------------- #
# Hazard 2: timezone
# ---------------------------------------------------------------- #

def test_utc_window_covers_a_game_that_crosses_midnight():
    """Slug 2026-05-10 -> ESPN game_date 2026-05-11 00:30 UTC."""
    start, end = utc_window(dt.date(2026, 5, 10))
    actual = dt.datetime(2026, 5, 11, 0, 30, tzinfo=UTC)
    assert start <= actual < end


def test_exact_date_join_would_have_missed_it():
    """Demonstrates why matching on date alone loses ~half the schedule."""
    slug_date = dt.date(2026, 5, 10)
    espn_date = dt.datetime(2026, 5, 11, 0, 30, tzinfo=UTC).date()
    assert slug_date != espn_date


# ---------------------------------------------------------------- #
# Hazard 3: slug order does not encode home/away
# ---------------------------------------------------------------- #

def test_parsed_slug_exposes_unordered_pair():
    p = parse_market_slug("aec-wnba-gsv-phx-2026-05-10")
    assert p is not None
    assert p.espn_pair == frozenset({"GS", "PHX"})


def test_orientation_comes_from_espn_not_the_slug(mirror):
    """Measured: 18 of 285 closed markets put the HOME team first.

    `aec-wnba-gsv-phx-2026-05-10` is one of them — GS was home and won 95-79,
    so a slug-order assumption would invert the moneyline.
    """
    S = mirror   # real history, read-only (see conftest)
    with S() as s:
        p = parse_market_slug("aec-wnba-gsv-phx-2026-05-10")
        o = resolve_orientation(session=s, parsed=p)
    assert o is not None, "known game failed to join"
    assert o.home_abbrev == "GS"      # NOT phx, despite being second in the slug
    assert o.away_abbrev == "PHX"
    assert o.first_is_home is True    # the slug's first team was home here


def test_orientation_handles_the_normal_ordering_too(mirror):
    S = mirror   # real history, read-only (see conftest)
    with S() as s:
        p = parse_market_slug("aec-wnba-min-tor-2026-07-30")
        o = resolve_orientation(session=s, parsed=p)
    if o is None:
        pytest.skip("game not in the database")
    assert {o.home_abbrev, o.away_abbrev} == {"MIN", "TOR"}


def test_ambiguous_or_missing_match_returns_none_not_a_guess():
    """A wrong join attaches the wrong outcome — worse than no join."""
    S = get_sessionmaker(get_engine())
    with S() as s:
        p = parse_market_slug("aec-wnba-min-tor-1999-01-01")
        assert resolve_orientation(session=s, parsed=p) is None


def test_orient_for_slug_flips_first_is_home_correctly():
    """The same ESPN game, seen from either slug ordering."""
    game = GameOrientation(
        espn_game_id="1", home_abbrev="GS", away_abbrev="PHX",
        game_date=dt.datetime(2026, 5, 11, 0, 30, tzinfo=UTC), first_is_home=False,
    )
    omap = {(frozenset({"GS", "PHX"}), dt.date(2026, 5, 11)): game}

    gs_first = orient_for_slug(parse_market_slug("aec-wnba-gsv-phx-2026-05-10"), omap)
    phx_first = orient_for_slug(parse_market_slug("aec-wnba-phx-gsv-2026-05-10"), omap)

    assert gs_first.first_is_home is True     # GS is home
    assert phx_first.first_is_home is False   # PHX is away
    # Both resolve to the same underlying game.
    assert gs_first.espn_game_id == phx_first.espn_game_id


def test_slug_prefixes_are_recognised():
    for slug, expected in [
        ("tsc-wnba-sea-atl-2026-07-31-165pt5", "tsc"),
        ("asc-wnba-sea-atl-2026-07-31-pos-19pt5", "asc"),
        ("aec-wnba-sea-atl-2026-07-31", "aec"),
    ]:
        p = parse_market_slug(slug)
        assert p is not None and p.market_type == expected


def test_garbage_slug_returns_none():
    assert parse_market_slug("not-a-slug") is None
    assert parse_market_slug("") is None
