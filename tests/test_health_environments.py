"""health.py knows which machine it is on, and says so calmly.

The bug this pins
-----------------
Production moved to EC2 and the laptop stack was deliberately stopped. Running
`scripts/health.py` on the laptop then printed **eight DEAD lines** describing
containers nobody intended to be running, and a red `SOMETHING IS DOWN`
verdict. Red that means "working as intended" is worse than no check at all:
it teaches the operator that the first-touch surface of the morning is noise.

So the retired state is a *state*, not a failure — one line, green verdict, and
a pointer at the machine that does matter.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

from core.healthchecks import MAX_DISK_USED_PCT, OK, WARN, check_disk_headroom

_HEALTH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "health.py"


def _load_health():
    """scripts/ is not a package, so load the module by path."""
    spec = importlib.util.spec_from_file_location("meridian_health", _HEALTH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["meridian_health"] = mod
    spec.loader.exec_module(mod)
    return mod


health = _load_health()


# ------------------------------------------------------------------ #
# Which machine am I on
# ------------------------------------------------------------------ #


def test_explicit_flag_beats_the_guess():
    """Someone who knows where they are outranks sys.platform. The guess is a
    convenience, not an authority."""
    assert health.detect_environment("server") == "server"
    assert health.detect_environment("laptop") == "laptop"


def test_falls_back_to_the_platform(monkeypatch):
    monkeypatch.setattr(health.sys, "platform", "darwin")
    assert health.detect_environment(None) == "laptop"
    monkeypatch.setattr(health.sys, "platform", "linux")
    assert health.detect_environment(None) == "server"


# ------------------------------------------------------------------ #
# The retired stack
# ------------------------------------------------------------------ #


def test_retired_note_points_at_the_machine_that_matters():
    """The whole value is in the sentence. If it does not name the replacement,
    the operator is left with 'not here' and nowhere to go."""
    assert "retired" in health.RETIRED_NOTE
    assert "deploy/aws/health.sh" in health.RETIRED_NOTE


def test_retired_laptop_reports_all_good_and_runs_no_checks(monkeypatch, capsys):
    """Zero containers up ON THE LAPTOP is intentional, so the verdict is green
    and the expensive checks are never reached.

    `todays_games` is patched to explode: if the retired path ever stops
    short-circuiting, this test fails loudly rather than passing slowly.
    """
    def _containers():
        _containers.up_count = 0
        _containers.expected_count = 8
        return []
    monkeypatch.setattr(health, "check_containers", _containers)
    monkeypatch.setattr(health, "todays_games",
                        lambda: pytest.fail("retired path must not run checks"))
    monkeypatch.setattr(health.sys, "argv", ["health.py", "--laptop"])

    assert health.main() == 0
    out = capsys.readouterr().out
    assert health.RETIRED_NOTE in out
    assert "ALL GOOD" in out
    assert "DEAD" not in out


def test_a_stopped_SERVER_stack_is_still_an_outage(monkeypatch, capsys):
    """The calm path is laptop-only, and that asymmetry is the point. Nothing
    running on the server is a real emergency, and must not be softened by the
    same branch."""
    def _containers():
        _containers.up_count = 0
        _containers.expected_count = 8
        from core.healthchecks import DEAD, Check
        return [Check(DEAD, "api", "NOT RUNNING")]
    monkeypatch.setattr(health, "check_containers", _containers)
    monkeypatch.setattr(health, "todays_games", lambda: ([], False))
    for name in ("check_espn", "check_book_lines", "check_app_heartbeats",
                 "check_local_pg_size", "check_retention", "check_real_orders",
                 "check_fill_watcher", "check_uptime", "check_docker_enabled",
                 "check_disk", "check_disk_headroom"):
        monkeypatch.setattr(health, name, lambda *a, **k: [])
    monkeypatch.setattr(health, "check_primary_db", lambda live: [])
    monkeypatch.setattr(health, "check_local_ticks", lambda live: [])
    monkeypatch.setattr(health.sys, "argv", ["health.py", "--server"])

    assert health.main() == 1, "a dead server stack must exit non-zero"
    assert health.RETIRED_NOTE not in capsys.readouterr().out


# ------------------------------------------------------------------ #
# Disk as a ratio
# ------------------------------------------------------------------ #


def test_disk_headroom_is_a_percentage_not_an_absolute(monkeypatch):
    """20 GB free is comfortable on a 1 TB laptop and nearly full on the
    server's 100 GB volume. Only the ratio travels between them."""
    import core.healthchecks as hc

    monkeypatch.setattr(hc.shutil, "disk_usage",
                        lambda p: (100_000_000_000, 95_000_000_000, 5_000_000_000))
    assert check_disk_headroom("/")[0].status == WARN

    monkeypatch.setattr(hc.shutil, "disk_usage",
                        lambda p: (1_000_000_000_000, 500_000_000_000, 500_000_000_000))
    assert check_disk_headroom("/")[0].status == OK


def test_the_warning_threshold_is_the_one_the_runbook_promises():
    assert MAX_DISK_USED_PCT == 80.0


def test_health_names_every_container_compose_defines():
    """A container health.py does not name is one it cannot report on.

    Five were missing on 2026-09-13 — MLB, both football ESPN feeds, both
    football odds recorders — so `docker compose ps` could show every one of
    them dead and health.py would still print a clean bill. The list is
    hand-kept, and a hand-kept inventory of a thing that grows weekly drifts
    in ONE direction: toward blindness, silently, because the missing row
    cannot report its own absence.

    Checked both ways on purpose. A name expected here with no compose service
    behind it is the mirror defect — a row that can only ever read DEAD — and
    that is the noise this module's docstring exists to prevent. Either
    direction is a failure; neither is visible by reading the file.
    """
    import re

    repo = pathlib.Path(__file__).resolve().parent.parent
    compose = {
        m.group(1)
        for f in repo.glob("docker-compose*.yml")
        for m in re.finditer(r"container_name:\s*(\S+)", f.read_text())
    }
    assert compose, "no compose files parsed — the check would pass vacuously"

    src = _HEALTH.read_text()
    block = src[src.index("    expected = {"):]
    block = block[: block.index("\n    }\n")]
    expected = set(re.findall(r'^\s*"(meridian-[^"]+)":', block, re.M))

    assert not compose - expected, (
        "compose defines containers health.py cannot report on: "
        f"{sorted(compose - expected)}")
    assert not expected - compose, (
        "health.py expects containers no compose file defines — these can "
        f"only ever read DEAD: {sorted(expected - compose)}")


def test_the_archive_readme_names_only_files_that_exist():
    """A README naming scripts that are not there is worse than no README.

    Three rows in analysis/archive/README.md described `capture_is_not_a_proxy
    .py`, `placement_curve_real_fills.py` and `flattening_book_insertion.py` as
    "live" — reproduce-these-first entries for files absent from the directory,
    from the repo, and from git's deletion history. Anyone following the
    README's own instruction ("before running one, check whether its finding
    still stands") hit nothing at all.

    Backticked `.py` names are the checkable surface, which is why the note
    about the removed three spells them without backticks.
    """
    import re

    d = pathlib.Path(__file__).resolve().parent.parent / "analysis" / "archive"
    named = set(re.findall(r"`([A-Za-z0-9_]+\.py)`", (d / "README.md").read_text()))
    assert named, "no filenames parsed — the check would pass vacuously"
    missing = sorted(n for n in named if not (d / n).exists())
    assert not missing, f"README names files that are not in the directory: {missing}"
