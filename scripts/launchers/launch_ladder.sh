#!/usr/bin/env bash
# launch_ladder.sh <winner-slug> <minutes> [ws]
#
# Read-only ladder executor: it writes TICKETS and pushes the phone. It places
# nothing -- placing is the operator's SEND on /arb.
#
# No --budget-usd and no --cooldown, deliberately. The previous version of this
# script passed "--budget-usd 2 --cooldown 10" and that pair is what turned 117
# candidate cycles into 4 tickets on 2026-09-18: the cap silenced a game for the
# rest of the night once $2 of NOTIONAL had been written against observations
# nobody placed, and the cooldown hid every repeat of a pair for ten minutes.
# The capital decision is the SEND click. The executor's job is to MISS NOTHING.
#
# "ws" as the third argument also starts the REST+stream comparator on the same
# game and window. That costs a second REST budget slot, so it goes on the games
# chosen to answer whether the REST assembly manufactures crossings -- not on
# every game.
set -euo pipefail
S=$1; M=${2:-240}; WS=${3:-}
API=$(docker inspect meridian-api --format "{{.Config.Image}}")
RUN="docker run -d --rm --network meridian_default --env-file /opt/meridian/.env
  -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian
  -v /opt/meridian/core:/app/core -v /opt/meridian/cfb:/app/cfb
  -v /opt/meridian/artifacts/reads:/out -w /app"

# Two floors. $25 is what reaches the DESK -- every crossing worth looking at,
# and /log keeps them all. $500 is what reaches the PHONE, because the operator
# asked for the buzzing to stop and the board to carry the rest: on 2026-09-18
# three games put 93 episodes over $25 and 13 over $500. PUSH_FLOOR=0 restores
# an alert on every ticket.
FLOOR=${FLOOR:-25}; PUSH_FLOOR=${PUSH_FLOOR:-500}
$RUN --name "ladder-${S:8:20}" "$API" sh -c \
  "python cfb/run_ladder_executor.py --prefix $S --every 20 --minutes $M --attempt-usd 1 --floor-usd $FLOOR --push-floor-usd $PUSH_FLOOR --push-cooldown 10 > /out/live_ladder_${S}.txt 2>&1"

if [ "$WS" = "ws" ]; then
  $RUN --name "wsfresh-${S:8:20}" "$API" sh -c \
    "python cfb/run_ws_freshness.py --prefix $S --every 20 --minutes $M > /out/ws_freshness_${S}.txt 2>&1"
fi
