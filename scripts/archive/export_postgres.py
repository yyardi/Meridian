"""Copy every table of the prod Meridian postgres to Parquet (zstd) on this Mac, verified.

    python export_postgres.py <out_dir>

Reads through an SSH tunnel on 127.0.0.1:15433 (opened by export_run.sh), READ_ONLY; writes
<schema>.<table>.parquet under <out_dir>, then compares row count, sum(id) (when the table has an
integer id) and the total length of every text column between postgres and the file. A table whose
checks differ is renamed *.parquet.BAD and reported; nothing on prod is changed. Writes a manifest
(manifest.tsv): table, rows, parquet bytes, postgres bytes, verified, seconds.
Skips a table whose verified file already exists, so a rerun resumes.
"""
import duckdb, os, sys, time


def verify(c, schema, name, path):
    """(postgres totals, parquet totals). Runs INSIDE postgres via postgres_query, so one row crosses the
    tunnel: count(*); sum(id) when there is an integer id; the byte length of every text column; and for
    json/jsonb columns (whose text form postgres must serialise to measure) the byte length of their text
    on a deterministic 0.1% sample, id % 997 = 0, which also checks DuckDB's text rendering of the JSON
    against postgres's own. The first version computed every length in DuckDB, re-pulling the table."""
    pg_types = dict(c.execute("SELECT * FROM postgres_query('pg', $q$SELECT column_name::text, data_type::text FROM information_schema.columns "
                              f"WHERE table_schema = '{schema}' AND table_name = '{name}'$q$)").fetchall())
    has_id = pg_types.get("id") in ("bigint", "integer", "smallint")
    text = [k for k, v in pg_types.items() if v in ("text", "character varying", "character")]
    js = [k for k, v in pg_types.items() if v in ("json", "jsonb")] if has_id else []
    pg = ["count(*)::bigint"] + (["coalesce(sum(id),0)::numeric"] if has_id else []) + [f'coalesce(sum(octet_length("{x}")),0)::bigint' for x in text] \
        + [f'coalesce(sum(octet_length("{x}"::text)) FILTER (WHERE id % 997 = 0),0)::bigint' for x in js]
    pq = ["count(*)"] + (["coalesce(sum(id),0)::HUGEINT"] if has_id else []) + [f'coalesce(sum(strlen("{x}")),0)::BIGINT' for x in text] \
        + [f'coalesce(sum(strlen("{x}")) FILTER (WHERE id % 997 = 0),0)::BIGINT' for x in js]
    pg = [f"{x} AS c{i}" for i, x in enumerate(pg)]                     # distinct names: postgres_query rejects duplicates
    # a table still being written gains rows between the export and this check: compare only rows up to
    # the export's highest id (both sides), so a live table verifies what was copied, not what came later
    bound = ""
    if has_id:
        mx = c.execute(f"SELECT max(id) FROM '{path}'").fetchone()[0]
        bound = f" WHERE id <= {int(mx)}" if mx is not None else ""
    a = tuple(int(v) for v in c.execute("SELECT * FROM postgres_query('pg', $q$SELECT " + ", ".join(pg) + f' FROM "{schema}"."{name}"{bound}$q$)').fetchone())
    b = tuple(int(v) for v in c.execute("SELECT " + ", ".join(pq) + f" FROM '{path}'{bound}").fetchone())
    return a, b

out = sys.argv[1]
c = duckdb.connect()
c.execute("LOAD postgres")
c.execute("ATTACH 'host=127.0.0.1 port=15433 dbname=meridian user=meridian password=meridian' AS pg (TYPE postgres, READ_ONLY)")
tables = c.execute("""
    SELECT * FROM postgres_query('pg', $$
      SELECT n.nspname, c.relname, pg_total_relation_size(c.oid)::bigint
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%'
      ORDER BY (c.relname LIKE '%y2026m0%') DESC, pg_total_relation_size(c.oid) ASC $$)""").fetchall()
man = os.path.join(out, "manifest.tsv")
if not os.path.exists(man):
    open(man, "w").write("table\trows\tparquet_bytes\tpostgres_bytes\tverified\tseconds\n")
done = {l.split("\t")[0] for l in open(man) if l.endswith("\tyes\t" + l.split("\t")[-1]) or "\tyes\t" in l}
print(f"{len(tables)} tables; {len(done)} already verified", flush=True)
for schema, name, pgbytes in tables:
    key = f"{schema}.{name}"
    path = os.path.join(out, key + ".parquet")
    if key in done and os.path.exists(path):
        continue
    src = f'pg."{schema}"."{name}"'
    t0 = time.time()
    try:
        if not os.path.exists(path) and os.path.exists(path + ".BAD"):
            os.replace(path + ".BAD", path)    # re-verify a file that failed the unbounded check instead of re-pulling it
        reused = os.path.exists(path)          # a file written before an interrupted verify is verified, not re-pulled
        if reused:
            try:
                c.execute(f"SELECT count(*) FROM '{path}'").fetchone()
            except Exception:                   # no footer: the COPY was interrupted; start the table over
                os.remove(path); reused = False
        if not reused:
            c.execute(f"COPY (SELECT * FROM {src}) TO '{path}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 500000)")
        a, b = verify(c, schema, name, path)
        ok = a == b
        if not ok:
            os.replace(path, path + ".BAD")
        dt = time.time() - t0
        size = os.path.getsize(path if ok else path + ".BAD")
        open(man, "a").write(f"{key}\t{a[0]}\t{size}\t{pgbytes}\t{'yes' if ok else 'NO'}\t{dt:.0f}\n")
        print(f"{key}: {a[0]:,} rows, {pgbytes/1e9:.2f} GB -> {size/1e6:,.1f} MB, {'verified' if ok else 'MISMATCH ' + str(a) + ' vs ' + str(b)}, {dt:.0f} s", flush=True)
    except Exception as e:
        print(f"{key}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
print("done", flush=True)
