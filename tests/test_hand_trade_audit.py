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

import pytest
import datetime as dt
from decimal import Decimal

from core.audit.hand_trades import (

    Fill,
    Resolution,
    build_round_trips,
    parse_activity,
    run_audit,
)


# The venue pairs book mechanics with economics exactly this way — measured on
# the 2026-08-25 activities export, all 496 trades. Fixtures derive `intent`
# from (side, outcome) so a test can never encode a pairing the venue never
# emits, which is how the sign bug survived: the fixtures carried no intent at
# all, so nothing could disagree with the mechanical fields.
_VENUE_INTENT = {
    ("ORDER_SIDE_BUY", "OUTCOME_SIDE_YES"): "ORDER_INTENT_BUY_LONG",
    ("ORDER_SIDE_SELL", "OUTCOME_SIDE_YES"): "ORDER_INTENT_SELL_LONG",
    ("ORDER_SIDE_SELL", "OUTCOME_SIDE_NO"): "ORDER_INTENT_BUY_SHORT",
    ("ORDER_SIDE_BUY", "OUTCOME_SIDE_NO"): "ORDER_INTENT_SELL_SHORT",
}


def _intent_for(side: str, outcome: str) -> str:
    return _VENUE_INTENT.get((side, outcome), "ORDER_INTENT_UNDEFINED")


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
    """A trade where WE are the passive side.

    This fixture used to set ``aggressorExecution: None`` with no
    ``isAggressor`` key, encoding the belief that the feed nulls the
    counterparty. It does not — both executions are always present — and a
    fixture built to that shape is precisely why the double-count survived a
    green suite. It now carries ``isAggressor`` and a populated counterparty,
    so anything reading the wrong side shows up here.
    """
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": slug,
            "isAggressor": False,          # ours is the passive execution
            "market": {"sportsMarketType": "basketball_team_full_game_total",
                       "gameStartTime": "2026-08-06T23:00:00Z"},
            "passiveExecution": {
                "order": {
                    "id": oid, "side": side, "outcomeSide": outcome,
                    "intent": _intent_for(side, outcome),
                    "manualOrderIndicator": (
                        "MANUAL_ORDER_INDICATOR_MANUAL" if manual else
                        "MANUAL_ORDER_INDICATOR_AUTOMATED"),
                },
                "lastPx": {"value": str(px)},
                "lastShares": str(shares),
                "transactTime": "2026-08-06T22:10:00.000000000Z",
                "commissionNotionalCollected": {"value": "0.01"},
            },
            # The counterparty, always present. Deliberately given a venue
            # order id that would blow up the exclusion tests if it were ever
            # read as ours.
            "aggressorExecution": {
                "order": {
                    "id": "COUNTERPARTY", "side": "ORDER_SIDE_BUY",
                    "outcomeSide": outcome,
                    # The venue redacts intent on the counterparty's leg: it is
                    # UNDEFINED on every passive leg in the real export.
                    "intent": "ORDER_INTENT_UNDEFINED",
                    "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_AUTOMATED",
                },
                "lastPx": {"value": str(px)},
                "lastShares": str(shares),
                "transactTime": "2026-08-06T22:10:00.000000000Z",
                "commissionNotionalCollected": {"value": "-0.01"},
            },
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
    """A realistic trade parses to exactly ONE fill: SELL YES 20 @ 0.25."""
    raw = _activity(oid="BQ8WS4B8CBA1", side="ORDER_SIDE_SELL",
                    outcome="OUTCOME_SIDE_YES", px="0.2500", shares="20.0000")
    fills, resolution, ok = parse_activity(raw)
    assert ok and resolution is None and len(fills) == 1
    f = fills[0]
    assert not f.is_buy and f.outcome_yes and f.manual
    assert f.yes_price == Decimal("0.25") and f.shares == Decimal("20.0000")
    assert f.yes_delta == Decimal("-20.0000")

# ------------------------------------------------------------------ #
# Whose execution is whose — the two-sided feed
# ------------------------------------------------------------------ #
#
# The helpers above build Fill objects directly, so none of them exercise
# parse_activity, which is where the account's numbers were actually being
# corrupted: the feed sends BOTH counterparties of every trade and the parser
# took both, booking a phantom offsetting fill against every real one. These
# drive raw activities instead.

def _two_sided(*, is_aggressor, slug="m1", price="0.4800", qty=12):
    """A trade shaped like the live feed: both executions present, same price,
    opposite order sides. Observed on 455 of 455 trades, 2026-08-17."""
    def _ex(order_id, side, commission):
        return {
            "lastPx": {"value": price, "currency": "USD"},
            "lastShares": qty,
            "transactTime": "2026-08-06T22:00:00.000000Z",
            "commissionNotionalCollected": {"value": commission, "currency": "USD"},
            "order": {
                "id": order_id, "side": side, "outcomeSide": "OUTCOME_SIDE_YES",
                "intent": _intent_for(side, "OUTCOME_SIDE_YES"),
                "marketSlug": slug,
                "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
            },
        }
    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": slug,
            "isAggressor": is_aggressor,
            "aggressorExecution": _ex("OURS_AGG", "ORDER_SIDE_BUY", "0.18"),
            "passiveExecution": _ex("THEIRS", "ORDER_SIDE_SELL", "-0.04"),
        },
    }

