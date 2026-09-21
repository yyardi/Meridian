"""Hypothesis #17's trigger, frames and exits, pinned.

The gate constants are NOT tested for value here on purpose — they are the
2026-08-08 pre-registration, and a test asserting them equal to themselves
would only make a future edit look reviewed. What is tested is that the
implementation obeys them, and that the two price frames do not get crossed.

**The frame is the thing most likely to be wrong and least likely to look
wrong.** Buying the NO side at its touch IS resting a sell of YES at the ask,
its cost is 1 - price, and its exit target is the mirror of the YES one. Every
one of those is a place where a sign error produces a plausible number with the
wrong meaning — which is how #16 passed a gate it should have failed.
"""

from __future__ import annotations

import datetime as dt

import pytest

from core.pulse.replay import ReplayContext, Tick, replay_game
from core.pulse.tight_game_reversion import (
    EXIT_MID,
    MARKET_MONEYLINE,
    TightGameReversion,
    Trade,
    _flat_target,
    _settle_open,
    charged_coefficients,
    minutes_left_in_q4,
)

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 8, 8, 2, 0, tzinfo=UTC)
GAME = "wnba-gsv-dal-2026-08-08"
ML = "aec-wnba-gsv-dal-2026-08-08"
#: The venue's taker coefficient on a fixture tick. PRE is what the venue
#: charged before it raised the fee on 2026-09-17 04:07Z, and it is the
#: default here because every Q4 archive this hypothesis replays is from
#: August; NOW is the current value. PRE is spelled, not imported: it is
#: history, and core/fees.py holds only the current value.
PRE, NOW = 0.06, 0.0695


def _tick(seconds, *, bid, ask, score="80-78", period="Q4", live=True,
          slug=ML, mtype=MARKET_MONEYLINE, coef=PRE):
    return Tick(
        captured_at=T0 + dt.timedelta(seconds=seconds),
        event_slug=GAME, market_slug=slug, sports_market_type=mtype,
        line=None, bid=bid, ask=ask, is_live=live, score=score, period=period,
        fee_coefficient=coef,
    )


def _run(ticks, target=_flat_target):
    strategy = TightGameReversion(target)
    replay_game(ticks, strategy, event_slug=GAME)
    return strategy


# ------------------------------------------------------------------ #
# The registered trigger
# ------------------------------------------------------------------ #


def test_trigger_fires_on_a_cheap_yes_in_a_tight_q4():
    assert TightGameReversion.triggers(_tick(0, bid=0.30, ask=0.34)) == "yes"


def test_trigger_fires_on_a_cheap_no_at_the_mirror_price():
    """A 0.68 YES mid means the NO side is quoted 0.32 — cheap, and it is the
    side the registration says to buy."""
    assert TightGameReversion.triggers(_tick(0, bid=0.66, ask=0.70)) == "no"


def test_no_trigger_when_the_price_is_not_extreme():
    assert TightGameReversion.triggers(_tick(0, bid=0.48, ask=0.52)) is None


def test_no_trigger_outside_q4():
    for period in ("Q1", "Q2", "Q3", "HT", "OT", None):
        assert TightGameReversion.triggers(
            _tick(0, bid=0.30, ask=0.34, period=period)) is None


def test_no_trigger_when_the_game_is_not_tight():
    """Margin 4 is outside the registered <= 3."""
    assert TightGameReversion.triggers(_tick(0, bid=0.30, ask=0.34, score="80-76")) is None
    assert TightGameReversion.triggers(_tick(0, bid=0.30, ask=0.34, score="80-77")) == "yes"


def test_no_trigger_on_other_market_types_or_pregame():
    assert TightGameReversion.triggers(
        _tick(0, bid=0.30, ask=0.34, mtype="basketball_team_full_game_total")) is None
    assert TightGameReversion.triggers(_tick(0, bid=0.30, ask=0.34, live=False)) is None


def test_no_trigger_on_an_unparseable_score():
    assert TightGameReversion.triggers(_tick(0, bid=0.30, ask=0.34, score="")) is None


