"""The separation, the guards, and the retirement — as tests of the CONFUSION.

Every assertion here encodes a way this report has been read wrong, not the
arithmetic. The arithmetic was never what failed: the blend was computed
correctly for weeks and meant the opposite of what it appeared to mean.
"""

from __future__ import annotations

import datetime as dt

import pytest

from analysis.guards import GuardViolation, assert_age_non_negative
from core.quote.report import (
    PHANTOM,
    REAL,
    UNMATCHED,
    PopulationReport,
    RegimeReport,
    classify_fill,
    format_report,
    net_capture_mark,
    score_fill,
)
from core.quote.storage import ASK, BID


# ---------------------------------------------------------------- the mechanism

def test_bid_fills_while_ask_still_above_is_a_phantom():
    """THE central confusion. The model fills on mid <= B; reality needs ask <= B.

    Our bid rests at 40c. The book's bid slid to 38c and the ask is still 44c,
    so the mid is 41c — no, 41c is above 40c; make the dip real: bid 34c,
    ask 44c, mid 39c, which is BELOW our 40c bid and fills us in the simulator.
    Nobody offered anywhere near 40c. This fill could not have happened.
    """
    assert classify_fill(side=BID, quote_price=0.40,
                         best_bid=0.34, best_ask=0.44) == PHANTOM


def test_bid_is_real_only_when_a_seller_crossed_down_to_us():
    assert classify_fill(side=BID, quote_price=0.40,
                         best_bid=0.34, best_ask=0.40) == REAL
    assert classify_fill(side=BID, quote_price=0.40,
                         best_bid=0.34, best_ask=0.39) == REAL


def test_ask_uses_the_bid_and_the_asymmetry_is_not_a_typo():
    """An ASK is only reachable by a buyer who came UP to it."""
    assert classify_fill(side=ASK, quote_price=0.60,
                         best_bid=0.60, best_ask=0.66) == REAL
    assert classify_fill(side=ASK, quote_price=0.60,
                         best_bid=0.55, best_ask=0.66) == PHANTOM


def test_the_side_that_matters_is_the_one_whose_absence_is_asked_about():
    """A BID needs the ASK. A recorded bid with no ask is UNMATCHED, not real.

    Folding "half a book" into a population would let a coverage hole read as an
    economic finding, and it would do so in the flattering direction.
    """
    assert classify_fill(side=BID, quote_price=0.40,
                         best_bid=0.34, best_ask=None) == UNMATCHED
    assert classify_fill(side=ASK, quote_price=0.60,
                         best_bid=None, best_ask=0.66) == UNMATCHED


# -------------------------------------------------- the blend means the opposite

def _pop(pop, n, staked, returned, games=12):
    return PopulationReport(regime="ingame", population=pop, n_fills=n,
                            n_settled=n, n_games=games, staked=staked,
                            returned=returned, roi_clustered=None)


def test_the_blend_understates_the_loss_by_five_and_a_half_times():
    """The specimen, at the measured WNBA proportions (17,339 fills): 63.9%
    phantom at +0.951c and 36.1% real at -3.376c blend to **-0.610c**.

    Note the unit trap this test also pins: the recorded "-1.60c ledgered blend"
    is a CAPTURE number and is NOT comparable to this one. On SETTLEMENT — the
    primary metric — the blend is -0.610c, so it understates the real loss by
    5.5x, not by the 2.1x the capture figures suggest. A blend is not a
    conservative estimate of the real number; it is a different number, in a
    different metric, and the report must never score it.
    """
    n_ph, n_re = 11084, 6255
    blend = (n_ph * 0.951 + n_re * -3.376) / (n_ph + n_re)
    assert blend == pytest.approx(-0.610, abs=0.005), blend
    assert -3.376 / blend == pytest.approx(5.5, abs=0.1)
    rr = RegimeReport(regime="ingame", populations={
        PHANTOM: _pop(PHANTOM, n_ph, 1.0, 1.0),
        REAL: _pop(REAL, n_re, 1.0, 1.0),
    })
    assert abs(rr.phantom_share - 0.639) < 0.001
    assert rr.populations[PHANTOM].verdict.startswith("NOT SCORED")


