"""Pins for the registered cross-venue in-play football read.

    pytest --noconftest tests/test_cross_venue_inplay_football.py

What is pinned, and why each is a separate test:
* team matching -- the two code spaces meet only through ESPN, and the two codes that
  differ (Kalshi WAS / JAC, Polymarket was / jax) are the ones a `.upper()` would lose;
* orientation -- the sign of every number in the read. Pinned THREE ways: the pure
  function, a settlement table over every final margin from -40 to +40 against both
  venues' stated YES rules, and a CONTROL on recorded tape rows that must fail if the
  orientation were flipped (and a companion that proves the rows can tell);
* the fee arithmetic -- Kalshi rounds UP to the cent per contract, checked at every cent
  price against integer arithmetic; Polymarket is unrounded as registered;
* the Kalshi ghost level -- a displayed side under the venue's 0.01 resolution is a float
  residue of the recorder's book, not an order, and must never reach the gap.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load():
    p = ROOT / "analysis" / "cross_venue" / "inplay_football_read.py"
    spec = importlib.util.spec_from_file_location("xv_inplay_football_read", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


R = _load()
GAME = "nfl-det-car-2026-10-04"


# ----------------------------------------------------------------------------- team matching
def test_both_venues_nfl_tables_reach_the_same_32_espn_codes():
    from core.kalshi.mapping import KALSHI_TO_ESPN_NFL
    assert len(R.POLYMARKET_NFL_TO_ESPN) == 32 and len(KALSHI_TO_ESPN_NFL) == 32
    assert set(R.POLYMARKET_NFL_TO_ESPN.values()) == set(KALSHI_TO_ESPN_NFL.values())


def test_the_codes_that_differ_meet_at_espn():
    from core.kalshi.mapping import KALSHI_TO_ESPN_NFL
    assert KALSHI_TO_ESPN_NFL["WAS"] == R.POLYMARKET_NFL_TO_ESPN["was"] == "WSH"
    assert KALSHI_TO_ESPN_NFL["JAC"] == R.POLYMARKET_NFL_TO_ESPN["jax"] == "JAX"
    # the shared-prefix pairs stay distinct (Kalshi's sub-title shows both as 'LA' / 'NY')
    assert len({R.POLYMARKET_NFL_TO_ESPN[c] for c in ("lac", "lar", "nyg", "nyj")}) == 4


def test_a_kalshi_spread_must_agree_with_its_own_sub_title():
    ok = R.parse_kalshi_market({"ticker": "KXNFLSPREAD-26OCT04DETCAR-DET11", "series": "KXNFLSPREAD",
                                "yes_sub_title": "DET Lions wins by over 10.5 points"})
    assert (ok.kind, ok.team_code, ok.line, ok.game_key) == ("spread", "DET", 10.5, "26OCT04DETCAR")
    assert R.parse_kalshi_market({"ticker": "KXNFLSPREAD-26OCT04DETCAR-DET11", "series": "KXNFLSPREAD",
                                  "yes_sub_title": "DET Lions wins by over 9.5 points"}) is None
    la = R.parse_kalshi_market({"ticker": "KXNFLSPREAD-26OCT04LACSEA-LAC4", "series": "KXNFLSPREAD",
                                "yes_sub_title": "LA Chargers wins by over 3.5 points"})
    assert (la.team_code, la.line) == ("LAC", 3.5)
    assert R.parse_kalshi_market({"ticker": "KXNFLSPREAD-26OCT04LACSEA-LAC4", "series": "KXNFLSPREAD",
                                  "yes_sub_title": "NY Giants wins by over 3.5 points"}) is None
    w = R.parse_kalshi_market({"ticker": "KXNFLGAME-26OCT04DETCAR-CAR", "series": "KXNFLGAME",
                               "yes_sub_title": "Carolina"})
    assert (w.kind, w.team_code, w.line) == ("winner", "CAR", 0.0)


def _markets():
    return [
        {"ticker": "KXNFLGAME-26OCT04DETCAR-DET", "series": "KXNFLGAME", "yes_sub_title": "Detroit"},
        {"ticker": "KXNFLGAME-26OCT04DETCAR-CAR", "series": "KXNFLGAME", "yes_sub_title": "Carolina"},
        {"ticker": "KXNFLSPREAD-26OCT04DETCAR-DET11", "series": "KXNFLSPREAD",
         "yes_sub_title": "DET Lions wins by over 10.5 points"},
        {"ticker": "KXNFLSPREAD-26OCT04DETCAR-CAR4", "series": "KXNFLSPREAD",
         "yes_sub_title": "CAR Panthers wins by over 3.5 points"},
    ]


def test_match_contracts_pairs_each_kalshi_market_with_the_same_outcome():
    espn = {"401872978": {"away": "DET", "home": "CAR", "date": "2026-10-05"}}
    pairs, log = R.match_contracts("nfl", _markets(), [GAME], espn)
    got = {(p.kalshi_ticker, p.poly_slug, p.sign) for p in pairs}
    assert got == {
        ("KXNFLGAME-26OCT04DETCAR-DET", f"aec-{GAME}", +1),
        ("KXNFLGAME-26OCT04DETCAR-CAR", f"aec-{GAME}", -1),
        ("KXNFLSPREAD-26OCT04DETCAR-DET11", f"asc-{GAME}-neg-10pt5", +1),
        ("KXNFLSPREAD-26OCT04DETCAR-CAR4", f"asc-{GAME}-pos-3pt5", -1),
    }
    assert log["matched_games"] == 1


def test_a_game_whose_slug_order_disagrees_with_espn_is_dropped_not_flipped():
    espn = {"401872978": {"away": "CAR", "home": "DET", "date": "2026-10-05"}}
    pairs, log = R.match_contracts("nfl", _markets(), [GAME], espn)
    assert pairs == [] and log["poly_first_is_not_espn_away"] == 4


def test_a_kalshi_team_in_neither_slug_slot_is_dropped():
    espn = {"x": {"away": "DET", "home": "CAR", "date": "2026-10-05"}}
    m = [{"ticker": "KXNFLGAME-26OCT04DETCAR-SEA", "series": "KXNFLGAME", "yes_sub_title": "Seattle"}]
    pairs, log = R.match_contracts("nfl", m, [GAME], espn)
    assert pairs == [] and log["orientation_not_established"] == 1


def test_cfb_is_never_paired_without_an_espn_identity_on_both_sides():
    m = [{"ticker": "KXNCAAFGAME-26OCT03STANWAKE-STAN", "series": "KXNCAAFGAME", "yes_sub_title": "Stanford"}]
    pairs, log = R.match_contracts("cfb", m, ["cfb-stan-wake-2026-10-03"], {})
    assert pairs == [] and log["kalshi_code_has_no_espn_identity"] == 1


# ----------------------------------------------------------------------------- orientation
def test_orient_is_plus_for_the_slug_first_team_and_minus_for_the_second():
    assert R.orient("DET", "DET", "CAR") == +1
    assert R.orient("CAR", "DET", "CAR") == -1
    assert R.orient("SEA", "DET", "CAR") is None
    assert R.orient("DET", "DET", "DET") is None


def test_slug_for_names_the_rung_carrying_the_outcome():
    assert R.poly_slug_for(GAME, "winner", 0.0, -1) == f"aec-{GAME}"
    assert R.poly_slug_for(GAME, "spread", 10.5, +1) == f"asc-{GAME}-neg-10pt5"
    assert R.poly_slug_for(GAME, "spread", 10.5, -1) == f"asc-{GAME}-pos-10pt5"
    with pytest.raises(ValueError):
        R.poly_slug_for(GAME, "spread", 10.0, +1)


@pytest.mark.parametrize("sign", [+1, -1])
@pytest.mark.parametrize("kind,line", [("winner", 0.0)] + [("spread", n + 0.5) for n in range(31)])
def test_kalshi_yes_settles_with_the_paired_polymarket_side_on_every_margin(kind, line, sign):
    """Against both venues' stated YES rules, through the production slug and the production
    slug grammar (core.ladder.live.game_and_line): Kalshi YES pays exactly when the paired
    Polymarket side (YES for sign +1, NO for sign -1) pays."""
    from core.ladder.live import game_and_line
    slug = R.poly_slug_for(GAME, kind, line, sign)
    _, poly_line = game_and_line(slug)
    for first_margin in range(-40, 41):
        if kind == "winner" and first_margin == 0:
            continue                        # a tie settles under rules this read does not use
        team_margin = first_margin if sign > 0 else -first_margin
        k = R.settles_yes_kalshi(kind, team_margin, line)
        p = R.settles_yes_poly(first_margin, poly_line)
        assert k == (p if sign > 0 else not p), (kind, line, sign, first_margin)


# Recorded rows, VERBATIM from the 2026-10-04 tapes (MIA at MIN, in play; Polymarket
# reads/stream/nfl-10041955, Kalshi reads/kalshi/nfl-1004), one pair per (kind, sign): at each,
# the venues' receive stamps are < 0.1 s apart and the price sits > 25c from even. Kalshi `-MIN`
# pays if Minnesota (the HOME team, the slug's SECOND) wins; the Polymarket winner's YES is Miami.
# Production orientation must put the two venues within 3c on the Kalshi outcome; a flipped
# orientation puts them > 30c apart.
FIXTURES = [
    ('KXNFLGAME-26OCT04MIAMIN-MIN', 'Minnesota',
     '{"recv":"2026-10-04T20:46:42.344+00:00","slug":"aec-nfl-mia-min-2026-10-04","line":0.0,"bid":0.1875,"ask":0.19,"bid_size":4192.59,"ask_size":1369.68,"tt":"2026-10-04T20:46:42.315344486Z","state":"MARKET_STATE_OPEN"}',
     '{"recv":"2026-10-04T20:46:42.334Z","type":"touch","yes_bid":0.81,"yes_bid_size":38098.14,"no_bid":0.18,"no_bid_size":150028.71,"changes":4}'),
    ('KXNFLGAME-26OCT04MIAMIN-MIA', 'Miami',
     '{"recv":"2026-10-04T20:49:27.357+00:00","slug":"aec-nfl-mia-min-2026-10-04","line":0.0,"bid":0.24,"ask":0.25,"bid_size":150.0,"ask_size":117.93,"tt":"2026-10-04T20:49:27.328606793Z","state":"MARKET_STATE_OPEN"}',
     '{"recv":"2026-10-04T20:49:27.345Z","type":"touch","yes_bid":0.24,"yes_bid_size":262.18,"no_bid":0.75,"no_bid_size":26.72,"changes":1}'),
    ('KXNFLSPREAD-26OCT04MIAMIN-MIN4', 'MIN Vikings wins by over 3.5 points',
     '{"recv":"2026-10-04T22:01:04.350+00:00","slug":"asc-nfl-mia-min-2026-10-04-pos-3pt5","line":3.5,"bid":0.15,"ask":0.155,"bid_size":0.44,"ask_size":22.0,"tt":"2026-10-04T22:01:04.312203020Z","state":"MARKET_STATE_OPEN"}',
     '{"recv":"2026-10-04T22:01:04.311Z","type":"touch","yes_bid":0.84,"yes_bid_size":71.97,"no_bid":0.12,"no_bid_size":69.0,"changes":2}'),
    ('KXNFLSPREAD-26OCT04MIAMIN-MIA2', 'MIA Dolphins wins by over 1.5 points',
     '{"recv":"2026-10-04T21:28:30.163+00:00","slug":"asc-nfl-mia-min-2026-10-04-neg-1pt5","line":-1.5,"bid":0.07,"ask":0.085,"bid_size":50.0,"ask_size":1513.99,"tt":"2026-10-04T21:28:30.064452104Z","state":"MARKET_STATE_OPEN"}',
     '{"recv":"2026-10-04T21:28:30.196Z","type":"touch","yes_bid":0.06,"yes_bid_size":1088.38,"no_bid":0.91,"no_bid_size":263.42,"changes":1}'),
]
MIA_MIN = "nfl-mia-min-2026-10-04"
MIA_MIN_ESPN = {"401872974": {"away": "MIA", "home": "MIN", "date": "2026-10-04"}}


def _oriented_mids(ticker: str, sub: str, poly_line: str, kalshi_line: str, flip: bool) -> tuple[float, float]:
    import json
    series = ticker.split("-", 1)[0]
    pairs, _ = R.match_contracts("nfl", [{"ticker": ticker, "series": series, "yes_sub_title": sub}],
                                 [MIA_MIN], MIA_MIN_ESPN)
    (pair,) = pairs
    p, k = json.loads(poly_line), json.loads(kalshi_line)
    assert p["slug"] == pair.poly_slug                     # the fixture row IS the paired market
    sign = -pair.sign if flip else pair.sign
    pr = {"t": np.array([0.0]), "bid": np.array([p["bid"]]), "ask": np.array([p["ask"]]),
          "bid_size": np.array([p["bid_size"]]), "ask_size": np.array([p["ask_size"]]),
          "open": np.array([True]), "tt": np.array([0.0])}
    kr = {"t": np.array([0.0]), "yb": np.array([k["yes_bid"]]), "ys": np.array([k["yes_bid_size"]]),
          "nb": np.array([k["no_bid"]]), "ns": np.array([k["no_bid_size"]])}
    pf, kf = R.poly_frame(pr, sign), R.kalshi_frame(kr)
    assert pf["valid"][0] and kf["valid"][0]
    return float((pf["bid"][0] + pf["ask"][0]) / 2), float((kf["bid"][0] + kf["ask"][0]) / 2)


@pytest.mark.parametrize("ticker,sub,poly_line,kalshi_line", FIXTURES)
def test_CONTROL_recorded_rows_agree_only_under_the_production_orientation(ticker, sub, poly_line, kalshi_line):
    """THE CONTROL. Fails if orientation is flipped anywhere between the tables and the frame
    (verified 2026-10-07 by inverting `orient`'s return: all four cases fail)."""
    p_mid, k_mid = _oriented_mids(ticker, sub, poly_line, kalshi_line, flip=False)
    assert abs(p_mid - k_mid) < 0.03, (p_mid, k_mid)


@pytest.mark.parametrize("ticker,sub,poly_line,kalshi_line", FIXTURES)
def test_the_control_rows_can_tell_the_two_orientations_apart(ticker, sub, poly_line, kalshi_line):
    """A control on a 50-50 price passes either way; these rows sit far from 0.5, so the
    flipped orientation puts the venues > 30c apart and the control above would fail."""
    p_mid, k_mid = _oriented_mids(ticker, sub, poly_line, kalshi_line, flip=True)
    assert abs(p_mid - k_mid) > 0.30, (p_mid, k_mid)


def test_the_control_covers_both_signs_and_both_kinds():
    seen = set()
    for ticker, sub, *_ in FIXTURES:
        series = ticker.split("-", 1)[0]
        (pair,), _ = R.match_contracts("nfl", [{"ticker": ticker, "series": series, "yes_sub_title": sub}],
                                       [MIA_MIN], MIA_MIN_ESPN)
        seen.add((pair.kind, pair.sign))
    assert seen == {("winner", 1), ("winner", -1), ("spread", 1), ("spread", -1)}


# ----------------------------------------------------------------------------- fees
def test_kalshi_fee_rounds_up_to_the_cent_at_every_cent_price():
    for c in range(101):
        exact_cents = -(-7 * c * (100 - c) // 10000)          # ceil(0.07 p (1-p) * 100), integers only
        assert R.kalshi_fee(c / 100) == pytest.approx(exact_cents / 100, abs=1e-12), c
    assert R.kalshi_fee(0.5) == 0.02 and R.kalshi_fee(0.10) == 0.01 and R.kalshi_fee(0.01) == 0.01
    assert list(R.kalshi_fee(np.array([0.5, 0.1]))) == [0.02, 0.01]


def test_polymarket_fee_is_the_period_coefficient_unrounded():
    assert R.poly_fee(0.5) == pytest.approx(0.0695 * 0.25, abs=1e-15)
    assert R.poly_fee(0.62) == pytest.approx(0.0695 * 0.62 * 0.38, abs=1e-15)


def test_net_gap_by_hand():
    """Kalshi bid 0.66 x 500, Polymarket ask 0.62 x 40: buy on Polymarket, sell on Kalshi.
    0.66 - 0.62 - 0.0695*0.62*0.38 - ceil(0.07*0.66*0.34 = 1.5708c) = 0.04 - 0.016374 - 0.02."""
    net, d, size = R.net_gap(np.array([0.66]), np.array([500.0]), np.array([0.70]), np.array([900.0]),
                             np.array([0.58]), np.array([70.0]), np.array([0.62]), np.array([40.0]))
    assert d[0] == 1 and size[0] == 40.0
    assert net[0] == pytest.approx(0.04 - 0.0695 * 0.62 * 0.38 - 0.02, abs=1e-12)
    # the mirror: buy on Kalshi at 0.60, sell on Polymarket at 0.66
    net, d, size = R.net_gap(np.array([0.55]), np.array([5.0]), np.array([0.60]), np.array([7.0]),
                             np.array([0.66]), np.array([3.0]), np.array([0.67]), np.array([9.0]))
    assert d[0] == 2 and size[0] == 3.0
    assert net[0] == pytest.approx(0.06 - 0.02 - 0.0695 * 0.66 * 0.34, abs=1e-12)


# ----------------------------------------------------------------------------- the Kalshi ghost level
def test_a_kalshi_side_under_the_venue_resolution_or_a_crossed_touch_is_invalid():
    k = {"t": np.arange(4.0), "yb": np.array([0.65, 0.40, 0.40, np.nan]), "ys": np.array([0.0, 12.0, 12.0, np.nan]),
         "nb": np.array([0.81, 0.58, 0.61, 0.5]), "ns": np.array([4e5, 9.0, 9.0, 1.0])}
    f = R.kalshi_frame(k)
    assert list(f["valid"]) == [False, True, False, False]
    assert list(f["ghost"]) == [True, False, False, False]
    assert list(f["crossed"]) == [True, False, True, False]       # 0.65 + 0.81 > 1 ; 0.40 + 0.61 > 1
    assert f["ask"][1] == pytest.approx(0.42)


# ----------------------------------------------------------------------------- episodes and concentration
def test_episode_life_runs_to_the_first_instant_that_breaks_it():
    ins = {"t": np.array([0.0, 1.0, 2.5, 4.0, 9.0]), "qual": np.array([True, True, False, True, True]),
           "dir": np.array([1, 1, 1, 1, 2]), "dollars": np.array([1.0, 3.0, 0.0, 2.0, 5.0]),
           "net_c": np.array([1.2, 1.5, 0.0, 1.1, 2.0])}
    eps = R.episodes_from(ins)
    assert [(e["start"], e["life"], e["first_dollars"], e["peak_dollars"], e["censored"]) for e in eps] == [
        (0.0, 2.5, 1.0, 3.0, False), (4.0, 5.0, 2.0, 2.0, False), (9.0, 0.0, 5.0, 5.0, True)]


def test_games_for_share_counts_from_the_largest():
    assert R.games_for_share({"a": 80.0, "b": 10.0, "c": 10.0}) == 1
    assert R.games_for_share({"a": 50.0, "b": 30.0, "c": 20.0}) == 2
    assert R.games_for_share({}) == 0