# ------------------------------------------------------------------ #
# Maker entry — earned, never assumed
# ------------------------------------------------------------------ #


def test_entry_rests_at_the_touch_and_cannot_fill_on_its_own_tick():
    """The order is placed at the bid. If it filled on the tick that created
    it, a maker order would silently have become a taker."""
    s = _run([_tick(0, bid=0.30, ask=0.34)])
    (order,) = s.orders.values()
    assert order.side == "buy" and order.limit_price == 0.30
    assert order.filled_at is None
    assert s.trades == [] and s.positions == {}


def test_a_later_tick_trading_through_fills_the_maker_order():
    s = _run([
        _tick(0, bid=0.30, ask=0.34),
        _tick(1, bid=0.28, ask=0.30),        # ask reaches our 0.30 bid
    ])
    (position,) = s.positions.values()
    assert position.side == "yes" and position.entry_cost == 0.30


def test_a_no_side_entry_rests_a_sell_and_costs_one_minus_price():
    """Buying NO at its touch is resting a SELL of YES at the ask. The cost of
    that NO contract is 1 - 0.70 = 0.30, not 0.70."""
    s = _run([
        _tick(0, bid=0.66, ask=0.70),
        _tick(1, bid=0.70, ask=0.74),        # bid rises to our 0.70 sell
    ])
    (position,) = s.positions.values()
    assert position.side == "no"
    assert position.entry_cost == pytest.approx(0.30)


def test_an_unfilled_order_is_cancelled_after_the_registered_patience():
    """The order must be CANCELLED, not left resting forever — an order that
    never expires would eventually fill on a price it was not offered at."""
    strategy = TightGameReversion(_flat_target)
    ctx = ReplayContext()
    ticks = [
        _tick(0, bid=0.30, ask=0.34),
        _tick(60, bid=0.30, ask=0.34),        # 1 min — still working
        _tick(120, bid=0.30, ask=0.34),       # 2 min — the window closes
    ]
    for tick in ticks:
        ctx._now = tick.captured_at
        strategy.on_tick(tick, ctx)

    placed = [o for o in ctx.orders if o.note == "yes"]
    assert len(placed) >= 1
    first = placed[0]
    assert first.cancelled_at == ticks[2].captured_at
    assert first.filled_at is None
    assert strategy.trades == [] and strategy.positions == {}


def test_only_one_position_at_a_time_per_market():
    """The trigger stays true for thousands of consecutive ticks; that must not
    become thousands of positions."""
    ticks = [_tick(0, bid=0.30, ask=0.34), _tick(1, bid=0.28, ask=0.30)]
    ticks += [_tick(2 + i, bid=0.29, ask=0.33) for i in range(50)]
    s = _run(ticks)
    assert len(s.positions) + len(s.trades) == 1


# ------------------------------------------------------------------ #
# Exit — the target, crossing the spread
# ------------------------------------------------------------------ #


def test_yes_position_exits_at_the_bid_when_the_mid_reaches_the_target():
    s = _run([
        _tick(0, bid=0.30, ask=0.34),
        _tick(1, bid=0.28, ask=0.30),        # filled at 0.30
        _tick(2, bid=0.49, ask=0.53),        # mid 0.51 >= 0.50
    ])
    (trade,) = s.trades
    assert trade.exit_reason == "target"
    assert trade.exit_proceeds == 0.49       # crossed to the bid, not the mid
    assert trade.exit_fee > 0                # the cross pays the taker fee
    assert trade.net_pnl == pytest.approx(0.49 - 0.30 - trade.exit_fee)


def test_no_position_exits_at_one_minus_ask_on_the_mirror_target():
    """A NO position's target is reached when the YES mid falls to 0.50, and it
    exits by buying YES back at the ask."""
    s = _run([
        _tick(0, bid=0.66, ask=0.70),
        _tick(1, bid=0.70, ask=0.74),        # NO filled, cost 0.30
        _tick(2, bid=0.46, ask=0.50),        # YES mid 0.48 <= 0.50
    ])
    (trade,) = s.trades
    assert trade.exit_reason == "target"
    assert trade.exit_proceeds == pytest.approx(0.50)     # 1 - ask
    assert trade.net_pnl == pytest.approx(0.50 - 0.30 - trade.exit_fee)


