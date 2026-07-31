"""Odds math and the closing-line guard.

The closing-line tests matter most: CLV is the backtest's primary metric, and
mislabelling a line as "closing" fabricates it.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from core.feeds.espn_odds import ESPNOddsFetcher
from core.feeds.odds_math import (
    american_to_probability,
    consensus,
    parse_american,
    parse_line,
    two_sided_no_vig,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 31, tzinfo=UTC)


# ---------------------------------------------------------------- #
# American odds parsing
# ---------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw,expected",
    [
        (-1400, Decimal(-1400)),   # core API: bare int
        ("+515", Decimal(515)),     # scoreboard: signed string
        ("-110", Decimal(-110)),
        ("EVEN", Decimal(100)),
        ("", None),
        (None, None),
    ],
)
def test_parse_american_handles_every_encoding(raw, expected):
    assert parse_american(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("o186.5", Decimal("186.5")),   # scoreboard total
        ("u186.5", Decimal("186.5")),
        ("+12.5", Decimal("12.5")),
        ("-3.5", Decimal("-3.5")),
        (186.5, Decimal("186.5")),
    ],
)
def test_parse_line_strips_over_under_prefixes(raw, expected):
    assert parse_line(raw) == expected


def test_american_to_probability():
    # -150 => 150/250 = 0.60
    assert american_to_probability(-150) == pytest.approx(Decimal("0.6"), abs=1e-9)
    # +150 => 100/250 = 0.40
    assert american_to_probability(150) == pytest.approx(Decimal("0.4"), abs=1e-9)


# ---------------------------------------------------------------- #
# Vig removal — the thing that would otherwise manufacture fake edge
# ---------------------------------------------------------------- #

def test_raw_probabilities_exceed_one():
    """A -110/-110 market implies ~104.8%. That excess is the book's margin."""
    a = american_to_probability(-110)
    b = american_to_probability(-110)
    assert a + b > Decimal("1.04")


def test_devigged_probabilities_sum_to_exactly_one():
    for odds_a, odds_b in [(-110, -110), (-150, 130), (-1400, 800), (-105, -115)]:
        pa, pb = two_sided_no_vig(odds_a, odds_b)
        assert pa + pb == pytest.approx(Decimal(1), abs=1e-9), f"{odds_a}/{odds_b}"


def test_devig_preserves_ordering():
    """De-vigging must not flip which side is the favourite."""
    pa, pb = two_sided_no_vig(-200, 170)
    assert pa > pb


def test_devig_of_symmetric_market_is_fifty_fifty():
    pa, pb = two_sided_no_vig(-110, -110)
    assert pa == pytest.approx(Decimal("0.5"), abs=1e-9)


# ---------------------------------------------------------------- #
# Consensus
# ---------------------------------------------------------------- #

def test_consensus_uses_median_not_mean():
    """One stale book must not drag the consensus."""
    lines = [Decimal("166.5"), Decimal("167.0"), Decimal("167.5"), Decimal("999.0")]
    assert consensus(lines) == Decimal("167.25")  # median; mean would be ~375


def test_consensus_ignores_nulls():
    assert consensus([Decimal("5"), None, Decimal("7")]) == Decimal("6")


def test_consensus_of_nothing_is_none():
    assert consensus([None, None]) is None


# ---------------------------------------------------------------- #
# Closing-line guard
# ---------------------------------------------------------------- #

def test_closing_line_requires_both_close_object_and_final_game():
    item = {
        "provider": {"name": "ESPN BET"},
        "overUnder": 166.5,
        "spread": 15.5,
        "open": {"total": {"american": "164.5"}},
        "close": {"total": {"american": "166.5"}},
    }
    final = ESPNOddsFetcher.parse_historical_item(item, "g1", NOW, NOW, game_is_final=True)
    assert final["is_closing_line"] is True
    assert final["open_total"] == Decimal("164.5")
    assert final["close_total"] == Decimal("166.5")

    # Same payload, game not yet final -> not a closing line.
    unplayed = ESPNOddsFetcher.parse_historical_item(item, "g1", NOW, NOW, game_is_final=False)
    assert unplayed["is_closing_line"] is False


