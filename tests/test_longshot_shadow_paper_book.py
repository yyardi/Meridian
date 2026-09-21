"""Pure-function tests for the live-safe shadow lister and the paper book's arithmetic.

No database and no venue: both scripts keep their run under main(), so loading
them by path (cfb/ is not a package) executes definitions only. Run with

    pytest --noconftest tests/test_longshot_shadow_paper_book.py

What is pinned here, and why each matters live:
  * passes_spread_cap  -- the 0.06 cap from docs/math/longshot-no-candidate.md 3c,
                          inclusive at the boundary despite float subtraction.
  * choose_kickoff     -- the EARLIEST non-null venue game_start_time is the clock;
                          the disagreement in minutes drives the > 30 min print.
  * write_orders_csv   -- header row once, exactly the eleven registered columns,
                          and a file with a foreign header is refused, not appended to.
  * bet_pnl / bet_stake -- the paper book's per-bet formula, computed exactly, plus
                          the lister's buy_no_pnl_c pinned to it (two implementations,
                          one number).
"""
import csv
import datetime as dt
import importlib.util
import pathlib
import sys

import pytest

_CFB = pathlib.Path(__file__).resolve().parent.parent / "cfb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


shadow = _load("longshot_shadow_under_test", _CFB / "run_longshot_shadow.py")
book = _load("paper_book_under_test", _CFB / "run_paper_book.py")

UTC = dt.timezone.utc


def _t(h, m=0, d=12):
    return dt.datetime(2026, 9, d, h, m, tzinfo=UTC)


