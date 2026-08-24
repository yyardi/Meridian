"""The pregame ML/spread backtest, and chiefly its SIGN.

The bug these pin
-----------------
`sportsbook_odds.spread` is the home HANDICAP — negative when home is favoured
(measured: mean −1.82 against a mean home margin of +1.55, corr −0.49 over
1,642 games). `prob_cover` is documented as `P(home margin > line)` — it wants
the number the margin must EXCEED. Those are negatives of each other.

The first draft passed the handicap straight through, so the model priced
`P(margin > −5)` — home losing by fewer than 5 — while settlement scored
`margin > +5`. The model bet the opposite side of the one it was graded on, in
every game. It did not look like a bug. It looked like a **result**: spread ROI
−7.27% with a game-clustered CI of [−14.3%, −0.26%] that excluded zero, which
would have been reported as "the executor trades a market that measurably
loses". Correcting the sign moved it to −3.95% [−11.1%, +3.5%], crossing zero.

A wrong sign is not a missing value (V19). It produces a confident answer of
the wrong shape, which is why the convention is asserted here directly rather
than being implied by an end-to-end number.
"""

from __future__ import annotations

import datetime as dt

import pytest
from types import SimpleNamespace

from core.backtest.moneyline import (
    CLV_UNAVAILABLE,
    MARKET_ML,
    MARKET_SPREAD,
    MarketBet,
    MarketSummary,
    _maybe_bet,
)
from strategies.wnba_totals.model.fair_value import prob_cover

UTC = dt.timezone.utc


class _Row:
    espn_game_id = "g1"
    game_date = dt.datetime(2026, 7, 1, tzinfo=UTC)
    season = 2026


# ------------------------------------------------------------------ #
# The sign
# ------------------------------------------------------------------ #


def test_prob_cover_wants_the_threshold_not_the_handicap():
    """Pins the asymmetry that caused the bug. Home favoured by 5 is
    `spread = -5`; the margin must exceed `+5`."""
    handicap = -5.0
    threshold = -handicap

    # A team projected to win by exactly the threshold is a coin flip to cover.
    assert prob_cover(threshold, threshold, 10.0) == pytest.approx(0.5)

    # Passing the handicap instead asks a different, much easier question.
    wrong = prob_cover(threshold, handicap, 10.0)
    assert wrong > 0.8, "handicap-as-threshold should look near-certain"
    assert wrong != pytest.approx(0.5)


def test_settlement_and_model_use_the_same_convention():
    """`margin + spread > 0` (settlement) and `prob_cover(margin, -spread)`
    (model) must agree about who covered."""
    for handicap, margin in [(-5.0, 9.0), (-5.0, 1.0), (3.5, 5.0), (3.5, -6.0)]:
        settled_home_covered = (margin + handicap) > 0
        # sigma tiny => the model is effectively certain, so its probability
        # collapses to the same boolean the settlement computes.
        p = prob_cover(margin, -handicap, 0.01)
        model_says_home = p > 0.5
        assert model_says_home == settled_home_covered, (
            f"handicap={handicap} margin={margin}: settlement said "
            f"{settled_home_covered}, model said {model_says_home}"
        )


# ------------------------------------------------------------------ #
# Bet selection
# ------------------------------------------------------------------ #


def test_no_bet_when_edge_is_below_threshold():
    assert _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                      p_model_home=0.52, p_book_home=0.50,
                      price_home=0.50, price_away=0.50,
                      home_won=True, min_edge=0.03) is None


def test_takes_the_away_side_when_that_is_where_the_edge_is():
    """Both sides are considered. Only ever taking home would halve the sample
    and bias the result toward whatever the home-field term does."""
    bet = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                     p_model_home=0.30, p_book_home=0.50,
                     price_home=0.50, price_away=0.50,
                     home_won=True, min_edge=0.03)
    assert bet is not None
    assert bet.side == "away"
    assert bet.won is False, "home won, so the away bet lost"
    assert bet.edge == pytest.approx(0.20)


def test_money_at_price_pnl():
    """Buy at 0.40, win -> +0.60. Buy at 0.40, lose -> -0.40 (C11)."""
    win = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                     p_model_home=0.60, p_book_home=0.40,
                     price_home=0.40, price_away=0.60,
                     home_won=True, min_edge=0.03)
    assert win.pnl == pytest.approx(0.60)
    lose = _maybe_bet(row=_Row(), market=MARKET_ML, line=None,
                      p_model_home=0.60, p_book_home=0.40,
                      price_home=0.40, price_away=0.60,
                      home_won=False, min_edge=0.03)
    assert lose.pnl == pytest.approx(-0.40)


