"""The one-artifact-root contract (core/paths.py).

Every writer routes through these helpers, and the compose mounts are written
against them — so the contract pinned here is what keeps a pg_dump inside the
container landing where the host-side job looks for it.
"""

from __future__ import annotations

from pathlib import Path

from core import paths


def test_default_root_is_repo_backups(monkeypatch):
    monkeypatch.delenv("MERIDIAN_DATA_DIR", raising=False)
    root = paths.data_dir()
    assert root.name == "backups"
    assert (root.parent / "core" / "paths.py").exists(), "anchored at the repo root"


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("MERIDIAN_DATA_DIR", "/somewhere/else")
    assert paths.data_dir() == Path("/somewhere/else")
    assert paths.ticks_dir() == Path("/somewhere/else/ticks")
    assert paths.supabase_dir() == Path("/somewhere/else/supabase")
    assert paths.reports_dir() == Path("/somewhere/else/reports")
    assert paths.exports_dir() == Path("/somewhere/else/exports")


def test_exports_has_no_container_side():
    """`exports/` is host-only: written by a script, opened by a human. Unlike
    `analytics_path()` there is nothing in a container to agree with, so it
    gets no DATA_DIR_CONTAINER counterpart and no compose mount. Adding one
    would widen a container's view of the artifact root to protect nothing —
    the api's mount was narrowed to reports/ for exactly that reason."""
    compose = (Path(paths.__file__).parent.parent / "docker-compose.yml").read_text()
    assert "/exports" not in compose


def test_the_writer_routes_through_the_helper():
    """No hardcoded exports path may creep back into the export script — the
    same rule the retention job is held to below."""
    src = (Path(paths.__file__).parent.parent
           / "scripts" / "export_wnba_trades.py").read_text()
    assert "exports_dir()" in src
    assert '/ "exports"' not in src


def test_blank_override_falls_back(monkeypatch):
    """An empty env var (easy to produce from compose interpolation) must not
    resolve the root to the current working directory."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", "  ")
    assert paths.data_dir().name == "backups"


def test_resolution_is_per_call_not_import_time(monkeypatch):
    monkeypatch.delenv("MERIDIAN_DATA_DIR", raising=False)
    before = paths.data_dir()
    monkeypatch.setenv("MERIDIAN_DATA_DIR", "/late/override")
    assert paths.data_dir() == Path("/late/override") != before


def test_archive_subtrees_are_exactly_two():
    """The operator's rule: archives live in supabase/ and ticks/, nothing
    else. reports/ is a regenerable-output subtree, not an archive."""
    archive_helpers = {paths.ticks_dir().name, paths.supabase_dir().name}
    assert archive_helpers == {"ticks", "supabase"}


def test_container_side_matches_compose():
    """BACKUP_DIR_CONTAINER and the compose bind must move together."""
    assert paths.BACKUP_DIR_CONTAINER == "/backups"
    compose = (Path(paths.__file__).parent.parent / "docker-compose.yml").read_text()
    assert "${MERIDIAN_DATA_DIR:-./backups}/ticks:/backups" in compose


def test_retention_routes_through_the_helpers():
    """No hardcoded backups/ paths may creep back into the retention job."""
    src = (Path(paths.__file__).parent / "retention.py").read_text()
    assert 'parent / "backups"' not in src
    assert "ticks_dir()" in src and "supabase_dir()" in src
