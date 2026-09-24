"""A read that a document calls nightly is in a cron script, or the document lies.

    pytest --noconftest tests/test_nightly_reads_are_wired.py

2026-09-24: two WNBA reads were built, run once, and reported to the operator
as rerunning nightly; nothing called them. A description has no test, so this
is the test.
"""
from __future__ import annotations

import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
NIGHTLY = {
    "cfb/run_pulse_live_scorecard.py": "scripts/nightly_scan.sh",
    "cfb/run_wnba_player_model.py": "scripts/nightly_scan.sh",
    "cfb/run_paper_book.py": "scripts/nightly_scan.sh",
    "scripts/fee_drift.py": "scripts/launchers/slate_verdict.sh",
    "scripts/edge_ledger.py": "scripts/launchers/slate_verdict.sh",
}


def test_every_read_called_nightly_is_named_in_its_cron_script():
    for runner, script in NIGHTLY.items():
        assert (ROOT / runner).exists(), runner
        src = (ROOT / script).read_text()
        assert pathlib.Path(runner).name in src, f"{runner} is documented as nightly and {script} does not run it"


def test_the_cron_scripts_are_valid_bash():
    for script in set(NIGHTLY.values()):
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)
