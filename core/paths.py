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

The docker-compose mounts must agree with these paths: the postgres container
stages dumps at ``/backups`` which compose binds to ``$MERIDIAN_DATA_DIR/ticks``.
Change one, change both — `tests/test_paths.py` pins the contract.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Where the postgres container sees the ticks staging directory. Compose
#: binds ``$MERIDIAN_DATA_DIR/ticks`` here; pg_dump/psql inside the container
#: write to this path and the host job picks the files up via `ticks_dir()`.
BACKUP_DIR_CONTAINER = "/backups"

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