def test_no_close_object_means_no_closing_line():
    """2020-2023 carry consensus lines but no open/close split."""
    item = {"provider": {"name": "Bet365"}, "overUnder": 166.5, "spread": 4.0}
    row = ESPNOddsFetcher.parse_historical_item(item, "g1", NOW, NOW, game_is_final=True)
    assert row["is_closing_line"] is False
    assert row["close_total"] is None
    assert row["over_under"] == Decimal("166.5")


def test_live_odds_are_never_marked_closing():
    """The live scoreboard nests current prices under keys named 'close'.

    Trusting that name would mark unplayed games as closing lines and corrupt
    the CLV benchmark.
    """
    entry = {
        "provider": {"name": "DraftKings"},
        "overUnder": 186.5,
        "spread": 12.5,
        "total": {"over": {"close": {"line": "o186.5", "odds": "-112"}},
                  "under": {"close": {"line": "u186.5", "odds": "-108"}}},
        "moneyline": {"home": {"close": {"odds": "+515"}},
                      "away": {"close": {"odds": "-750"}}},
    }
    row = ESPNOddsFetcher.parse_live_odds(entry, "g1", NOW, NOW)
    assert row["is_closing_line"] is False
    assert row["close_total"] is None
    # ...but the prices themselves are still captured
    assert row["over_under"] == Decimal("186.5")
    assert row["home_moneyline"] == Decimal("515")
    assert row["away_moneyline"] == Decimal("-750")


def test_juice_in_close_total_is_rejected():
    """ESPN overloads close.total.american.

    For 2024+ it holds the LINE ("166.5"); for 2023 and earlier the SAME field
    holds the ODDS ("-115"). Trusting the field name writes juice into
    close_total and flags the row as a closing line — silently corrupting CLV.
    Observed live on 2023 game 401558893.
    """
    item = {
        "provider": {"name": "ESPN BET"},
        "overUnder": 249.5,
        "close": {"total": {"american": "-115"}},   # odds, not a line
    }
    row = ESPNOddsFetcher.parse_historical_item(item, "g1", NOW, NOW, game_is_final=True)
    assert row["close_total"] is None
    assert row["is_closing_line"] is False
    # the genuine line is still captured
    assert row["over_under"] == Decimal("249.5")


def test_genuine_close_total_still_accepted():
    """The fix must not reject real closing lines (2024+)."""
    item = {
        "provider": {"name": "ESPN BET"},
        "overUnder": 166.5,
        "open": {"total": {"american": "164.5"}},
        "close": {"total": {"american": "166.5"}},
    }
    row = ESPNOddsFetcher.parse_historical_item(item, "g1", NOW, NOW, game_is_final=True)
    assert row["close_total"] == Decimal("166.5")
    assert row["open_total"] == Decimal("164.5")
    assert row["is_closing_line"] is True


@pytest.mark.parametrize(
    "value,reference,expected",
    [
        (Decimal("166.5"), Decimal("166.5"), Decimal("166.5")),  # exact match
        (Decimal("164.5"), Decimal("166.5"), Decimal("164.5")),  # small move, fine
        (Decimal("-115"), Decimal("249.5"), None),               # negative -> odds
        (Decimal("115"), Decimal("249.5"), None),                # far from line
        (Decimal("50"), None, None),                             # implausibly low
        (Decimal("500"), None, None),                            # implausibly high
        (None, Decimal("166.5"), None),
    ],
)
def test_plausible_total_guard(value, reference, expected):
    from core.feeds.odds_math import plausible_total

    assert plausible_total(value, reference) == expected


def test_missing_provider_does_not_crash():
    row = ESPNOddsFetcher.parse_historical_item({}, "g1", NOW, NOW, game_is_final=True)
    assert row["provider_name"] == "unknown"
    assert row["is_closing_line"] is False
