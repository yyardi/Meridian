"""The cross-venue pairing rules the founding-thesis statistics rest on.

Four behaviors pinned, each named by the pre-registration in
`core/kalshi/analysis.py`:

* **The 60s window** — snapshots further apart do not pair. Pinned by spec,
  not tunable.
* **Line identity** — a Kalshi strike pairs with an identical Polymarket line
  and nothing else; a half-point off is basis, not a match.
* **Orientation** — spread/winner contracts pair team-to-team, with the
  `-pos-` complement inverted into the same YES frame (V14/V15/V20: getting a
  frame backwards inverts a gap while leaving it plausible).
* **Clustering** — games are the sample unit: median-of-game-medians, and
  sign persistence over game-level medians with zero-gap games excluded from
  the denominator.

Fixtures use deliberately fake keys (year 2099) and delete only their own
rows, per this suite's convention.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import delete

from core.kalshi.analysis import (
    PAIR_TOLERANCE_SECONDS,
    Pair,
    build_pairs,
    kalshi_team_from_ticker,
    median_abs_gap,
    pm_spread_team_and_invert,
    sign_persistence,
)
from core.storage import (
    KalshiContract,
    KalshiGame,
    KalshiSnapshot,
    MarketSnapshot,
    get_engine,
    get_sessionmaker,
)

UTC = dt.timezone.utc
TIP = dt.datetime(2099, 1, 1, 23, 0, tzinfo=UTC)
T0 = TIP - dt.timedelta(hours=3)

GAME = "99JAN01PHXATL"
EVENT = "wnba-phx-atl-2099-01-01"

_Session = get_sessionmaker(get_engine())


def _kalshi_rows(s, ticker, market_type, strike, mid, at):
    """One contract row + one priced snapshot at `at` with the given mid."""
    half = Decimal("0.01")
    mid = Decimal(str(mid))
    s.add(KalshiContract(
        captured_at=at, ticker=ticker, event_ticker=f"KXE-{GAME}",
        series_ticker="KXWNBATOTAL", game_key=GAME, market_type=market_type,
        floor_strike=None if strike is None else Decimal(str(strike)),
    ))
    s.add(KalshiSnapshot(
        captured_at=at, ticker=ticker, event_ticker=f"KXE-{GAME}",
        series_ticker="KXWNBATOTAL", game_key=GAME, market_type=market_type,
        floor_strike=None if strike is None else Decimal(str(strike)),
        yes_bid=mid - half, yes_ask=mid + half,
    ))


def _pm_row(s, slug, mtype, line, mid, at):
    half = Decimal("0.01")
    mid = Decimal(str(mid))
    s.add(MarketSnapshot(
        captured_at=at, market_slug=slug, event_slug=EVENT,
        sports_market_type=mtype,
        line=None if line is None else Decimal(str(line)),
        best_bid=mid - half, best_ask=mid + half,
        is_live=False, game_start_time=TIP,
    ))


@pytest.fixture
def venue_game():
    def _wipe(s):
        s.execute(delete(KalshiSnapshot).where(KalshiSnapshot.game_key == GAME))
        s.execute(delete(KalshiContract).where(KalshiContract.game_key == GAME))
        s.execute(delete(KalshiGame).where(KalshiGame.game_key == GAME))
        s.execute(delete(MarketSnapshot).where(MarketSnapshot.event_slug == EVENT))
        s.commit()

    with _Session() as s:
        _wipe(s)
        s.add(KalshiGame(
            game_key=GAME, local_date=TIP, first_code="PHX", second_code="ATL",
            first_espn="PHX", second_espn="ATL",
            polymarket_event_slug=EVENT, game_start_time=TIP,
            first_seen_at=T0,
        ))
        s.commit()
        yield s
        _wipe(s)


# ------------------------------------------------------------------ #
# The 60-second window
# ------------------------------------------------------------------ #


def test_pair_tolerance_is_the_registered_60s():
    assert PAIR_TOLERANCE_SECONDS == 60.0, "pinned by the pre-registration"


def test_snapshots_beyond_60s_do_not_pair(venue_game):
    s = venue_game
    _kalshi_rows(s, f"KXWNBATOTAL-{GAME}-T165", "total", 165.5, 0.50, T0)
    _pm_row(s, "tsc-wnba-phx-atl-2099-01-01-165pt5",
            "basketball_team_full_game_total", 165.5, 0.50,
            T0 + dt.timedelta(seconds=61))
    s.commit()
    assert build_pairs(s) == []


def test_snapshots_within_60s_pair(venue_game):
    s = venue_game
    _kalshi_rows(s, f"KXWNBATOTAL-{GAME}-T165", "total", 165.5, 0.48, T0)
    _pm_row(s, "tsc-wnba-phx-atl-2099-01-01-165pt5",
            "basketball_team_full_game_total", 165.5, 0.52,
            T0 + dt.timedelta(seconds=59))
    s.commit()
    (p,) = build_pairs(s)
    assert p.market_type == "total"
    assert p.gap == pytest.approx(0.04)          # PM minus Kalshi, same frame


# ------------------------------------------------------------------ #
# Line identity
# ------------------------------------------------------------------ #


def test_half_point_off_is_basis_not_a_match(venue_game):
    s = venue_game
    _kalshi_rows(s, f"KXWNBATOTAL-{GAME}-T164", "total", 164.5, 0.50, T0)
    _pm_row(s, "tsc-wnba-phx-atl-2099-01-01-165pt5",
            "basketball_team_full_game_total", 165.5, 0.50, T0)
    s.commit()
    assert build_pairs(s) == [], "165.5 must not pair with 164.5"


def test_spread_line_must_match_and_team_orient(venue_game):
    """PM `-neg-10pt5` from PHX = 'PHX wins by more than 10.5' — pairs with
    the PHX Kalshi contract at strike 10.5 directly, not ATL's, and not 9.5."""
    s = venue_game
    _kalshi_rows(s, f"KXWNBASPREAD-{GAME}-PHX10", "spread", 10.5, 0.30, T0)
    _kalshi_rows(s, f"KXWNBASPREAD-{GAME}-ATL10", "spread", 10.5, 0.25, T0)
    _kalshi_rows(s, f"KXWNBASPREAD-{GAME}-PHX9", "spread", 9.5, 0.35, T0)
    _pm_row(s, "asc-wnba-phx-atl-2099-01-01-neg-10pt5",
            "basketball_team_full_game_spread", -10.5, 0.33, T0)
    s.commit()
    (p,) = build_pairs(s)
    # The Pair keeps PM's verbatim signed line; matching runs on |line|.
    assert p.team == "PHX" and abs(p.line) == pytest.approx(10.5)
    assert p.kalshi_mid == pytest.approx(0.30), "PHX contract, not ATL or 9.5"
    assert p.gap == pytest.approx(0.03)


