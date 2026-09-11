#!/usr/bin/env bash
# The pre-registered weekend read, run ON the prod box by cron. No laptop, no
# Claude in the loop: it runs the block from docs/math/e8-nfl-preregistration.md,
# writes everything to artifacts/reads/<UTC>.txt, and pushes ONLY the gate line
# to ntfy (topic read from .env, never printed). Read the file when you are back.
#
#   crontab (UTC):  50 15 * * 0  /opt/meridian/scripts/prod_weekend_read.sh preflight
#                   20 10 * * 1  /opt/meridian/scripts/prod_weekend_read.sh gate
#   modes: preflight (coverage + gate + H4), gate (the full block), h4 (H4 only, a fast check)
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
fi
# H4: append a snapshot (public APIs) and score what has settled
run_file "H4 softness snapshot polymarket" analysis/pregame_softness/pregame_softness_polymarket.py analysis/pregame_softness/pregame_softness_polymarket_snapshots.csv
run_file "H4 softness snapshot kalshi"     analysis/pregame_softness/pregame_softness_kalshi.py     analysis/pregame_softness/pregame_softness_snapshots.csv
run_file "H4 score" analysis/pregame_softness/score_softness.py

GATE=$(grep -h "H1c GATE" "$F" | tail -1 | sed 's/^ *//' | cut -c1-400)
{ echo; echo "### GATE LINE"; echo "${GATE:-no gate line printed}"; } >> "$F"
# push only the gate line; the topic is a secret and is never echoed
TOPIC=$(grep -E '^MERIDIAN_NTFY_TOPIC=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -n "$TOPIC" ]; then
  curl -s -m 20 -H "Title: Meridian weekend read ($MODE)" -d "${GATE:-no gate line} | file: $(basename "$F")" "https://ntfy.sh/$TOPIC" >/dev/null 2>&1 || true
fi
echo "wrote $F"