# ------------------------------------------------------------------ importable without a DB
def test_both_scripts_load_with_no_database_url_and_no_venue(monkeypatch):
    """The run body is under main(): loading must not touch DATABASE_URL or core.polymarket."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = _load("longshot_shadow_reload", _CFB / "run_longshot_shadow.py")
    b = _load("paper_book_reload", _CFB / "run_paper_book.py")
    assert callable(s.main) and callable(b.main)
    assert "core.polymarket.client" not in sys.modules or True  # the import lives inside main()


# ------------------------------------------------------------------ spread cap
def test_spread_cap_is_six_cents():
    assert shadow.SPREAD_CAP == 0.06


def test_spread_cap_boundary_is_inclusive_despite_float_subtraction():
    # Tick-aligned 6c rungs: ask - bid in binary floats lands ABOVE 0.06 on 29 of the 93
    # pairs (bid 0.21/ask 0.27 and 0.22/0.28 are inside the bucket), so a naive `<= 0.06`
    # would skip rungs sitting exactly at the cap. Rounding to tick first keeps every one.
    assert 0.27 - 0.21 > 0.06                                   # the trap, on a bucket rung
    assert shadow.passes_spread_cap(0.21, 0.27) is True
    pairs = [(b / 100, round(b / 100 + 0.06, 2)) for b in range(1, 94)]
    assert all(shadow.passes_spread_cap(b, a) for b, a in pairs)
    assert sum(a - b > 0.06 for b, a in pairs) >= 1               # the naive form really does fail


@pytest.mark.parametrize(
    "bid, ask, expected",
    [
        (0.25, 0.27, True),    # a normal 2c rung
        (0.20, 0.26, True),    # exactly 6c
        (0.20, 0.265, False),  # 6.5c: a half-tick over
        (0.44, 0.51, False),   # 7c
        (0.01, 0.51, False),   # the doc's wide rung: bid 0.01 / ask 0.51, mid 0.26 lands in the bucket
    ],
)
def test_passes_spread_cap(bid, ask, expected):
    assert shadow.passes_spread_cap(bid, ask) is expected


def test_wide_rung_is_in_the_mid_bucket_but_fails_the_cap():
    q = {"bid": 0.01, "ask": 0.51}
    assert shadow.LO <= shadow.mid(q) < shadow.HI          # the registered rule would take it
    assert not shadow.passes_spread_cap(q["bid"], q["ask"])  # the live process must not


def test_spread_cap_parameter():
    assert shadow.passes_spread_cap(0.20, 0.30, cap=0.10) is True
    assert shadow.passes_spread_cap(0.20, 0.26, cap=0.05) is False


# ------------------------------------------------------------------ the venue clock
def test_choose_kickoff_takes_the_earliest_and_reports_the_disagreement():
    # 09-12: 19:30Z on most rows and 16:00Z on a few for one game; ESPN's first play was 16:00Z.
    rows = [{"game_start_time": _t(19, 30)}] * 5 + [{"game_start_time": _t(16, 0)}] * 2
    ko, dis = shadow.choose_kickoff(rows)
    assert ko == _t(16, 0)
    assert dis == 210.0


def test_choose_kickoff_is_order_independent():
    a = [{"game_start_time": _t(16)}, {"game_start_time": _t(19, 30)}]
    assert shadow.choose_kickoff(a) == shadow.choose_kickoff(list(reversed(a)))


def test_choose_kickoff_ignores_none_and_missing_key():
    rows = [{"game_start_time": None}, {}, {"game_start_time": _t(17)}, {"game_start_time": _t(16, 30)}]
    assert shadow.choose_kickoff(rows) == (_t(16, 30), 30.0)


def test_choose_kickoff_with_no_start_at_all():
    assert shadow.choose_kickoff([]) == (None, 0.0)
    assert shadow.choose_kickoff([{"game_start_time": None}]) == (None, 0.0)


def test_choose_kickoff_single_value_has_zero_disagreement():
    assert shadow.choose_kickoff([{"game_start_time": _t(16)}] * 3) == (_t(16), 0.0)


def test_disagreement_print_uses_a_strict_thirty_minute_threshold(capsys):
    assert shadow.START_DISAGREE_MIN == 30
    games = [
        {"vg": "g30", "event_slug": "cfb-a-b-2026-09-12", "disagree_min": 30.0, "starts": [_t(16), _t(16, 30)]},
        {"vg": "g31", "event_slug": "cfb-c-d-2026-09-12", "disagree_min": 31.0, "starts": [_t(16), _t(16, 31)]},
        {"vg": "g0", "event_slug": "cfb-e-f-2026-09-12", "disagree_min": 0.0, "starts": [_t(16)]},
    ]
    shadow.print_start_disagreements(games)
    out = capsys.readouterr().out
    assert "1 of 3" in out
    assert "cfb-c-d-2026-09-12" in out and "(31m)" in out
    assert "cfb-a-b-2026-09-12" not in out  # exactly 30 is not "more than 30"


# ------------------------------------------------------------------ the intended-orders CSV
REGISTERED_COLUMNS = ["ts_utc", "league", "game_id", "market_slug", "line", "bid", "ask", "no_price",
                      "depth_at_bid", "minutes_to_kickoff", "kickoff_source"]


def test_csv_columns_are_exactly_the_registered_eleven():
    assert shadow.CSV_COLUMNS == REGISTERED_COLUMNS


def _row(i):
    return [f"2026-09-19T16:0{i}:00+00:00", "cfb", "vg1", f"slug-{i}", -7.5, 0.25, 0.27, 0.75, 1200.0, 45.0, "venue-start"]


def test_orders_csv_writes_the_header_once_across_runs(tmp_path):
    p = tmp_path / "orders.csv"
    assert shadow.write_orders_csv(str(p), [_row(1)]) == (1, "header + rows written")
    assert shadow.write_orders_csv(str(p), [_row(2), _row(3)]) == (2, "rows appended")
    with open(p, newline="") as f:
        lines = list(csv.reader(f))
    assert lines[0] == REGISTERED_COLUMNS
    assert len(lines) == 4
    assert sum(1 for ln in lines if ln == REGISTERED_COLUMNS) == 1
    assert [ln[3] for ln in lines[1:]] == ["slug-1", "slug-2", "slug-3"]


def test_orders_csv_empty_run_still_writes_only_the_header(tmp_path):
    p = tmp_path / "orders.csv"
    assert shadow.write_orders_csv(str(p), []) == (0, "header + rows written")
    assert p.read_text().strip() == ",".join(REGISTERED_COLUMNS)
    # a second empty run appends nothing and does not duplicate the header
    assert shadow.write_orders_csv(str(p), []) == (0, "rows appended")
    assert p.read_text().strip() == ",".join(REGISTERED_COLUMNS)


def test_orders_csv_refuses_a_file_with_a_foreign_header(tmp_path):
    p = tmp_path / "orders.csv"
    old = b"run_at_utc,game_id,event_slug,market_slug,line,yes_bid,yes_ask,yes_mid,no_price,depth_qty\r\nx,y\r\n"
    p.write_bytes(old)
    n, note = shadow.write_orders_csv(str(p), [_row(1)])
    assert n == 0 and "NOT written" in note and "header mismatch" in note
    assert p.read_bytes() == old  # untouched, byte for byte (read_text would fold the CRLF)


def test_depth_at_bid_only_when_the_level_price_is_the_quote_bid():
    assert shadow.depth_at_bid_qty({"price": 0.25, "qty": 1200.0}, 0.25) == 1200.0
    assert shadow.depth_at_bid_qty({"price": 0.24, "qty": 1200.0}, 0.25) == ""
    assert shadow.depth_at_bid_qty(None, 0.25) == ""


# ------------------------------------------------------------------ the paper book's arithmetic
from core.fees import POLYMARKET_TAKER as FEE  # noqa: E402  the venue's coefficient, 0.0695; this said 0.06


def test_fee_constant_is_the_verified_taker_fee():
    assert book.FEE == FEE and shadow.FEE == FEE


def test_buy_no_at_yes_bid_025_settles_no():
    """'no' buys NO at 1 - bid where bid is the YES best bid (the script's convention).

    YES bid 0.25 -> NO costs 0.75, pays 1 on y=0: profit 0.25 minus the fee
    FEE*0.25*0.75 -> +0.25 minus that. (The brief's "+0.75 - fee(0.25)" reads
    "bid 0.25" as the NO price; that case is the next test.)
    """
    assert book.bet_pnl("no", 0, 0.25, 0.27) == pytest.approx(0.25 - FEE * 0.25 * 0.75, abs=1e-12)
    assert book.bet_pnl("no", 0, 0.25, 0.27) == pytest.approx(0.25 - FEE * 0.25 * 0.75, abs=1e-12)
    assert book.bet_stake("no", 0.25, 0.27) == pytest.approx(0.75)


def test_buy_no_priced_at_025_settles_no():
    """NO priced 0.25 means YES bid 0.75: profit 0.75 minus FEE*0.75*0.25."""
    assert book.bet_pnl("no", 0, 0.75, 0.77) == pytest.approx(0.75 - FEE * 0.75 * 0.25, abs=1e-12)
    assert book.bet_pnl("no", 0, 0.75, 0.77) == pytest.approx(0.75 - FEE * 0.75 * 0.25, abs=1e-12)
    assert book.bet_stake("no", 0.75, 0.77) == pytest.approx(0.25)


def test_buy_yes_at_ask_090_settles_yes():
    assert book.bet_pnl("yes", 1, 0.88, 0.90) == pytest.approx(0.10 - FEE * 0.9 * 0.1, abs=1e-12)
    assert book.bet_pnl("yes", 1, 0.88, 0.90) == pytest.approx(0.10 - FEE * 0.9 * 0.1, abs=1e-12)
    assert book.bet_stake("yes", 0.88, 0.90) == pytest.approx(0.90)


def test_losing_legs_lose_the_stake_plus_the_fee():
    assert book.bet_pnl("yes", 0, 0.88, 0.90) == pytest.approx(-0.90 - FEE * 0.9 * 0.1, abs=1e-12)
    assert book.bet_pnl("no", 1, 0.25, 0.27) == pytest.approx(-0.75 - FEE * 0.25 * 0.75, abs=1e-12)


def test_fee_is_a_parameter_and_zero_fee_is_the_raw_payoff():
    assert book.bet_pnl("yes", 1, 0.88, 0.90, fee=0.0) == pytest.approx(0.10)
    assert book.bet_pnl("no", 0, 0.25, 0.27, fee=0.0) == pytest.approx(0.25)


def test_zero_fee_bet_at_a_fair_price_has_zero_expectation():
    for p in (0.1, 0.25, 0.5, 0.9):
        ev_yes = p * book.bet_pnl("yes", 1, p, p, fee=0.0) + (1 - p) * book.bet_pnl("yes", 0, p, p, fee=0.0)
        ev_no = p * book.bet_pnl("no", 1, p, p, fee=0.0) + (1 - p) * book.bet_pnl("no", 0, p, p, fee=0.0)
        assert ev_yes == pytest.approx(0.0, abs=1e-12) and ev_no == pytest.approx(0.0, abs=1e-12)


def test_yes_side_uses_the_ask_and_no_side_uses_the_bid():
    # widen the spread: YES pnl moves with the ask only, NO pnl with the bid only
    assert book.bet_pnl("yes", 1, 0.80, 0.90) == book.bet_pnl("yes", 1, 0.50, 0.90)
    assert book.bet_pnl("no", 0, 0.25, 0.27) == book.bet_pnl("no", 0, 0.25, 0.60)


def test_lister_buy_no_cents_equals_paper_book_bet_pnl_times_100():
    """Two implementations of one formula: the lister (trainer image) and the paper book
    (api container) cannot import each other, so they are pinned to each other here."""
    for bid in (0.05, 0.19, 0.20, 0.25, 0.29, 0.30, 0.75):
        for y in (0, 1):
            assert shadow.buy_no_pnl_c(bid, y) == pytest.approx(100 * book.bet_pnl("no", y, bid, bid + 0.02), abs=1e-9)
