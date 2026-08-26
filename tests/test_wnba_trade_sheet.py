"""The WNBA trade sheet's parsing and P&L arithmetic, pinned.

Two things here are worth breaking a build over.

**Which execution is ours.** The feed sends both counterparties of every trade.
Picking the wrong one, or both, books a phantom offsetting fill against every
real trade. ``test_only_our_side_of_a_two_sided_trade_is_parsed`` drives a raw
activity shaped like the live one, so the parse itself is under test — not a
hand-built ``WnbaFill`` that skips the part that can go wrong.

**Where the money lands.** P&L is booked on entry rows, matched FIFO, so the
money columns can be summed. ``test_money_columns_do_not_double_count`` is the
property that makes the sheet safe to total.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import json
import pytest

from core.audit.wnba_trade_sheet import (
    Resolution,
    WnbaFill,
    build_rows,
    game_label,
    line_from_slug,
    market_label,
    our_execution,
    parse_activity,
)
from core.team_mapping import parse_market_slug

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 6, 22, 0, tzinfo=UTC)
ZERO = Decimal("0")

TOTAL = "tsc-wnba-la-min-2026-08-06-197pt5"
SPREAD = "asc-wnba-la-wsh-2026-08-15-pos-13pt5"

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


MONEY = "aec-wnba-por-phx-2026-08-16"


def _fill(minutes, *, buy, yes, px, shares, slug=TOTAL, oid="H1", commission="0"):
    return WnbaFill(
        market_slug=slug,
        parsed=parse_market_slug(slug),
        at=T0 + dt.timedelta(minutes=minutes),
        venue_order_id=oid,
        is_buy=buy,
        outcome_yes=yes,
        yes_price=Decimal(str(px)),
        shares=Decimal(str(shares)),
        commission=Decimal(commission),
    )


def _no_settlement(_slug):
    raise AssertionError("settlement must not be consulted for trade-closed lots")


def _settles(payout):
    return lambda _slug: Decimal(payout)


def _resolution(hours=4, slug=TOTAL):
    return Resolution(slug, T0 + dt.timedelta(hours=hours))


# ------------------------------------------------------------------ #
# Which execution is ours
# ------------------------------------------------------------------ #


def _two_sided_activity(*, is_aggressor: bool) -> dict:
    """A trade shaped like the live feed: BOTH sides present, same price,
    opposite order sides. Observed on 455 of 455 trades, 2026-08-17."""

    def _execution(order_id, side, commission):
        return {
            "lastPx": {"value": "0.4800", "currency": "USD"},
            "lastShares": 12,
            "transactTime": "2026-08-17T01:08:58.676592684Z",
            "commissionNotionalCollected": {"value": commission, "currency": "USD"},
            "order": {
                "id": order_id,
                "side": side,
                "outcomeSide": "OUTCOME_SIDE_YES",
                "intent": _intent_for(side, "OUTCOME_SIDE_YES"),
                "marketSlug": MONEY,
                "manualOrderIndicator": "MANUAL_ORDER_INDICATOR_MANUAL",
            },
        }

    return {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": MONEY,
            "isAggressor": is_aggressor,
            "aggressorExecution": _execution("AGGRESSOR", "ORDER_SIDE_BUY", "0.18"),
            "passiveExecution": _execution("PASSIVE", "ORDER_SIDE_SELL", "-0.04"),
        },
    }


@pytest.mark.parametrize(
    "is_aggressor,order_id,is_buy,commission",
    [(True, "AGGRESSOR", True, "0.18"), (False, "PASSIVE", False, "-0.04")],
)
def test_only_our_side_of_a_two_sided_trade_is_parsed(
    is_aggressor, order_id, is_buy, commission
):
    """``isAggressor`` picks our execution. Taking both would net our own trade
    against the counterparty's mirror image and score it as flat."""
    fill, resolution, ok = parse_activity(_two_sided_activity(is_aggressor=is_aggressor))
    assert ok and resolution is None
    assert fill.venue_order_id == order_id
    assert fill.is_buy is is_buy
    assert fill.commission == Decimal(commission)   # differs by side: fee vs rebate
    assert fill.shares == Decimal("12")