def test_a_position_that_never_reaches_target_stays_open_for_settlement():
    s = _run([
        _tick(0, bid=0.30, ask=0.34),
        _tick(1, bid=0.28, ask=0.30),
        _tick(2, bid=0.20, ask=0.24),        # moved against us
    ])
    assert s.trades == [] and len(s.positions) == 1


# ------------------------------------------------------------------ #
# Settlement — the venue's 0/1, never inferred
# ------------------------------------------------------------------ #


def _open_position(side, cost):
    strategy = TightGameReversion(_flat_target)
    strategy.positions[ML] = Trade(
        event_slug=GAME, market_slug=ML, side=side,
        entered_at=T0, entry_cost=cost,
    )
    return strategy


def test_yes_position_settles_to_one_when_the_market_settles_yes():
    s = _open_position("yes", 0.30)
    assert _settle_open(s, {ML: 1}) == 0
    (trade,) = s.trades
    assert trade.exit_proceeds == 1.0 and trade.exit_reason == "settlement"
    assert trade.exit_fee == 0.0             # settlement is not a trade
    assert trade.net_pnl == pytest.approx(0.70)


def test_no_position_settles_to_one_when_the_market_settles_NO():
    """The frame that would silently invert: a NO holder wins on settlement 0."""
    s = _open_position("no", 0.30)
    _settle_open(s, {ML: 0})
    (trade,) = s.trades
    assert trade.exit_proceeds == 1.0 and trade.net_pnl == pytest.approx(0.70)


def test_losing_settlement_returns_nothing():
    s = _open_position("yes", 0.30)
    _settle_open(s, {ML: 0})
    (trade,) = s.trades
    assert trade.exit_proceeds == 0.0 and trade.net_pnl == pytest.approx(-0.30)


def test_an_unknown_settlement_is_reported_not_guessed():
    s = _open_position("yes", 0.30)
    assert _settle_open(s, {}) == 1
    assert s.trades == [] and len(s.positions) == 1


# ------------------------------------------------------------------ #
# The minutes-left approximation, and the co-primary's guard
# ------------------------------------------------------------------ #


def test_minutes_left_interpolates_across_the_q4_span_and_is_capped():
    start, end = T0, T0 + dt.timedelta(minutes=20)
    assert minutes_left_in_q4(start, start, end) == 10.0
    assert minutes_left_in_q4(end, start, end) == 0.0
    assert minutes_left_in_q4(start + dt.timedelta(minutes=10), start, end) == 5.0
    # Outside the span it clamps rather than going negative.
    assert minutes_left_in_q4(end + dt.timedelta(minutes=5), start, end) == 0.0


def test_a_target_of_none_suppresses_the_exit_rather_than_defaulting():
    """If the anchored target cannot be computed, the co-primary must NOT fall
    back to 0.50 — that would make it a second copy of the primary arm and
    condition (5) would be vacuous."""
    s = _run([
        _tick(0, bid=0.30, ask=0.34),
        _tick(1, bid=0.28, ask=0.30),
        _tick(2, bid=0.60, ask=0.64),        # would exit under the flat target
    ], target=lambda _t: None)
    assert s.trades == []                    # no exit taken
    assert len(s.positions) == 1


def test_the_flat_target_is_the_registered_exit_mid():
    assert _flat_target(_tick(0, bid=0.3, ask=0.34)) == EXIT_MID


def test_a_one_sided_book_does_not_crash_the_exit_check():
    """A thin Q4 quotes one side only, so `tick.mid` is None. Comparing that to
    the target raised TypeError and killed the whole 50-game run partway
    through — the position must simply wait instead."""
    s = _run([
        _tick(0, bid=0.30, ask=0.34),
        _tick(1, bid=0.28, ask=0.30),        # filled
        _tick(2, bid=None, ask=0.55),        # ask only — no mid
        _tick(3, bid=0.52, ask=None),        # bid only — no mid
        _tick(4, bid=0.49, ask=0.53),        # two-sided again: exit
    ])
    (trade,) = s.trades
    assert trade.exit_reason == "target" and trade.exit_proceeds == 0.49


