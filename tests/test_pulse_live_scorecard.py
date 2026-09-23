"""The PULSE live scorecard's arithmetic, on fixtures. No database, no venue.

    pytest --noconftest tests/test_pulse_live_scorecard.py

cfb/ is not a package, so the script is loaded by path (the paper-book tests'
pattern); its run is under main(), so loading executes definitions only.

What is pinned, and why each matters:
  * dedupe      -- the two keys remove exactly the 2026-09-14 collision shapes
                   and keep the first-written row; the removed count is returned.
  * regime      -- the playoff boundary is 2026-09-14 00:00Z on decided_at.
  * taker_pnl   -- equals run_paper_book.bet_pnl to the float on both
                   coefficients (two implementations, one number), refuses None.
  * limit arm   -- taker arm + spread + fee on every row, by identity.
  * settlement  -- venue first, the engine's stamp second, 0.5 excluded,
                   disagreement counted.
  * estimator   -- games not rows: G, Kish G_eff, no interval under two games;
                   row-weighted and equal-weight points both present and distinct
                   on unbalanced clusters.
  * calibration -- the gap's sign; log-loss clipping is counted.
  * the report  -- runs end to end on fixtures; every table carries its header.
"""
import datetime as dt
import importlib.util
import math
import pathlib
import sys
from decimal import Decimal

import pytest

_CFB = pathlib.Path(__file__).resolve().parent.parent / "cfb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load("pulse_live_scorecard_under_test", _CFB / "run_pulse_live_scorecard.py")
book = _load("paper_book_for_scorecard_test", _CFB / "run_paper_book.py")

UTC = dt.timezone.utc
#: The coefficient before 2026-09-17 04:07Z and the one since, as the column
#: stores them. History, not imported: core/fees.py owns only the current one.
PRE, POST = Decimal("0.060000"), Decimal("0.069500")


def _t(d, h=0, m=0, s=0, us=0):
    return dt.datetime(2026, 9, d, h, m, s, us, tzinfo=UTC)


def _row(i, *, market="tsc-wnba-a-b-2026-09-20", event="wnba-a-b-2026-09-20",
         at=None, action="enter", side="yes", limit=0.40, bid=0.40, ask=0.44,
         fv=0.50, phase="in_play", version="v4", strategy="winner", coef=POST,
         filled_at=None, withdrawn_at=None, mid_at_fill=None, row_settlement=None,
         capped=None):
    return dict(id=i, decided_at=at or _t(20, 1, 0, i), event_slug=event,
                market_slug=market, game_id=None, strategy=strategy, phase=phase,
                action=action, side=side, estimates_version=version, reason=None,
                binding_constraint=None, limit_price=limit, bid=bid, ask=ask,
                fair_value=fv, edge_net=None, capped_stake_usd=capped,
                filled_at=filled_at, mid_at_fill=mid_at_fill, withdrawn_at=withdrawn_at,
                row_settlement=row_settlement,
                fee_coefficient=None if coef is None else float(coef))


