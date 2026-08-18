# Artifact paths — one root, two archive subtrees

Consolidated 2026-08-17 at the operator's request; before this, archive
folders sprawled (`backups/supabase-final`, `backups/supabase-live-archive-*`,
loose `pre-migrate-*.sql`) with each path hardcoded where it was used.

**The root** is `MERIDIAN_DATA_DIR` (default `<repo>/backups`), resolved
per-call by [`core/paths.py`](../../core/paths.py). No code in `core/` may
create a new top-level folder in the repo.

| subtree | what | writer |
|---|---|---|
| `ticks/` | local monthly partition dumps + container staging | `core/retention.py` (monthly), postgres container via the `/backups` mount |
| `supabase/` | the primary's rolling CSV archives, and the operator's hand-filed exports (`export-20260817/`, `live-archive-20260805/`, `pre-migrate-*.sql`) | `core/retention.py` (rolling) |
| `reports/` | regenerable outputs (`analytics.json`) — an output, not an archive | `core/analytics.py` |

**The compose contract**: the postgres container writes dumps at `/backups`
(`core.paths.BACKUP_DIR_CONTAINER`), which docker-compose binds to
`${MERIDIAN_DATA_DIR:-./backups}/ticks`. These two move together or the
retention job's staging silently breaks — `tests/test_paths.py` pins the pair.
The api container gets the whole root at `/data`
(`core.paths.DATA_DIR_CONTAINER`) **plus `MERIDIAN_DATA_DIR=/data`**, so a
file the host wrote resolves to the same bytes inside it; the bind without the
env var is the failure documented in [analytics-path.md](analytics-path.md).
Setting `MERIDIAN_DATA_DIR` therefore requires a container recreate to take
effect, and it must be set in the shell/`.env` compose reads, not only for
python.

Retired: the `./recorder-logs:/app/logs` mount (nothing ever wrote there —
every service logs to stdout); the alerter's disk check now stats the artifact
root instead of `recorder-logs/`. `data/`, `recorder-logs/`, and the root
`odds_backfill*.log` / `recorder.log` files are dead artifacts of pre-container
runs: nothing in code reads or writes them, and deleting what remains on disk
is the operator's call (nothing here deletes anything, per the retention
invariant).