# ------------------------------------------------------------------ #
# Reporting discipline
# ------------------------------------------------------------------ #


def _bet(game: str, price: float, won: bool) -> MarketBet:
    return MarketBet(
        espn_game_id=game, game_date=_Row.game_date, season=2026,
        market=MARKET_ML, side="home", line=None,
        model_probability=0.5, book_probability=0.5, entry_price=price,
        edge=0.05, won=won, pnl=(1 - price) if won else -price, fee=0.0,
    )


def test_hit_rate_is_reported_with_its_breakeven():
    """C11: a 40% hit rate on 0.40 entries is breakeven, not failure. The two
    numbers are meaningless apart, so `entry_cost` must always be present."""
    s = MarketSummary(market=MARKET_ML)
    s.bets = [_bet(f"g{i}", 0.40, i < 4) for i in range(10)]
    d = s.as_dict()
    assert d["hit_rate"] == pytest.approx(0.40)
    assert d["entry_cost_stake_weighted"] == pytest.approx(0.40)
    assert d["roi"] == pytest.approx(0.0, abs=1e-9)


def test_clv_is_absent_with_a_stated_reason_never_a_number():
    """No open->close pair exists for these markets. A fabricated CLV would sit
    in the same column as the totals engine's real one."""
    s = MarketSummary(market=MARKET_SPREAD)
    s.bets = [_bet("g1", 0.5, True)]
    d = s.as_dict()
    assert d["mean_clv"] is None
    assert "fabricat" in d["clv_unavailable_because"].lower()
    assert d["clv_unavailable_because"] == CLV_UNAVAILABLE


def test_roi_ci_is_clustered_by_game_not_by_bet():
    """One game contributing many bets must not count as many clusters — the
    moneyline and the spread on one game are the same disagreement twice."""
    s = MarketSummary(market=MARKET_ML)
    s.bets = [_bet("same-game", 0.5, True) for _ in range(50)]
    assert s.n == 50 and s.games == 1
    assert s.roi_interval() is None, "one cluster cannot support an interval"


# ------------------------------------------------------------------ #
# You cannot transact at the de-vigged price
# ------------------------------------------------------------------ #


def test_entry_price_is_what_you_pay_not_the_books_fair_value():
    """The de-vigged price is the book's BELIEF; the raw price is its OFFER.

    Buying at the de-vigged price measures whether the model out-forecasts the
    book, which is a real question — but it is not a return, because no such
    price is available to trade. WNBA moneyline overround runs ~4.3%, roughly
    2 probability points on one side, which is larger than the entire edge this
    backtest was reporting. Charging it is the difference between 'the model
    disagrees usefully' and 'this makes money'.
    """
    from core.backtest.moneyline import _maybe_bet, MARKET_ML

    row = SimpleNamespace(
        espn_game_id="401", game_date=dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc),
        season=2025,
    )
    # Book believes home wins 40% but charges 42% for the ticket.
    bet = _maybe_bet(
        row=row, market=MARKET_ML, line=None,
        p_model_home=0.50, p_book_home=0.40,
        price_home=0.42, price_away=0.62,
        home_won=True, min_edge=0.03,
    )
    assert bet is not None
    assert bet.book_probability == pytest.approx(0.40)
    assert bet.entry_price == pytest.approx(0.42), "must cost the offer, not the belief"
    # Edge is measured against belief; cost is charged at the offer.
    assert bet.edge == pytest.approx(0.10)


def test_charging_vig_lowers_roi_on_the_same_selection():
    """Same bets, honest price: ROI must fall by roughly the vig.

    Pins the direction so a future refactor cannot quietly restore free
    entry — the failure mode that made the moneyline look profitable.
    """
    from core.backtest.moneyline import MarketBet, MarketSummary, MARKET_ML
    from core.backtest.fills import pnl_for_contract

    def summary(price: float) -> MarketSummary:
        s = MarketSummary(market=MARKET_ML)
        for i in range(100):
            won = i < 41                       # 41% hit rate
            s.bets.append(MarketBet(
                espn_game_id=str(i), game_date=dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc),
                season=2025, market=MARKET_ML, side="home", line=None,
                model_probability=0.45, book_probability=0.40,
                entry_price=price, edge=0.05, won=won,
                pnl=pnl_for_contract(price, won), fee=0.0,
            ))
        return s

    fair = summary(0.4047).roi        # what the old frame reported
    honest = summary(0.4220).roi      # +2.1 pts of vig, the real offer
    assert fair > 0, "de-vigged entry makes a 41% hit rate look profitable"
    assert honest < 0, "at the price actually offered, the same bets lose"


