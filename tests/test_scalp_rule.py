"""The paper scalp rule, on fixture rows. No database, no network.

    pytest --noconftest tests/test_scalp_rule.py

Everything here drives the pure functions in core/gridiron/scalp.py; the loop
itself is not exercised, and the one thing worth asserting about the module as
a whole -- that it cannot reach the venue -- is checked by reading its imports.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

import pytest

from core.gridiron.scalp import (entry_price, entry_side, exit_check, exit_price,
                                 fee, is_stale, params_from_env, realise, triggered)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 13, 20, 0, tzinfo=UTC)
HOME, AWAY = "8", "2633"
#: The venue's coefficient on a fixture row: C is the current one, PRE what
#: the venue charged before it raised the fee on 2026-09-17 04:07Z. PRE is
#: spelled here and not imported because it is history; core/fees.py holds
#: only the current value.
C, PRE = 0.0695, 0.06


def _pos(side="yes", entry=0.40, tp=0.05, stop=0.10, size=25.0, pos_team=AWAY,
         coef=C):
    return {"side": side, "entry_px": entry, "tp": tp, "stop": stop,
            "size_usd": size, "pos_team": pos_team, "entered_at": NOW,
            "market_slug": "aec-nfl-a-b-2026-09-13", "fee_coefficient": coef}


def _chk(pos, bid, ask, *, pos_team=AWAY, final=False, stale=False, maker=False):
    return exit_check(pos, bid=bid, ask=ask, pos_team=pos_team,
                      game_final=final, stale=stale, maker_exit=maker)


# ------------------------------------------------------------------ the side
def test_the_offence_is_yes_when_away_and_no_when_home():
    """YES is always the away team on this venue."""
    assert entry_side(AWAY, HOME, AWAY) == "yes"
    assert entry_side(HOME, HOME, AWAY) == "no"


@pytest.mark.parametrize("pos_team", [None, "", "9999"])
def test_an_unknown_possession_takes_no_side_rather_than_guessing(pos_team):
    """A kickoff or end-of-period row can name a team this game does not have."""
    assert entry_side(pos_team, HOME, AWAY) is None


def test_ints_and_strings_are_the_same_team():
    assert entry_side(2633, HOME, 2633) == "yes"
    assert entry_side("2633", HOME, 2633) == "yes"


# ----------------------------------------------------------------- the price
def test_buying_no_costs_one_minus_the_bid_not_the_bid():
    """The defect this test exists for: NO priced at `bid` would make every
    home-offence ticket look ~2x cheaper than it is."""
    assert entry_price("yes", 0.40, 0.44) == pytest.approx(0.44)
    assert entry_price("no", 0.40, 0.44) == pytest.approx(0.60)


def test_a_taker_exit_crosses_the_spread_in_the_other_direction():
    assert exit_price("yes", 0.40, 0.44) == pytest.approx(0.40)
    assert exit_price("no", 0.40, 0.44) == pytest.approx(0.56)


def test_entering_and_exiting_immediately_loses_the_spread_and_two_fees():
    """A round trip on an unchanged book must be strictly negative."""
    for side in ("yes", "no"):
        px = entry_price(side, 0.40, 0.44)
        pos = _pos(side=side, entry=px)
        out = exit_price(side, 0.40, 0.44)
        pnl, f = realise(pos, "drive_end", out, maker_exit=False, coefficient=C)
        assert pnl < 0 and f > 0


@pytest.mark.parametrize("px", [0.0, 1.0])
def test_the_fee_vanishes_at_the_bounds(px):
    assert fee(px, 0.0695) == 0.0


# --------------------------------------------------------------- the trigger
@pytest.mark.parametrize("trig, ytg, want", [
    ("ytg40", 40, True), ("ytg40", 41, False), ("ytg40", 12, True),
    ("ytg20", 20, True), ("ytg20", 21, False)])
def test_the_yard_line_triggers_are_inclusive_at_their_limit(trig, ytg, want):
    assert triggered(trig, {"yards_to_goal": ytg, "drive_id": "d2"},
                     {"drive_id": "d1"}) is want


def test_it_fires_on_the_FIRST_play_of_a_drive_not_every_play_inside_it():
    inside = {"yards_to_goal": 15, "drive_id": "d7"}
    assert triggered("ytg40", inside, {"drive_id": "d6"}) is True
    assert triggered("ytg40", inside, {"drive_id": "d7"}) is False


def test_the_first_drive_we_ever_see_can_fire():
    assert triggered("ytg40", {"yards_to_goal": 10, "drive_id": "d1"}, None) is True


def test_a_missing_yard_line_does_not_fire():
    assert triggered("ytg40", {"yards_to_goal": None, "drive_id": "d1"}, None) is False


@pytest.mark.parametrize("now, then, want", [
    (0.55, 0.50, True), (0.50, 0.52, True), (0.51, 0.50, False), (0.50, 0.50, False)])
def test_move2c_is_two_cents_either_way(now, then, want):
    assert triggered("move2c", {}, None, mid_now=now, mid_60s_ago=then) is want


def test_move2c_without_a_prior_mid_does_not_fire():
    """No 60s-ago quote is not a zero move -- it is no measurement."""
    assert triggered("move2c", {}, None, mid_now=0.9, mid_60s_ago=None) is False


# -------------------------------------------------------------- the freshness
@pytest.mark.parametrize("play_age, tick_age, want", [
    (5, 5, False), (31, 5, True), (5, 31, True), (31, 31, True), (30, 30, False)])
def test_either_stale_input_blocks_an_entry(play_age, tick_age, want):
    """They fail independently: the venue can keep quoting a game whose play
    feed has died, and the reverse."""
    assert is_stale(NOW, play_at=NOW - dt.timedelta(seconds=play_age),
                    tick_at=NOW - dt.timedelta(seconds=tick_age), max_age_s=30) is want


@pytest.mark.parametrize("missing", ["play_at", "tick_at"])
def test_a_missing_timestamp_is_stale_not_fresh(missing):
    kw = {"play_at": NOW, "tick_at": NOW, "max_age_s": 30}
    kw[missing] = None
    assert is_stale(NOW, **kw) is True


# ------------------------------------------------------------------ the exits
def test_take_profit_fires_at_the_target_and_not_below():
    pos = _pos(entry=0.40)                       # tp at 0.42
    assert _chk(pos, 0.42, 0.43) == ("tp", 0.42)
    assert _chk(pos, 0.4199, 0.43) is None


def test_the_stop_fires_at_the_bound():
    pos = _pos(entry=0.40)                       # stop at 0.36
    assert _chk(pos, 0.36, 0.38) == ("stop", 0.36)
    assert _chk(pos, 0.3601, 0.38) is None


def test_one_snapshot_cannot_cross_both_bounds_so_the_order_is_a_tie_break():
    """A single price is either at-or-below the stop or at-or-above the target,
    never both -- so the stop-first ordering bites only on inverted parameters.
    It is checked here because an earlier docstring claimed it resolved a case
    that cannot arise, and a comment nobody tests is how that survives."""
    pos = _pos(entry=0.40, tp=0.05, stop=0.10)   # stop 0.36, tp 0.42
    assert _chk(pos, 0.36, 0.38)[0] == "stop"
    assert _chk(pos, 0.42, 0.44)[0] == "tp"
    inverted = _pos(entry=0.40, tp=0.05, stop=-0.20)   # stop 0.48 ABOVE tp 0.42
    # 0.45 is at-or-below the inverted stop AND at-or-above the target: the one
    # book state where both regions overlap, which is exactly the tie-break
    assert _chk(inverted, 0.45, 0.47)[0] == "stop", "stop wins when params invert"


def test_the_two_second_cadence_bounds_what_the_book_can_see():
    """A position that touched its target between cycles is recorded at what it
    did later. Pinned so the limitation is a test, not only a paragraph."""
    pos = _pos(entry=0.40)                        # tp 0.42
    assert _chk(pos, 0.41, 0.43) is None          # not seen at the touch...
    assert _chk(pos, 0.37, 0.39, pos_team=HOME)[0] == "drive_end"   # ...recorded here


def test_the_drive_ending_closes_the_position_at_the_taker_price():
    pos = _pos(entry=0.40, pos_team=AWAY)
    assert _chk(pos, 0.41, 0.43, pos_team=HOME) == ("drive_end", 0.41)


def test_possession_unchanged_holds():
    assert _chk(_pos(entry=0.40), 0.41, 0.43, pos_team=AWAY) is None


@pytest.mark.parametrize("kw, reason", [({"final": True}, "final"), ({"stale": True}, "stale")])
def test_final_and_stale_close_ahead_of_everything(kw, reason):
    """Neither leaves a price we are entitled to keep holding against."""
    pos = _pos(entry=0.40)
    assert _chk(pos, 0.45, 0.46, pos_team=HOME, **kw)[0] == reason


def test_a_no_side_exits_on_its_own_price_not_the_yes_price():
    pos = _pos(side="no", entry=0.60)            # tp at 0.63
    assert _chk(pos, 0.35, 0.37) == ("tp", pytest.approx(0.63))


# ----------------------------------------------------------- the maker variant
def test_the_maker_exit_fills_at_the_limit_and_pays_no_exit_fee():
    pos = _pos(entry=0.40)                       # rests at 0.42
    got = _chk(pos, 0.42, 0.44, maker=True)
    assert got == ("tp", pytest.approx(0.42))
    pnl_m, fee_m = realise(pos, "tp", got[1], maker_exit=True, coefficient=C)
    pnl_t, fee_t = realise(pos, "tp", got[1], maker_exit=False, coefficient=C)
    assert fee_m < fee_t and pnl_m > pnl_t
    assert fee_m == pytest.approx((25.0 / 0.40) * fee(0.40, C))  # entry fee only


def test_the_two_variants_share_a_trigger_and_differ_only_in_price_and_fee():
    """A resting sell fills when OUR side's bid reaches the limit -- the same
    quantity a taker sells into. So they fire together; the maker takes exactly
    its limit and pays nothing, the taker takes the touch and pays the fee."""
    pos = _pos(entry=0.40)                       # tp at 0.42
    assert _chk(pos, 0.4199, 0.45, maker=True) is None
    assert _chk(pos, 0.4199, 0.45, maker=False) is None
    assert _chk(pos, 0.44, 0.46, maker=True) == ("tp", pytest.approx(0.42))
    assert _chk(pos, 0.44, 0.46, maker=False) == ("tp", pytest.approx(0.44))


def test_a_maker_exit_on_a_non_tp_reason_still_pays_the_taker_fee():
    pos = _pos(entry=0.40)
    _, f = realise(pos, "drive_end", 0.39, maker_exit=True, coefficient=C)
    assert f == pytest.approx((25.0 / 0.40) * (fee(0.40, C) + fee(0.39, C)))


# ------------------------------------------------------------------ the ticket
def test_the_ticket_costs_size_usd_whatever_the_price():
    for entry in (0.10, 0.40, 0.90):
        pos = _pos(entry=entry)
        contracts = 25.0 / entry
        pnl, _ = realise(pos, "drive_end", entry, maker_exit=False, coefficient=C)
        assert contracts * entry == pytest.approx(25.0)
        assert pnl == pytest.approx(-contracts * fee(entry, C) * 2, rel=1e-9)


# ------------------------------------------------------------------- the config
def test_an_unknown_trigger_fails_loudly():
    with pytest.raises(SystemExit, match="ytg40"):
        params_from_env({"TRIGGER": "moon"})


def test_the_defaults_are_the_spec():
    p = params_from_env({})
    assert (p["trigger"], p["tp"], p["stop"], p["size_usd"], p["maker_exit"],
            p["max_age_s"]) == ("ytg40", 0.05, 0.10, 25.0, False, 30.0)


def test_maker_exit_is_off_unless_explicitly_one():
    assert params_from_env({"MAKER_EXIT": "0"})["maker_exit"] is False
    assert params_from_env({"MAKER_EXIT": "true"})["maker_exit"] is False
    assert params_from_env({"MAKER_EXIT": "1"})["maker_exit"] is True


# --------------------------------------------------------------- the safety bar
def test_the_engine_cannot_reach_the_venue():
    """Structural, not a promise in a comment: no venue client is importable
    from this module, so no code path in it can place an order."""
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "core" / "gridiron" / "scalp.py").read_text(encoding="utf-8")
    for banned in ("polymarket", "PolymarketGatewayClient", "requests", "httpx",
                   "urllib", "place_order", "aiohttp"):
        assert not re.search(rf"\b{banned}\b", src, re.I), f"scalp.py references {banned}"


def test_a_timestamp_from_the_future_is_stale_not_fresh():
    """★ The gate was admitting exactly the corrupt rows.

    `age > max_age_s` alone treats a NEGATIVE age as perfectly fresh, so a
    play stamped in the future passes the one check meant to stop it.
    Measured 2026-09-14: 85 of 2,727 NFL plays recorded 09-10..14 carry a
    wall_clock 24 hours ahead (min lag -86,378s = -86,400 plus the usual
    lag), while 93.7% of GOOD plays were refused for being a median 52.8s
    old at first sight. The gate refused the real ones and let the broken
    ones through.
    """
    import datetime as dt

    from core.gridiron.scalp import is_stale

    utc = dt.timezone.utc
    now = dt.datetime(2026, 9, 14, 12, 0, tzinfo=utc)
    fresh = now - dt.timedelta(seconds=5)
    tomorrow = now + dt.timedelta(days=1)

    assert is_stale(now, play_at=tomorrow, tick_at=fresh, max_age_s=30.0), (
        "a play stamped 24 hours in the future passed the freshness gate")
    assert is_stale(now, play_at=fresh, tick_at=tomorrow, max_age_s=30.0), (
        "the tick side does not check the future either")
    # And the ordinary case still works in both directions.
    assert not is_stale(now, play_at=fresh, tick_at=fresh, max_age_s=30.0)
    assert is_stale(now, play_at=now - dt.timedelta(seconds=31),
                    tick_at=fresh, max_age_s=30.0)
    # A second of clock skew between the feed's clock and ours is tolerated;
    # a day is not skew.
    assert not is_stale(now, play_at=now + dt.timedelta(milliseconds=500),
                        tick_at=fresh, max_age_s=30.0)


# ------------------------------------------------------ the row's coefficient
# The venue raised its taker coefficient on 2026-09-17 04:07Z. The engine reads
# the newest market_snapshots row, which carries the coefficient in force when
# it was written, so a paper book written across that instant charges each leg
# what the venue charged then -- never today's constant on both.


def test_each_leg_is_charged_at_the_coefficient_on_its_own_row():
    """Opened before the raise, closed after it: the entry pays the old
    coefficient and the exit the new one, as expressions in each."""
    pos = _pos(entry=0.40, coef=PRE)
    contracts = 25.0 / 0.40
    _, f = realise(pos, "drive_end", 0.39, maker_exit=False, coefficient=C)
    assert f == pytest.approx(contracts * (PRE * 0.40 * 0.60 + C * 0.39 * 0.61))
    # The same book with both legs pre-raise is cheaper by exactly the raise
    # on the exit leg, and nothing else moved.
    _, f_pre = realise(pos, "drive_end", 0.39, maker_exit=False, coefficient=PRE)
    assert f - f_pre == pytest.approx(contracts * (C - PRE) * 0.39 * 0.61)
    assert f > f_pre


@pytest.mark.parametrize("leg", ["entry", "exit"])
def test_a_charged_leg_whose_row_has_no_coefficient_is_refused(leg):
    """Never silently priced at today's: the silent path is the defect."""
    pos = _pos(entry=0.40, coef=None if leg == "entry" else C)
    with pytest.raises(ValueError, match="fee_coefficient"):
        realise(pos, "drive_end", 0.39, maker_exit=False,
                coefficient=None if leg == "exit" else C)


def test_fee_needs_the_row_s_coefficient_and_charges_that_row():
    """Nothing in the scalp prices a bet now: every price is a recorded tick,
    so a missing coefficient is an error, never today's constant."""
    from core.fees import POLYMARKET_TAKER as POST   # the coefficient since 2026-09-17; PRE is the one before
    with pytest.raises(ValueError):
        fee(0.40, None)
    assert fee(0.40, PRE) == pytest.approx(PRE * 0.40 * 0.60)
    assert fee(0.40, PRE) < fee(0.40, POST)


def test_the_tick_query_reads_the_coefficient_beside_the_touch():
    from core.gridiron.scalp import TICK_SQL
    assert "fee_coefficient" in TICK_SQL
