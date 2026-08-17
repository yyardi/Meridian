# The Supabase exit — one database, one source of truth

2026-08-17. The free tier was fully restricted (egress 525%, DB size 200%),
and every mitigation (rolling archives, growth digests) was fighting a cap
that no longer needed to exist: the local Postgres already held the biggest
dataset (the tick stream) and runs on a machine with 180 GB free.

## The import (`scripts/import_supabase_export.py`)

The verified export (`backups/supabase/export-20260817/`, 17 CSVs) was merged
into local Postgres with **natural keys, never ids** — the local DB held three
id situations at once (locally-authored stream tables, stale sync mirrors
sharing Supabase's id space, and a verbatim kalshi mirror), so an id-keyed
upsert would have been silently destructive for at least one of them (the
`sync_local.py` hazard, avoided the same way):

* every imported row got a remapped id (`old + local_max + 1M headroom`, so
  concurrent live-recorder writes could not collide mid-import);
* insertion was `ON CONFLICT (<natural unique>) DO UPDATE` — stale mirror
  copies kept their local ids and took the export's authoritative values;
* id-link columns (`book_levels.snapshot_id`, `shadow_orders.prediction_id`,
  `orders.*_id`, `pending_exits.*_id`) were rebuilt through old→new maps;
* remote pregame `book_levels` rows with NULL `captured_at` were backfilled
  from their parent snapshot (exact for that era; the local partition PK
  requires it);
* sequences reset above the new max at the end. Nothing was deleted at any
  step; `service_heartbeats` (runtime state) and `retention_log` (empty in
  the export) were deliberately not imported.

Per-table staged/before/after counts are printed by the script; the run's
receipt lives in the PR description.

## The repoint

Every service's `DATABASE_URL` in docker-compose now defaults to local
Postgres, overridable by **one env var** (`MERIDIAN_DATABASE_URL`) — the AWS
door. `MERIDIAN_TX_POOLER` is gone from compose (it was Supabase session-mode
arithmetic; the rewrite logic in `core/storage/base.py` stays dormant for a
future pooler). The live recorder was already local and is untouched.

Consequences, all in this change:

* health checks and the alerter watch the **primary db** labels; the 500 MB
  plan-cap WARN is gone (growth is bounded by partition retention and watched
  by the disk check);
* the Supabase rolling job is **parked, not deleted**: `rolling_if_due`
  no-ops while the primary URL is local, and wakes the day the URL points at
  a remote again — the check is on the URL, not a flag someone must remember;
* `sync_local.py` is historical (there is no remote to sync from);
* the host `.env` `DATABASE_URL` points at `localhost:5433`.
