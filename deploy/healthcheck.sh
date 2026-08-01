#!/usr/bin/env bash
# Meridian health check. Exit 0 = healthy, 1 = stale.
# The alert that matters: snapshots are unrecoverable, so silence is the
# failure mode. Wire this into cron and alert on non-zero exit.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -d .venv ]; then source .venv/bin/activate; fi
python -m core --status --gap-minutes "${GAP_MINUTES:-90}"
