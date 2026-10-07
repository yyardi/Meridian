# The data archive: prod postgres and tapes to Parquet, off the server

2026-10-07. The operator's rule: recorded data is never deleted; it is moved. The prod disk
(286 GB) filled on 2026-10-07 with postgres growing ~5.5 GB a day, so closed months leave the
server as Parquet files on the operator's machine and SSD.

**Tool.** `scripts/archive/export_run.sh <out_dir>` opens a compressed SSH tunnel to prod postgres
(port 5433 on the box's loopback; the address comes from `~/.meridian-server` and is never written
down) and runs `scripts/archive/export_postgres.py`, which needs `duckdb` (its `postgres`
extension installs on first use). Every table becomes `<schema>.<table>.parquet` (zstd), read-only
on prod, nothing written on the server's disk. A rerun resumes: verified tables are skipped, a file
whose verify was interrupted is verified in place, never pulled again.

**Verification, inside postgres** (`postgres_query` pushes the aggregate down; one row crosses
the tunnel): row count, `sum(id)`, total bytes of every text column, and for json/jsonb the bytes
of the text form on a deterministic 0.1% sample (`id % 997 = 0`). A deliberately truncated JSON
value fails it. A table still being written is compared on rows up to the export's highest id;
that does not settle tables whose writers hold transactions open (rows with lower ids commit
later), so the current month is a point-in-time copy until it closes.

**First run (2026-10-07):** 81 tables, ~250 GB in postgres → 4.2 GB of Parquet (book levels ~43×,
snapshots with raw JSON 60–130×); 79 verified exactly, the two October partitions point-in-time.
Throughput ~150–350k rows/s; the 108 GB September snapshot partition took 47 min to copy and
4.5 min to verify. Tapes (`artifacts/reads`, 7.8 GB, mostly gzipped) copied with rsync.

**Monthly routine.** After a month closes: export, confirm the month's partitions verify, then —
only with the operator's yes — drop those partitions on prod. Keep a second copy somewhere other
than one SSD.
