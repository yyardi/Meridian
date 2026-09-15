"""A nomination in a push must carry its NUMBER and its confound caution.

MLB stood at 23 settled games on 2026-09-15 against the paper book's G>=25
floor, and the arm closest to nominating was mlb_spread_yes_70_100 at +15.51c —
the away-team confound, which has produced three "excludes 0" headlines already.
The push named the arm and nothing else, so the first thing the operator would
have seen is a strategy name with no number and no warning.

These pin the PUSH only. The gate is deliberately untouched: tuning a decision
rule around the arm you can see about to trip it is how a rule stops being
pre-registered.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "nightly_scan.sh"
TEXT = SH.read_text(encoding="utf-8")
BLOCK = TEXT[TEXT.index('if [ "$PB_POS" -gt 0 ]'):TEXT.index("# --- the push")]

#: the real shape, copied from artifacts/reads/paper_book_2026-09-15T0440Z.txt
REAL = ("wnba_spread_yes_80_100       101    40        93    +5.84   +0.063"
        "      +5.78 [+2.96, +8.60]   POSITIVE, excludes 0")


def test_valid_bash():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_the_awk_offsets_pick_the_MEAN_and_the_INTERVAL():
    """Counted wrong by hand once: NF-4/NF-3/NF-2 yields the interval and the
    word POSITIVE. Pinned against the real line so the offsets cannot drift."""
    out = subprocess.run(
        ["awk", '{printf "%s %s %s%s", $1, $(NF-5), $(NF-4), $(NF-3)}'],
        input=REAL, capture_output=True, text=True).stdout
    assert out == "wnba_spread_yes_80_100 +5.78 [+2.96,+8.60]", out
    assert "POSITIVE" not in out


def test_the_script_uses_those_offsets():
    assert "$(NF-5), $(NF-4), $(NF-3)" in BLOCK


def test_a_yes_side_nomination_carries_the_away_caution():
    assert 'grep -q "_yes_"' in BLOCK
    assert "AWAY" in BLOCK and "home twin" in BLOCK


def test_the_caution_keys_on_the_shape_not_on_a_named_arm():
    """It must fire for arms that do not exist yet. A caution listing today's
    suspects is a caution that silently stops applying."""
    for arm in ("mlb_spread_yes_70_100", "wnba_spread_yes_80_100"):
        assert arm not in BLOCK, f"{arm} hardcoded; key on _yes_ instead"


def test_the_gate_itself_is_untouched():
    """The paper book nominates on G>=25 AND excludes 0, and prints the twin
    beside rather than gating on it. This change must not have moved that."""
    assert "PB_POS" in BLOCK and "excludes 0" in TEXT
    assert "G >= 25" not in BLOCK and "MIN_G" not in BLOCK
