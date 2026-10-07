"""Coin Race questions 2 (basket) and 3 (farming fill cost): the arithmetic the screens rest on.

Pure functions only; no database, no network."""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1] / "analysis" / "coinrace"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"coinrace_{name}", _ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bs = _load("basket_screen")
ff = _load("farm_fill_screen")


# ---------------------------------------------------------------- fees
@pytest.mark.parametrize("p,c,cents", [(50, 1, 2), (1, 1, 1), (99, 1, 1), (50, 100, 175), (1, 100, 7), (21, 1, 2), (10, 200, 126)])
def test_fee_is_quadratic_rounded_up_to_the_cent(p, c, cents):
    # 0.07 * c * p * (1 - p) dollars, rounded UP to the cent: 50c x 1 = 1.75c -> 2c; 1c x 100 = 6.93c -> 7c
    assert bs.fee_cents(p, c) == cents


def test_fee_refuses_prices_outside_the_book():
    with pytest.raises(ValueError):
        bs.fee_cents(0, 1)
    with pytest.raises(ValueError):
        bs.fee_cents(100, 1)


# ---------------------------------------------------------------- basket
def test_basket_by_hand():
    # five legs, YES bid 19 / NO bid 79 each: YES ask 21 x 5 = 105, fee ceil(7*21*79/10000)=2c x 5 = 10c
    # -> YES basket 100 - 105 - 10 = -15c; NO ask 81 x 5 = 405, fee ceil(7*81*19/10000)=2c x 5 -> 400 - 405 - 10 = -15c
    y, n = bs.basket_net([19] * 5, [79] * 5, c=1)
    assert (y, n) == (-15.0, -15.0)


def test_yes_basket_reads_only_no_bids_and_no_basket_only_yes_bids():
    yb, nb = [3, 2, 1, 29, 15], [91, 92, 94, 69, 73]
    y0, n0 = bs.basket_net(yb, nb, c=200)
    y1, n1 = bs.basket_net([b + 2 for b in yb], nb, c=200)      # raise every YES bid: YES basket unchanged
    assert y1 == y0 and n1 > n0
    y2, n2 = bs.basket_net(yb, [b + 2 for b in nb], c=200)      # raise every NO bid: NO basket unchanged
    assert n2 == n0 and y2 > y0


def test_control_a_two_cent_shift_on_one_leg_flips_the_sign():
    # the farm scorer's 2026-10-04 17:22:06.6Z sample of window 26OCT041330, the closest any NO basket came to
    # clearing (-0.03c at 200 a leg): YES bids BTC 15, ETH 17, HYPE 7, SOL 64, XRP 1; NO bids 84, 82, 88, 23, 97
    yb = [15, 17, 7, 64, 1]
    nb = [84, 82, 88, 23, 97]
    _, n = bs.basket_net(yb, nb, c=200)
    assert -1 < n < 0
    shifted = yb.copy(); shifted[3] += 2                      # SOL's NO ask 2c cheaper
    _, n_up = bs.basket_net(shifted, nb, c=200)
    assert n_up > 0
    shifted[3] -= 4                                           # and 2c dearer: further from zero
    _, n_dn = bs.basket_net(shifted, nb, c=200)
    assert n_dn < n


def test_screen_shift_moves_only_the_named_leg():
    legs = {}
    for coin, yb, nb in (("BTC", 0.03, 0.91), ("ETH", 0.02, 0.92), ("HYPE", 0.01, 0.94), ("SOL", 0.29, 0.69), ("XRP", 0.15, 0.73)):
        legs[coin] = {"yes_best": yb, "no_best": nb, "ref_yes": yb, "ref_no": nb, "depth_yes": 500, "depth_no": 500}
    ticks = {(1.0e9, "KXCRYPTOLEAD15M-26OCT052330"): legs}
    base = bs.screen(ticks, {}, c=200)[0]
    moved = bs.screen(ticks, {}, c=200, shift=("SOL", 2))[0]
    assert base["sum_yes_ask"] == 81 and moved["sum_yes_ask"] == 79
    assert moved["yes_net"] > base["yes_net"] > 0


def test_episodes_count_a_run_once():
    rows = [{"ev": "A", "t": 0, "yes_net": 1}, {"ev": "A", "t": 60, "yes_net": 2}, {"ev": "A", "t": 120, "yes_net": -1},
            {"ev": "A", "t": 180, "yes_net": 3}, {"ev": "B", "t": 240, "yes_net": 3}]
    eps = bs.episodes(rows, "yes_net")
    assert [(e["ev"], e["n"], e["net0"]) for e in eps] == [("A", 2, 1), ("A", 1, 3), ("B", 1, 3)]


