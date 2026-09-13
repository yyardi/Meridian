"""The daily mlb mode is a contract with the crontab, so pin it here.

Bash is not unit-testable from pytest, but the three things that would silently
break the daily run ARE checkable as text: the mode exists, it returns before
the football block, and it runs in the container that has a venue client.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

SH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "prod_weekend_read.sh"
TEXT = SH.read_text(encoding="utf-8")


def test_the_script_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(SH)]).returncode == 0


def test_the_mlb_mode_exists_and_is_documented_with_its_cron_time():
    assert 'if [ "$MODE" = mlb ]; then' in TEXT
    assert re.search(r"^#\s+40 10 \* \* \*\s+/opt/meridian/scripts/prod_weekend_read\.sh mlb$",
                     TEXT, re.M), "the crontab line the operator pastes must stay in the header"


def test_mlb_returns_before_the_football_block():
    """A daily 10:40Z run must not fall through into the weekend gate, which is
    a long job and would also run on six days it was never meant to."""
    start = TEXT.index('if [ "$MODE" = mlb ]; then')
    assert "exit 0" in TEXT[start:TEXT.index("# 0. coverage", start)]
    assert TEXT.index("# 0. coverage", start) > start


def test_both_mlb_jobs_run_where_the_venue_client_lives():
    """Settlement comes from the venue for both, and the trainer image has no
    venue client -- that is why the football calibration runs in trainer and
    these two do not."""
    block = TEXT[TEXT.index('if [ "$MODE" = mlb ]; then'):TEXT.index("# 0. coverage")]
    for script in ("cfb/run_paper_book.py", "cfb/run_ladder_calibration.py"):
        line = next(l for l in block.splitlines() if script in l)
        assert "meridian-api" in line, f"{script} must run in the api container"
    assert "LEAGUES=mlb" in block and "LEAGUE=mlb" in block


def test_the_mlb_block_does_not_touch_a_recorder():
    block = TEXT[TEXT.index('if [ "$MODE" = mlb ]; then'):TEXT.index("# 0. coverage")]
    assert not re.search(r"docker (compose|restart|stop|start|run)\b", block)
    assert "recorder" not in block.lower()