def test_helper_returns_the_offer_alongside_the_belief():
    """The regression, pinned where it actually lived: the price SOURCE.

    `_maybe_bet` always took price and belief as separate arguments, so a unit
    test of it passes whether or not the wiring is correct — which is why the
    original defect survived review. The helper returned only the de-vigged
    probability, so the call site had nothing else to pass and priced every
    moneyline entry at the book's fair value, silently deleting the ~4.3%
    overround. Assert the offer comes back, and that it costs more than belief.
    """
    import datetime as _dt
    from sqlalchemy import delete as _delete
    from core.storage import SportsbookOdds, get_sessionmaker
    from core.backtest.moneyline import _ml_and_spread_for_game

    gid = "vig-test-1"
    day = _dt.datetime(2025, 6, 1, tzinfo=_dt.timezone.utc)
    Session = get_sessionmaker()
    with Session() as s:
        s.add(SportsbookOdds(
            espn_game_id=gid, game_date=day, provider_name="TestBook",
            captured_at=day, home_moneyline=-150, away_moneyline=130, spread=-3.5,
        ))
        s.commit()
        try:
            p_home, raw_home, raw_away, line, _price = _ml_and_spread_for_game(s, gid)
        finally:
            s.execute(_delete(SportsbookOdds).where(SportsbookOdds.espn_game_id == gid))
            s.commit()

    assert p_home is not None and raw_home is not None and raw_away is not None
    # -150/+130 => raw 0.600 / 0.4348, overround 1.0348.
    assert raw_home == pytest.approx(0.600, abs=1e-3)
    assert raw_away == pytest.approx(0.4348, abs=1e-3)
    assert raw_home + raw_away > 1.0, "raw prices must still carry the vig"
    assert p_home == pytest.approx(0.5798, abs=1e-3), "belief is de-vigged"
    # The thing that was lost: the offer costs more than the belief.
    assert raw_home > p_home
    assert line == pytest.approx(-3.5)


def test_run_backtest_charges_the_offer_end_to_end():
    """The wiring guard. The helper test above proves the offer is AVAILABLE;
    this proves run_backtest actually SPENDS it.

    Both are needed: reverting the call site to `price_home=p_home_book` leaves
    the helper test green, because the helper still returns the right numbers —
    nobody was obliged to use them. That gap is how the defect shipped.
    """
    import datetime as _dt
    from sqlalchemy import delete as _delete
    from core.storage import (
        SportsbookOdds, TeamGameLog, get_engine, get_sessionmaker,
    )
    from core.backtest.moneyline import run_backtest, MoneylineConfig, MARKET_ML

    season = 1997                      # fictional, cannot collide
    Session = get_sessionmaker(get_engine())
    with Session() as s:
        s.execute(_delete(SportsbookOdds).where(SportsbookOdds.espn_game_id.like("mlvig-%")))
        s.execute(_delete(TeamGameLog).where(TeamGameLog.season == season))
        s.commit()
        for i in range(40):
            gid = f"mlvig-{i}"
            day = _dt.datetime(season, 6, 1, tzinfo=dt.timezone.utc) + _dt.timedelta(days=i)
            # Home team genuinely stronger, so the model forms an opinion.
            for team, opp, home, scored, allowed in (
                ("MV_H", "MV_A", True, 92, 78),
                ("MV_A", "MV_H", False, 78, 92),
            ):
                s.add(TeamGameLog(
                    game_date=day, season=season, espn_game_id=gid,
                    team_id=team, team_abbrev=team, opponent_id=opp,
                    opponent_abbrev=opp, is_home=home, points_scored=scored,
                    points_allowed=allowed, is_completed=True, season_type=2,
                ))
            s.add(SportsbookOdds(
                espn_game_id=gid, game_date=day, provider_name="TestBook",
                captured_at=day, over_under=170.0, home_moneyline=-150,
                away_moneyline=130, spread=-3.5,
            ))
        s.commit()
        try:
            result = run_backtest(
                session=s,
                config=MoneylineConfig(start_season=season, end_season=season,
                                       min_edge=0.0),
            )
            bets = result.summaries[MARKET_ML].bets
        finally:
            s.execute(_delete(SportsbookOdds).where(SportsbookOdds.espn_game_id.like("mlvig-%")))
            s.execute(_delete(TeamGameLog).where(TeamGameLog.season == season))
            s.commit()

    assert bets, "fixture produced no moneyline bets — the guard would be vacuous"
    free = [b for b in bets if b.entry_price <= b.book_probability]
    assert not free, (
        f"{len(free)}/{len(bets)} entries priced at or below the de-vigged "
        "belief — run_backtest is spending the belief, not the offer"
    )