# ---------------------------------------------------------------- farming fills
def _prints(rows):
    df = pd.DataFrame(rows, columns=["ticker", "created_ts", "yes_price", "no_price", "count", "taker_side", "trade_id"])
    df["settle"] = df.get("settle", 0.0)
    return df


def test_taker_side_no_fills_the_yes_bid_at_yes_price():
    pr = ff.side_prints(_prints([("M", 1.0, 0.02, 0.98, 10, "no", "a"), ("M", 2.0, 0.95, 0.05, 7, "yes", "b")]))
    assert pr[pr.trade_id == "a"].iloc[0][["side", "x_c"]].tolist() == ["yes", 2]
    assert pr[pr.trade_id == "b"].iloc[0][["side", "x_c"]].tolist() == ["no", 5]


def test_first_in_queue_vs_behind_a_thousand():
    pr = ff.side_prints(_prints([("M", 1.0, 0.01, 0.99, 600, "no", "a"), ("M", 2.0, 0.01, 0.99, 600, "no", "b"),
                                 ("M", 3.0, 0.02, 0.98, 50, "no", "c"), ("M", 4.0, 0.01, 0.99, 300, "no", "d")]))
    first = ff.fills_fixed(pr, 1, ahead=0.0)
    behind = ff.fills_fixed(pr, 1, ahead=1000.0)
    assert first.tolist() == [600, 400, 0, 0]                 # a 2c print does not reach a 1c bid; 1,000 cap
    assert behind.tolist() == [0, 200, 0, 300]                # the first 1,000 at <=1c go to the queue ahead
    assert ff.fills_fixed(pr, 2, ahead=0.0).tolist() == [600, 400, 0, 0]


def test_front_quotes_one_tick_over_the_last_book_and_respects_the_cap():
    pr = ff.side_prints(_prints([("M", 100.0, 0.03, 0.97, 10, "no", "a"), ("M", 130.0, 0.05, 0.95, 10, "no", "b"),
                                 ("M", 200.0, 0.02, 0.98, 10, "no", "c"), ("M", 260.0, 0.01, 0.99, 10, "no", "d")]))
    book = pd.DataFrame({"ticker": ["M", "M", "M"], "ts": [90.0, 190.0, 250.0],
                         "b_yes_c": [3.0, 10.0, 2.0], "b_no_c": [90.0, 80.0, 90.0]})
    pr = ff.attach_best_bid(pr, book)
    f, p = ff.fills_front(pr, cap_c=10)
    # t=100: b 3 -> p 4, print 3 fills; t=130: print at 5 is above p 4 -> no fill; t=200: b 10 -> p 11 > cap,
    # not quoted; t=260: b 2 -> p 3, print 1 fills at 3
    assert p.tolist() == [4, 4, -1, 3]
    assert f.tolist() == [10, 0, 0, 10]


def test_best_bid_never_comes_from_the_future():
    pr = ff.side_prints(_prints([("M", 100.0, 0.03, 0.97, 10, "no", "a")]))
    book = pd.DataFrame({"ticker": ["M"], "ts": [100.5], "b_yes_c": [3.0], "b_no_c": [90.0]})
    pr = ff.attach_best_bid(pr, book)
    assert pr.b_src.tolist() == ["none"] and pr.b_c.isna().all()


def test_fallback_is_the_previous_print_into_the_same_side():
    pr = ff.side_prints(_prints([("M", 10.0, 0.04, 0.96, 5, "no", "a"), ("M", 11.0, 0.90, 0.10, 5, "yes", "b"),
                                 ("M", 12.0, 0.03, 0.97, 5, "no", "c")]))
    book = pd.DataFrame({"ticker": ["M"], "ts": [500.0], "b_yes_c": [3.0], "b_no_c": [90.0]})
    pr = ff.attach_best_bid(pr, book)
    yes = pr[pr.side == "yes"]
    assert yes.b_src.tolist() == ["none", "prev_print"] and yes.b_c.tolist()[1] == 4


@pytest.mark.parametrize("side,settle,p_c,per", [("yes", 1.0, 2, 0.98), ("yes", 0.0, 2, -0.02), ("no", 1.0, 2, -0.02),
                                                 ("no", 0.0, 2, 0.98), ("yes", 0.5, 2, 0.48)])
def test_settlement_pnl_per_filled_contract(side, settle, p_c, per):
    pr = pd.DataFrame({"side": [side], "settle": [settle]})
    assert ff.pnl(pr, pd.Series([1.0]), [p_c]).iloc[0] == pytest.approx(per)


def test_denominator_is_every_market_window():
    pr = pd.DataFrame({"ticker": ["A"], "f_x": [10.0], "pl_x": [-0.1]})
    uni = pd.DataFrame({"ticker": ["A", "B"], "event_ticker": ["E", "E"], "close_ts": [0.0, 0.0]})
    mw = ff.per_market_window(pr, ["f_x", "pl_x"], uni)
    assert mw.f_x.tolist() == [10.0, 0.0] and mw.pl_x.mean() == pytest.approx(-0.05)