def test_a_one_sided_book_does_not_trigger_an_entry():
    for bid, ask in ((None, 0.34), (0.30, None), (None, None)):
        assert TightGameReversion.triggers(_tick(0, bid=bid, ask=ask)) is None


# ------------------------------------------------------------------ #
# The exit fee is the EXIT TICK's own coefficient
# ------------------------------------------------------------------ #
# The venue raised its taker coefficient on 2026-09-17 04:07Z; every Q4
# archive this replays was recorded before that. An exit charged at today's
# constant would overstate every trade's cost by 16 %. The fee is read off
# the tick the exit crosses on, never off a constant.


def _yes_round_trip(slug, coef):
    """Entry at 0.30 fills on the second tick; the third reaches the target
    and carries `coef`, the coefficient the exit is charged at."""
    return [
        _tick(0, bid=0.30, ask=0.34, slug=slug),
        _tick(1, bid=0.28, ask=0.30, slug=slug),              # filled at 0.30
        _tick(2, bid=0.49, ask=0.53, slug=slug, coef=coef),   # exit at the bid
    ]


def test_a_pre_change_exit_and_a_post_change_exit_in_one_replay_are_charged_differently():
    """Two markets in one game, identical books, one exit tick from before
    the raise and one from after: each pays theta * p * (1-p) at ITS tick's
    coefficient, and the difference is exactly the raise."""
    s = _run(_yes_round_trip("aec-pre", PRE) + _yes_round_trip("aec-now", NOW))
    by = {t.market_slug: t for t in s.trades}
    assert set(by) == {"aec-pre", "aec-now"}
    pre, now = by["aec-pre"], by["aec-now"]
    assert pre.exit_proceeds == now.exit_proceeds == 0.49
    assert pre.exit_fee == pytest.approx(PRE * 0.49 * 0.51)
    assert now.exit_fee == pytest.approx(NOW * 0.49 * 0.51)
    assert now.exit_fee - pre.exit_fee == pytest.approx((NOW - PRE) * 0.49 * 0.51)
    assert pre.net_pnl > now.net_pnl                       # the old fee was cheaper
    assert (pre.exit_coefficient, now.exit_coefficient) == (PRE, NOW)


def test_an_exit_tick_without_a_coefficient_is_refused_not_charged_at_todays():
    with pytest.raises(ValueError, match="fee_coefficient"):
        _run(_yes_round_trip(ML, None))


def test_a_no_side_exit_is_charged_at_its_tick_too():
    """The mirror frame pays 1 - ask; its fee comes from the same tick."""
    s = _run([
        _tick(0, bid=0.66, ask=0.70),
        _tick(1, bid=0.70, ask=0.74),                        # NO filled, cost 0.30
        _tick(2, bid=0.46, ask=0.50, coef=NOW),              # YES mid 0.48 <= 0.50
    ])
    (trade,) = s.trades
    assert trade.side == "no" and trade.exit_proceeds == pytest.approx(0.50)
    assert trade.exit_fee == pytest.approx(NOW * 0.50 * 0.50)


def test_the_report_names_what_was_charged_not_a_constant():
    """A settled position pays no fee and carries no coefficient; the target
    exits report the distinct coefficients they were actually charged at."""
    s = _run(_yes_round_trip("aec-pre", PRE) + _yes_round_trip("aec-now", NOW)
             + [_tick(0, bid=0.30, ask=0.34, slug="aec-open"),
                _tick(1, bid=0.28, ask=0.30, slug="aec-open")])   # fills, never exits
    _settle_open(s, {"aec-open": 1})
    assert charged_coefficients(s.trades) == [PRE, NOW]
    assert charged_coefficients([]) == []
