#!/usr/bin/env bash
# The pre-registered weekend read, run ON the prod box by cron. No laptop, no
# Claude in the loop: it runs the block from docs/math/e8-nfl-preregistration.md,
# writes everything to artifacts/reads/<UTC>.txt, and pushes ONLY the gate line
# to ntfy (topic read from .env, never printed). Read the file when you are back.
#
#   crontab (UTC):  50 15 * * 0  /opt/meridian/scripts/prod_weekend_read.sh preflight
#                   20 10 * * 1  /opt/meridian/scripts/prod_weekend_read.sh gate
#                   40 10 * * *  /opt/meridian/scripts/prod_weekend_read.sh mlb
#   modes: preflight (coverage + gate + H4), gate (the full block), h4 (H4 only, a fast check),
#          mlb (DAILY 10:40Z: the paper book on MLB only, then the MLB ladder calibration)
#   gate mode also runs THE PAPER BOOK (cfb/run_paper_book.py, via the api container: it
#   needs the venue client for settlement) into artifacts/reads/paper_book_<UTC>.txt.
#
#   Saturday CFB shadow lister (cfb/run_longshot_shadow.py MODE=live: lists the longshot-NO
#   intended orders, PLACES NOTHING, writes only artifacts/reads/longshot_shadow_orders.csv).
#   NOT installed by this file -- the operator adds these two lines to the ubuntu crontab
#   (UTC; same `sudo -n` shape as the two lines above), verbatim:
#   */10 15-23 * * 6  sudo -n docker run --rm -i --network meridian_default -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -e MODE=live -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts -w /app meridian-trainer python3 - < /opt/meridian/cfb/run_longshot_shadow.py >> /opt/meridian/artifacts/reads/longshot_shadow_live.log 2>&1
#   */10 0-4 * * 0    sudo -n docker run --rm -i --network meridian_default -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian -e MODE=live -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts -w /app meridian-trainer python3 - < /opt/meridian/cfb/run_longshot_shadow.py >> /opt/meridian/artifacts/reads/longshot_shadow_live.log 2>&1
set -u
cd /opt/meridian || exit 1
MODE=${1:-gate}
OUT=/opt/meridian/artifacts/reads; mkdir -p "$OUT"
F="$OUT/$(date -u +%Y-%m-%dT%H%MZ)-$MODE.txt"
D=(docker run --rm -i --network meridian_default
   -e DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian
   -v /opt/meridian/cfb:/app/cfb -v /opt/meridian/artifacts:/app/artifacts
   -v /opt/meridian/analysis:/app/analysis -w /app)
run() {  # run LABEL [-e K=V ...] < script      (script piped over stdin)
  local label=$1; shift
  { echo; echo "### $label  ($(date -u +%H:%MZ))"; } >> "$F"
  "${D[@]}" "$@" meridian-trainer python3 - >> "$F" 2>&1
}
run_file() {  # run_file LABEL path/inside/app [args...]   (script run AS A FILE:
  # the softness scripts locate their CSVs next to their own file, which a
  # piped script does not have -- the first smoke run died on exactly that)
  local label=$1; shift
  { echo; echo "### $label  ($(date -u +%H:%MZ))"; } >> "$F"
  "${D[@]}" meridian-trainer python3 "$@" >> "$F" 2>&1
}
{ echo "# weekend read  mode=$MODE  $(date -u)"; echo "# code: $(git rev-parse --short HEAD) $(git branch --show-current)"; } > "$F"

# --------------------------------------------------------------------------- #
# mlb: the daily read. Baseball needs no game map and no ESPN feed -- both the
# paper book and the calibration settle from the VENUE's own endpoint -- so it
# runs entirely in the api container (the trainer image has no venue client)
# and returns before the football block. Settled labels are cached in
# artifacts/reads/settlements.json, so the second run costs a few HTTP calls
# instead of ~18k.
# --------------------------------------------------------------------------- #
if [ "$MODE" = mlb ]; then
  { echo; echo "### PAPER BOOK, mlb  ($(date -u +%H:%MZ))"; } >> "$F"
  docker exec -i -e LEAGUES=mlb meridian-api python - < cfb/run_paper_book.py >> "$F" 2>&1
  echo "paper book exit $?" >> "$F"
  { echo; echo "### MLB LADDER CALIBRATION  ($(date -u +%H:%MZ))"; } >> "$F"
  docker exec -i -e LEAGUE=mlb meridian-api python - < cfb/run_ladder_calibration.py >> "$F" 2>&1
  echo "calibration exit $?" >> "$F"
  echo "wrote $F"
  exit 0
