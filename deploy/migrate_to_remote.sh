#!/usr/bin/env bash
# Move Meridian's data from local Docker Postgres to a remote database.
#
# Usage:
#   1. Put the remote connection string in .env as REMOTE_DATABASE_URL
#   2. ./deploy/migrate_to_remote.sh
#
# Safe to re-run: it dumps local, applies the schema remotely via Alembic,
# then copies data. Local data is never deleted.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && source .venv/bin/activate

if [ ! -f .env ]; then echo "no .env found"; exit 1; fi
REMOTE=$(grep -E '^REMOTE_DATABASE_URL=' .env | cut -d= -f2- || true)
if [ -z "$REMOTE" ]; then
  echo "REMOTE_DATABASE_URL is not set in .env"
  echo "Add it, then re-run. The value is never printed or logged."
  exit 1
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP="backups/pre-migrate-${STAMP}.sql"
mkdir -p backups

echo "1/4  dumping local data ..."
docker compose exec -T postgres pg_dump -U meridian --data-only \
  --exclude-table=alembic_version meridian > "$DUMP"
echo "     wrote $DUMP ($(du -h "$DUMP" | cut -f1))"

echo "2/4  creating schema on the remote ..."
DATABASE_URL="$REMOTE" alembic upgrade head

echo "3/4  loading data ..."
# psql form: strip SQLAlchemy's +psycopg driver marker.
PSQL_URL=$(printf '%s' "$REMOTE" | sed 's/+psycopg//')
# Run psql from inside the postgres container so the host needs no client
# installed. The URL is passed on stdin-adjacent env, never echoed.
docker compose exec -T -e PGURL="$PSQL_URL" postgres \
  sh -c 'psql "$PGURL" -v ON_ERROR_STOP=1' < "$DUMP" >/dev/null

echo "4/4  verifying row counts match ..."
python - <<'PY'
import os
from sqlalchemy import func, select
from dotenv import dotenv_values
from core.storage import (BookLevel, MarketSnapshot, Prediction, ResolvedOutcome,
                          ShadowOrder, SportsbookOdds, TeamGameLog,
                          get_engine, get_sessionmaker)

vals = dotenv_values(".env")
TABLES = [MarketSnapshot, BookLevel, TeamGameLog, SportsbookOdds,
          Prediction, ResolvedOutcome, ShadowOrder]

def counts(url):
    S = get_sessionmaker(get_engine(url))
    with S() as s:
        return {t.__tablename__: s.scalar(select(func.count(t.id))) for t in TABLES}

local = counts(vals["DATABASE_URL"])
remote = counts(vals["REMOTE_DATABASE_URL"])
ok = True
for name in local:
    mark = "OK " if local[name] == remote[name] else "MISMATCH"
    if local[name] != remote[name]:
        ok = False
    print(f"  {mark:9}{name:<20} local={local[name]:>7}  remote={remote[name]:>7}")
print()
print("migration verified" if ok else "COUNTS DIFFER — do not switch over yet")
raise SystemExit(0 if ok else 1)
PY

echo
echo "Done. To switch over:"
echo "  1. set DATABASE_URL to the remote value in .env"
echo "  2. update docker-compose.yml service env to the same"
echo "  3. docker compose up -d --force-recreate recorder scheduler"
echo "  4. ./deploy/dashboard.sh   # confirm rows still climbing"