def test_our_execution_selects_by_is_aggressor():
    trade = _two_sided_activity(is_aggressor=True)["trade"]
    assert our_execution(trade)["order"]["id"] == "AGGRESSOR"
    trade["isAggressor"] = False
    assert our_execution(trade)["order"]["id"] == "PASSIVE"


def test_non_wnba_market_is_skipped_not_failed():
    """Another league is benign, not schema drift: ok stays True."""
    nba = "aec-nba-bos-lal-2026-05-09"
    activity = _two_sided_activity(is_aggressor=True)
    activity["trade"]["marketSlug"] = nba
    activity["trade"]["aggressorExecution"]["order"]["marketSlug"] = nba
    assert parse_activity(activity) == (None, None, True)


def test_missing_our_side_is_reported_as_unparsed():
    activity = _two_sided_activity(is_aggressor=True)
    activity["trade"]["aggressorExecution"] = None
    assert parse_activity(activity) == (None, None, False)


def test_wnba_resolution_is_parsed_and_other_leagues_ignored():
    raw = {
        "type": "ACTIVITY_TYPE_POSITION_RESOLUTION",
        "positionResolution": {
            "marketSlug": TOTAL,
            "updateTime": "2026-08-07T00:04:34.770665196Z",
        },
    }
    _, resolution, ok = parse_activity(raw)
    assert ok and resolution.market_slug == TOTAL
    raw["positionResolution"]["marketSlug"] = "aec-nba-bos-lal-2026-05-09"
    assert parse_activity(raw) == (None, None, True)


def test_unrelated_activity_types_are_benign():
    """Transfers and fee rebates are not fills and must not read as drift."""
    for kind in ("ACTIVITY_TYPE_TRANSFER", "ACTIVITY_TYPE_TAKER_FEE_REBATE"):
        assert parse_activity({"type": kind}) == (None, None, True)


# ------------------------------------------------------------------ #
# Labels — pinned to the venue's own wording
# ------------------------------------------------------------------ #


def test_line_from_slug_reads_the_sign_from_the_slug():
    assert line_from_slug(TOTAL) == Decimal("197.5")
    assert line_from_slug(SPREAD) == Decimal("13.5")
    assert line_from_slug("asc-wnba-chi-sea-2026-08-16-neg-10pt5") == Decimal("-10.5")
    assert line_from_slug(MONEY) is None


@pytest.mark.parametrize(
    "slug,yes,expected",
    [
        (TOTAL, True, "OVER 197.5"),
        (TOTAL, False, "UNDER 197.5"),
        # YES is the first slug team at the slug's signed line; NO is the other
        # team at the negated line. Reproduces marketMetadata.outcome, 94/94.
        (SPREAD, True, "LA +13.5"),
        (SPREAD, False, "WSH -13.5"),
        ("asc-wnba-chi-sea-2026-08-16-neg-10pt5", True, "CHI -10.5"),
        ("asc-wnba-chi-sea-2026-08-16-neg-10pt5", False, "SEA +10.5"),
        (MONEY, True, "POR to win"),
        (MONEY, False, "PHX to win"),
    ],
)
def test_market_label_names_the_side_actually_taken(slug, yes, expected):
    assert market_label(parse_market_slug(slug), slug, yes) == expected


def test_game_label_does_not_claim_home_or_away():
    """Slug team order is positional only, so the label uses a neutral
    separator rather than "@" or "vs"."""
    label = game_label(parse_market_slug(TOTAL))
    assert label == "LA / MIN 2026-08-06"
    assert "@" not in label and " vs " not in label


# ------------------------------------------------------------------ #
# P&L — booked on the entry row, matched FIFO
# ------------------------------------------------------------------ #


