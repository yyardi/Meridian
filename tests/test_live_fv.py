"""Live FV strip tests.

Three things carry the weight:

* **It stays display-only.** The strip must have no path to an order. That is
  a property of the code, so it is asserted against the source rather than
  trusted to review.
* **Frame conventions.** The margin is computed in the first team's frame
  because that is the frame the YES side of the book is quoted in. Mixing them
  is the V15 bug and it produces numbers that pass every individual check.
* **Interpolation edges.** There is no game clock, so minutes-remaining is
  interpolated; period start, halftime, overtime and a quarter that runs long
  are each capable of producing a negative time and an imaginary square root.
"""

from __future__ import annotations

import inspect
import math

import pytest

from core.live_fv import (
    DEFAULT_SIGMA,
    GAP_HIGHLIGHT,
    REGULATION_MINUTES,
    LiveFV,
    fair_value,
    minutes_remaining,
    parse_score,
)


def _row(**kw) -> LiveFV:
    base = dict(
        event_slug="wnba-aaa-bbb-2026-08-06", market_slug="aec-wnba-aaa-bbb-2026-08-06",
        label="AAA to win", period="Q2", score="40-42", margin=-2,
        minutes_left=20.0, minutes_left_is_estimate=True, pregame_price=0.50,
        fair_value=0.45, bid=0.40, ask=0.42,
    )
    base.update(kw)
    return LiveFV(**base)


# --------------------------------------------------------------------- #
# Display only — asserted, not assumed
# --------------------------------------------------------------------- #


def test_the_module_never_imports_the_executor():
    """No path from a displayed number to a sent order."""
    import core.live_fv as m

    source = inspect.getsource(m)
    for forbidden in ("core.executor", "build_order", "LimitOrder",
                      "ShadowOrder", "place_order", "kelly"):
        assert forbidden not in source, f"{forbidden} must not reach the FV strip"


def test_the_serialised_row_carries_no_order_or_size_fields():
    from core.live_fv import as_dict

    keys = set(as_dict(_row()))
    assert not keys & {"order", "quantity", "size", "ticket", "intent", "side"}


def test_the_fv_strip_no_longer_renders_on_the_page():
    """The page's live-FV strip was deleted in the two-table redesign — the
    lines table carries PULSE's live FV instead. The ENDPOINT and this
    module's own no-order-path discipline (tested above) are unchanged; what
    this pins now is that the deleted consumer stays deleted rather than
    creeping back as a third view of the same data."""
    from pathlib import Path

    html = Path("static/index.html").read_text()
    assert "loadLiveFV" not in html
    assert "loadLiveTotals" not in html
    assert "loadEVGuard" not in html


# --------------------------------------------------------------------- #
# Frame conventions
# --------------------------------------------------------------------- #


def test_score_parses_as_first_team_then_second_team():
    assert parse_score("46-34") == (46, 34)


def test_an_unparseable_score_is_none_not_a_guess():
    assert parse_score(None) is None
    assert parse_score("") is None
    assert parse_score("live") is None


def test_fair_value_is_quoted_in_the_yes_frame_so_it_compares_to_the_book():
    """A leading first team must price above 0.5, matching a YES quote."""
    fv = fair_value(margin=+8, minutes_left=10.0, pregame_price=0.50)
    assert fv > 0.5


def test_the_gap_is_model_minus_market_in_one_frame():
    row = _row(fair_value=0.60, bid=0.40, ask=0.42)
    assert row.mid == pytest.approx(0.41)
    assert row.gap == pytest.approx(0.19)


def test_a_trailing_first_team_prices_below_a_leading_one_on_the_same_book():
    up = fair_value(margin=+5, minutes_left=20.0, pregame_price=0.50)
    down = fair_value(margin=-5, minutes_left=20.0, pregame_price=0.50)
    assert up + down == pytest.approx(1.0)
    assert down < 0.5 < up


def test_the_pregame_price_moves_the_fair_value_in_its_own_direction():
    """A favourite tied at the half must price above an underdog tied."""
    fav = fair_value(margin=0, minutes_left=20.0, pregame_price=0.80)
    dog = fair_value(margin=0, minutes_left=20.0, pregame_price=0.20)
    assert fav > 0.5 > dog


def test_no_pregame_price_yields_no_fair_value_rather_than_a_coin_flip():
    """A 50/50 prior on a mismatch is a wrong assumption, not a neutral one.

    This is the assumption that made hypothesis #16 look like a 6.8c edge.
    """
    assert fair_value(margin=-2, minutes_left=20.0, pregame_price=None) is None


# --------------------------------------------------------------------- #
# Interpolation edges
# --------------------------------------------------------------------- #


