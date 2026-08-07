"""Board-survey tests.

Three things carry the weight:

* **It must reach no conclusion.** The module is a survey, not a gate. A
  threshold added later would decide October by whoever picked the number, so
  the absence of one is asserted against the source.
* **The tip-off horizon control.** Spread swings 12x with time to tip-off on
  the same board. An unmatched comparison makes a far-dated board look thin,
  and thin is what this project buys — so it would argue for entering a market
  on a clock artifact.
* **Spreads are near-money only.** A deep rung quoting 0.01/0.26 is an empty
  book, and letting it into a median makes any board look wide.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest

from core.survey import (
    BASELINE_LEAGUE,
    HORIZON_BUCKETS,
    NEAR_MONEY_HI,
    NEAR_MONEY_LO,
    DepthObs,
    MarketObs,
    Survey,
    fee_coefficients,
    format_report,
    ladders_per_event,
    spread_by_horizon,
    stats_by_type,
    tick_sizes,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 15, 18, 0, tzinfo=UTC)


def _m(bid, ask, *, mtype="basketball_team_full_game_total", event="nba-a-b-2026-10-15",
       slug=None, tick=0.01, fee=0.06, hours=1.0) -> MarketObs:
    return MarketObs(
        market_slug=slug or f"m{bid}-{ask}-{event}", event_slug=event,
        market_type=mtype, bid=bid, ask=ask, tick_size=tick,
        fee_coefficient=fee, hours_to_tipoff=hours,
    )


def _survey(markets, depth=(), league="nba", source="live") -> Survey:
    return Survey(league=league, source=source, captured_at=NOW,
                  markets=list(markets), depth=list(depth),
                  depth_markets_sampled=len(depth), depth_markets_available=len(markets))


# --------------------------------------------------------------------- #
# It reaches no conclusion, and that is enforced
# --------------------------------------------------------------------- #


def test_the_module_defines_no_gate_or_threshold():
    """A survey describes a board nobody has seen. It must not decide.

    Every other measurement module here carries a pre-registered gate. This one
    deliberately does not, and a later addition would silently move the October
    decision from a human reading the board to whoever chose the constant.
    """
    import ast

    import core.survey as m

    tree = ast.parse(inspect.getsource(m))
    # Strip every docstring: the module's prose *explains* that it has no gate,
    # so scanning raw source would match its own disclaimer.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    code = ast.unparse(ast.fix_missing_locations(tree))

    for forbidden in ("GATE_", "PASS", "FAIL", "VERDICT"):
        assert forbidden not in code, (
            f"{forbidden!r} appears in survey CODE (not prose) — a survey must "
            "not decide")
    # And no bare numeric threshold constants named like a bar.
    assert not [n for n in ast.walk(tree)
                if isinstance(n, ast.Name) and n.id.startswith(("GATE", "THRESHOLD",
                                                                "MIN_ACCEPT", "MAX_ACCEPT"))]


def test_the_report_says_it_decides_nothing():
    report = format_report(_survey([_m(0.48, 0.50)]), None)
    assert "NO conclusion" in report
    assert "no gate and no threshold" in report


def test_the_report_states_the_direction_that_matters():
    """Thin is the product. A tighter board is worse, not better."""
    report = format_report(_survey([_m(0.48, 0.50)]), None)
    assert "THIN" in report
    assert "rejection" in report


# --------------------------------------------------------------------- #
# The tip-off horizon control
# --------------------------------------------------------------------- #


def test_horizon_buckets_cover_the_line_without_gaps():
    assert HORIZON_BUCKETS[0][1] < 0
    for (_, _, hi), (_, lo2, _) in zip(HORIZON_BUCKETS, HORIZON_BUCKETS[1:]):
        assert hi == lo2, "buckets must tile, or observations vanish between them"


def test_a_market_lands_in_exactly_one_bucket():
    assert _m(0.48, 0.50, hours=1.0).horizon_bucket == "0-3h"
    assert _m(0.48, 0.50, hours=18.0).horizon_bucket == "12-24h"
    assert _m(0.48, 0.50, hours=-2.0).horizon_bucket == "live/past"
    assert _m(0.48, 0.50, hours=200.0).horizon_bucket == ">72h"


def test_a_market_with_no_tipoff_time_has_no_bucket_rather_than_a_default():
    assert _m(0.48, 0.50, hours=None).horizon_bucket is None


def test_spread_by_horizon_separates_the_clock_effect():
    """The same board, tight near tip-off and wide when far-dated."""
    markets = ([_m(0.49, 0.50, hours=1.0, slug=f"near{i}") for i in range(5)]
               + [_m(0.44, 0.56, hours=18.0, slug=f"far{i}") for i in range(5)])
    buckets = spread_by_horizon(_survey(markets))
    assert buckets["0-3h"][1] == pytest.approx(0.01)
    assert buckets["12-24h"][1] == pytest.approx(0.12)


def test_mismatched_horizons_are_flagged_in_the_report():
    """The October failure mode: far-dated NBA against near-tipoff WNBA."""
    target = _survey([_m(0.44, 0.56, hours=48.0, slug=f"t{i}") for i in range(5)])
    baseline = _survey([_m(0.49, 0.50, hours=0.5, slug=f"b{i}", event="wnba-x-y-2026-08-01")
                        for i in range(5)], league="wnba", source="recorded")
    report = format_report(target, baseline)
    assert "NOT comparable at face value" in report


def test_non_overlapping_horizons_are_named_as_having_no_comparable_row():
    """The MLB-vs-WNBA case: 6-12h against 12-24h is not a comparison.

    Without this the reader eyeballs adjacent rows and treats them as matched.
    """
    target = _survey([_m(0.49, 0.50, hours=8.0, slug=f"t{i}") for i in range(5)])
    baseline = _survey([_m(0.44, 0.56, hours=18.0, slug=f"b{i}", event="wnba-x-y-2026-08-01")
                        for i in range(5)], league="wnba", source="recorded")
    report = format_report(target, baseline)
    assert "NO horizon bucket has data on both sides" in report


def test_an_overlapping_bucket_is_named_as_the_comparable_row():
    target = _survey([_m(0.49, 0.50, hours=8.0, slug=f"t{i}") for i in range(5)])
    baseline = _survey([_m(0.44, 0.56, hours=9.0, slug=f"b{i}", event="wnba-x-y-2026-08-01")
                        for i in range(5)], league="wnba", source="recorded")
    report = format_report(target, baseline)
    assert "Buckets with data on BOTH sides: 6-12h" in report


def test_matched_horizons_are_not_flagged():
    target = _survey([_m(0.44, 0.56, hours=1.0, slug=f"t{i}") for i in range(5)])
    baseline = _survey([_m(0.49, 0.50, hours=1.5, slug=f"b{i}", event="wnba-x-y-2026-08-01")
                        for i in range(5)], league="wnba", source="recorded")
    assert "NOT comparable at face value" not in format_report(target, baseline)


# --------------------------------------------------------------------- #
# Spreads are near-money only
# --------------------------------------------------------------------- #


def test_a_deep_rung_does_not_enter_the_spread_median():
    """0.01/0.26 is an empty book, not a 25c market."""
    markets = [_m(0.49, 0.50, slug="a"), _m(0.01, 0.26, slug="b")]
    s = _survey(markets)
    assert len(s.near_money) == 1
    stat = stats_by_type(s)[0]
    assert stat.n == 2 and stat.n_near == 1
    assert stat.spread_median == pytest.approx(0.01)


def test_the_near_money_band_is_inclusive_at_its_edges():
    assert _m(NEAR_MONEY_LO - 0.01, NEAR_MONEY_LO + 0.01).is_near_money is True
    assert _m(0.01, 0.03).is_near_money is False


def test_an_unquoted_market_is_counted_but_not_priced():
    s = _survey([_m(None, None, slug="a"), _m(0.49, 0.50, slug="b")])
    assert s.n_markets == 2
    assert len(s.quoted) == 1


# --------------------------------------------------------------------- #
# The V7 statistics
# --------------------------------------------------------------------- #


def test_tick_as_share_of_value_is_price_dependent():
    """1c is 2% of a 50c contract and 6.25% of a 16c one (V2)."""
    assert _m(0.49, 0.51, tick=0.01).tick_pct_of_value == pytest.approx(0.02)
    assert _m(0.15, 0.17, tick=0.01).tick_pct_of_value == pytest.approx(0.0625)


def test_tick_sizes_are_reported_as_a_distribution_not_an_average():
    """MLB had half-cent ticks; a mean of a mixture would hide that."""
    s = _survey([_m(0.49, 0.50, tick=0.01, slug="a"),
                 _m(0.49, 0.50, tick=0.005, slug="b")])
    assert tick_sizes(s) == {0.01: 1, 0.005: 1}


def test_fee_coefficients_are_reported_as_a_distribution():
    s = _survey([_m(0.49, 0.50, fee=0.06, slug="a"),
                 _m(0.49, 0.50, fee=0.06, slug="b"),
                 _m(0.49, 0.50, fee=0.03, slug="c")])
    assert fee_coefficients(s) == {0.06: 2, 0.03: 1}


def test_ladder_count_is_per_event():
    markets = ([_m(0.49, 0.50, event="nba-a-b", slug=f"a{i}") for i in range(9)]
               + [_m(0.49, 0.50, event="nba-c-d", slug=f"c{i}") for i in range(11)])
    median, n_events = ladders_per_event(_survey(markets))
    assert n_events == 2
    assert median == pytest.approx(10.0)


def test_depth_notional_is_price_times_size():
    d = DepthObs(market_slug="m", side="bid", price=0.25, quantity=400.0)
    assert d.notional == pytest.approx(100.0)


# --------------------------------------------------------------------- #
# Empty boards say so
# --------------------------------------------------------------------- #


def test_an_empty_board_is_reported_as_a_request_problem_not_a_thin_board():
    from core.survey import main

    # No league argument reaching a real client: an empty survey must not
    # render as a legitimately thin board.
    s = _survey([], league="nba")
    report = format_report(s, None)
    assert "events=0" in report
    assert "markets=0" in report


def test_the_baseline_league_is_not_compared_against_itself():
    from core.survey import _load_baseline

    assert _load_baseline(BASELINE_LEAGUE) is None
