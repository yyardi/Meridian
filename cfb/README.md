# The CFB fair-value model

Written by the research agent; run in the `trainer` image, which is the only
image built with xgboost + scikit-learn (the `model` extra).

    docker compose -f docker-compose.yml -f docker-compose.trainer.yml \
      run --rm trainer python3 -m cfb.<module>

## What the data looks like by the time it reaches here

Three recorded tables plus one map, all populated on prod:

| table | what |
|---|---|
| `espn_cfb_live_plays` | per-play raw state: down, distance, `yards_to_goal`, possession, scores, `wall_clock` |
| `espn_cfb_game_state` | per-poll game level: timeouts, live line, ESPN's own win probability |
| `espn_cfb_win_probability` | ESPN's per-play WP — a benchmark, never a feature |
| `cfb_game_map` | ESPN event id ↔ venue game id, plus division and match confidence |

The join that makes any of this tradeable, verified end to end:
**1,709 plays across 14 games find a market price a mean 1.4 s from their own
`wall_clock`.**

    espn_cfb_live_plays.game_id
      -> cfb_game_map.espn_game_id .. cfb_game_map.venue_game_id
      -> market_snapshots.game_id, nearest captured_at to wall_clock

## Three constraints that are not negotiable

**Overtime has no clock.** `game_seconds_remaining` is undefined there, and so
is every time-decayed feature including `spread_time`. Emit nothing rather
than zero, and route OT to its own head — a silently imputed zero produces
confident nonsense in the highest-leverage state in the sport.

**We have no informational advantage.** Our observation lags ESPN's own play
stamp by ~30 s, and the market has already moved by then. The only defensible
claim is a better state→probability map than the market's, exercised in the
stable intervals *between* plays. A model sold as reacting to plays would be
false.

**Timeouts are impoverished live.** ESPN gives game-level `timeoutsUsed` at
poll time where CFBD gives exact per-play counts. Degrade the training data to
match — never enrich the serving data — or check importance first and drop the
feature from both.

## What "it works" means here

Not calibration, and not an information coefficient with a borrowed threshold.
**Act on the disagreement, score against the outcome, charge the measured
cost**, game-clustered over whole games. The output is cents per trade net of
cost, with an interval. Calibration (stratified by phase *and* by `|spread|`,
because cross-division blowouts are a third of volume and the documented weak
spot) and residual-form IC are diagnostics, not the bar.

The kill criterion: if it does not beat the **contemporaneous** Polymarket mid
out of sample, it does not go live. The closing line is a pregame quantity and
an in-game model beats it just by reading the scoreboard.