def test_period_start_is_exact_not_an_estimate():
    """The only instant the clock is known. win_curve.py measures here."""
    for period, expected in (("Q2", 30.0), ("Q3", 20.0), ("Q4", 10.0)):
        left, is_estimate, _ = minutes_remaining(period, seconds_into_period=0.0)
        assert left == pytest.approx(expected)
        assert is_estimate is False


def test_mid_period_is_interpolated_and_flagged_as_an_estimate():
    left, is_estimate, _ = minutes_remaining("Q1", seconds_into_period=300.0)
    assert left == pytest.approx(35.0)      # 5 of Q1's 10 minutes used
    assert is_estimate is True


def test_a_quarter_that_runs_long_is_clamped_not_allowed_to_go_negative():
    """Wall clock overruns game clock constantly — timeouts, fouls, reviews.

    Without the clamp this drives minutes_left negative and sqrt() raises.
    """
    clock = minutes_remaining("Q4", seconds_into_period=45 * 60.0)
    assert clock.minutes_left == 0.0


def test_an_exhausted_clock_is_marked_unusable_rather_than_zero_minutes():
    """The failure this exists to prevent: FV 1.000 on a three-point game.

    A WNBA quarter takes 15-20 wall-clock minutes, so the estimate saturates
    every game. At `minutes_left = 0` the formula stops being a probability
    and becomes a step function, printing certainty exactly where the estimate
    is least trustworthy.
    """
    clock = minutes_remaining("Q4", seconds_into_period=45 * 60.0)
    assert clock.usable is False
    assert "exhausted" in clock.note
    # And the step function it would have produced:
    assert fair_value(margin=3, minutes_left=0.0, pregame_price=0.5) == 1.0


def test_a_normal_in_period_estimate_stays_usable():
    clock = minutes_remaining("Q3", seconds_into_period=240.0)
    assert clock.usable is True
    assert clock.is_estimate is True


def test_overtime_is_unusable_so_no_number_is_shown_under_a_does_not_apply_note():
    assert minutes_remaining("OT", seconds_into_period=60.0).usable is False


def test_an_unknown_or_missing_period_is_unusable():
    assert minutes_remaining("Q7", seconds_into_period=0.0).usable is False
    assert minutes_remaining(None, seconds_into_period=0.0).usable is False


def test_halftime_stays_usable_because_its_clock_is_exact():
    assert minutes_remaining("HT", seconds_into_period=900.0).usable is True


def test_the_clock_still_unpacks_as_a_three_tuple():
    left, is_estimate, note = minutes_remaining("Q2", seconds_into_period=0.0)
    assert (left, is_estimate, note) == (30.0, False, None)


def test_halftime_is_exact_and_does_not_burn_clock():
    left, is_estimate, note = minutes_remaining("HT", seconds_into_period=900.0)
    assert left == pytest.approx(20.0)
    assert is_estimate is False
    assert note == "halftime"


def test_overtime_has_no_regulation_minutes_left_and_says_so():
    """★ THIS TEST USED TO PIN `left == OT_MINUTES`, AND `OT_MINUTES = 5.0` HAD
    THE COMMENT "overtime periods are 5 minutes in the WNBA". A WNBA length, and
    the tape says it is exercised on football: 23,760 CFB rows over 3 games and
    15,209 NFL rows over 1 carry `event_period='OT'`.

    CFB overtime is UNTIMED possessions, so there is no remaining-minutes
    quantity to compute; the old countdown reached 0.0 after five wall-clock
    minutes and sat there through the rest of a real overtime. NFL regulation
    overtime is 10 minutes, not 5.

    This field means REGULATION minutes remaining, and in overtime that is
    exactly zero for every league -- the true value, not a safer guess, which is
    why the constant is gone rather than becoming a per-league map."""
    clock = minutes_remaining("OT", seconds_into_period=0.0)
    assert clock.minutes_left == 0.0
    assert clock.usable is False
    assert "overtime" in (clock.note or "").lower()
    # and no length is asserted in the note any more
    assert "5 minutes" not in (clock.note or "")


def test_overtime_is_zero_at_every_elapsed_including_past_any_ot_length():
    """A CFB overtime can run half an hour of wall clock. The old form was
    monotonically decreasing and floored at five minutes in, so it looked
    plausible early and was pinned at zero for the part that mattered."""
    for secs in (0.0, 120.0, 300.0, 1800.0, 3600.0):
        clock = minutes_remaining("OT2", seconds_into_period=secs)
        assert clock.minutes_left == 0.0, f"OT2 at {secs}s gave {clock.minutes_left}"
        assert clock.usable is False


