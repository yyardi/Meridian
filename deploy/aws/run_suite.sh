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
  postgres:16-alpine -p 5433 >/dev/null

for i in $(seq 1 60); do
  docker exec "$PG" pg_isready -U meridian -d meridian -p 5433 >/dev/null 2>&1 && break
  sleep 1
  [ "$i" = 60 ] && { echo "postgres never became ready"; exit 1; }
done

echo "==> suite"
# The image installs the runtime deps only (pip install -e . without extras)
# and does not COPY tests/, so the repo is mounted and the dev extras added
# in the container. --no-deps is deliberate: nothing from the compose stack
# is touched, and the production Postgres is not on this network at all.
# --network container:$PG puts the suite in the Postgres container's OWN
# network namespace, so "localhost:5432" genuinely reaches the throwaway
# database. This SATISFIES conftest's local-only guard rather than bypassing
# it: that guard refuses any URL without localhost/127.0.0.1 because the tests
# write and delete rows, and it is right to. Note its error message offers
# MERIDIAN_TEST_DATABASE_URL as an escape hatch, but the check runs on the
# resolved URL either way -- the variable does not bypass it. Reported.
#
# No URL overrides are passed: conftest's ADMIN engine is hardcoded to
# localhost:5433/meridian to create and sweep its own per-run database, so the
# throwaway Postgres listens on 5433 and the suite runs EXACTLY as designed
# rather than against a redirected environment. Overriding the test URL while
# leaving the admin URL untouched is what produced 382 collection errors on the
# first attempt -- the per-run database was created somewhere the tests never
# looked.
docker run --rm --network "container:$PG" \
  -v "$REPO":/src -w /src \
  --entrypoint sh "$IMG" -c \
  'pip install --quiet --no-cache-dir "pytest>=8.0" >/dev/null && exec python -m pytest "$@"' _ "$@"
