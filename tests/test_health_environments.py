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
