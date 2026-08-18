"""The hand-trade audit's arithmetic, pinned.

Everything here is C11's frame: money at the actual price, YES cost = price
paid, NO cost = 1 − price. The reconstruction rules under test:

* an episode runs zero → nonzero → zero net YES exposure, per market;
* a fill that crosses zero is split, and the crossing opens a new round trip;
* settlement closes the remainder at the market's 0/1 YES payout — from the
  public settlement endpoint, never inferred;
* button orders are excluded by venue order id ONLY (the fill watcher's
  attribution rule), never by similarity;
* an unknown settlement leaves the episode OPEN and unscored — reported,
  never guessed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from core.audit.hand_trades import (
    Fill,
    Resolution,
    build_round_trips,
    parse_activity,
    run_audit,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 6, 22, 0, tzinfo=UTC)
TIP = dt.datetime(2026, 8, 6, 23, 0, tzinfo=UTC)


def _fill(minutes, *, buy, yes, px, shares, slug="m1", oid="H1",
          mtype="basketball_team_full_game_total", start=TIP, manual=True):
    return Fill(
        market_slug=slug, market_type=mtype, game_start=start,
        at=T0 + dt.timedelta(minutes=minutes), venue_order_id=oid,
        is_buy=buy, outcome_yes=yes,
        yes_price=Decimal(str(px)), shares=Decimal(str(shares)),
        manual=manual, commission=Decimal("0"),
    )


def _no_settlement(_slug):
    raise AssertionError("settlement must not be consulted for trade-closed trips")


# ------------------------------------------------------------------ #
# The C11 frame
# ------------------------------------------------------------------ #


def test_yes_round_trip_scored_at_prices():
    """Buy 10 YES at 0.30, sell at 0.50: $3 in, $5 out, +66.7%."""
    fills = [
        _fill(0, buy=True, yes=True, px=0.30, shares=10),
        _fill(30, buy=False, yes=True, px=0.50, shares=10),
    ]
    closed, open_ = build_round_trips(fills, [], _no_settlement)
    assert open_ == []
    (t,) = closed
    assert t.staked == Decimal("3.0") and t.returned == Decimal("5.0")
    assert t.roi == Decimal("2") / Decimal("3")
    assert t.win and t.direction == "YES" and t.closed_by == "trades"
    assert t.entry_cost == Decimal("0.30")


def test_no_cost_is_one_minus_price():
    """Buying NO at YES-frame 0.80 stakes 0.20/contract (V14: the venue
    reports every price in the YES frame). Settlement at YES=0 pays the NO
    holder 1.00/contract."""
    fills = [_fill(0, buy=True, yes=False, px=0.80, shares=5)]
    resolutions = [Resolution("m1", T0 + dt.timedelta(hours=4))]
    closed, open_ = build_round_trips(fills, resolutions, lambda s: Decimal("0"))
    (t,) = closed
    assert t.direction == "NO"
    assert t.staked == Decimal("1.0")        # 5 x (1 - 0.80)
    assert t.returned == Decimal("5.0")      # 5 x 1.00
    assert t.closed_by == "settlement"
    assert t.entry_cost == Decimal("0.20")


def test_losing_settlement_returns_zero():
    fills = [_fill(0, buy=True, yes=True, px=0.25, shares=8)]
    resolutions = [Resolution("m1", T0 + dt.timedelta(hours=4))]
    closed, _ = build_round_trips(fills, resolutions, lambda s: Decimal("0"))
    (t,) = closed
    assert t.staked == Decimal("2.0") and t.returned == Decimal("0")
    assert not t.win


# ------------------------------------------------------------------ #
# Episode boundaries
# ------------------------------------------------------------------ #


def test_zero_crossing_splits_into_two_round_trips():
    """Buy 10 YES then sell 15: the sell closes 10 and opens a 5-short."""
    fills = [
        _fill(0, buy=True, yes=True, px=0.40, shares=10),
        _fill(10, buy=False, yes=True, px=0.60, shares=15),
    ]
    resolutions = [Resolution("m1", T0 + dt.timedelta(hours=4))]
    closed, open_ = build_round_trips(fills, resolutions, lambda s: Decimal("1"))
    assert len(closed) == 2 and open_ == []
    long_trip, short_trip = closed
    assert long_trip.direction == "YES"
    assert long_trip.staked == Decimal("4.0") and long_trip.returned == Decimal("6.0")
    assert short_trip.direction == "NO"
    assert short_trip.staked == Decimal("2.0")       # 5 x (1 - 0.60)
    assert short_trip.returned == Decimal("0")       # YES settled 1; short loses
    assert short_trip.closed_by == "settlement"


def test_partial_exit_then_settlement_is_mixed():
    fills = [
        _fill(0, buy=True, yes=True, px=0.20, shares=10),
        _fill(20, buy=False, yes=True, px=0.35, shares=4),
    ]
    resolutions = [Resolution("m1", T0 + dt.timedelta(hours=4))]
    closed, _ = build_round_trips(fills, resolutions, lambda s: Decimal("1"))
    (t,) = closed
    assert t.closed_by == "mixed"
    assert t.returned == Decimal("4") * Decimal("0.35") + Decimal("6")


def test_unknown_settlement_leaves_position_open_not_guessed():
    fills = [_fill(0, buy=True, yes=True, px=0.30, shares=10)]
    resolutions = [Resolution("m1", T0 + dt.timedelta(hours=4))]
    closed, open_ = build_round_trips(fills, resolutions, lambda s: None)
    assert closed == [] and len(open_) == 1


def test_markets_are_independent():
    fills = [
        _fill(0, buy=True, yes=True, px=0.30, shares=10, slug="m1"),
        _fill(1, buy=True, yes=True, px=0.60, shares=5, slug="m2"),
        _fill(30, buy=False, yes=True, px=0.50, shares=10, slug="m1"),
        _fill(31, buy=False, yes=True, px=0.55, shares=5, slug="m2"),
    ]
    closed, open_ = build_round_trips(fills, [], _no_settlement)
    assert len(closed) == 2 and open_ == []


# ------------------------------------------------------------------ #
# Phase split
# ------------------------------------------------------------------ #


def test_phase_is_decided_by_first_entry_vs_game_start():
    pre = _fill(0, buy=True, yes=True, px=0.30, shares=1)          # 22:00 < 23:00 tip
    live = _fill(90, buy=True, yes=True, px=0.30, shares=1, slug="m2")  # 23:30
    fills = [pre, _fill(5, buy=False, yes=True, px=0.30, shares=1),
             live, _fill(95, buy=False, yes=True, px=0.30, shares=1, slug="m2")]
    closed, _ = build_round_trips(fills, [], _no_settlement)
    phases = {t.market_slug: t.phase for t in closed}
    assert phases == {"m1": "pregame", "m2": "live"}


# ------------------------------------------------------------------ #
# Exclusion and provenance
# ------------------------------------------------------------------ #


def _activity(*, oid, side, outcome, px, shares, slug="m1", manual=True):
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": slug,
            "market": {"sportsMarketType": "basketball_team_full_game_total",
                       "gameStartTime": "2026-08-06T23:00:00Z"},
            "passiveExecution": {
                "order": {
                    "id": oid, "side": side, "outcomeSide": outcome,
                    "manualOrderIndicator": (
                        "MANUAL_ORDER_INDICATOR_MANUAL" if manual else
                        "MANUAL_ORDER_INDICATOR_AUTOMATED"),
                },
                "lastPx": {"value": str(px)},
                "lastShares": str(shares),
                "transactTime": "2026-08-06T22:10:00.000000000Z",
                "commissionNotionalCollected": {"value": "0.01"},
            },
            "aggressorExecution": None,
        },
    }


def test_button_orders_excluded_by_venue_id_only():
    """The hand fill and the button fill are identical in market, price and
    size — only the venue order id separates them, and it must be enough."""
    acts = [
        _activity(oid="HAND1", side="ORDER_SIDE_BUY", outcome="OUTCOME_SIDE_YES",
                  px="0.30", shares="10"),
        _activity(oid="BTN99", side="ORDER_SIDE_BUY", outcome="OUTCOME_SIDE_YES",
                  px="0.30", shares="10"),
    ]
    report = run_audit(acts, excluded_ids={"BTN99"}, settlement_lookup=lambda s: None)
    prov = report["provenance"]
    assert prov["hand_fills_scored"] == 1
    assert prov["button_fills_excluded_by_venue_order_id"] == 1
    assert "DESCRIPTIVE" in prov["kind"], "this report is not allowed a verdict"


def test_kept_non_manual_fills_are_counted_loudly():
    acts = [_activity(oid="ODD1", side="ORDER_SIDE_BUY", outcome="OUTCOME_SIDE_YES",
                      px="0.30", shares="1", manual=False)]
    report = run_audit(acts, excluded_ids=set(), settlement_lookup=lambda s: None)
    assert report["provenance"]["kept_fills_not_marked_MANUAL"] == 1


def test_unparsed_activity_is_counted_never_guessed():
    acts = [{"type": "ACTIVITY_TYPE_TRADE", "trade": {"passiveExecution": {
        "order": {"id": "X"}}}}]
    report = run_audit(acts, excluded_ids=set(), settlement_lookup=lambda s: None)
    assert report["provenance"]["unparsed_activities"] == 1
    assert report["provenance"]["hand_fills_scored"] == 0


def test_parse_real_shape_smoke():
    """The observed 2026-08-07 shape parses: SELL YES 20 @ 0.25, MANUAL."""
    raw = _activity(oid="BQ8WS4B8CBA1", side="ORDER_SIDE_SELL",
                    outcome="OUTCOME_SIDE_YES", px="0.2500", shares="20.0000")
    fills, resolution, ok = parse_activity(raw)
    assert ok and resolution is None and len(fills) == 1
    f = fills[0]
    assert not f.is_buy and f.outcome_yes and f.manual
    assert f.yes_price == Decimal("0.25") and f.shares == Decimal("20.0000")
    assert f.yes_delta == Decimal("-20.0000")


# ------------------------------------------------------------------ #
# V22 — a trade has two sides and the venue sends both
# ------------------------------------------------------------------ #
#
# This module used to take every non-null execution, on the belief written
# into its own docstring that "the feed nulls the side that is not ours".
# Measured 2026-08-17: 455 of 455 trade activities carried BOTH, so every
# trade was scored twice — once as us, once as our counterparty, at opposite
# YES exposure. `isAggressor` is the discriminator.


def _two_sided(*, is_aggressor, our_side="ORDER_SIDE_BUY",
               our_outcome="OUTCOME_SIDE_YES", their_outcome="OUTCOME_SIDE_UNSPECIFIED",
               slug="m1"):
    """The real shape: both executions populated, one of them ours."""
    def _leg(oid, side, outcome, manual, commission):
        return {
            "order": {"id": oid, "side": side, "outcomeSide": outcome,
                      "manualOrderIndicator": manual},
            "lastPx": {"value": "0.4800"},
            "lastShares": "12.0000",
            "transactTime": "2026-08-06T22:10:00.000000000Z",
            "commissionNotionalCollected": {"value": commission},
        }

    their_side = ("ORDER_SIDE_SELL" if our_side == "ORDER_SIDE_BUY"
                  else "ORDER_SIDE_BUY")
    ours = _leg("OURS", our_side, our_outcome,
                "MANUAL_ORDER_INDICATOR_MANUAL", "0.1800")
    theirs = _leg("THEIRS", their_side, their_outcome,
                  "MANUAL_ORDER_INDICATOR_UNDEFINED", "-0.0400")
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": slug,
            "isAggressor": is_aggressor,
            "qty": "12",
            "realizedPnl": {"value": "2.54"},
            "market": {"sportsMarketType": "basketball_team_full_game_total",
                       "gameStartTime": "2026-08-06T23:00:00Z"},
            "aggressorExecution": ours if is_aggressor else theirs,
            "passiveExecution": theirs if is_aggressor else ours,
        },
    }


def test_only_our_side_of_a_two_sided_trade_is_scored():
    for is_aggressor in (True, False):
        fills, _, ok = parse_activity(_two_sided(is_aggressor=is_aggressor))
        assert ok, "the real shape must parse"
        assert len(fills) == 1, "the counterparty's leg is not our fill"
        assert fills[0].venue_order_id == "OURS"
        assert fills[0].yes_delta == Decimal("12.0000")


def test_counting_both_legs_would_have_netted_to_zero():
    """Why the double count was invisible: the two legs are equal and
    opposite, so a market's net exposure always returned to zero and the
    reconstruction happily closed round trips out of counterparty fills."""
    trade = _two_sided(is_aggressor=True, their_outcome="OUTCOME_SIDE_YES")["trade"]
    ours = trade["aggressorExecution"]["order"]
    theirs = trade["passiveExecution"]["order"]
    assert ours["side"] != theirs["side"] and ours["outcomeSide"] == theirs["outcomeSide"]


def test_an_unspecified_outcome_on_our_leg_is_refused():
    """The venue only redacts the counterparty's outcome. If `isAggressor`
    ever points at a redacted leg the field has changed meaning, and every row
    of an export would silently invert. Refuse rather than invert."""
    raw = _two_sided(is_aggressor=True, our_outcome="OUTCOME_SIDE_UNSPECIFIED")
    fills, _, ok = parse_activity(raw)
    assert not ok and fills == []


def test_both_legs_present_with_no_isaggressor_is_refused_not_guessed():
    raw = _two_sided(is_aggressor=True)
    del raw["trade"]["isAggressor"]
    fills, _, ok = parse_activity(raw)
    assert not ok and fills == []


def test_a_single_execution_still_resolves_without_isaggressor():
    """The one-sided shape the older fixtures use: nothing to choose between,
    so it parses rather than refusing."""
    raw = _activity(oid="SOLO", side="ORDER_SIDE_BUY",
                    outcome="OUTCOME_SIDE_YES", px="0.30", shares="10")
    assert "isAggressor" not in raw["trade"]
    fills, _, ok = parse_activity(raw)
    assert ok and len(fills) == 1 and fills[0].venue_order_id == "SOLO"
