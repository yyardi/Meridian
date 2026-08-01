#!/usr/bin/env bash
# One-screen view of what Meridian is actually doing.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv ] && source .venv/bin/activate

echo "SERVICES"
docker compose ps --format '  {{.Name}}: {{.Status}}'
echo
echo "RECORDER"
python -m core --status 2>/dev/null | sed 's/^/  /'
echo
echo "DATA"
docker compose exec -T postgres psql -U meridian -d meridian -tAF' ' -c "
SELECT '  market_snapshots ' || count(*) || ' rows, ' ||
       count(DISTINCT captured_at) || ' cycles' FROM market_snapshots
UNION ALL SELECT '  book_levels      ' || count(*) FROM book_levels
UNION ALL SELECT '  team_game_logs   ' || count(*) || ' (' ||
       count(DISTINCT espn_game_id) || ' games)' FROM team_game_logs
UNION ALL SELECT '  sportsbook_odds  ' || count(*) FROM sportsbook_odds
UNION ALL SELECT '  predictions      ' || count(*) FROM predictions
UNION ALL SELECT '  resolved_outcomes ' || count(*) FROM resolved_outcomes
UNION ALL SELECT '  shadow_orders    ' || count(*) || ' (0 real orders placed)' FROM shadow_orders;"
echo
echo "NEXT GAMES BEING TRACKED"
docker compose exec -T postgres psql -U meridian -d meridian -tAF' | ' -c "
SELECT '  ' || event_slug, count(*) || ' markets', to_char(min(game_start_time),'Mon DD HH24:MI')
FROM market_snapshots WHERE captured_at = (SELECT max(captured_at) FROM market_snapshots)
GROUP BY event_slug ORDER BY min(game_start_time) LIMIT 6;"
