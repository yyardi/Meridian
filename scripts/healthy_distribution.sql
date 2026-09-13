-- HEALTHY DISTRIBUTION AT THE ALARM'S OWN BASE.
--
-- WHY THIS EXISTS: freeze_history.sql buckets by date_trunc('hour', ...) even
-- though its header comment says "Per 10-minute bucket". Every healthy figure
-- quoted before 2026-09-06 (74.4%, and the 81-97% range) is therefore an HOURLY
-- share. The alarm asks the same question of a shorter window. A threshold
-- carried across those two bases is wrong by construction.
--
-- ★ RUN WITH psql, NOT A PYTHON DRIVER — \set and :'VAR' are client features.
--   docker compose exec -T postgres psql -U meridian -d meridian -f this_file
--
-- READ THE OUTPUT IN THIS ORDER:
--   1. near_floor_buckets <- IF THIS IS 0, THE RUN SAID NOTHING ABOUT THE FLOOR.
--        MIN_MARKETS is a guard on THIN slates. A sample whose thinnest bucket
--        holds 42 markets cannot validate a 12-market floor, however clean it
--        looks. The 2026-09-06 run had near_floor_buckets = 0 and was read by
--        both of us as confirming MIN_MARKETS=12. It did not.
--   2. pct_below_floor    <- this IS the false-positive rate, per bucket.
--   3. p05 / p01 / worst  <- where the left tail sits.
-- The median is nearly irrelevant: the detector tests for a point mass at zero,
-- so only the left tail can generate a false page.
--
-- ★ ONE STATEMENT ON PURPOSE. An earlier version put the thin-slate sizing in a
-- SECOND statement referencing the same CTE; CTE scope ends with its statement,
-- so it failed with `relation "per_bucket" does not exist` and the only query
-- that could speak about thin slates was the one that did not run. Splitting it
-- would also let the two halves drift onto different bases — the exact bug this
-- file exists to correct. `readable` is a GROUPING COLUMN, not a WHERE clause.
--
-- SAMPLING CAVEAT: these are TUMBLING buckets. The alarm runs a SLIDING window
-- every RUN_EVERY_MIN (144 sweeps/day at 10 min). Tumbling buckets give the rate
-- per INDEPENDENT window; the real daily page count lies between
-- pct_below_floor x 48 and x 144, nearer the top because overlapping windows are
-- positively correlated. Quote the range, not a point estimate.

\set BUCKET_MIN 30
\set FLOOR_PCT 5.0
-- MUST equal MIN_MARKETS in scripts/alarm_v5.py. If these drift apart, this
-- query measures a false-positive rate for a floor the alarm does not use.
\set MIN_MARKETS 12
-- 17:38, NOT 17:39. Measured cliff: 17:37 = 12.87% movers, 17:38 = 3.34%,
-- 17:39 = 0.06%, 17:40 = 0.00%. Cutting at 17:39 leaves the partially-frozen
-- 17:38 bucket inside the "healthy" set, contaminating it in the flattering
-- direction.
\set FREEZE_START '2026-09-05 17:38:00+00'

WITH bucketed AS (
  SELECT date_trunc('hour', captured_at)
           + (interval '1 minute' * :BUCKET_MIN)
             * floor(extract(minute FROM captured_at) / :BUCKET_MIN)   AS bucket,
         -- field 1 is the market TYPE, field 2 the league. VERIFIED against prod
         -- slugs 2026-09-06 on BOTH tapes: cfb (asc 4,104 / tsc 3,661 / aec 67)
         -- and wnba (tsc 63 / asc 56 / aec 13). Not a guess.
         split_part(market_slug, '-', 2)                               AS league,
         market_slug,
         count(DISTINCT (best_bid, best_ask))                          AS pairs
  FROM market_snapshots
  WHERE is_live = true
    AND best_bid IS NOT NULL AND best_ask IS NOT NULL
    AND captured_at > '2026-09-03'
    AND captured_at < :'FREEZE_START'      -- healthy only; incident excluded
  GROUP BY 1, 2, 3
),
per_bucket AS (
  SELECT bucket, league,
         count(*)                                              AS quoted_markets,
         100.0 * count(*) FILTER (WHERE pairs > 1) / count(*)   AS pct_moved
  FROM bucketed
  GROUP BY 1, 2
),
tagged AS (
  SELECT *, (quoted_markets >= :MIN_MARKETS) AS readable FROM per_bucket
)
SELECT league,
       readable,                                       -- false rows = the blind spot
       count(*)                                                        AS buckets,
       min(quoted_markets)                                             AS thinnest,
       max(quoted_markets)                                             AS densest,
       -- ★ DID THIS RUN EXERCISE THE REGIME THE FLOOR GOVERNS? ★
       -- Buckets within 2x of the floor. If 0, the floor is UNTESTED and
       -- pct_below_floor below is silent about it, however reassuring it looks.
       count(*) FILTER (WHERE quoted_markets < 2 * :MIN_MARKETS)       AS near_floor_buckets,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY pct_moved)::numeric, 1) AS median_pct,
       round(percentile_cont(0.05) WITHIN GROUP (ORDER BY pct_moved)::numeric, 1) AS p05,
       round(percentile_cont(0.01) WITHIN GROUP (ORDER BY pct_moved)::numeric, 1) AS p01,
       round(min(pct_moved)::numeric, 1)                               AS worst,
       count(*) FILTER (WHERE pct_moved <= :FLOOR_PCT)                 AS n_below_floor,
       round(100.0 * count(*) FILTER (WHERE pct_moved <= :FLOOR_PCT)
                   / count(*), 3)                                      AS pct_below_floor
FROM tagged
GROUP BY league, readable
ORDER BY league, readable DESC;
