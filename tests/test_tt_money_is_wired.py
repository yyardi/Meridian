"""A registered criterion the runner never calls is registered in name only.

core/tt/money.py shipped with 20 passing tests and NO CALLER: cfb/run_tt_elo.py
imported `elo, rule` and its SQL selected only the mid, so the money arm could
never have run — and the suite was green throughout, because the tests
exercised the module directly. These tests assert the WIRING, which is the only
thing that was ever missing.
"""
from __future__ import annotations

import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
RUN = importlib.import_module("cfb.run_tt_elo")
SRC = pathlib.Path(RUN.__file__).read_text(encoding="utf-8")


def test_the_runner_imports_the_money_arm():
    assert "money" in SRC.split("from core.tt import")[1].split("\n")[0]


def test_the_sql_selects_the_EXECUTABLE_sides_not_only_the_mid():
    """You buy YES at the ask and NO at 1-bid. A mid understates the bar by the
    half-spread, which is the whole quantity in dispute."""
    assert "best_bid, best_ask" in RUN.PRICE_SQL
    assert "captured_at < game_start_time" in RUN.PRICE_SQL, "entry must be PREGAME"


def test_money_prints_on_every_state_including_zero(capsys):
    """The four states must all PRINT. Silence at zero bets is how a criterion
    goes a month without anyone noticing it never ran."""
    RUN.BOOKS.clear()
    assert "NOT YET" in RUN._money_line([]) and "no book" in RUN._money_line([])

    RUN.BOOKS["s"] = (0.40, 0.42, 0.0695)
    assert "0 eligible" in RUN._money_line([])
    RUN.BOOKS.clear()


def test_the_money_arm_is_not_gated_on_the_signal_verdict():
    """Conditioning the money arm on a signal PASS selects on the same outcomes
    the signal was read from. It must run regardless."""
    body = SRC[SRC.index("MONEY"):SRC.index("MONEY") + 400]
    assert "_money_line(ok)" in SRC
    for gate in ("if v ==", "if excludes", "if verdict =="):
        assert gate not in body, f"money arm must not be gated on {gate!r}"


def test_report_emits_a_money_line_per_competition(capsys):
    """End to end through report(), which is what the cron actually calls."""
    import datetime as dt
    from core.tt import elo
    ms = [elo.Match(f"aec-setkameua-aaa{i:03d}-bbb{i:03d}-2026-09-14",
                    "setkameua", f"aaa{i:03d}", f"bbb{i:03d}", i % 2,
                    dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc), 0.5)
          for i in range(4)]
    RUN.BOOKS.clear()
    RUN.report(ms, None)
    out = capsys.readouterr().out
    assert out.count("MONEY") >= 1, "report() printed no MONEY line"
    assert "NOT YET" in out
