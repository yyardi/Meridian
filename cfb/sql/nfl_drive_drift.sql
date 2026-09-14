WITH trig AS (
  SELECT 'MIDFIELD' arm, l.game_id, l.drive_id, min(l.wall_clock) wc,
         bool_and(l.drive_is_home_offense) home_off
  FROM espn_cfb_live_plays l
  WHERE l.league='nfl' AND l.yards_to_goal BETWEEN 1 AND 40 AND l.down BETWEEN 1 AND 4
    AND l.wall_clock IS NOT NULL AND NOT coalesce(l.is_overtime,false)
  GROUP BY 1,2,3
  UNION ALL
  SELECT 'SCORING', l.game_id, l.play_id, l.wall_clock, l.drive_is_home_offense
  FROM espn_cfb_live_plays l
  WHERE l.league='nfl' AND l.scoring_play AND l.wall_clock IS NOT NULL
    AND NOT coalesce(l.is_overtime,false)
), t AS (
  SELECT trig.*, m.venue_game_id vg, CASE WHEN trig.home_off THEN -1 ELSE 1 END sgn
  FROM trig JOIN cfb_game_map m ON m.espn_game_id = trig.game_id
  WHERE m.venue_game_id IS NOT NULL
), q AS (
  SELECT t.*,
    (SELECT (s.best_bid+s.best_ask)/2 FROM market_snapshots s
       WHERE s.game_id=t.vg AND s.sports_market_type LIKE '%winner' AND s.best_bid IS NOT NULL
         AND s.captured_at >= t.wc AND s.captured_at < t.wc + interval '60 seconds'
       ORDER BY s.captured_at LIMIT 1) m0,
    (SELECT (s.best_bid+s.best_ask)/2 FROM market_snapshots s
       WHERE s.game_id=t.vg AND s.sports_market_type LIKE '%winner' AND s.best_bid IS NOT NULL
         AND s.captured_at >= t.wc + interval '30 seconds' AND s.captured_at < t.wc + interval '120 seconds'
       ORDER BY s.captured_at LIMIT 1) m30,
    (SELECT (s.best_bid+s.best_ask)/2 FROM market_snapshots s
       WHERE s.game_id=t.vg AND s.sports_market_type LIKE '%winner' AND s.best_bid IS NOT NULL
         AND s.captured_at >= t.wc + interval '300 seconds' AND s.captured_at < t.wc + interval '420 seconds'
       ORDER BY s.captured_at LIMIT 1) m300
  FROM t
)
SELECT arm, horizon, sum(n) n, count(*) g,
       round(avg(gm)::numeric,3) mean_per_game_c,
       round((stddev_samp(gm)/sqrt(count(*)))::numeric,3) se_c,
       round((avg(gm) - 2.145*stddev_samp(gm)/sqrt(count(*)))::numeric,3) lo,
       round((avg(gm) + 2.145*stddev_samp(gm)/sqrt(count(*)))::numeric,3) hi
FROM (
  SELECT arm, horizon, game_id, count(*) n, avg(move) gm FROM (
    SELECT arm, game_id, '030s' horizon, sgn*(m30-m0)*100 move FROM q WHERE m0 IS NOT NULL AND m30 IS NOT NULL
    UNION ALL
    SELECT arm, game_id, '300s', sgn*(m300-m0)*100 FROM q WHERE m0 IS NOT NULL AND m300 IS NOT NULL
  ) y GROUP BY 1,2,3
) z GROUP BY 1,2 ORDER BY 1,2;
