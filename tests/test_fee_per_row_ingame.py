"""The in-game family charges each row at the coefficient the venue recorded on it.

    pytest --noconftest tests/test_fee_per_row_ingame.py   (all but the one DB-backed test)
    pytest tests/test_fee_per_row_ingame.py                (that one runs CLOSE_SQL for real)

The venue RAISED its taker coefficient at 2026-09-17 04:07Z; core/fees.py has both values with
their row counts, and market_snapshots.fee_coefficient carries the one charged on every row.
Six research runners charged one constant across every row, so a read spanning that instant
charged every pre-change row 16 % too much -- and run_extreme_hold went further: it TRAPPED any
tick whose coefficient differed from the constant, so a window spanning the raise skipped every
pre-change game and reported them under a TRAP counter.

Five of the six are SCRIPTS (an engine and the whole run at module level), so the shipped
functions are lifted by AST into a namespace, the way tests/test_scan_floor.py does; the sixth
(run_ladder_calibration) imports. Every expectation is an expression in the row's coefficient,
never pinned cents: a pinned cent is what broke six stream-scan expectations when the venue
moved, and it would break again the next time it moves.
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect
import pathlib
import re
from bisect import bisect_right
from collections import defaultdict
from decimal import Decimal

import pytest

from core.fees import KALSHI_TAKER, recorded_fee

ROOT = pathlib.Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc

#: The coefficient the venue charged BEFORE 2026-09-17 04:07Z, and the one since. Spelled
#: here and not imported, because the old one is HISTORY: core/fees.py owns the current
#: value and must not gain a second constant to keep the past in.
PRE, POST = 0.06, 0.0695


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _lift(rel: str, names: set[str], **ns):
    """The shipped functions, lifted out by AST so no module-level work runs.

    `recorded_fee` is core's; the runners' own ImportError fallbacks are tested
    separately to be the same contract."""
    tree = ast.parse(_src(rel))
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in fns} == set(names), (rel, names, [n.name for n in fns])
    space: dict = {"recorded_fee": recorded_fee, **ns}
    exec(compile(ast.Module(body=fns, type_ignores=[]), rel, "exec"), space)  # noqa: S102 - the shipped source
    return space


# --------------------------------------------------------------------------- #
# run_extreme_hold: the URGENT one, because it TRAPPED rather than overcharged.
# --------------------------------------------------------------------------- #
class TestExtremeHold:
    REL = "cfb/run_extreme_hold.py"
    #: Q_TICKS tuples: (captured_at, bid, ask, fee_coefficient, slug)
    SPANNING = [(None, 0.90, 0.92, PRE, "s"), (None, 0.91, 0.93, POST, "s")]

    def test_a_window_spanning_the_raise_no_longer_traps(self):
        """★ THE DEFECT. The trap was `abs(r[3] - FEE) > 1e-9` on ANY tick, so a
        game with one pre-change tick was skipped whole and counted under TRAP.
        The fixture is one the old check fires on, so this test can fail."""
        assert any(abs(r[3] - POST) > 1e-9 for r in self.SPANNING)     # the old trap's own predicate
        fee_trap = _lift(self.REL, {"fee_trap"})["fee_trap"]
        assert fee_trap(self.SPANNING) is None
        src = _src(self.REL)
        assert "abs(r[3] - FEE)" not in src and "POLYMARKET_TAKER" not in src
        assert "trap = fee_trap(rows)" in src, "the loop does not run the trap it ships"

    def test_a_null_coefficient_still_traps_and_is_counted(self):
        fee_trap = _lift(self.REL, {"fee_trap"})["fee_trap"]
        label = fee_trap(self.SPANNING + [(None, 0.91, 0.93, None, "s")])
        assert label and label.startswith("TRAP") and "NULL" in label

    def test_each_entry_is_charged_at_its_own_ticks_coefficient(self):
        entry = _lift(self.REL, {"entry"})["entry"]
        win, paid, pm = 1.0, 0.93, 0.925
        pre, post = entry(win, paid, pm, PRE), entry(win, paid, pm, POST)
        assert pre["fe"] == pytest.approx(-PRE * paid * (1 - paid))
        assert post["fe"] == pytest.approx(-POST * paid * (1 - paid))
        assert pre["net"] - post["net"] == pytest.approx((POST - PRE) * paid * (1 - paid))
        assert pre["nm"] - post["nm"] == pytest.approx((POST - PRE) * pm * (1 - pm))
        assert (pre["fc"], post["fc"]) == (PRE, POST)                # the coefficient travels with the bet
        assert pre["net"] == pytest.approx(win - paid + pre["fe"])   # the exact split holds at either

    def test_an_entry_without_a_coefficient_is_refused(self):
        entry = _lift(self.REL, {"entry"})["entry"]
        with pytest.raises(ValueError):
            entry(1.0, 0.93, 0.925, None)

    def test_the_loop_and_the_break_even_read_the_ticks_own_coefficient(self):
        src = _src(self.REL)
        assert "fee_coefficient::float fc" in src                    # Q_TICKS carries it
        assert "FC = [r[3] for r in rows]" in src
        assert "entry(win, paid, pm, FC[i])" in src                  # the entry at ITS tick's
        assert 'recorded_fee(b["p"], b["fc"])' in src                # and the break-even too
        assert "coefficients on scored ticks" in src                 # the header says what was charged


# --------------------------------------------------------------------------- #
# run_ladder_calibration: importable, and its close query can be run for real.
# --------------------------------------------------------------------------- #
class TestLadderCalibration:
    ROW = dict(bid=0.48, ask=0.50, y=1)

    def test_a_close_is_charged_at_its_own_rows_coefficient(self):
        from cfb.run_ladder_calibration import taker_net
        pre = taker_net({**self.ROW, "fee_coefficient": PRE})
        post = taker_net({**self.ROW, "fee_coefficient": POST})
        assert pre[0] - post[0] == pytest.approx(100 * (POST - PRE) * 0.50 * 0.50)   # buy YES at the ask
        assert pre[1] - post[1] == pytest.approx(100 * (POST - PRE) * 0.48 * 0.52)   # buy NO at 1-bid
        assert pre[0] == pytest.approx(100 * (1 - 0.50 - PRE * 0.50 * 0.50))

    def test_a_close_without_a_coefficient_is_refused(self):
        from cfb.run_ladder_calibration import taker_net
        with pytest.raises(ValueError):
            taker_net({**self.ROW, "fee_coefficient": None})
        with pytest.raises(KeyError):
            taker_net(dict(self.ROW))                                # the column never selected

    def test_report_charges_through_taker_net_and_both_close_queries_select_the_column(self):
        from cfb import run_ladder_calibration as R
        assert "taker_net(r)" in inspect.getsource(R.report)
        for sql in (R.CLOSE_SQL, R.MLB_CLOSE_SQL):
            assert "fee_coefficient::float fee_coefficient" in sql
        assert not hasattr(R, "FEE") and "POLYMARKET_TAKER" not in inspect.getsource(R)

    def test_close_sql_returns_each_rows_coefficient_from_the_database(self):
        """The query as shipped, against the schema: two closes on one game, one
        row from each side of the raise, come back carrying their own value."""
        from sqlalchemy import text

        from cfb.run_ladder_calibration import CLOSE_SQL, TYPES, taker_net
        from core.storage import MarketSnapshot, get_engine, get_sessionmaker

        Session = get_sessionmaker(get_engine())
        vg, ko = "test-fee-per-row-vg", dt.datetime(2026, 9, 17, 16, 0, tzinfo=UTC)

        def _snap(slug, hours_before, coef):
            return MarketSnapshot(captured_at=ko - dt.timedelta(hours=hours_before), market_slug=slug,
                                  game_id=vg, sports_market_type=TYPES[0], best_bid=Decimal("0.48"),
                                  best_ask=Decimal("0.50"), fee_coefficient=Decimal(str(coef)), is_live=False)
        try:
            with Session() as s:
                s.add_all([_snap("test-fee-per-row-pre", 14, PRE), _snap("test-fee-per-row-post", 1, POST)])
                s.commit()
                rows = {r._mapping["market_slug"]: dict(r._mapping) for r in s.execute(
                    text(CLOSE_SQL), {"vg": vg, "lo": ko - dt.timedelta(days=3), "ko": ko, "types": list(TYPES)})}
        finally:
            with Session() as s:
                s.execute(text("delete from market_snapshots where game_id = :vg"), {"vg": vg})
                s.commit()
        assert rows["test-fee-per-row-pre"]["fee_coefficient"] == PRE
        assert rows["test-fee-per-row-post"]["fee_coefficient"] == POST
        for r in rows.values():
            r["y"] = 1
        yes_pre, yes_post = taker_net(rows["test-fee-per-row-pre"])[0], taker_net(rows["test-fee-per-row-post"])[0]
        assert yes_pre - yes_post == pytest.approx(100 * (POST - PRE) * 0.50 * 0.50)


# --------------------------------------------------------------------------- #
# run_ladder_rv: two legs are two rows, and can straddle the raise.
# --------------------------------------------------------------------------- #
class TestLadderRv:
    REL = "cfb/run_ladder_rv.py"

    def test_each_leg_is_charged_at_its_own_snapshots_coefficient(self):
        leg_fees = _lift(self.REL, {"leg_fees"})["leg_fees"]
        qa, qb = dict(bid=0.40, ask=0.44, fc=PRE), dict(bid=0.30, ask=0.34, fc=POST)   # the pair straddles the raise
        assert leg_fees("long", qa, qb) == pytest.approx(PRE * 0.40 * 0.60 + POST * 0.34 * 0.66)
        assert leg_fees("short", qa, qb) == pytest.approx(PRE * 0.44 * 0.56 + POST * 0.30 * 0.70)
        same = dict(bid=0.40, ask=0.44)
        pre = leg_fees("long", {**same, "fc": PRE}, {**same, "fc": PRE})
        post = leg_fees("long", {**same, "fc": POST}, {**same, "fc": POST})
        assert post - pre == pytest.approx((POST - PRE) * (0.40 * 0.60 + 0.44 * 0.56))

    def test_a_leg_without_a_coefficient_is_refused(self):
        leg_fees = _lift(self.REL, {"leg_fees"})["leg_fees"]
        with pytest.raises(ValueError):
            leg_fees("long", dict(bid=0.40, ask=0.44, fc=None), dict(bid=0.30, ask=0.34, fc=POST))
        with pytest.raises(KeyError):
            leg_fees("short", dict(bid=0.40, ask=0.44), dict(bid=0.30, ask=0.34, fc=POST))

    def test_the_ladder_select_carries_it_and_both_sides_charge_through_leg_fees(self):
        src = _src(self.REL)
        assert '"fee_coefficient::float AS fc "' in src
        assert 'leg_fees("long", qa, qb)' in src and 'leg_fees("short", qa, qb)' in src
        assert "TAKER_THETA" not in src and "POLYMARKET_TAKER" not in src
        assert "MAX_LEG_SPREAD = 0.06" in src      # a spread cap, not a fee: left alone on purpose


# --------------------------------------------------------------------------- #
# run_momentum_scalp: one trade, entry and taker exit on different ticks.
# --------------------------------------------------------------------------- #
class TestMomentumScalp:
    REL = "cfb/run_momentum_scalp.py"
    P_IN, P_OUT = 0.42, 0.45

    def _run(self, FC):
        """One YES trade: entry at tick 1 (ask 0.42), take-profit at tick 2 (bid 0.45)."""
        C, cells = defaultdict(int), defaultdict(list)
        ns = _lift(self.REL, {"trade"}, C=C, cells=cells, KS=(2, 5, 10), SS=(5, 10, 20),
                   S120=dt.timedelta(seconds=120), DBG=None, bisect_right=bisect_right)
        t0 = dt.datetime(2026, 9, 17, 4, 0, tzinfo=UTC)
        T = [t0 + dt.timedelta(seconds=10 * i) for i in range(4)]
        B, A = [0.40, 0.40, 0.45, 0.45], [0.42, 0.42, 0.47, 0.47]
        M = [(a + b) / 2 for a, b in zip(A, B)]
        ns["trade"]("T1", "YES", t0 + dt.timedelta(seconds=5), t0 + dt.timedelta(seconds=25),
                    T, B, A, M, FC, list(T), "g", None)
        return cells, C

    def test_entry_and_exit_are_charged_at_their_own_ticks(self):
        cells, _ = self._run([PRE, PRE, POST, POST])        # the trade straddles the raise
        (net, gross, fee_pct, kind, *_), = cells[("T1", "taker", 2, 5)]
        p_in, p_out = self.P_IN, self.P_OUT
        assert kind == "tp"
        assert fee_pct == pytest.approx(100 * (PRE * p_in * (1 - p_in) + POST * p_out * (1 - p_out)) / p_in)
        assert net == pytest.approx(gross - fee_pct)
        # the control: the same ticks all pre-change differ by exactly the exit's raise
        cells_pre, _ = self._run([PRE] * 4)
        assert fee_pct - cells_pre[("T1", "taker", 2, 5)][0][2] == pytest.approx(
            100 * (POST - PRE) * p_out * (1 - p_out) / p_in)

    def test_a_tick_without_a_coefficient_is_refused(self):
        with pytest.raises(ValueError):
            self._run([PRE, None, POST, POST])

    def test_the_tick_select_carries_it_and_only_the_fee_table_is_priced_now(self):
        src = _src(self.REL)
        assert "fee_coefficient::float fc" in src
        assert "def trade(arm, side, t_in, deadline, T, B, A, M, FC, chg, game, away_won)" in src
        assert src.count('FC, chg, g["eg"]') == 2, "both trade() call sites pass the per-tick column"
        assert "recorded_fee(p_in, FC[i])" in src and "recorded_fee(p_out, FC[j])" in src
        assert "taker_fee(p)" in src and "# fee-now: an illustration" in src and "def fee(" not in src \
            and "def fee_now" not in src   # the illustrative table is the only NOW-priced use, marked where it happens


# --------------------------------------------------------------------------- #
# run_slowside: the trade at minute t is priced from minute t's row.
# --------------------------------------------------------------------------- #
class TestSlowside:
    REL = "cfb/run_slowside.py"
    PREV, NOW, LATER = (0.50, 0.52), (0.50, 0.54), (0.53, 0.55)    # ask-led UP: buy the stale ask a1 = 0.54
    PX = 0.54

    def test_the_trade_is_charged_at_its_minutes_coefficient(self):
        observe = _lift(self.REL, {"observe"})["observe"]
        pre = observe((*self.PREV, PRE), (*self.NOW, PRE), (*self.LATER, PRE))
        post = observe((*self.PREV, POST), (*self.NOW, POST), (*self.LATER, POST))
        px = self.PX
        assert pre[0] == "ask-led" and pre[3] == post[3]                     # gross carries no fee
        assert pre[2] - post[2] == pytest.approx((POST - PRE) * px * (1 - px))
        assert pre[2] == pytest.approx(pre[3] - PRE * px * (1 - px))
        # only minute t's row prices the trade: the neighbours' coefficients change nothing
        mixed = observe((*self.PREV, POST), (*self.NOW, PRE), (*self.LATER, POST))
        assert mixed[2] == pytest.approx(pre[2])

    def test_a_minute_without_a_coefficient_is_refused(self):
        observe = _lift(self.REL, {"observe"})["observe"]
        with pytest.raises(ValueError):
            observe((*self.PREV, PRE), (*self.NOW, None), (*self.LATER, PRE))

    def test_a_sub_cent_move_is_still_no_observation(self):
        observe = _lift(self.REL, {"observe"})["observe"]
        assert observe((0.50, 0.52, PRE), (0.505, 0.52, PRE), (0.50, 0.52, PRE)) is None

    def test_the_select_and_the_minute_tuple_carry_it(self):
        src = _src(self.REL)
        assert "fee_coefficient::float AS fc" in src
        assert '(s["bid"], s["ask"], s["fc"])' in src
        assert "observe(minute[ks[i-1]], minute[ks[i]], minute[ks[i]+2])" in src
        assert "POLYMARKET_TAKER" not in src and "FEE * px" not in src
        assert "fee coefficients on tape" in src                            # the header says what was charged


# --------------------------------------------------------------------------- #
# run_cross_venue: the Polymarket leg per row; Kalshi has no such column.
# --------------------------------------------------------------------------- #
class TestCrossVenue:
    REL = "cfb/run_cross_venue.py"
    KB, KA, PB, PA = 0.40, 0.42, 0.60, 0.62      # YES at Kalshi's ask + NO at Polymarket's 1-bid is the cheaper arm

    def test_the_polymarket_leg_is_charged_at_its_sweeps_coefficient(self):
        dutch_cost = _lift(self.REL, {"fee", "dutch_cost"}, FK=KALSHI_TAKER)["dutch_cost"]
        kb, ka, pb, pa = self.KB, self.KA, self.PB, self.PA
        pre, post = dutch_cost(kb, ka, pb, pa, PRE), dutch_cost(kb, ka, pb, pa, POST)
        assert pre == pytest.approx(ka + (1 - pb) + KALSHI_TAKER * ka * (1 - ka) + PRE * pb * (1 - pb))
        assert post - pre == pytest.approx((POST - PRE) * pb * (1 - pb))    # only the Polymarket leg moved

    def test_a_sweep_without_a_coefficient_is_refused(self):
        dutch_cost = _lift(self.REL, {"fee", "dutch_cost"}, FK=KALSHI_TAKER)["dutch_cost"]
        with pytest.raises(ValueError):
            dutch_cost(self.KB, self.KA, self.PB, self.PA, None)

    def test_kalshi_stays_one_constant_because_its_snapshots_carry_no_fee_field(self):
        src = _src(self.REL)
        assert "fee_coefficient::float fc" in src                           # the Polymarket query
        assert "for tp, pb, pa, pc in ps" in src and "dutch_cost(kb, ka, pb, pa, pc)" in src
        assert "POLYMARKET_TAKER" not in src and re.search(r"\bFP\b", src) is None
        ks_query = src[src.index(' ks="""'):src.index(' pm="""')]
        assert "kalshi_snapshots" in ks_query
        assert "fee_multiplier" not in ks_query and "fee_type" not in ks_query
        assert "fee(ka, FK)" in src and "fee(bl, FK)" in src               # both Kalshi legs at FK


# --------------------------------------------------------------------------- #
# The bare-run fallbacks: the same strict contract, never a constant.
# --------------------------------------------------------------------------- #
GUARDED = ["cfb/run_ladder_calibration.py", "cfb/run_ladder_rv.py", "cfb/run_momentum_scalp.py",
           "cfb/run_slowside.py", "cfb/run_cross_venue.py"]


@pytest.mark.parametrize("rel", GUARDED)
def test_the_bare_run_bootstraps_the_repo_root_and_imports_the_one_recorded_fee(rel):
    """These five are piped into a container over stdin, where core/ may not be
    on sys.path. They used to keep an ImportError fallback copy of recorded_fee;
    a copy is a second place to be wrong, so each now puts the repo root on
    sys.path itself and imports the one function. No handler, no constant."""
    src = _src(rel)
    boot = src.find("sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))")
    imp = src.find("from core.fees import")
    assert 0 <= boot < imp, rel
    assert '"__file__" in globals()' in src[boot:imp], rel   # piped over stdin there is no __file__
    assert "except ImportError" not in src, rel
    tree = ast.parse(src)
    assert not [n for n in tree.body if isinstance(n, ast.Try)
                and any(isinstance(h.type, ast.Name) and h.type.id == "ImportError" for h in n.handlers)], rel


def test_extreme_hold_imports_core_unguarded_like_the_rest_of_its_imports():
    src = _src("cfb/run_extreme_hold.py")
    assert "from core.fees import recorded_fee" in src and "except ImportError" not in src