fi

# 0. coverage: mapped games vs games with ESPN state and venue winner tape, last 3 days
docker exec meridian-postgres psql -U meridian -d meridian -A -F'|' -c "
SELECT m.division, m.espn_date::date d, count(*) mapped,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM espn_cfb_game_state s WHERE s.game_id=m.espn_game_id)) espn,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM market_snapshots ms WHERE ms.game_id=m.venue_game_id AND ms.sports_market_type LIKE '%winner' AND ms.captured_at > now() - interval '4 days')) venue
FROM cfb_game_map m WHERE m.espn_date > now() - interval '3 days' AND m.espn_date < now() GROUP BY 1,2 ORDER BY 2,1" >> "$F" 2>&1

# 1. THE GATE (pooled, prints its own verdict), then the per-league splits beside it
if [ "$MODE" != h4 ]; then
run "H1c pooled CFB+NFL, MOVE_STRATUM (the gate)" -e LEAGUE=both -e MOVE_STRATUM=1 < cfb/run_making_touch.py
fi
if [ "$MODE" = gate ]; then
  run "H1 overshoot NFL"  -e LEAGUE=nfl < cfb/run_overshoot.py
  run "H1 overshoot CFB"  -e LEAGUE=cfb < cfb/run_overshoot.py
  run "H2 E1 at plays, NFL" -e LEAGUE=nfl < cfb/run_making_touch.py
  run "H2 E6 dead windows, NFL" -e LEAGUE=nfl -e DEAD_WINDOW=1 < cfb/run_making_touch.py
  run "H3 ladder RV, NFL" -e LEAGUE=nfl < cfb/run_ladder_rv.py
  run "Saturday hypothesis: CFB spread rungs mid 0.2-0.3, buy NO (pregame-ladder-calibration.md)" -e LEAGUE=cfb < cfb/run_ladder_calibration.py
  run "Kalshi vs DraftKings lag, hour by hour (kalshi-early-week.md; registered read 09-19)" < cfb/run_kalshi_dk_lag.py
fi
# H4: append a snapshot (public APIs) and score what has settled
run_file "H4 softness snapshot polymarket" analysis/pregame_softness/pregame_softness_polymarket.py analysis/pregame_softness/pregame_softness_polymarket_snapshots.csv
run_file "H4 softness snapshot kalshi"     analysis/pregame_softness/pregame_softness_kalshi.py     analysis/pregame_softness/pregame_softness_snapshots.csv
run_file "H4 score" analysis/pregame_softness/score_softness.py

# 2. THE PAPER BOOK (gate mode only): every registered shadow strategy, priced at the
#    pregame close and settled by the venue's own endpoint, so it runs in the api
#    container (the trainer image has no venue client). Its table goes to its own file;
#    the read file names that file. Unsettled markets are counted, never scored.
if [ "$MODE" = gate ]; then
  { echo; echo "### PAPER BOOK  ($(date -u +%H:%MZ))"; } >> "$F"
  if [ -f cfb/run_paper_book.py ]; then
    PB="$OUT/paper_book_$(date -u +%Y-%m-%dT%H%MZ).txt"
    docker exec -i meridian-api python - < cfb/run_paper_book.py > "$PB" 2>&1; PB_RC=$?
    echo "paper book: $PB (exit $PB_RC)" >> "$F"
  else
    echo "paper book NOT run: cfb/run_paper_book.py is missing from this checkout" >> "$F"
  fi
fi

GATE=$(grep -h "H1c GATE" "$F" | tail -1 | sed 's/^ *//' | cut -c1-400)
{ echo; echo "### GATE LINE"; echo "${GATE:-no gate line printed}"; } >> "$F"
# push only the gate line; the topic is a secret and is never echoed
TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ] && [ "$MODE" != h4 ]; then
  curl -s -m 20 -H "Title: Meridian weekend read ($MODE)" -d "${GATE:-no gate line} | file: $(basename "$F")" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 || true
fi
echo "wrote $F"
