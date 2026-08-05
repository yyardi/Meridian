# Supabase free-tier quota — what blew it and what holds it down

**2026-08-05.** The org went over both free-plan limits: database size 857 MB
of 500 (183%), egress 15.09 GB of 5 (302%). Grace period ran to 2026-09-03;
past that, every request 402s.

## The two causes

**Size** was history, not growth: 761,963 `is_live` rows in `market_snapshots`
(620 MB with `raw`) — the 200ms ticks from games 13002446/447/448, written
back when the live recorder still pointed at Supabase, before the B11 repoint
to local. Plus 406,094 `book_levels` rows hanging off them (42% of that table).

**Egress** was `sync_local` re-pulling every durable table in full on every
run. A full copy of tables that gain a few thousand rows a day moved the whole
history nightly.

## The fix (archive → delete → vacuum → incremental)

1. Supabase-only rows (540 pregame snapshots for games 13002449–452, plus
   8,607 book levels) copied into local Postgres first, deduped on
   `(market_slug, captured_at)` — ids are independent between the databases,
   so never copy by id.
2. Every live row archived to `backups/supabase-live-archive-2026-08-05/`
   (compressed COPY, `raw` included, integrity-checked) **before** deletion.
3. `DELETE ... WHERE is_live AND id <= <max archived id>` — the id bound means
   rows written between archive and delete survive. The FK cascade took the
   406k live book levels in the same statement.
4. `VACUUM FULL` on both tables. This is not optional: DELETE alone leaves the
   pages allocated, and **Supabase enforces the reported size**. 857 MB → 266 MB.
5. `sync_local` is now incremental by default (keyset from the local max id);
   `--rebuild` does the old full copy and is the only way in-place updates
   reach local. Measured after: a catch-up sync took 19 s.

## Keeping it that way

- `scripts/health.py` now prints `supabase size` and WARNs at 400 MB.
- The pregame recorder's live-flagged trickle (~150 rows/game) still lands in
  Supabase. Accepted — it is years from mattering.
- If size creeps again: same recipe, archive before delete, and remember the
  vacuum.