# ------------------------------------------------------------------ #
# Orientation and frames
# ------------------------------------------------------------------ #


def test_pos_spread_pairs_with_opponent_and_inverts(venue_game):
    """PM `-pos-10pt5` from PHX = 'PHX +10.5' = complement of 'ATL wins by
    over 10.5'. It must pair against the ATL contract as 1 − kalshi_mid —
    the V15 failure mode is getting this backwards and calling it a gap."""
    s = venue_game
    _kalshi_rows(s, f"KXWNBASPREAD-{GAME}-ATL10", "spread", 10.5, 0.30, T0)
    _pm_row(s, "asc-wnba-phx-atl-2099-01-01-pos-10pt5",
            "basketball_team_full_game_spread", 10.5, 0.72, T0)
    s.commit()
    (p,) = build_pairs(s)
    assert p.team == "ATL"
    assert p.kalshi_mid == pytest.approx(0.70), "1 - 0.30: complement frame"
    assert p.gap == pytest.approx(0.02)


def test_winner_pairs_on_the_slugs_first_team(venue_game):
    """V20: PM winner YES = the slug's first team. The Kalshi ticker names its
    team in the suffix; only PHX's contract may pair."""
    s = venue_game
    _kalshi_rows(s, f"KXWNBAGAME-{GAME}-PHX", "winner", None, 0.60, T0)
    _kalshi_rows(s, f"KXWNBAGAME-{GAME}-ATL", "winner", None, 0.40, T0)
    _pm_row(s, "aec-wnba-phx-atl-2099-01-01",
            "basketball_team_full_game_winner", None, 0.63, T0)
    s.commit()
    (p,) = build_pairs(s)
    assert p.team == "PHX" and p.kalshi_mid == pytest.approx(0.60)