def test_yes_round_trip_books_pnl_on_the_entry():
    """Buy 10 YES at 0.30, sell at 0.50: $3 in, $5 out, +$2 on the entry."""
    entry = _fill(0, buy=True, yes=True, px=0.30, shares=10)
    exit_ = _fill(30, buy=False, yes=True, px=0.50, shares=10)
    rows, unscored = build_rows([entry, exit_], [], _no_settlement)
    assert unscored == []
    first, second = rows
    assert (first.dollars_in, first.dollars_out, first.pnl) == (
        Decimal("3.0"), Decimal("5.0"), Decimal("2.0"))
    assert first.role == "ENTRY" and first.closed_by == "trades"
    assert first.entry_cost == Decimal("0.30")
    # The exit carries no money of its own — it is booked on the entry.
    assert second.role == "EXIT" and second.closed_by == ""
    assert second.dollars_in == ZERO and second.dollars_out == ZERO
    assert second.pnl is None


def test_no_contract_costs_one_minus_price():
    """Buying NO at YES-frame 0.80 stakes 0.20/contract; YES settling 0 pays
    the NO holder 1.00."""
    rows, _ = build_rows([_fill(0, buy=True, yes=False, px=0.80, shares=5)],
                         [_resolution()], _settles("0"))
    (row,) = rows
    assert row.dollars_in == Decimal("1.0")      # 5 x (1 - 0.80)
    assert row.dollars_out == Decimal("5.0")     # 5 x 1.00
    assert row.pnl == Decimal("4.0")
    assert row.closed_by == "settlement"
    assert row.entry_cost == Decimal("0.20")


def test_losing_settlement_returns_nothing():
    rows, _ = build_rows([_fill(0, buy=True, yes=True, px=0.25, shares=8)],
                         [_resolution()], _settles("0"))
    (row,) = rows
    assert row.dollars_in == Decimal("2.0") and row.dollars_out == ZERO
    assert row.pnl == Decimal("-2.0")


def test_zero_crossing_splits_the_fill_into_exit_and_entry():
    """Buy 10 YES then sell 15: the sell closes 10 and opens a 5-short."""
    entry = _fill(0, buy=True, yes=True, px=0.40, shares=10)
    flip = _fill(10, buy=False, yes=True, px=0.60, shares=15)
    rows, _ = build_rows([entry, flip], [_resolution()], _settles("1"))
    first, second = rows
    assert first.role == "ENTRY"
    assert first.dollars_in == Decimal("4.0") and first.dollars_out == Decimal("6.0")
    # The flip both closed the long and opened a short: 5 x (1 - 0.60) = $2.
    assert second.role == "EXIT+ENTRY"
    assert second.dollars_in == Decimal("2.0")
    assert second.dollars_out == ZERO            # YES settled 1; the short lost
    assert second.pnl == Decimal("-2.0")
    assert second.closed_by == "settlement"


def test_partial_exit_then_settlement_is_mixed():
    entry = _fill(0, buy=True, yes=True, px=0.20, shares=10)
    part = _fill(20, buy=False, yes=True, px=0.35, shares=4)
    rows, _ = build_rows([entry, part], [_resolution()], _settles("1"))
    row = rows[0]
    assert row.dollars_in == Decimal("2.0")
    assert row.dollars_out == Decimal("1.4") + Decimal("6.0")   # 4@0.35 + 6@1.00
    assert row.closed_by == "mixed"
    assert row.pnl == Decimal("5.4")


def test_fifo_matches_the_oldest_lot_first():
    """Two entries at different prices; one exit covering only the first."""
    old = _fill(0, buy=True, yes=True, px=0.20, shares=5)
    new = _fill(5, buy=True, yes=True, px=0.60, shares=5)
    exit_ = _fill(10, buy=False, yes=True, px=0.50, shares=5)
    rows, _ = build_rows([old, new, exit_], [], _no_settlement)
    assert rows[0].closed_by == "trades"
    assert rows[0].pnl == Decimal("1.5")            # 2.50 out - 1.00 in
    assert rows[1].closed_by == "open" and rows[1].pnl is None


