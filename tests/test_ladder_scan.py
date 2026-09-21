"""The ladder scanner, pinned on the cases that actually went wrong.

Every test here is a defect that occurred while measuring this, not a
hypothetical: the double-count that overstated CFB 2.5x, the stale rung that
produced an 88c "arbitrage", the min-of-two-legs rule, and the fee netting that
separates a real violation from a pair that merely crosses the spread.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core.ladder import scan  # noqa: E402


def _rungs(**kw):
    """line -> (bid, ask, bid_size, ask_size)"""
    return {float(k.lstrip("m").replace("_", ".")) * (-1 if k.startswith("m") else 1): v
            for k, v in kw.items()}


def test_a_consistent_ladder_yields_nothing():
    """Higher line dearer, as arithmetic requires."""
    r = {0.0: (0.50, 0.51, 100, 100), 1.5: (0.60, 0.61, 100, 100)}
    assert scan.scan_ladder("g", r) == []


def test_the_inversion_is_found_and_priced_net_of_BOTH_fees():
    # buy line 1.5 at 0.49, sell line 0.0 at 0.62 -- impossible, 1.5 is easier
    r = {0.0: (0.62, 0.63, 500, 500), 1.5: (0.48, 0.49, 500, 500)}
    v = scan.scan_ladder("g", r)
    assert len(v) == 1
    raw = 0.62 - 0.49
    assert v[0].edge < raw, "fees must be netted off both legs"
    assert abs(v[0].edge - (raw - scan.fee(0.49) - scan.fee(0.62))) < 1e-12


def test_a_pair_that_merely_crosses_the_spread_is_not_a_violation():
    """The fee is what separates these. Without netting it, far more pairs
    qualify and none of the extras are tradeable."""
    r = {0.0: (0.500, 0.510, 100, 100), 1.5: (0.495, 0.499, 100, 100)}
    v = scan.scan_ladder("g", r)
    assert v == [], "0.5c gross cannot survive two fees near 0.5"


def test_a_stale_deep_rung_is_excluded_rather_than_counted():
    """USC -17.5 at 0.930 against -10.5 at 0.040 gave an 88c 'edge'. Including
    those inflated the total ~2.5x and not one had size behind it."""
    r = {-17.5: (0.930, 0.940, 10, 10), -10.5: (0.030, 0.040, 10, 10)}
    assert scan.scan_ladder("g", r) == []
    wide = scan.scan_ladder("g", r, max_edge=1.0)
    assert len(wide) == 1 and wide[0].edge > 0.15, "the guard, not the arithmetic"


def test_size_is_the_SMALLER_leg():
    """An arbitrage is only as big as its smaller side. Polymarket routinely
    shows depth on one leg and nothing on the other."""
    r = {0.0: (0.62, 0.63, 4, 900), 1.5: (0.48, 0.49, 900, 900)}
    v = scan.scan_ladder("g", r)
    assert v[0].size == 4
    assert v[0].dollars == v[0].edge * 4


def test_best_per_game_does_not_double_count_a_shared_rung():
    """One mispriced rung violates against every rung it pairs with; they share
    a leg and compete for the same depth. Summing pairs overstated CFB by 2.5x
    ($1,024.95 vs $413.90)."""
    r = {0.0: (0.62, 0.63, 500, 500), 1.5: (0.48, 0.49, 500, 500),
         2.5: (0.47, 0.48, 500, 500)}
    v = scan.scan_ladder("g", r)
    assert len(v) >= 2, "the shared rung should produce several pairs"
    total_pairs = sum(x.dollars for x in v)
    best = scan.best_per_game(v)["g"]
    assert best == max(x.dollars for x in v)
    assert best < total_pairs, "best-per-game must be strictly below the pair sum"


def test_kalshi_rate_is_higher_and_shrinks_the_edge():
    r = {0.0: (0.62, 0.63, 500, 500), 1.5: (0.48, 0.49, 500, 500)}
    pm = scan.scan_ladder("g", r, fee_rate=0.06)[0].edge
    kal = scan.scan_ladder("g", r, fee_rate=0.07)[0].edge
    assert kal < pm


def test_the_module_cannot_place_an_order():
    """A property of the imports, not a promise."""
    src = pathlib.Path(scan.__file__).read_text(encoding="utf-8")
    for bad in ("import requests", "httpx", "PolymarketGateway", "place_order", "urllib"):
        assert bad not in src


def test_an_implausible_quoted_size_is_capped():
    """book_levels carries a 1% NFL tail to 10,729,773 contracts. Uncapped, ONE
    reading (+2.02c x 978,801 against a median size of 46) was 82% of the whole
    NFL in-play total, turning $5,454 into $24,040."""
    r = {0.0: (0.62, 0.63, 978_801, 978_801), 1.5: (0.48, 0.49, 978_801, 978_801)}
    v = scan.scan_ladder("g", r)
    assert v[0].size == scan.MAX_PLAUSIBLE_SIZE
    assert v[0].dollars < 0.15 * scan.MAX_PLAUSIBLE_SIZE


def test_the_cap_does_not_touch_a_plausible_book():
    """CFB is unaffected until the cap falls below 1,000 -- that is how we know
    the tail is NFL-specific rather than an artifact of capping."""
    r = {0.0: (0.62, 0.63, 900, 900), 1.5: (0.48, 0.49, 900, 900)}
    assert scan.scan_ladder("g", r)[0].size == 900


def test_the_fee_coefficient_is_the_venue_s_published_one():
    """0.0695, read off `feeCoefficient` on every market object the recorder
    stores: 214,790 rows across NFL, CFB, WNBA and MLB on 2026-09-21, all of
    them, and confirmed independently by two discovery agents the same day.
    The 0.06 that stood here since the ladder work began was never checked
    against that field. The gap is 16 % of the fee, about half a cent per
    pair at even prices, and every dollar measured before the change was
    overstated by it."""
    assert scan.DEFAULT_FEE_RATE == 0.0695
    assert scan.fee(0.5) == 0.0695 * 0.25
    # The sub-cent crossing the old constant reported is not one: sell 0.44
    # against buy 0.41 cleared by +0.07c at 0.06 and fails by -0.23c now.
    e_old = 0.44 - 0.41 - 0.06 * 0.41 * 0.59 - 0.06 * 0.44 * 0.56
    e_new = 0.44 - 0.41 - scan.fee(0.41) - scan.fee(0.44)
    assert e_old > 0 > e_new
