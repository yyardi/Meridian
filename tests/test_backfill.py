"""Backfill coverage accounting.

The coverage report is what tells the backtest how much of its sample can
support CLV. If it overstates closing-line coverage, the headline metric is
silently fabricated — so these tests pin the accounting.
"""

from __future__ import annotations

from core.backfill import (
    MAX_PLAUSIBLE_GAME_TOTAL,
    MIN_PLAUSIBLE_GAME_TOTAL,
    Backfill,
    SeasonCoverage,
)
from core.storage import get_engine, get_sessionmaker


def test_real_coverage_matches_known_reality():
    """Against the live database, after the 2020-2026 backfill.

    These numbers are load-bearing: 2020-2022 genuinely have no closing lines
    (ESPN provides multi-book consensus but no open/close split), so CLV must
    not be computed there.
    """
    bf = Backfill(sessionmaker=get_sessionmaker(get_engine()))
    rows = {c.season: c for c in bf.coverage(2020, 2026)}

    # Every season has games and odds.
    for season in range(2020, 2027):
        assert rows[season].regular > 0, f"{season} has no regular-season games"
        assert rows[season].with_odds > 0, f"{season} has no odds"

    # The seasons that cannot support CLV.
    for season in (2020, 2021, 2022):
        assert rows[season].with_closing_line == 0, (
            f"{season} reports closing lines; ESPN has none for it. "
            "Suspect the close.total juice-vs-line bug has regressed."
        )

    # The seasons that can.
    for season in (2024, 2025, 2026):
        assert rows[season].with_closing_line > 200, season

    # No exhibition/All-Star totals leaked in.
    assert all(c.suspicious_totals == 0 for c in rows.values())


def test_postseason_cohorts_are_small_enough_to_warn_about():
    """Playoff samples are ~15-24 games/season.

    The record feature is down-weighted in playoffs, and the backtest reports
    them separately — but no playoff-specific conclusion is supportable at this
    size, which the report must make obvious.
    """
    bf = Backfill(sessionmaker=get_sessionmaker(get_engine()))
    rows = [c for c in bf.coverage(2020, 2025) if c.postseason]
    assert rows, "expected postseason games in 2020-2025"
    assert all(c.postseason <= 30 for c in rows), [c.postseason for c in rows]


def test_plausible_total_bounds_exclude_all_star_games():
    """All-Star games run ~250 and would wreck a model fit."""
    assert MIN_PLAUSIBLE_GAME_TOTAL < 111  # lowest real game observed
    assert MAX_PLAUSIBLE_GAME_TOTAL >= 247  # highest real game observed
    assert MAX_PLAUSIBLE_GAME_TOTAL < 300  # but an All-Star game is excluded


def test_season_coverage_defaults_are_zero():
    c = SeasonCoverage(season=2026)
    assert (c.regular, c.postseason, c.with_odds, c.with_closing_line) == (0, 0, 0, 0)