def test_open_lot_has_no_pnl():
    """Cost with no return yet is an unfinished position, not a loss."""
    rows, _ = build_rows([_fill(0, buy=True, yes=True, px=0.30, shares=10)], [],
                         _no_settlement)
    (row,) = rows
    assert row.dollars_in == Decimal("3.0")
    assert row.closed_by == "open" and row.pnl is None


def test_partially_closed_lot_is_flagged_and_unscored():
    entry = _fill(0, buy=True, yes=True, px=0.20, shares=10)
    part = _fill(20, buy=False, yes=True, px=0.35, shares=4)
    rows, _ = build_rows([entry, part], [], _no_settlement)
    assert rows[0].closed_by == "partial" and rows[0].pnl is None


def test_unknown_settlement_leaves_the_lot_open_and_names_the_market():
    """Never guess a payout — report the market as unscored instead."""
    rows, unscored = build_rows([_fill(0, buy=True, yes=True, px=0.30, shares=10)],
                                [_resolution()], lambda _s: None)
    (row,) = rows
    assert unscored == [TOTAL]
    assert row.closed_by == "open" and row.pnl is None


def test_positions_in_different_markets_do_not_net():
    a = _fill(0, buy=True, yes=True, px=0.30, shares=10, slug=TOTAL)
    b = _fill(1, buy=False, yes=True, px=0.30, shares=10, slug=MONEY)
    rows, _ = build_rows([a, b], [], _no_settlement)
    assert all(r.role == "ENTRY" for r in rows)
    assert all(r.closed_by == "open" for r in rows)


def test_settlement_of_one_market_does_not_touch_another():
    a = _fill(0, buy=True, yes=True, px=0.30, shares=10, slug=TOTAL)
    b = _fill(1, buy=True, yes=True, px=0.30, shares=10, slug=MONEY)
    rows, _ = build_rows([a, b], [_resolution(slug=TOTAL)], _settles("1"))
    by_slug = {r.fill.market_slug: r for r in rows}
    assert by_slug[TOTAL].closed_by == "settlement"
    assert by_slug[MONEY].closed_by == "open"


def test_money_columns_do_not_double_count():
    """The property that makes the sheet safe to total: every dollar staked is
    on exactly one row, and so is every dollar returned."""
    fills = [
        _fill(0, buy=True, yes=True, px=0.40, shares=10),
        _fill(10, buy=False, yes=True, px=0.60, shares=15),   # flips to short 5
        _fill(20, buy=True, yes=True, px=0.50, shares=5),     # closes the short
    ]
    rows, _ = build_rows(fills, [], _no_settlement)
    # Long:  10 @ 0.40       = 4.00 staked, closed 10 @ 0.60       = 6.00 back.
    # Short:  5 @ (1 - 0.60) = 2.00 staked, closed  5 @ (1 - 0.50) = 2.50 back.
    assert sum(r.dollars_in for r in rows) == Decimal("6.0")
    assert sum(r.dollars_out for r in rows) == Decimal("8.5")
    assert sum(r.pnl for r in rows if r.pnl is not None) == Decimal("2.5")
    for row in rows:
        if row.pnl is not None:
            assert row.pnl == row.dollars_out - row.dollars_in


# ------------------------------------------------------------------ #
# Contract traded vs exposure taken — the sheet's easiest misreading
# ------------------------------------------------------------------ #


