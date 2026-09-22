"""The launchers name their containers after the game, whatever the league's tag length.

    pytest --noconftest tests/test_launcher_names.py

2026-09-21 23:58Z: `sexec--atl-ny-2026-09-21`. The launchers cut the slug at a
fixed offset of 8, which is `aec-mlb-` / `aec-nfl-` / `aec-cfb-` but one short
of `aec-wnba-`, so every WNBA container carried a leading hyphen. Cosmetic in
docker ps and nowhere else (nothing matches these names), but a name that is
wrong for one league is the kind of thing that becomes a matcher later.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHERS = {
    "scripts/launchers/launch_stream_exec.sh": ["sexec"],
    "scripts/launchers/launch_sampler.sh": ["sampler"],
    "scripts/launchers/launch_ladder.sh": ["ladder", "wsfresh"],
}
GAMES = ["aec-mlb-tor-bal-2026-09-21", "aec-wnba-atl-ny-2026-09-21", "aec-nfl-nyg-lar-2026-09-21",
         "aec-cfb-southern-miss-appalachian-state-2026-09-19"]


def _name(script: str, prefix: str, slug: str) -> str:
    src = (ROOT / script).read_text()
    m = re.search(r'--name "' + prefix + r'-(\$\{[^}]+\})"', src)
    assert m, (script, prefix)
    g = re.search(r"^G=(.*?)(\s+#.*)?$", src, re.M)
    assert g, f"{script} derives no G"
    out = subprocess.run(["bash", "-c", f'S="{slug}"; G={g.group(1)}; echo "{prefix}-{m.group(1)}"'],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_every_launcher_names_the_container_after_the_game_for_every_league_tag_length():
    for script, prefixes in LAUNCHERS.items():
        for prefix in prefixes:
            for slug in GAMES:
                name = _name(script, prefix, slug)
                game = slug.split("-", 2)[2]
                assert "--" not in name and name.startswith(f"{prefix}-{game[:20]}"), (script, slug, name)
                assert len(name) <= len(prefix) + 21


def test_the_fixed_offset_is_gone():
    for script in LAUNCHERS:
        assert "${S:8:20}" not in (ROOT / script).read_text(), script