def test_cluster_ci_brackets_the_mean():
    v = pd.Series(np.r_[np.zeros(50), np.ones(50)])
    c = pd.Series(np.repeat(np.arange(20), 5))
    m, lo, hi = ff.cluster_ci(v, c, reps=500)
    assert m == pytest.approx(0.5) and lo < m < hi


def test_front_live_pays_one_tick_over_the_sweep_top():
    # one taker order sweeps 3c then 2c (same created_ts): the live best bid was 3c, we sit at 4c and take both;
    # a later print at 9c -> 10c (at the cap); a print at 10c -> 11c is over the cap and not quoted
    pr = ff.side_prints(_prints([("M", 1.0, 0.03, 0.97, 5, "no", "a"), ("M", 1.0, 0.02, 0.98, 7, "no", "b"),
                                 ("M", 2.0, 0.09, 0.91, 4, "no", "c"), ("M", 3.0, 0.10, 0.90, 4, "no", "d")]))
    f, p = ff.fills_front_live(pr, cap_c=10)
    assert p.tolist() == [4, 4, 10, -1]
    assert f.tolist() == [5, 7, 4, 0]


# ---------------------------------------------------------------- baskets executed on the tape
def _basket_prints(ev, t, side, n, prices, extra=()):
    coins = ["BTC", "ETH", "HYPE", "SOL", "XRP"]
    return [(ev, c, t + 0.001 * i, side, n, p) for i, (c, p) in enumerate(zip(coins, prices))] + list(extra)


def test_tape_basket_by_hand():
    # all five YES bought at 13/8/9/31/31 (sum 92c), 119 a leg -- the 2026-10-06 03:22:58Z basket
    pr = _basket_prints("26OCT052330", 1000.0, "yes", 119, [13, 8, 9, 31, 31])
    (b,) = bs.tape_baskets(pr)
    assert b["side"] == "yes" and b["n"] == 119 and b["vwap_sum"] == 92
    # fees at 119: ceil(.07*119*p(1-p)) per leg = 95 + 62 + 69 + 179 + 179 = 584c
    assert b["net_usd"] == pytest.approx((100 * 119 - 92 * 119 - 584) / 100)


def test_tape_basket_needs_five_equal_legs_and_one_side():
    four = _basket_prints("W", 0.0, "yes", 10, [20, 20, 20, 20, 20])[:4]
    assert bs.tape_baskets(four) == []
    unequal = _basket_prints("W", 0.0, "yes", 10, [20, 20, 20, 20, 20])
    unequal[-1] = ("W", "XRP", 0.004, "yes", 30, 20)
    assert bs.tape_baskets(unequal) == []
    mixed = _basket_prints("W", 0.0, "yes", 10, [20, 20, 20, 20, 20])
    mixed[-1] = ("W", "XRP", 0.004, "no", 10, 20)
    assert bs.tape_baskets(mixed) == []
    apart = _basket_prints("W", 0.0, "yes", 10, [20, 20, 20, 20, 20])
    apart[-1] = ("W", "XRP", 5.0, "yes", 10, 20)                # a leg 5 s later is not the same basket
    assert bs.tape_baskets(apart) == []


def test_no_basket_prices_the_no_legs():
    # buying NO on all five where YES printed 1/2/3/4/90: NO paid 99+98+97+96+10 = 400 -> gross 0
    (b,) = bs.tape_baskets(_basket_prints("W", 0.0, "no", 100, [1, 2, 3, 4, 90]))
    assert b["side"] == "no" and b["vwap_sum"] == 400 and b["gross_c"] == 0 and b["net_c"] < 0


def test_residue_reads_the_first_book_after_the_basket():
    (b,) = bs.tape_baskets(_basket_prints("E", 100.0, "yes", 50, [13, 8, 9, 31, 31]))
    coins = ["BTC", "ETH", "HYPE", "SOL", "XRP"]
    # candles (end, yes_bid, yes_ask): one before the basket that clears (asks sum 80) must be ignored; the
    # one after has asks 14/9/10/33/40 = 106 -> nothing left
    cand = {f"KXCRYPTOLEAD15M-E-{c}": [(90.0, 1, a0), (120.0, 1, a1)]
            for c, a0, a1 in zip(coins, [10, 8, 8, 27, 27], [14, 9, 10, 33, 40])}
    (d,) = bs.basket_detail([b], cand, {"E": 40.0})
    assert d["minute_of_window"] == pytest.approx(1.0)
    assert d["after_net_c1"] < 0 and d["after_lag_s"] == pytest.approx(120.0 - b["t1"])
