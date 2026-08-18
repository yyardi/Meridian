"""Writer path == reader path, for the analytics blob.

The model-performance page reported "run `python -m core.analytics` first"
while the operator was running exactly that, successfully, on the host. Both
sides were already routed through `core/paths.py` and both spelled the path
the same way — and they still resolved to different files, because the writer
runs on the host and the reader runs in a container that had no mount for the
artifact root. Symbolic agreement is not the property that matters; landing on
the same bytes is.

So this pins the contract at both levels, the same way `tests/test_paths.py`
pins the postgres staging mount:

* **In process** — write through the writer's resolution, read through the
  endpoint, and require the endpoint to hand back what was written.
* **In compose** — the api container gets *both* halves (the bind and the
  ``MERIDIAN_DATA_DIR`` that makes `data_dir()` point at it). Either half
  alone silently reinstates the bug.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import paths
from core.api import app

REPO = Path(paths.__file__).resolve().parent.parent


@pytest.fixture
def client():
    return TestClient(app)


def test_the_filename_is_written_down_exactly_once():
    """One literal, in `core/paths.py`. A second one is how the two sides
    drifted apart the first time — they can agree today and diverge in a
    refactor that only touches one of them."""
    offenders = [
        p.relative_to(REPO)
        for p in (REPO / "core").rglob("*.py")
        if p.name != "paths.py" and "analytics.json" in p.read_text()
    ]
    assert not offenders, f"analytics.json named outside core/paths.py: {offenders}"


def test_writer_and_reader_agree_on_the_path(client, tmp_path, monkeypatch):
    """The endpoint reports the path it looked in; it must be the one
    `analytics_path()` hands the writer."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path))
    body = client.get("/api/analytics").json()
    assert body["looked_in"] == str(paths.analytics_path())
    assert Path(body["looked_in"]).parent == tmp_path / "reports"


def test_the_page_reads_what_the_writer_wrote(client, tmp_path, monkeypatch):
    """End to end: the bytes the writer's resolution produces are the bytes
    the page gets back. This is the test that would have gone red."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path))

    out = paths.analytics_path()          # writer's resolution
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": {"bets": 7, "roi": -0.11}}))

    body = client.get("/api/analytics").json()   # reader's resolution
    assert "error" not in body
    assert body["summary"]["bets"] == 7


def test_resolution_is_per_call_on_both_sides(client, tmp_path, monkeypatch):
    """Neither side may bind the path at import. `core/analytics.py` did —
    a module-level ``OUT = reports_dir() / ...`` — which made the writer deaf
    to any environment set after import, containers included."""
    first = tmp_path / "one"
    second = tmp_path / "two"
    for root in (first, second):
        (root / "reports").mkdir(parents=True)

    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(first))
    (first / "reports" / "analytics.json").write_text('{"summary": {"bets": 1}}')
    assert client.get("/api/analytics").json()["summary"]["bets"] == 1

    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(second))
    (second / "reports" / "analytics.json").write_text('{"summary": {"bets": 2}}')
    assert client.get("/api/analytics").json()["summary"]["bets"] == 2


def test_a_missing_blob_names_the_path_it_wanted(client, tmp_path, monkeypatch):
    """The original error said only "run `python -m core.analytics` first",
    which is indistinguishable from "I ran it and cannot see the result" —
    and sent the operator to re-run a job that had already worked."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path))
    (tmp_path / "reports").mkdir()

    body = client.get("/api/analytics").json()
    assert str(tmp_path) in body["error"]
    assert body["data_dir_exists"] is True


def test_a_missing_root_is_reported_as_a_mount_problem(client, tmp_path, monkeypatch):
    """No artifact root at all is the container symptom, not the "never built"
    one, and the message has to separate them."""
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path / "not-mounted"))

    body = client.get("/api/analytics").json()
    assert body["data_dir_exists"] is False
    assert paths.DATA_DIR_CONTAINER in body["error"]


def test_compose_gives_the_api_both_halves_of_the_mount():
    """The bind alone is not enough. Without ``MERIDIAN_DATA_DIR`` set inside
    the container, `data_dir()` falls back to ``/app/backups`` — not the mount
    — and the page breaks again with the volume sitting right there."""
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())
    api = compose["services"]["api"]

    mount = f"${{MERIDIAN_DATA_DIR:-./backups}}/reports:{paths.DATA_DIR_CONTAINER}/reports:ro"
    assert mount in api["volumes"], "api must see the host reports subtree"
    assert api["environment"]["MERIDIAN_DATA_DIR"] == paths.DATA_DIR_CONTAINER

    # Read-only: the api serves this artifact and never produces it.
    assert all(v.endswith(":ro") for v in api["volumes"])


def test_the_api_is_given_reports_and_nothing_else():
    """Least privilege, and not a style preference.

    The api reads exactly one artifact and serves every other file from the
    image's own `static/`. Mounting the whole root would additionally hand an
    unauthenticated service — bound to all interfaces so the dashboard is
    reachable over the tailnet — read access to the database dumps under
    `ticks/` and `supabase/`, for no benefit whatsoever.
    """
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text())

    for volume in compose["services"]["api"]["volumes"]:
        # rsplit, not split: the host side is `${MERIDIAN_DATA_DIR:-./backups}`
        # and compose's default-value syntax contains a colon of its own.
        host_side, container_side, _mode = volume.rsplit(":", 2)
        assert host_side.endswith("/reports"), (
            f"api mounts {host_side!r}; it needs reports/ and nothing else"
        )
        assert container_side == f"{paths.DATA_DIR_CONTAINER}/reports"
