#!/usr/bin/env bash
# Run the pytest suite ON THE SERVER, against a THROWAWAY Postgres.
#
# Why this exists: the suite needs a Postgres at 5433 and the operator's laptop
# is not a dependency this project may have — they stop and start Docker for
# their coursework, and nobody restarts it for us. Before this script, PRs sat
# unmerged for want of a suite run.
#
# Why a throwaway database rather than the production instance: the suite
# creates and drops databases. Production Postgres holds the tick recorder's
# live writes; a suite that shares its instance shares its fate. Isolation here
# is by CONTAINER, not merely by database name.
#
#   bash deploy/aws/run_suite.sh            # whole suite
#   bash deploy/aws/run_suite.sh tests/test_pulse_v4_eval.py -k v3d
set -euo pipefail

REPO=${MERIDIAN_REPO:-/opt/meridian}
NET=meridian-suite-net
PG=meridian-suite-pg
IMG=${MERIDIAN_TEST_IMAGE:-meridian-scheduler}

cleanup() {
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
docker network create "$NET" >/dev/null

echo "==> throwaway postgres"
docker run -d --rm --name "$PG" --network "$NET" \
  -e POSTGRES_USER=meridian -e POSTGRES_PASSWORD=meridian -e POSTGRES_DB=meridian \
  postgres:16-alpine >/dev/null

for i in $(seq 1 60); do
  docker exec "$PG" pg_isready -U meridian -d meridian >/dev/null 2>&1 && break
  sleep 1
  [ "$i" = 60 ] && { echo "postgres never became ready"; exit 1; }
done

echo "==> suite"
# The image installs the runtime deps only (pip install -e . without extras)
# and does not COPY tests/, so the repo is mounted and the dev extras added
# in the container. --no-deps is deliberate: nothing from the compose stack
# is touched, and the production Postgres is not on this network at all.
docker run --rm --network "$NET" \
  -v "$REPO":/src -w /src \
  -e MERIDIAN_TEST_DATABASE_URL="postgresql+psycopg://meridian:meridian@${PG}:5432/meridian_suite_$$" \
  -e DATABASE_URL="postgresql+psycopg://meridian:meridian@${PG}:5432/meridian_suite_$$" \
  --entrypoint sh "$IMG" -c \
  'pip install --quiet --no-cache-dir "pytest>=8.0" >/dev/null && exec python -m pytest "$@"' _ "$@"
