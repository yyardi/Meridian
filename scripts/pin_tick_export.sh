#!/usr/bin/env bash
# Pin a tick export with the FULL survey column set.
#
# Why this exists: the ad-hoc export path carried only the analysis columns,
# and the day-one survey's depth (M2) and fee (M3) modules run DEGRADED
# without fee_coefficient, book_tier, min_tick_size, min_trade_qty — columns
# the snapshot table has always had. Listing night cannot be re-run, so the
# export path is fixed ahead of it and pinned as a script rather than retyped.
#
#   bash scripts/pin_tick_export.sh 'wnba'          # league prefix filter
#   bash scripts/pin_tick_export.sh 'nba' out.csv.gz
set -euo pipefail
LEAGUE="${1:?league prefix, e.g. nba}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${2:-backups/exports/live_ticks_${LEAGUE}_full_${TS}.csv.gz}"
docker compose exec -T postgres psql -U meridian -d meridian -c "\copy (
  select event_slug, market_slug, sports_market_type, line, captured_at,
         best_bid, best_ask, event_period, event_score, is_live,
         fee_coefficient, book_tier, min_tick_size, min_trade_qty
    from market_snapshots
   where is_live and market_slug like '%-${LEAGUE}-%'
   order by market_slug, captured_at
) to stdout with (format csv, header)" | gzip -1 > "$OUT"
echo "pinned: $OUT ($(gzip -cd "$OUT" | wc -l) rows)"
