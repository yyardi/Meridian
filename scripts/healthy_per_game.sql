-- HEALTHY PER-GAME DISTRIBUTION — sets the constant for the per-game trigger.
--
-- WHY: alarm_v5 pools every market in a league, so a totally frozen block of
-- 1,443 markets diluted by 1,857 healthy ones reads 6.47% and passes a 5% floor.
-- Measured on the real tape at anchor 2026-09-05 18:20Z. The alarm would have
-- MISSED the freeze it was built for. Markets share a fate by GAME, so the
-- trigger must be "K games show ~no movement", not "the league's pooled share
-- is low".
--
-- ★ RUN WITH psql (\set and :'VAR' are client features):
--   docker compose exec -T postgres psql -U meridian -d meridian -f this_file
--
-- ★ THE NUMBER THAT SETS K IS PANEL B's `extreme` COLUMN — the MAXIMUM number of
-- simultaneously-quiet games ever seen in a healthy 30-minute bucket. K must sit
-- above it, or the alarm pages on ordinary football. Panel A is context; do not
-- set a threshold from it.
--
-- ★ AND READ PANEL C FIRST. If `games_dropped` is large, the floor is discarding
-- most of the population and Panel B is measured on a minority — the same defect
-- as the near_floor_buckets=0 run we both misread this morning.
--
-- Every filter matches scripts/alarm_v5.py exactly: same 600s stream guard (the
-- is_live flag never clears, so dead streams otherwise read as quoted-and-still),
-- same 30-minute window, same FLOOR_PCT. If these drift apart this measures a
-- threshold the alarm does not use.

\set BUCKET_MIN 30
\set GUARD_S 600
\set FLOOR_PCT 5.0
-- A game with 2 markets gives a share of 0/50/100 and is noise. Must be a real
-- floor, and Panel C reports what it costs.
\set MIN_MKTS_PER_GAME 4
-- 17:38, not 17:39. Cliff: 17:37 = 12.87% movers, 17:38 = 3.34%, 17:39 = 0.06%.
\set FREEZE_START '2026-09-05 17:38:00+00'

WITH raw AS (
  SELECT market_slug, game_id, captured_at, best_bid, best_ask,
         split_part(market_slug, '-', 2) AS league,
         lead(captured_at) OVER (PARTITION BY market_slug ORDER BY captured_at) AS next_at
  FROM market_snapshots
  WHERE is_live = true
    AND best_bid IS NOT NULL AND best_ask IS NOT NULL
    AND captured_at > '2026-09-03'
    AND captured_at < :'FREEZE_START'          -- healthy only; incident excluded
),
w AS (   -- stream-running guard: a row counts only if its market kept streaming
  SELECT * FROM raw
  WHERE next_at IS NOT NULL
    AND next_at - captured_at <= make_interval(secs => :GUARD_S)
),
bucketed AS (
  SELECT date_trunc('hour', captured_at)
           + (interval '1 minute' * :BUCKET_MIN)
             * floor(extract(minute FROM captured_at) / :BUCKET_MIN)  AS bucket,
         league, game_id, market_slug,
         count(DISTINCT (best_bid, best_ask))                         AS pairs
  FROM w
  GROUP BY 1, 2, 3, 4
),
per_game AS (
  SELECT bucket, league, game_id,
         count(*)                                            AS markets,
         100.0 * count(*) FILTER (WHERE pairs > 1) / count(*) AS pct_moved
  FROM bucketed
  GROUP BY 1, 2, 3
),
judged AS (SELECT * FROM per_game WHERE markets >= :MIN_MKTS_PER_GAME),
per_bucket AS (
  SELECT bucket, league,
         count(*)                                              AS games_judged,
         count(*) FILTER (WHERE pct_moved <= :FLOOR_PCT)       AS games_quiet
  FROM judged
  GROUP BY 1, 2
)

--  panel                         | n      | a    | b    | c    | extreme
--  A per-game pct_moved          | games  | p50  | p05  | p01  | worst game
--  B quiet games PER BUCKET      | buckets| p50  | p95  | p99  | ★ MAX -> sets K
--  C what the floor discarded    | games  | kept | -    | -    | dropped
SELECT 'A  per-game pct_moved (context only)' AS panel, league,
       count(*)::int                                                             AS n,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY pct_moved)::numeric,1) AS a,
       round(percentile_cont(0.05) WITHIN GROUP (ORDER BY pct_moved)::numeric,1) AS b,
       round(percentile_cont(0.01) WITHIN GROUP (ORDER BY pct_moved)::numeric,1) AS c,
       round(min(pct_moved)::numeric,1)                                          AS extreme
FROM judged GROUP BY league
UNION ALL
SELECT 'B  quiet games per bucket  <- SETS K', league,
       count(*)::int,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY games_quiet)::numeric,1),
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY games_quiet)::numeric,1),
       round(percentile_cont(0.99) WITHIN GROUP (ORDER BY games_quiet)::numeric,1),
       max(games_quiet)::numeric
FROM per_bucket GROUP BY league
UNION ALL
SELECT 'C  floor cost: games kept vs dropped', league,
       count(*)::int,
       count(*) FILTER (WHERE markets >= :MIN_MKTS_PER_GAME)::numeric,
       NULL, NULL,
       count(*) FILTER (WHERE markets <  :MIN_MKTS_PER_GAME)::numeric
FROM per_game GROUP BY league
ORDER BY 1, 2;
