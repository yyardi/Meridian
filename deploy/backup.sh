#!/usr/bin/env bash
# pg_dump to ./backups. The prediction log and snapshot history are
# irreplaceable — a season of recorded line movement cannot be reconstructed
# at any price. TEST A RESTORE; a configured backup you have never restored
# is not a backup.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="backups/meridian-${STAMP}.sql.gz"
docker compose exec -T postgres pg_dump -U meridian meridian | gzip > "$OUT"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
# Keep the last 14.
ls -1t backups/meridian-*.sql.gz | tail -n +15 | xargs -r rm --
