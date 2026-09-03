#!/usr/bin/env bash
# Deploy an engine container with its ENGINE IDENTITY stamped (amendment 12).
#
# The engines that write cohort rows FAIL CLOSED without GIT_COMMIT, so this
# script exists to make the stamp unforgettable rather than to make it
# optional. Run it on the prod host, from the checkout being deployed.
#
#   scripts/deploy_engine.sh quote-engine docker-compose.quote.yml
#
set -euo pipefail
SERVICE="${1:?usage: deploy_engine.sh <service> [overlay.yml ...]}"; shift
FILES=(-f docker-compose.yml); for f in "$@"; do FILES+=(-f "$f"); done

GIT_COMMIT="$(git rev-parse HEAD)"
# TRACKED modifications only. The first version checked --porcelain outright
# and refused on prod, where an untracked .venv-health/ sits beside the
# checkout — a guard that blocks every real deploy while catching nothing,
# since the image COPYs specific tracked directories and untracked strays
# cannot reach it. What must be refused is a MODIFIED tracked file: that
# would make the stamp name a commit which does not describe the built code.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "REFUSING: tracked files are modified — the stamp would name a commit" >&2
  echo "that does not describe the code being built. Commit or stash first." >&2
  git status --short --untracked-files=no >&2
  exit 1
fi
export GIT_COMMIT
echo "deploying $SERVICE at $GIT_COMMIT"
docker compose "${FILES[@]}" build --build-arg "GIT_COMMIT=$GIT_COMMIT" "$SERVICE"
docker compose "${FILES[@]}" up -d "$SERVICE"

echo "--- verifying the stamp reached the container ---"
sleep 3
docker compose "${FILES[@]}" exec -T "$SERVICE" printenv MERIDIAN_ENGINE_COMMIT \
  || echo "WARNING: could not read the stamp back — check before trusting the cohort"
