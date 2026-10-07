#!/bin/bash
# Open (or reuse) the compressed tunnel to prod postgres and run the verified Parquet export.
OUT=${1:?out dir}
if ! nc -z -w 3 127.0.0.1 15433 2>/dev/null; then
  ssh -i ~/.ssh/meridian-aws.pem -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=10 \
      -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -f -N -C -L 15433:127.0.0.1:5433 \
      "ubuntu@$(cat ~/.meridian-server)" 2>&1 | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<ip>/g'
  sleep 2
fi
exec "${PYTHON:-python3}" "$(dirname "$0")/export_postgres.py" "$OUT"