def test_the_stronger_flag_survives_the_legacy_tuple_unpacking():
    """★ THE MECHANISM BY WHICH `usable` WENT MISSING. `Clock.__iter__` offers
    3-tuple unpacking of (minutes_left, is_estimate, note), so dropping the
    stronger flag is what happens by DEFAULT -- including in the tests just
    above, which unpacked three values for years. `Clock`'s own docstring calls
    `usable` the stronger of the two, and both places that showed
    `minutes_left` to a human dropped it."""
    clock = minutes_remaining("OT", seconds_into_period=60.0)
    left, is_estimate, note = clock          # the lossy interface
    assert (left, is_estimate) == (0.0, True)
    assert clock.usable is False             # only reachable on the object
    # is_estimate does NOT carry the same information, which is the whole point
    est_only = minutes_remaining("Q3", seconds_into_period=60.0)
    assert est_only.is_estimate is True and est_only.usable is True


def test_a_final_game_has_no_time_left_and_a_step_function_value():
    left, is_estimate, note = minutes_remaining("FT", seconds_into_period=0.0)
    assert left == 0.0 and is_estimate is False and note == "final"
    assert fair_value(margin=-1, minutes_left=0.0, pregame_price=0.9) == 0.0


def test_an_unknown_period_falls_back_loudly_rather_than_silently():
    left, is_estimate, note = minutes_remaining("Q7", seconds_into_period=0.0)
    assert left == REGULATION_MINUTES
    assert is_estimate is True
    assert "unrecognised" in note


def test_a_missing_period_is_flagged_rather_than_assumed_to_be_q1():
    _, is_estimate, note = minutes_remaining(None, seconds_into_period=0.0)
    assert is_estimate is True
    assert "no period" in note


def test_negative_elapsed_time_cannot_add_minutes_to_the_clock():
    """Clock skew between writers must not manufacture extra game."""
    left, _, _ = minutes_remaining("Q2", seconds_into_period=-600.0)
    assert left == pytest.approx(30.0)


# --------------------------------------------------------------------- #
# Highlighting
# --------------------------------------------------------------------- #


def test_a_small_gap_is_not_highlighted():
    row = _row(fair_value=0.42, bid=0.40, ask=0.42)     # mid 0.41, gap 1c
    assert abs(row.gap) < GAP_HIGHLIGHT
    assert row.highlight is False


def test_a_large_gap_is_highlighted_in_both_directions():
    assert _row(fair_value=0.60, bid=0.40, ask=0.42).highlight is True
    assert _row(fair_value=0.20, bid=0.40, ask=0.42).highlight is True


def test_a_missing_quote_is_not_a_gap_of_zero():
    row = _row(bid=None, ask=None)
    assert row.mid is None and row.gap is None and row.highlight is False


def test_fair_value_stays_finite_across_the_whole_price_range():
    for price in (0.0, 0.01, 0.5, 0.99, 1.0):
        for minutes in (0.1, 10.0, 40.0):
            fv = fair_value(margin=0, minutes_left=minutes, pregame_price=price)
            assert fv is not None and math.isfinite(fv) and 0.0 <= fv <= 1.0


# --------------------------------------------------------------------- #
# The stale-flag filter. C16: `is_live` is never cleared.
# --------------------------------------------------------------------- #
def test_a_market_whose_stream_died_is_not_priced_as_live():
    """★ `is_live IS TRUE` selects a FROZEN flag, not a live market.

    Measured on prod 2026-09-14: 11,227 of 12,290 markets whose last row says
    live have not been written in over 600 seconds, and the oldest such row is
    43 days old. Nothing clears the flag — when a game ends its markets drop
    off the venue's board, so the last row says live forever.

    Two markets here differ ONLY in how old their newest row is. The fresh one
    must price; the stale one must not, or a 43-day-old quote is fair value.
    The decision is core/board.py:market_state(), so there is one definition
    of live rather than a second freshness rule written here.
    """
    import datetime as _dt

    from sqlalchemy import text

    from core.live_fv import build_live_fv
    from core.storage import get_engine, get_sessionmaker

    UTC = _dt.timezone.utc
    now = _dt.datetime.now(UTC)
    start = now - _dt.timedelta(hours=1)          # tipped off, well inside 3.5h
    Session = get_sessionmaker(get_engine())

    def _mk(s, slug, captured_at):
        s.execute(text("""
            INSERT INTO market_snapshots
              (market_slug, event_slug, captured_at, is_live, game_start_time,
               sports_market_type, event_period, event_score,
               best_bid, best_ask)
            VALUES (:m, :e, :c, true, :g,
                    'basketball_team_full_game_winner', 2, '50-48', 0.50, 0.52)
        """), {"m": slug, "e": slug, "c": captured_at, "g": start})

    fresh, stale = "wnba-fresh-stream-2099-01-01", "wnba-dead-stream-2099-01-01"
    with Session() as s:
        for slug in (fresh, stale):
            s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                      {"m": slug})
        _mk(s, fresh, now - _dt.timedelta(seconds=5))
        _mk(s, stale, now - _dt.timedelta(hours=2))     # writer died 2h ago
        s.commit()
    try:
        with Session() as s:
            got = {r.market_slug for r in build_live_fv(s, within_hours=6.0)}
        assert stale not in got, (
            "a market last written 2 hours ago was priced as live — the "
            "frozen is_live flag was believed")
        assert fresh in got, (
            "the control failed: a market written 5 seconds ago was dropped, "
            "so this test would pass against a function that returns nothing")
    finally:
        with Session() as s:
            for slug in (fresh, stale):
                s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                          {"m": slug})
            s.commit()


