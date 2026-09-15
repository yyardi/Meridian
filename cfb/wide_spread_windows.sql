\pset footer off
\t on
SET max_parallel_workers_per_gather = 0;
-- The module's predicate and constants, MIRRORED (MIN_SPREAD 0.01,
-- MAX_SPREAD 0.50 for this run, MIN_MID/MAX_MID 0.20/0.80,
-- HORIZON_TOLERANCE (0.5, 2.0), horizon 30s). Sampled at 5% because one CFB
-- day is ~1M live two-sided rows on a two-core box; sampling QUOTES is a
-- random subsample of WINDOWS, since each window is one quote and its own
-- t+30 mark, so it does not disturb the game clustering.
WITH q AS (
  SELECT game_id, market_slug, captured_at,
         (best_bid + best_ask) / 2.0 AS mid,
         (best_ask - best_bid)       AS spread
  FROM market_snapshots
  WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL AND game_id IS NOT NULL
    AND is_live IS TRUE
    AND captured_at >= CAST(:'lo' AS timestamptz)
    AND captured_at <  CAST(:'hi' AS timestamptz)
    AND market_slug LIKE :'pat'
    AND (best_ask - best_bid) BETWEEN 0.01 AND 0.50
    AND (best_bid + best_ask) / 2.0 BETWEEN 0.20 AND 0.80
    AND random() < 0.05)
SELECT q.game_id || chr(9) || q.market_slug || chr(9)
       || round(q.spread, 4) || chr(9)
       || round(m.mid - q.mid, 4) || chr(9)
       || CASE WHEN m.mid <= q.mid - q.spread/2 THEN 1 ELSE 0 END || chr(9)
       || CASE WHEN m.mid >= q.mid + q.spread/2 THEN 1 ELSE 0 END
FROM q
CROSS JOIN LATERAL (
  SELECT (s.best_bid + s.best_ask) / 2.0 AS mid
  FROM market_snapshots s
  WHERE s.market_slug = q.market_slug
    AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL
    AND s.captured_at >= q.captured_at + interval '15 seconds'
    AND s.captured_at <= q.captured_at + interval '60 seconds'
  ORDER BY abs(extract(epoch FROM (s.captured_at
            - (q.captured_at + interval '30 seconds'))))
  LIMIT 1) AS m;