# ------------------------------------------------------------------ loads without a DB
def test_the_script_loads_with_no_database_url_and_no_venue(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    m = _load("pulse_live_scorecard_reload", _CFB / "run_pulse_live_scorecard.py")
    assert callable(m.main)
    assert "d.decided_at >= :since" in m.DECISIONS_SQL
    assert ":month_floor" in m.DECISIONS_SQL and "::" not in m.DECISIONS_SQL.split(":month_floor")[1][:2]


# ------------------------------------------------------------------ dedupe
def test_calibration_key_collapses_the_yes_no_pair_and_the_target_stop_pair():
    at = _t(20, 1, 0, 0)
    rows = [
        _row(1, at=at, side="yes", limit=0.40),                        # the 24-group shape:
        _row(2, at=at, side="no", limit=0.44),                         # same tick, two sides
        _row(3, at=at, action="exit", limit=0.45),                     # the 60-group shape:
        _row(4, at=at, action="exit", limit=0.44),                     # target then stop
        _row(5, at=_t(20, 1, 0, 1)),                                   # a different instant
    ]
    kept, removed = sc.dedupe(rows, sc.CALIBRATION_KEY)
    assert [r["id"] for r in kept] == [1, 3, 5]      # first-written per (market, instant, action)
    assert removed == 2
    assert sc.collisions(rows, sc.CALIBRATION_KEY) == {"enter": 1, "exit": 1}


def test_bet_key_keeps_both_sides_of_the_same_tick():
    at = _t(20, 1, 0, 0)
    rows = [_row(1, at=at, side="yes", limit=0.40), _row(2, at=at, side="no", limit=0.44),
            _row(3, at=at, side="yes", limit=0.40)]                   # an exact copy: removed
    kept, removed = sc.dedupe(rows, sc.BET_KEY)
    assert [r["id"] for r in kept] == [1, 2] and removed == 1


def test_first_written_means_lowest_id_whatever_the_input_order():
    at = _t(20)
    kept, _ = sc.dedupe([_row(9, at=at), _row(2, at=at)], sc.CALIBRATION_KEY)
    assert [r["id"] for r in kept] == [2]


# ------------------------------------------------------------------ regime
def test_playoffs_start_at_the_operator_s_date_in_utc():
    assert sc.regime(dt.datetime(2026, 9, 13, 23, 59, 59, tzinfo=UTC)) == "regular"
    assert sc.regime(dt.datetime(2026, 9, 14, 0, 0, 0, tzinfo=UTC)) == "playoffs"


# ------------------------------------------------------------------ the fee and the arms
@pytest.mark.parametrize("coef", [PRE, POST])
@pytest.mark.parametrize("side,y", [("yes", 1), ("yes", 0), ("no", 1), ("no", 0)])
def test_taker_pnl_is_the_paper_book_s_bet_pnl(coef, side, y):
    bid, ask = 0.37, 0.41
    assert sc.taker_pnl(side, y, bid, ask, coef) == book.bet_pnl(side, y, bid, ask, coef)
    assert sc.taker_stake(side, bid, ask) == book.bet_stake(side, bid, ask)


def test_taker_pnl_charges_the_row_s_coefficient_not_one_constant():
    a, b = sc.taker_pnl("yes", 1, 0.37, 0.41, PRE), sc.taker_pnl("yes", 1, 0.37, 0.41, POST)
    assert b < a and math.isclose(a - b, float(POST - PRE) * 0.41 * 0.59)


def test_a_missing_coefficient_is_refused_not_charged_at_today_s():
    with pytest.raises(ValueError):
        sc.taker_pnl("yes", 1, 0.37, 0.41, None)


def test_the_limit_arm_exceeds_the_taker_arm_by_spread_plus_fee_on_every_row():
    bid, ask = 0.37, 0.41
    for side, limit, y in (("yes", bid, 1), ("yes", bid, 0), ("no", ask, 1), ("no", ask, 0)):
        p = ask if side == "yes" else bid
        gap = sc.limit_pnl(side, y, limit) - sc.taker_pnl(side, y, bid, ask, POST)
        assert math.isclose(gap, (ask - bid) + float(POST) * p * (1 - p))


def test_lifecycle_arm_is_named_by_withdrawn_at_not_by_the_absence_of_a_fill():
    assert sc.lifecycle_arm(_row(1, filled_at=_t(20))) == "filled"
    assert sc.lifecycle_arm(_row(2, withdrawn_at=_t(20))) == "withdrawn"
    assert sc.lifecycle_arm(_row(3)) == "neither"             # never posted, or still open


def test_mid_move_to_fill_is_signed_to_the_position():
    # YES bought with mid 0.42; the mid fell to 0.40 to fill it: adverse, -2c.
    assert sc.signed_mid_move(_row(1, side="yes", bid=0.40, ask=0.44, mid_at_fill=0.40)) == pytest.approx(-2.0)
    # NO bought with mid 0.42; the mid rose to 0.44 to fill it: adverse, -2c.
    assert sc.signed_mid_move(_row(2, side="no", bid=0.40, ask=0.44, mid_at_fill=0.44)) == pytest.approx(-2.0)
    assert sc.signed_mid_move(_row(3)) is None


# ------------------------------------------------------------------ settlement
def test_settlement_prefers_the_venue_then_the_engine_s_stamp_and_excludes_a_half():
    rows = [_row(1, market="m-venue", row_settlement=0),          # venue says 1, stamp says 0
            _row(2, market="m-stamped", row_settlement=1),        # venue silent, stamp 1
            _row(3, market="m-half"),
            _row(4, market="m-open")]
    answers = {"m-venue": 1, "m-half": 0.5}
    by_market, counts = sc.resolve_settlements(rows, lambda s: answers.get(s))
    assert by_market == {"m-venue": 1, "m-stamped": 1, "m-half": None, "m-open": None}
    assert counts == dict(venue=1, row=1, half=1, unsettled=1, disagree=1)


def test_scoreable_drops_and_counts_every_reason():
    rows = [_row(1, phase="pregame"), _row(2, market="unsettled"), _row(3, fv=None),
            _row(4, bid=None), _row(5, bid=0.50, ask=0.50), _row(6)]
    kept, why = sc.scoreable(rows, {"tsc-wnba-a-b-2026-09-20": 1})
    assert [r["id"] for r in kept] == [6] and kept[0]["y"] == 1
    assert why == {"pregame_phase": 1, "unsettled_or_half": 1, "no_fair_value": 1,
                   "no_two_sided_touch": 2}


# ------------------------------------------------------------------ the estimator
def test_g_eff_is_kish_and_the_two_points_differ_on_unbalanced_clusters():
    cs = sc.cluster_stats({"g1": [1.0], "g2": [0.0, 0.0, 0.0]})
    assert cs["n"] == 4 and cs["G"] == 2
    assert cs["g_eff"] == pytest.approx(16 / 10)
    assert cs["mean"] == pytest.approx(0.25)           # row-weighted
    assert cs["game_mean"] == pytest.approx(0.5)       # equal weight per game
    assert cs["lo"] is not None and cs["game_lo"] is not None


def test_one_game_has_no_interval_and_says_so():
    cs = sc.cluster_stats({"g1": [1.0, 0.0, 1.0]})
    assert cs["G"] == 1 and cs["lo"] is None and cs["game_lo"] is None
    assert "no interval" in sc._ci(cs["mean"], cs["lo"], cs["hi"], "+.2f")


def test_calibration_counts_games_not_rows():
    rows = [{**_row(i, market=f"m{i}"), "y": 1} for i in range(18)]   # 18 rungs, one game
    c = sc.calibration_cell(rows)
    assert c["rows"] == 18 and c["markets"] == 18 and c["games"] == 1
    assert c["diff_lo"] is None


def test_the_gap_is_positive_when_the_model_is_closer_and_negative_when_the_mid_is():
    closer = [{**_row(i, event=f"g{i}", fv=0.90, bid=0.58, ask=0.62), "y": 1} for i in range(4)]
    c = sc.calibration_cell(closer)
    assert c["brier_model"] < c["brier_market"] and c["diff"] > 0 and c["diff_lo"] > 0
    farther = [{**_row(i, event=f"g{i}", fv=0.60, bid=0.88, ask=0.92), "y": 1} for i in range(4)]
    assert sc.calibration_cell(farther)["diff"] < 0


def test_log_loss_clips_certainty_and_counts_it():
    assert sc.logloss(1.0, 0) == pytest.approx(-math.log(sc.LOGLOSS_CLIP))
    assert sc.logloss(0.5, 1) == pytest.approx(math.log(2))
    c = sc.calibration_cell([{**_row(1, fv=1.0), "y": 1}, {**_row(2, fv=0.5), "y": 1}])
    assert c["clipped"] == 1


def test_gap_buckets_are_half_open_and_the_last_is_closed():
    assert sc.gap_bucket(0.0) == "[0.00,0.02)"
    assert sc.gap_bucket(0.02) == "[0.02,0.05)"
    assert sc.gap_bucket(0.199) == "[0.10,0.20)"
    assert sc.gap_bucket(0.20) == "[0.20,1.00]" and sc.gap_bucket(1.0) == "[0.20,1.00]"


def test_side_win_is_which_way_the_model_leaned():
    yes_won = {**_row(1, fv=0.6, bid=0.48, ask=0.52), "y": 1}
    no_lost = {**_row(2, fv=0.4, bid=0.48, ask=0.52), "y": 1}
    assert sc.bet_won(yes_won) and not sc.bet_won(no_lost)


def test_pnl_cell_excludes_and_counts_rows_without_a_coefficient():
    rows = [{**_row(1, coef=None), "y": 1}, {**_row(2, event="g2"), "y": 1}]
    c = sc.pnl_cell(rows)
    assert c["no_coef"] == 1 and c["bets"] == 1 and c["games"] == 1
    assert c["pnl"] == pytest.approx(sc.taker_pnl("yes", 1, 0.40, 0.44, POST))
    assert c["limit_cents"] == pytest.approx(60.0)


# ------------------------------------------------------------------ the report, end to end
def _fixture():
    """Two regular-season games and two playoff games, eighteen-ish rows,
    with each collision shape, an unsettled market and a pre-change row."""
    rows = []
    n = 0
    for g, (day, coef) in enumerate(((10, PRE), (11, PRE), (18, POST), (20, POST))):
        for k in range(3):
            n += 1
            market = f"tsc-wnba-g{g}-r{k}"
            rows.append(_row(n, market=market, event=f"wnba-g{g}", at=_t(day, 1, 0, k),
                             fv=0.55 + 0.05 * k, bid=0.40, ask=0.44, coef=coef,
                             filled_at=_t(day, 1, 1) if k == 0 else None,
                             withdrawn_at=_t(day, 1, 2) if k == 1 else None,
                             mid_at_fill=0.40 if k == 0 else None,
                             row_settlement=1 if k == 0 else None))
            n += 1
            rows.append(_row(n, market=market, event=f"wnba-g{g}", at=_t(day, 1, 0, k),
                             action="exit", side="yes", limit=0.45, fv=0.58, coef=coef))
            n += 1
            rows.append(_row(n, market=market, event=f"wnba-g{g}", at=_t(day, 1, 0, k),
                             action="exit", side="yes", limit=0.44, fv=0.58, coef=coef))
            n += 1
            rows.append(_row(n, market=market, event=f"wnba-g{g}", at=_t(day, 1, 3, k),
                             action="hold", side="yes", limit=0.45, fv=0.61, coef=coef))
    n += 1
    rows.append(_row(n, market="tsc-wnba-open", event="wnba-g9", at=_t(21), phase="in_play"))
    n += 1
    rows.append(_row(n, market="tsc-wnba-g0-r0", event="wnba-g0", at=_t(10, 0, 30), phase="pregame"))
    answers = {f"tsc-wnba-g{g}-r{k}": (1 if g % 2 == 0 else 0) for g in range(4) for k in range(3)}
    return rows, answers


def test_the_report_runs_on_fixtures_and_carries_every_header():
    rows, answers = _fixture()
    by_market, counts = sc.resolve_settlements(rows, lambda s: answers.get(s))
    text = sc.format_report(rows, by_market, counts, since=_t(1), now=_t(22))
    for header in (sc.CAL_HEADER, sc.GAP_HEADER, sc.PNL_HEADER, sc.ARM_HEADER):
        assert header in text
    assert "regular" in text and "playoffs" in text
    assert "collision rows removed" in text
    assert "settlement per market: venue 12, row 0, half 0, unsettled 1" in text
    assert "pregame_phase 1" in text and "unsettled_or_half 1" in text
    assert "distinct coefficients: 0.0600, 0.0695" in text
    # every table line is as wide as its header, so the columns the manager reads line up
    lines = text.splitlines()
    for header, line_fn in ((sc.CAL_HEADER, sc.cal_line), (sc.PNL_HEADER, sc.pnl_line)):
        i = lines.index(header)
        assert len(lines[i + 1]) == len(header), (header, lines[i + 1])


def test_the_report_names_the_population_on_every_table_line():
    rows, answers = _fixture()
    by_market, counts = sc.resolve_settlements(rows, lambda s: answers.get(s))
    text = sc.format_report(rows, by_market, counts, since=_t(1), now=_t(22))
    lines = text.splitlines()
    for header in (sc.CAL_HEADER, sc.PNL_HEADER, sc.ARM_HEADER):
        i = lines.index(header) + 1
        while i < len(lines) and lines[i] and not lines[i].startswith(("CALIBRATION", "PAPER", "THE ")):
            first = lines[i].split()[0]
            assert first in ("regular", "playoffs", "all", "version"), lines[i]
            i += 1


def test_the_report_with_no_rows_says_so_instead_of_printing_nothing():
    text = sc.format_report([], {}, dict(venue=0, row=0, half=0, unsettled=0, disagree=0),
                            since=_t(1), now=_t(22))
    assert "rows 0 -- nothing decided in the window" in text
    assert sc.PNL_HEADER in text
