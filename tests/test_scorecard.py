"""ANCHOR scorecard tests.

The scorecard exists because three earlier ways of counting were wrong, and
each wrong way flattered us. These pin the corrections.
"""

from __future__ import annotations

import pytest

from core.scorecard import BREAKEVEN, MIN_GAMES, Settled, format_report, score


def _row(game: str, market: str, model: float, mkt: float, outcome: int) -> Settled:
    return Settled(event_slug=game, market_slug=market, market_type="total",
                   model=model, market=mkt, outcome=outcome)


def test_a_bet_exists_only_where_the_model_disagrees():
    assert _row("g", "m", 0.60, 0.50, 1).is_bet
    assert not _row("g", "m", 0.505, 0.50, 1).is_bet     # inside tolerance


def test_the_side_is_which_way_it_disagreed():
    assert _row("g", "m", 0.60, 0.50, 1).bet_side == "YES"
    assert _row("g", "m", 0.40, 0.50, 1).bet_side == "NO"


def test_a_correct_looking_row_can_be_a_losing_bet():
    """The 84%-hit-rate trap: model 0.78, market 0.86, settles YES.
    Probability was on the right side of 0.50, but the bet was a SELL and
    it lost."""
    r = _row("g", "m", 0.78, 0.86, 1)
    assert r.model > 0.5 and r.outcome == 1      # "correct" by the old measure
    assert r.bet_side == "NO"
    assert r.bet_won is False


def test_sample_size_is_games_not_rows():
    rows = [_row("g1", f"m{i}", 0.6, 0.5, 1) for i in range(18)]
    s = score(rows)
    assert s["n_markets"] == 18
    assert s["n_games"] == 1


def test_one_game_cannot_produce_an_interval():
    rows = [_row("g1", f"m{i}", 0.6, 0.5, i % 2) for i in range(18)]
    assert score(rows)["win"] is None


def test_a_missing_interval_is_stated_not_omitted():
    """Silence reads as 'fine'. This project lost 2.5 hours to that."""
    rows = [_row("g1", f"m{i}", 0.6, 0.5, i % 2) for i in range(18)]
    text = format_report(rows, label="v4")
    assert "BET WIN RATE" in text
    assert "NO INTERVAL" in text


def test_two_games_do_produce_an_interval():
    rows = [_row(f"g{g}", f"m{g}{i}", 0.6, 0.5, 1) for g in range(2) for i in range(5)]
    assert score(rows)["win"] is not None


def test_brier_edge_is_positive_when_the_model_is_closer():
    rows = [_row(f"g{g}", f"m{g}", 0.9, 0.6, 1) for g in range(4)]
    s = score(rows)
    assert s["brier_model"] < s["brier_market"]
    assert s["brier_edge"].mean > 0


def test_brier_edge_is_negative_when_the_market_is_closer():
    rows = [_row(f"g{g}", f"m{g}", 0.6, 0.9, 1) for g in range(4)]
    s = score(rows)
    assert s["brier_edge"].mean < 0


def test_a_thin_sample_refuses_a_verdict():
    rows = [_row(f"g{g}", f"m{g}", 0.9, 0.5, 1) for g in range(3)]
    text = format_report(rows, label="v4")
    assert "NO VERDICT" in text
    assert str(MIN_GAMES) in text


def test_passing_needs_both_breakeven_and_out_forecasting():
    """A model can clear breakeven on luck. Beating the market's Brier is the
    claim that has to be true."""
    rows = [_row(f"g{g}", f"m{g}{i}", 0.95, 0.55, 1)
            for g in range(MIN_GAMES) for i in range(4)]
    text = format_report(rows, label="v4")
    assert "PASS" in text


def test_a_losing_model_is_reported_as_failing():
    rows = [_row(f"g{g}", f"m{g}{i}", 0.9, 0.5, 0)
            for g in range(MIN_GAMES) for i in range(4)]
    text = format_report(rows, label="v4")
    assert "FAIL" in text


def test_nothing_settled_reports_no_data():
    assert "NO DATA" in format_report([], label="v4")


def test_breakeven_matches_the_two_way_market():
    assert BREAKEVEN == pytest.approx(0.524, abs=0.001)


# ------------------------------------------------------------------ #
# Money at price (C11 frame) with a measured fill concession (C13)
# ------------------------------------------------------------------ #

from core.scorecard import money_score  # noqa: E402


def _priced(game, market, model, mkt, outcome, bid, ask):
    return Settled(event_slug=game, market_slug=market, market_type="total",
                   model=model, market=mkt, outcome=outcome, bid=bid, ask=ask)


def test_money_yes_bet_is_costed_at_the_maker_bid():
    """YES rests at the bid (maker-only is load-bearing). Win pays 1."""
    rows = [_priced("g1", "m1", 0.60, 0.50, 1, bid=0.48, ask=0.52)]
    s = money_score(rows)
    assert s["staked"] == pytest.approx(0.48)
    assert s["returned"] == 1.0
    assert s["roi_pooled"] == pytest.approx(1 / 0.48 - 1)


def test_money_no_bet_costs_one_minus_ask():
    """NO rests at the YES ask and costs 1 − ask (V14). NO wins when
    outcome = 0."""
    rows = [_priced("g1", "m1", 0.40, 0.50, 0, bid=0.48, ask=0.52)]
    s = money_score(rows)
    assert s["staked"] == pytest.approx(0.48)  # 1 - 0.52
    assert s["returned"] == 1.0


def test_concession_worsens_the_price_never_the_selection():
    """C13's rule: every arm scores the identical bet set; only cost moves."""
    rows = [
        _priced("g1", "m1", 0.60, 0.50, 1, bid=0.48, ask=0.52),
        _priced("g2", "m2", 0.40, 0.50, 1, bid=0.48, ask=0.52),  # NO, loses
    ]
    base = money_score(rows)
    dear = money_score(rows, concession=0.0211)
    assert base["n_bets"] == dear["n_bets"] == 2
    assert dear["staked"] == pytest.approx(base["staked"] + 2 * 0.0211)
    assert dear["returned"] == base["returned"]
    assert dear["roi_pooled"] < base["roi_pooled"]


def test_money_clusters_by_game_not_row():
    """One game's 3 correlated wins are one cluster; ROI interval uses games."""
    rows = ([_priced("g1", f"m{i}", 0.60, 0.50, 1, bid=0.50, ask=0.52)
             for i in range(3)]
            + [_priced("g2", "mx", 0.60, 0.50, 0, bid=0.50, ask=0.52)])
    s = money_score(rows)
    assert s["n_games"] == 2
    assert s["roi_clustered"]["games"] == 2


def test_taker_frame_uses_the_crossing_price():
    rows = [_priced("g1", "m1", 0.60, 0.50, 1, bid=0.48, ask=0.52)]
    assert money_score(rows, taker=True)["staked"] == pytest.approx(0.52)


def test_rows_without_a_touch_are_skipped_and_counted():
    rows = [Settled(event_slug="g", market_slug="m", market_type="total",
                    model=0.60, market=0.50, outcome=1)]
    s = money_score(rows)
    assert s["n_bets"] == 0 and s["skipped_no_touch"] == 1
