"""The live-FV engines must not be able to pull the web app in.

    pytest --noconftest tests/test_engine_coupling.py

`_human_market` lived in `core/api.py`, and both engines imported it INSIDE A
FUNCTION. Every import-time graph looked clean; the cost was paid on the first
call, when a price engine loaded FastAPI.

Measured on this tree before the move:

    core.live_fv alone            9 project modules, 1,060 total
    once core.api was pulled in  34 project modules, 1,426 total, fastapi loaded

A function-local import is invisible to exactly the check you would reach for,
so these run the import in a SUBPROCESS and read `sys.modules` -- an in-process
assertion would pass or fail on whatever an earlier test had already imported.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

ENGINES = ["core.live_fv", "core.live_totals_fv"]


def _probe(code: str):
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                         capture_output=True, text=True, cwd=".")
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout.strip()


@pytest.mark.parametrize("mod", ENGINES)
def test_importing_an_engine_does_not_import_the_web_app(mod):
    got = _probe(f"""
        import sys
        sys.path.insert(0, '.')
        import {mod}
        print('core.api' in sys.modules, 'fastapi' in sys.modules)
    """)
    assert got == "False False", f"{mod} pulled in {got}"


@pytest.mark.parametrize("mod", ENGINES)
def test_the_module_no_longer_names_core_api_at_all(mod):
    """The import was function-local, so absence from sys.modules is necessary
    and not sufficient -- an untaken branch would still pass the check above."""
    src = open(mod.replace(".", "/") + ".py", encoding="utf-8").read()
    assert "from core.api import" not in src
    assert "import core.api" not in src


@pytest.mark.parametrize("mod", ENGINES)
def test_calling_the_labeller_still_does_not_reach_the_web_app(mod):
    """The real test of the cut: run the thing the engine actually calls."""
    got = _probe(f"""
        import sys
        sys.path.insert(0, '.')
        import {mod}
        from core.team_mapping import human_market
        human_market('asc-wnba-ny-phx-2026-08-18-pos-10pt5',
                     'basketball_team_full_game_spread', 10.5)
        print('core.api' in sys.modules, 'fastapi' in sys.modules)
    """)
    assert got == "False False"


def test_the_labeller_is_cheap_where_it_now_lives():
    n = int(_probe("""
        import sys
        sys.path.insert(0, '.')
        from core.team_mapping import human_market
        print(len([k for k in sys.modules if k.split('.')[0] == 'core']))
    """))
    assert n <= 6, f"core.team_mapping now costs {n} core modules"


# ------------------------------------------------------- behaviour unchanged
@pytest.mark.parametrize("slug, mtype, line, want", [
    ("tsc-wnba-ny-phx-2026-08-18-191pt5", "basketball_team_full_game_total", 191.5, "Total 191.5"),
    ("tsc-wnba-ny-phx-2026-08-18", "basketball_team_full_game_total", None, "Total"),
    ("aec-wnba-ny-phx-2026-08-18", "basketball_team_full_game_winner", None, "NY to win"),
    ("asc-wnba-ny-phx-2026-08-18-pos-10pt5", "basketball_team_full_game_spread", 10.5, "NY +10.5"),
    ("asc-wnba-ny-phx-2026-08-18-neg-10pt5", "basketball_team_full_game_spread", 10.5, "NY -10.5"),
    ("asc-wnba-ny-phx-2026-08-18-pos-10pt5", "basketball_team_full_game_spread", None, "NY spread"),
    ("something-else", None, None, "something-else"),
])
def test_every_label_shape_is_what_it_was(slug, mtype, line, want):
    from core.team_mapping import human_market
    assert human_market(slug, mtype, line) == want


def test_pos_still_means_getting_the_points():
    """The reason this function exists: `ny-phx-pos-10pt5` reads as 'NY by 10.5'
    and means NY +10.5. Opposite bets."""
    from core.team_mapping import human_market
    assert human_market("asc-wnba-ny-phx-2026-08-18-pos-10pt5",
                        "basketball_team_full_game_spread", 10.5).endswith("+10.5")


def test_the_api_keeps_its_own_name_so_its_call_sites_did_not_churn():
    import core.api
    from core.team_mapping import human_market
    assert core.api._human_market is human_market