def test_exactly_one_fill_per_trade_never_both_counterparties():
    """The regression. Both executions are present; only ours is scored."""
    fills, _, ok = parse_activity(_two_sided(is_aggressor=True))
    assert ok and len(fills) == 1
    assert fills[0].venue_order_id == "OURS_AGG"
    assert fills[0].is_buy is True

def test_is_aggressor_false_selects_the_passive_execution():
    fills, _, ok = parse_activity(_two_sided(is_aggressor=False))
    assert ok and len(fills) == 1
    assert fills[0].venue_order_id == "THEIRS"      # ours in this trade
    assert fills[0].is_buy is False
    # Commission follows the side too: the aggressor pays, the passive earns.
    assert fills[0].commission == Decimal("-0.04")

def test_a_two_sided_trade_does_not_net_itself_to_zero():
    """What the bug did to the arithmetic. Taking both counterparties books
    +12 and −12 in one market: an episode that opens and closes on a single
    trade, stakes real dollars, and settles break-even — which is not a win,
    so it dilutes the win rate while inflating stake."""
    fills, _, _ = parse_activity(_two_sided(is_aggressor=True))
    assert sum(f.yes_delta for f in fills) == Decimal("12")
    closed, open_ = build_round_trips(fills, [], _no_settlement)
    assert closed == []                  # one fill opens a position, closes none
    assert len(open_) == 1 and open_[0].contracts == Decimal("12")

def test_missing_is_aggressor_fails_loudly_rather_than_guessing():
    """A wrong side is a wrong sign, not a missing value, so an unattributable
    trade is reported as unparsed instead of resolved by coin flip."""
    raw = _two_sided(is_aggressor=True)
    del raw["trade"]["isAggressor"]
    assert parse_activity(raw) == ([], None, False)
    raw["trade"]["isAggressor"] = "true"          # string, not bool
    assert parse_activity(raw) == ([], None, False)

def test_missing_our_execution_is_unparsed():
    raw = _two_sided(is_aggressor=True)
    raw["trade"]["aggressorExecution"] = None
    assert parse_activity(raw) == ([], None, False)

def test_redacted_intent_on_our_leg_is_refused_not_guessed():
    """`intent` is the field the sign is computed from (V28), so a redacted one
    on the leg `isAggressor` picked means the SELECTION is wrong.

    The venue emits ORDER_INTENT_UNDEFINED only on the counterparty's leg —
    measured on the 2026-08-25 export, our own leg carries one of the four real
    intents on all 496 trades. Refusing is therefore correct rather than
    conservative: the alternative is falling back to side/outcomeSide, which is
    exactly the book-mechanics reading that inverted 207 of those 496 rows.
    """
    raw = _two_sided(is_aggressor=True)
    raw["trade"]["aggressorExecution"]["order"]["intent"] = "ORDER_INTENT_UNDEFINED"
    assert parse_activity(raw) == ([], None, False)


def test_book_mechanics_alone_cannot_book_a_fill():
    """A row carrying only side/outcomeSide — no intent — must refuse.

    This is the shape the fixtures used to have, and it is why the sign bug
    survived a green suite: nothing in the feed could contradict the mechanical
    fields because the authoritative one was never present.
    """
    raw = _two_sided(is_aggressor=True)
    del raw["trade"]["aggressorExecution"]["order"]["intent"]
    assert parse_activity(raw) == ([], None, False)


def test_a_redacted_counterparty_leg_is_simply_not_looked_at():
    """The normal live shape: theirs redacted, ours intact, and we score ours."""
    raw = _two_sided(is_aggressor=True)
    raw["trade"]["passiveExecution"]["order"]["outcomeSide"] = "OUTCOME_SIDE_UNSPECIFIED"
    fills, _, ok = parse_activity(raw)
    assert ok and len(fills) == 1 and fills[0].outcome_yes is True


# --------------------------------------------------------------------- #
# Sign, booked from `intent` (V28). Same defect as the trade sheet's: this
# module shared the (side, outcomeSide) reading, and the two modules agreeing
# to the cent on WNBA was evidence about a SHARED ASSUMPTION, not about
# correctness. Verified against the 2026-08-25 export before changing either.
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "intent, side, outcome, expect_positive, what",
    [
        ("ORDER_INTENT_BUY_LONG", "ORDER_SIDE_BUY", "OUTCOME_SIDE_YES", True, "buy YES"),
        ("ORDER_INTENT_SELL_LONG", "ORDER_SIDE_SELL", "OUTCOME_SIDE_YES", False, "sell YES"),
        ("ORDER_INTENT_BUY_SHORT", "ORDER_SIDE_SELL", "OUTCOME_SIDE_NO", False, "buy NO"),
        ("ORDER_INTENT_SELL_SHORT", "ORDER_SIDE_BUY", "OUTCOME_SIDE_NO", True, "sell NO"),
    ],
)
def test_hand_fill_sign_follows_intent(intent, side, outcome, expect_positive, what):
    raw = _activity(oid="HAND1", side=side, outcome=outcome, px="0.25", shares="20")
    raw["trade"]["passiveExecution"]["order"]["intent"] = intent
    fills, _, ok = parse_activity(raw)
    assert ok and len(fills) == 1, f"{what} was not parsed"
    assert (fills[0].yes_delta > 0) is expect_positive, (
        f"{what} ({intent}) booked {fills[0].yes_delta:+} YES exposure; "
        f"side={side} reads the opposite because that is where the order RESTS"
    )