def test_selling_the_under_contract_is_being_long_the_over():
    """The trap this column exists to close: on 2026-07-29 the operator SOLD
    the Under on ATL/DAL 181.5, the total came in under the line, and the row
    shows a loss. Labelled only by the contract, that reads as a bet that won
    and lost money. The exposure label says what was actually on."""
    fill = _fill(0, buy=False, yes=False, px=0.49, shares=10)
    assert fill.market == "UNDER 197.5"      # the contract, as the venue names it
    assert fill.exposure == "OVER 197.5"     # what the position actually was
    assert fill.yes_delta == Decimal("10")   # long YES == long the Over


def test_buying_a_contract_leaves_market_and_exposure_the_same():
    fill = _fill(0, buy=True, yes=True, px=0.30, shares=10)
    assert fill.market == fill.exposure == "OVER 197.5"


def test_selling_a_team_contract_is_backing_the_other_team():
    fill = _fill(0, buy=False, yes=True, px=0.60, shares=5, slug=MONEY)
    assert fill.market == "POR to win"
    assert fill.exposure == "PHX to win"


def test_position_is_blank_for_a_pure_exit():
    """A fill that only closes an earlier lot puts on nothing, so it reports no
    position — the same rule the money columns follow."""
    entry = _fill(0, buy=True, yes=True, px=0.30, shares=10)
    exit_ = _fill(30, buy=False, yes=True, px=0.50, shares=10)
    rows, _ = build_rows([entry, exit_], [], _no_settlement)
    assert rows[0].position == "OVER 197.5"
    assert rows[1].role == "EXIT" and rows[1].position == ""


def test_flip_reports_the_position_it_opened_not_the_one_it_closed():
    entry = _fill(0, buy=True, yes=True, px=0.40, shares=10)
    flip = _fill(10, buy=False, yes=True, px=0.60, shares=15)
    rows, _ = build_rows([entry, flip], [], _no_settlement)
    assert rows[0].position == "OVER 197.5"
    assert rows[1].role == "EXIT+ENTRY" and rows[1].position == "UNDER 197.5"


# --------------------------------------------------------------------- #
# The money columns must name their convention.
#
# V27: the venue's own ``realizedPnl`` is per-position, average-cost, ex-fees.
# This sheet's money is FIFO per round trip. Two policies over the same fills
# disagree row by row and agree in total, so an unqualified "P&L" beside a
# venue field of the same name invites the operator to read a mismatch as an
# error. The label is the only thing standing between those two readings, and
# it was previously untested — the suite stayed green through a rename.
# --------------------------------------------------------------------- #


def test_pnl_column_names_its_convention() -> None:
    from scripts.export_wnba_trades import COLUMNS

    headers = [h for h, _ in COLUMNS]
    pnl = [h for h in headers if "P&L" in h]
    assert pnl, f"no P&L column found in {headers}"
    for h in pnl:
        assert "FIFO" in h, (
            f"money column {h!r} does not name its policy. The venue's "
            "realizedPnl is average-cost per position (V27); an unqualified "
            "label lets a by-construction row mismatch read as a bug."
        )


def test_printed_caveat_contrasts_both_policies() -> None:
    """The caveat prints beside the total, where an unqualified number gets read."""
    import inspect

    from scripts import export_wnba_trades

    src = inspect.getsource(export_wnba_trades)
    assert "FIFO" in src and "average-cost" in src, (
        "the printed caveat must name both policies, not just warn vaguely"
    )
    assert "NOT CONFIRMED AGAINST THE VENUE" not in src, (
        "stale caveat: V27 settled the scope question on 2026-08-25 — the "
        "disagreement is by construction, not an open discrepancy"
    )


