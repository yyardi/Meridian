"""One root for everything the system writes to disk.

Before this module, artifact folders sprawled: ``backups/supabase``,
``backups/supabase-final``, ``backups/supabase-live-archive-2026-08-05``,
loose ``pre-migrate-*.sql`` at the backups root, plus ``reports/``,
``recorder-logs/`` and a dead ``data/`` — each path hardcoded where it was
used. Consolidated 2026-08-17 at the operator's request.

The rules:

* **One root**: ``MERIDIAN_DATA_DIR`` (default ``<repo>/backups``). Nothing in
  ``core/`` may create a new top-level folder in the repo.
* **Archives live in exactly two subtrees** — ``supabase/`` (the primary's
  rolling CSV archives, plus the operator's hand-filed exports) and ``ticks/``
  (the local monthly partition dumps, and the container staging mount).
  The retention invariant applies to both: nothing here is ever deleted
  without a verified copy, so movers rename and never remove.
* Generated, regenerable artifacts (``reports/analytics.json``) get their own
  subtree under the same root — they are outputs, not archives, and can be
  rebuilt from the database at any time.

  **"Generated" does not imply "regenerable", and the distinction is a
  deletion hazard.** ``reports/`` is safe to clear because every byte of it
  can be rebuilt by re-running a job. A future subtree holding generated
  output that carries anything a human typed — an annotated export, a sheet
  with the operator's reasoning in it — cannot be rebuilt by anything, and a
  retention rule copied from ``reports/`` on the strength of both being
  "outputs" would destroy the only irreplaceable thing under this root.
  Check regenerability per subtree, never by category.

The docker-compose mounts must agree with these paths: the postgres container
stages dumps at ``/backups`` which compose binds to ``$MERIDIAN_DATA_DIR/ticks``,
and the api container sees ``reports/`` at ``/data/reports`` with
``MERIDIAN_DATA_DIR=/data`` set to match, so a file the host wrote resolves to
the same path inside it.
Change one, change both — `tests/test_paths.py` pins the contract.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Where the postgres container sees the ticks staging directory. Compose
#: binds ``$MERIDIAN_DATA_DIR/ticks`` here; pg_dump/psql inside the container
#: write to this path and the host job picks the files up via `ticks_dir()`.
BACKUP_DIR_CONTAINER = "/backups"

#: Where an application container's ``data_dir()`` points.
#:
#: The postgres mount is a *staging* mount: the container writes there and a
#: host job collects it, so the two sides may name the path differently. This
#: one is the opposite — the api container must resolve `analytics_path()` to
#: the **same file** the host-run analytics job wrote. That only holds if
#: compose does both halves together: bind the host artifact root's
#: ``reports/`` at ``<this>/reports`` *and* set ``MERIDIAN_DATA_DIR`` to this
#: value inside the container. Bind without the env var and `data_dir()` falls
#: back to ``/app/backups``, which is not the mount — the exact bug that made
#: the model-performance page report "run `python -m core.analytics` first"
#: forever, no matter how many times the operator ran it.
#:
#: Only ``reports/`` is bound, so inside the api this is a root with exactly
#: one subtree in it. `ticks_dir()` and `supabase_dir()` resolve to paths that
#: do not exist there, which is correct: the api has no business reading
#: database dumps, and it is an unauthenticated service on all interfaces.
DATA_DIR_CONTAINER = "/data"

_REPO_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """The one artifact root. ``MERIDIAN_DATA_DIR`` overrides; default
    ``<repo>/backups``. Read per call, not at import — tests and containers
    set the environment after import."""
    override = (os.environ.get("MERIDIAN_DATA_DIR") or "").strip()
    return Path(override) if override else _REPO_ROOT / "backups"


def ticks_dir() -> Path:
    """Local tick-archive dumps + the container staging mount."""
    return data_dir() / "ticks"


def supabase_dir() -> Path:
    """The primary's rolling archives and hand-filed exports."""
    return data_dir() / "supabase"


def reports_dir() -> Path:
    """Regenerable outputs (analytics.json). Not an archive."""
    return data_dir() / "reports"


def analytics_path() -> Path:
    """The pre-computed model-performance blob — **one** function, called by
    both the writer (`core.analytics`) and the reader (`core.api`).

    Existed as two independently-derived expressions until 2026-08-17. They
    agreed symbolically and still resolved to different files, because the
    writer runs on the host and the reader runs in a container that had no
    mount: same code, same env, two disks. `tests/test_analytics_path.py`
    pins writer == reader so a future move cannot separate them again.
    """
    return reports_dir() / "analytics.json"