def test_ticker_suffix_resolves_through_the_code_map():
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG05DALWSH-DAL") == "DAL"
    assert kalshi_team_from_ticker("KXWNBASPREAD-26AUG06LVIND-IND10") == "IND"
    # The two codes that differ between venues (kalshi-venue-facts):
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG05CONNNY-CONN") == "CON"
    assert kalshi_team_from_ticker("KXWNBAGAME-26AUG05PDXSEA-PDX2") == "POR"


def test_pm_spread_resolution_table():
    assert pm_spread_team_and_invert("x-neg-10pt5", -10.5, "PHX", "ATL") == \
        ("PHX", 10.5, False)
    assert pm_spread_team_and_invert("x-pos-10pt5", 10.5, "PHX", "ATL") == \
        ("ATL", 10.5, True)
    assert pm_spread_team_and_invert("x-10pt5", 10.5, "PHX", "ATL") is None


def test_live_snapshots_never_pair(venue_game):
    s = venue_game
    _kalshi_rows(s, f"KXWNBATOTAL-{GAME}-T165", "total", 165.5, 0.50, T0)
    with _Session() as s2:
        s2.add(MarketSnapshot(
            captured_at=T0, market_slug="tsc-wnba-phx-atl-2099-01-01-165pt5",
            event_slug=EVENT, sports_market_type="basketball_team_full_game_total",
            line=Decimal("165.5"), best_bid=Decimal("0.49"),
            best_ask=Decimal("0.51"), is_live=True, game_start_time=TIP,
        ))
        s2.commit()
    s.commit()
    assert build_pairs(s) == [], "pregame only, per the spec"


# ------------------------------------------------------------------ #
# Clustering — games are the sample unit
# ------------------------------------------------------------------ #


def _pair(game, gap, i=0):
    return Pair(
        game_key=game, market_type="total", line=165.5, team=None,
        captured_pm=T0 + dt.timedelta(minutes=i),
        captured_kalshi=T0 + dt.timedelta(minutes=i),
        pm_mid=0.5 + gap, kalshi_mid=0.5, hours_to_tipoff=3.0,
    )


def test_median_abs_gap_is_median_of_game_medians():
    """A game with 100 correlated rows is one observation, not 100."""
    pairs = [_pair("g1", 0.10, i) for i in range(100)] + [_pair("g2", 0.02)]
    assert median_abs_gap(pairs) == pytest.approx(0.06), \
        "pooled median would say 0.10 — game-weighted says (0.10+0.02)/2"


def test_sign_persistence_excludes_zero_gap_games():
    pairs = ([_pair("g1", 0.03)] + [_pair("g2", 0.01)] + [_pair("g3", -0.02)]
             + [_pair("g4", 0.0)])
    fraction, signed, total = sign_persistence(pairs)
    assert total == 4 and signed == 3, "the zero-gap game carries no sign"
    assert fraction == pytest.approx(2 / 3)


def test_sign_persistence_all_one_sign():
    pairs = [_pair("g1", 0.03), _pair("g2", 0.01), _pair("g3", 0.005)]
    fraction, signed, total = sign_persistence(pairs)
    assert fraction == 1.0 and signed == 3 == total


def test_float_dust_is_not_a_sign():
    """Measured on the 2026-08-10 run: a game-median of +5.55e-17 — pure
    (bid+ask)/2 arithmetic residue on a 1-cent-tick market — must not count
    as a signed game. The smallest real gap is a half-tick, 0.005."""
    pairs = [_pair("g1", 5.551115123125783e-17), _pair("g2", -0.005)]
    fraction, signed, total = sign_persistence(pairs)
    assert total == 2 and signed == 1, "dust carries no sign"
    assert fraction == 1.0
