"""The nightly fee-drift line: agreement, drift, and silence told apart.

    pytest --noconftest tests/test_fee_drift.py
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts import fee_drift  # noqa: E402

T0 = dt.datetime(2026, 9, 21, 4, 0, tzinfo=dt.timezone.utc)
T1 = dt.datetime(2026, 9, 22, 3, 59, tzinfo=dt.timezone.utc)


def test_every_recorded_coefficient_equal_to_the_constant_is_ok():
    line, code = fee_drift.verdict([(0.0695, 1_234_567, T0, T1)], constant=0.0695)
    assert code == 0 and line.startswith("FEE OK") and "1,234,567" in line


def test_the_venue_s_own_change_would_have_been_caught_the_next_morning():
    """The 2026-09-17 shape: the old value until 04:00Z, the new one after."""
    rows = [(0.0695, 528_563, T0.replace(hour=4, minute=7), T1),
            (0.06, 57_257, T0.replace(hour=0), T0.replace(hour=4))]
    line, code = fee_drift.verdict(rows, constant=0.06)
    assert code == 2 and line.startswith("FEE DRIFT")
    assert "0.0695 on 528,563 rows" in line and "update core/fees.py" in line


def test_a_numeric_type_from_the_driver_compares_as_a_number():
    from decimal import Decimal
    line, code = fee_drift.verdict([(Decimal("0.069500"), 10, T0, T1)], constant=0.0695)
    assert code == 0, line


def test_silence_is_not_agreement():
    line, code = fee_drift.verdict([], constant=0.0695)
    assert code == 1 and line.startswith("FEE UNKNOWN")


def test_the_default_constant_is_the_one_in_core_fees():
    from core.fees import POLYMARKET_TAKER
    line, code = fee_drift.verdict([(POLYMARKET_TAKER, 1, T0, T1)])
    assert code == 0


def test_the_sql_prunes_on_a_month_boundary_and_windows_on_a_day():
    assert "date_trunc('month', now() - interval '1 day')" in fee_drift.SQL
    assert "captured_at >= now() - interval '1 day'" in fee_drift.SQL
    assert "fee_coefficient IS NOT NULL" in fee_drift.SQL