# --------------------------------------------------------------------- #
# Sign, booked from `intent` and not from book mechanics.
#
# The defect this pins: `side`/`outcomeSide` describe how an order RESTS on the
# book, and a NO buy rests as a YES-side sell. Booking from them inverted every
# SHORT row — 207 of 496 of our own legs in the 2026-08-25 export (148
# BUY_SHORT, 59 SELL_SHORT), which graded out as 25 of 58 WNBA markets carrying
# an exact sign flip.
#
# It survived review because the flips PARTIALLY CANCEL: the sheet total came
# to +$7.15 against a pinned +$14.61 gross, so the aggregate looked plausible
# while the rows lied. A total is not a check on a sign — only a per-row or
# per-market assertion is, which is what these are.
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "intent, side, outcome, expect_positive, what",
    [
        ("ORDER_INTENT_BUY_LONG", "ORDER_SIDE_BUY", "OUTCOME_SIDE_YES", True, "buy YES"),
        ("ORDER_INTENT_SELL_LONG", "ORDER_SIDE_SELL", "OUTCOME_SIDE_YES", False, "sell YES"),
        # The two that inverted. Note `side` reads the OPPOSITE of the economics.
        ("ORDER_INTENT_BUY_SHORT", "ORDER_SIDE_SELL", "OUTCOME_SIDE_NO", False, "buy NO"),
        ("ORDER_INTENT_SELL_SHORT", "ORDER_SIDE_BUY", "OUTCOME_SIDE_NO", True, "sell NO"),
    ],
)
def test_yes_exposure_follows_intent_not_book_mechanics(
    intent, side, outcome, expect_positive, what
):
    raw = {
        "type": "ACTIVITY_TYPE_TRADE",
        "trade": {
            "marketSlug": MONEY,
            "isAggressor": True,
            "aggressorExecution": {
                "lastPx": {"value": "0.4800"},
                "lastShares": 12,
                "transactTime": "2026-08-17T01:08:58.676592684Z",
                "commissionNotionalCollected": {"value": "0.18"},
                "order": {"id": "OURS", "side": side, "outcomeSide": outcome,
                          "intent": intent, "marketSlug": MONEY},
            },
            "passiveExecution": {
                "lastPx": {"value": "0.4800"},
                "lastShares": 12,
                "transactTime": "2026-08-17T01:08:58.676592684Z",
                "commissionNotionalCollected": {"value": "-0.04"},
                "order": {"id": "THEIRS", "side": "ORDER_SIDE_BUY",
                          "outcomeSide": "OUTCOME_SIDE_UNSPECIFIED",
                          "intent": "ORDER_INTENT_UNDEFINED", "marketSlug": MONEY},
            },
        },
    }
    fill, _, ok = parse_activity(raw)
    assert ok and fill is not None, f"{what} was not parsed"
    assert (fill.yes_delta > 0) is expect_positive, (
        f"{what} ({intent}) booked {fill.yes_delta:+} YES exposure. "
        f"side={side} says the opposite — that is book mechanics, not economics."
    )


def test_short_intents_disagree_with_the_mechanical_reading():
    """Guard the guard: if these ever agreed, the test above could not fail."""
    for intent, side, outcome in [
        ("ORDER_INTENT_BUY_SHORT", "ORDER_SIDE_SELL", "OUTCOME_SIDE_NO"),
        ("ORDER_INTENT_SELL_SHORT", "ORDER_SIDE_BUY", "OUTCOME_SIDE_NO"),
    ]:
        mechanical = ("BUY" in side) == outcome.endswith("_YES")
        economic = ("_BUY_" in intent) == intent.endswith("_LONG")
        assert mechanical is not economic, (
            f"{intent}: the two readings agree, so a sign bug here is untestable"
        )


# --------------------------------------------------------------------- #
# Building from a PINNED export.
#
# The live path guarantees completeness by walking the feed to `eof`. Reading a
# file bypasses that walk, so the same defect — a sheet silently missing the
# OLDEST trades — can arrive through a door that never had the guard. These pin
# the guard on the new door.
# --------------------------------------------------------------------- #


def _envelope(pages):
    return {"pages": pages, "page_count": len(pages), "fetched_at": "20260825T233057Z"}


def _page(n, *, eof, cursor=None):
    acts = [{"type": "ACTIVITY_TYPE_TRADE", "trade": {"marketSlug": f"m{i}"}}
            for i in range(n)]
    p = {"activities": acts, "eof": eof}
    if cursor:
        p["nextCursor"] = cursor
    return p