def test_unmatched_is_excluded_from_the_phantom_share_denominator():
    """Otherwise the phantom share moves with RECORDER HEALTH rather than with
    the simulator, and a depth outage reads as the strategy improving."""
    rr = RegimeReport(regime="ingame", populations={
        PHANTOM: _pop(PHANTOM, 60, 1.0, 1.0),
        REAL: _pop(REAL, 40, 1.0, 1.0),
        UNMATCHED: _pop(UNMATCHED, 9000, 0.0, 0.0),
    })
    assert rr.phantom_share == pytest.approx(0.60)


# ------------------------------------------------------------ rule 22, wired

def test_a_regime_with_no_fills_cannot_print_a_bare_zero():
    """Rule 22. An empty report must say WHICH kind of empty it is."""
    text = format_report({}, session=None)
    assert "UNPROVEN INSTRUMENT" in text
    assert "NOT evidence of absence" in text


def test_a_regime_with_no_real_fills_says_so_rather_than_scoring_nothing():
    rr = RegimeReport(regime="ingame", populations={
        PHANTOM: _pop(PHANTOM, 900, 400.0, 402.0)})
    text = format_report({"ingame": rr}, session=None)
    assert "no REAL fills in this regime" in text
    assert "VERDICT: PASS" not in text      # the caveat mentions PASS; no verdict does


# ------------------------------------------------------------ rule 25, wired

def test_the_staked_roi_prints_its_parts_and_warns_that_it_ranks_inactivity():
    """Rule 25. A ratio whose optimum is 'never act' must say so beside itself."""
    rr = RegimeReport(regime="ingame", populations={
        REAL: PopulationReport(
            regime="ingame", population=REAL, n_fills=6255, n_settled=6255,
            n_games=13, staked=3000.0, returned=2789.0, roi_clustered=None)})
    text = format_report({"ingame": rr}, session=None)
    assert "events=6255" in text            # the parts travel with the ratio
    assert "per_event=" in text
    assert "RULE 25" in text
    assert "NEVER ACTING" in text


# ------------------------------------------------------------ rule 23, wired

def test_a_touch_from_the_future_trips_the_age_assert():
    """A forward join's one-sided cap is vacuous and reads like a freshness gate."""
    assert_age_non_negative(0.0, "the measured case — every fill is age 0")
    with pytest.raises(GuardViolation, match="vacuous"):
        assert_age_non_negative(-90000.0, "a book 25h AFTER the fill")


# --------------------------------------------------- the retirement, pinned

def test_capture_is_identically_the_negative_overshoot():
    """Why capture is retired, as arithmetic rather than as a claim.

    The fill rule fires when the mid reaches the quote, so `capture` has no
    freedom left: it equals -(how far the mid went past our price). Zero degrees
    of freedom means no gradient read off it can fail to appear.
    """
    for qp, mid in ((0.40, 0.385), (0.40, 0.40), (0.62, 0.58)):
        overshoot = qp - mid                      # how far past us the mid went
        assert net_capture_mark(side=BID, quote_price=qp,
                                mid_at_fill=mid) == pytest.approx(-overshoot)


def test_capture_does_not_appear_in_the_report():
    rr = RegimeReport(regime="ingame", populations={
        REAL: PopulationReport(
            regime="ingame", population=REAL, n_fills=6255, n_settled=6255,
            n_games=13, staked=3000.0, returned=2789.0, roi_clustered=None)})
    text = format_report({"ingame": rr}, session=None).lower()
    assert "net capture at fill" not in text
    assert "retired" in text


# ------------------------------------------------------------ money at price

def test_an_ask_is_the_no_side_at_the_complementary_price():
    assert score_fill(side=BID, quote_price=0.40, settlement=1) == (0.40, 1.0)
    assert score_fill(side=ASK, quote_price=0.40, settlement=1) == (0.60, 0.0)


def test_floors_are_read_on_the_real_population_not_the_tape():
    """38,465 fills over 24 games is far past the floors — on the BLEND. The
    floors must bind on `real`, or a tape made of phantoms buys a verdict."""
    rr = RegimeReport(regime="ingame", populations={
        PHANTOM: _pop(PHANTOM, 24814, 12000.0, 12100.0, games=24),
        REAL: _pop(REAL, 400, 200.0, 190.0, games=24),
    })
    assert rr.n_fills > 25000
    assert not rr.at_floor
    assert rr.verdict == "NO DATA"