def test_the_api_row_carries_usable_not_only_is_estimate():
    """★ THE FLAG STOPPED AT THE BOUNDARY. `fair_value` respects `usable`, and
    the two places that surface `minutes_left` to a human -- `as_dict` for
    /api and `game_detail.TradeContext` -- both dropped it. So a reading the
    module had marked unusable arrived on a screen labelled only "est.".
    Asserted on the serialised row, which is what the UI actually receives."""
    from core.live_fv import LiveFV, as_dict

    row = LiveFV(
        event_slug="e", market_slug="m", label="L", period="OT", score="10-10",
        margin=0, minutes_left=0.0, minutes_left_is_estimate=True,
        pregame_price=0.5, fair_value=None, bid=0.4, ask=0.6,
        minutes_left_usable=False,
    )
    d = as_dict(row)
    assert d["minutes_left_usable"] is False
    assert d["minutes_left_is_estimate"] is True      # both present, not one
    assert d["fair_value"] is None                    # and the FV is suppressed


def test_game_detail_context_carries_usable_too():
    """The second consumer. It reads the three fields by hand, which is the same
    omission the legacy tuple makes automatically."""
    import inspect

    from core.game_detail import TradeContext

    assert "minutes_left_usable" in inspect.signature(TradeContext).parameters
    src = inspect.getsource(__import__("core.game_detail", fromlist=["x"]))
    assert "minutes_left_usable=minutes_left_usable" in src


def test_usable_survives_the_real_construction_path_not_just_a_hand_built_row():
    """★ THE TEST THAT WAS MISSING, AND A MUTATION FOUND THE GAP. My first
    version of the usable tests built a `LiveFV` by hand, so deleting the
    `minutes_left_usable=clock.usable` line in `build_live_fv` broke nothing --
    the field's default answered for it. This goes through the database and the
    real function, for a REGULATION row (usable) and an OVERTIME row (not), so
    the propagation itself is what is under test rather than the dataclass.
    """
    import datetime as _dt

    from sqlalchemy import text

    from core.live_fv import build_live_fv
    from core.storage import get_engine, get_sessionmaker

    UTC = _dt.timezone.utc
    now = _dt.datetime.now(UTC)
    start = now - _dt.timedelta(hours=1)
    Session = get_sessionmaker(get_engine())
    q3 = "dbg-usable-q3-aec-wnba-conn-dal-2026-09-14"
    ot = "dbg-usable-ot-aec-wnba-conn-dal-2026-09-14"

    def _mk(s, slug, period):
        s.execute(text("""
            INSERT INTO market_snapshots
              (market_slug, event_slug, captured_at, is_live, game_start_time,
               sports_market_type, event_period, event_score, best_bid, best_ask)
            VALUES (:m, :e, :c, true, :g,
                    'basketball_team_full_game_winner', :p, '80-80', 0.48, 0.52)
        """), {"m": slug, "e": f"ev-{slug}", "c": now - _dt.timedelta(seconds=5),
               "g": start, "p": period})

    try:
        with Session() as s:
            for slug in (q3, ot):
                s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                          {"m": slug})
            _mk(s, q3, "Q3")
            _mk(s, ot, "OT")
            s.commit()
        with Session() as s:
            rows = {r.market_slug: r for r in build_live_fv(s, within_hours=6.0)}

        assert q3 in rows and ot in rows, f"setup failed, got {sorted(rows)}"
        # The control: a regulation row must come back USABLE, or this test
        # would pass against a build_live_fv that hardcoded False.
        assert rows[q3].minutes_left_usable is True
        assert rows[ot].minutes_left_usable is False
        assert rows[ot].minutes_left == 0.0
        assert rows[ot].fair_value is None
    finally:
        with Session() as s:
            for slug in (q3, ot):
                s.execute(text("DELETE FROM market_snapshots WHERE market_slug = :m"),
                          {"m": slug})
            s.commit()
