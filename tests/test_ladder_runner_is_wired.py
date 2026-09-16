"""The scanner module must have a caller, and the caller must place nothing.

core/tt/money.py shipped with 20 green tests and no importer outside its own
test file, so a registered criterion could never fire (STATUS §0be). This file
exists so core/ladder/ cannot repeat it: a module nothing calls is a module
that does nothing, and no test of the module itself can tell.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUN = ROOT / "cfb" / "run_ladder_scan.py"
SRC = RUN.read_text(encoding="utf-8")


def test_the_runner_exists_and_imports_the_module():
    assert "from core.ladder import scan" in SRC


def test_the_module_has_a_caller_outside_its_own_tests():
    """The exact check that would have caught the money-arm defect."""
    callers = [p for p in ROOT.rglob("*.py")
               if "core/ladder" not in str(p) and not p.name.startswith("test_")
               and "core.ladder" in p.read_text(encoding="utf-8", errors="ignore")]
    assert callers, "core.ladder has no caller outside its own package"


def test_it_runs_and_reports_rather_than_crashing():
    r = subprocess.run([sys.executable, str(RUN), "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "--league" in r.stdout


def test_legs_come_from_ONE_timestamp():
    """A ladder assembled across timestamps is not an arbitrage. The dict must
    be keyed on (game, captured_at), not on game alone."""
    assert "snaps[(gid, ts)]" in SRC
    assert re.search(r"defaultdict\(dict\)", SRC)


def test_depth_uses_max_not_a_bare_subquery():
    """book_levels has duplicate level_index=0 rows -- worst 27 on NFL. A
    scalar subquery raises 'more than one row returned'."""
    assert SRC.count("SELECT max(quantity)") == 2


def test_the_runner_cannot_place_an_order():
    for bad in ("place_order", "PolymarketGateway", "requests.post", "MERIDIAN_ORDER_TOKEN"):
        assert bad not in SRC


def test_it_says_the_size_is_quoted_rather_than_filled():
    """The one thing a reader must not assume. §0bj measured no consumption."""
    assert "QUOTED, NOT FILLED" in SRC