def test_pinned_export_is_read_and_names_its_snapshot(tmp_path):
    from scripts.export_wnba_trades import activities_from_export

    f = tmp_path / "venue_activities_20260825T233057Z.json"
    f.write_text(json.dumps(_envelope([_page(2, eof=False, cursor="c1"),
                                       _page(3, eof=True)])))
    acts, provenance = activities_from_export(f)
    assert len(acts) == 5
    # The sheet must be able to say WHICH snapshot it came from, or it is not
    # re-gradable against the ledger it was checked against.
    assert "20260825T233057Z" in provenance and "5 activities" in provenance


def test_a_truncated_export_is_refused_not_silently_short(tmp_path):
    """The failure this guard exists for: a snapshot that never reached eof
    yields a sheet missing the oldest trades, which looks complete."""
    from scripts.export_wnba_trades import activities_from_export

    f = tmp_path / "truncated.json"
    f.write_text(json.dumps(_envelope([_page(2, eof=False, cursor="still-more")])))
    with pytest.raises(RuntimeError, match="never reached eof"):
        activities_from_export(f)


def test_a_flat_dump_does_not_claim_verified_completeness(tmp_path):
    """A bare list carries no eof marker, so completeness cannot be checked —
    the provenance string must say so rather than implying it was."""
    from scripts.export_wnba_trades import activities_from_export

    f = tmp_path / "flat.json"
    f.write_text(json.dumps([{"type": "ACTIVITY_TYPE_TRADE"}]))
    acts, provenance = activities_from_export(f)
    assert len(acts) == 1
    assert "not verifiable" in provenance


# --------------------------------------------------------------------- #
# `placed by` must not claim "hand" past the orders table's horizon.
#
# The defect: the label was "system if known, else hand if we know ANY ids,
# else unknown" — which treats a NON-EMPTY set as a COMPLETE one. Against a
# merely stale database, every system order placed after its last row reads
# "hand" on the operator's own annotation sheet. Measured 2026-08-26: the
# configured DB held 5 ids, newest 2026-08-07, nineteen days back. An EMPTY
# table would have produced an honest sheet; five rows defeated the fallback.
# --------------------------------------------------------------------- #


_H = dt.datetime(2026, 8, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    "at, oid, ours, horizon, expect, why",
    [
        (_H, "A", {"A"}, _H, "system", "a known id is ours whenever it appears"),
        (_H - dt.timedelta(days=1), "Z", {"A"}, _H, "hand",
         "inside the horizon an unknown id really is not ours"),
        (_H + dt.timedelta(seconds=1), "Z", {"A"}, _H, "unknown",
         "ONE SECOND past the horizon the table cannot speak — do not claim hand"),
        (_H, "Z", set(), None, "unknown", "no ids at all: the old honest fallback"),
        (_H, "Z", {"A"}, None, "unknown", "ids but no horizon: cannot bound them"),
    ],
)
def test_placed_by_refuses_to_claim_past_its_horizon(
    at, oid, ours, horizon, expect, why
):
    from scripts.export_wnba_trades import placed_by

    assert placed_by(at, oid, ours, horizon) == expect, why


def test_a_stale_but_populated_table_is_worse_than_an_empty_one():
    """The inversion worth pinning: partial data defeats the honest fallback.

    With five ids from nineteen days ago, a fill from tonight must read
    "unknown" — the same answer an empty table gives — and must NOT read "hand".
    """
    from scripts.export_wnba_trades import placed_by

    tonight = dt.datetime(2026, 8, 26, 1, 58, tzinfo=UTC)
    stale = {"OLD1", "OLD2", "OLD3", "OLD4", "OLD5"}
    assert placed_by(tonight, "NEW", stale, _H) == "unknown"
    assert placed_by(tonight, "NEW", set(), None) == "unknown"
