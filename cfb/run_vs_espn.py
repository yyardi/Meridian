"""Our CFB win-probability model vs ESPN's, on the SAME plays.

WHY THIS TEST, TONIGHT. Edge is measured against the contemporaneous
Polymarket mid, and the venue has been frozen at 0.0% price movement for
hours, so that number cannot be produced. This is the strongest test that IS
available: ESPN's in-game WP is a competent production model, we recorded it
per play beside our own inputs, and both are scored against the same realised
outcome.

WHAT A WIN HERE WOULD AND WOULD NOT MEAN.
  WOULD: our state->probability map is better than a competent public one.
         That is the only thing that can produce edge for us, because at ~30s
         feed lag we have no speed advantage -- the price already reflects the
         play by the time we see it.
  WOULD NOT: that we can trade it. The market is a different opponent from
         ESPN and is the one that decides. This is a necessary condition,
         not a sufficient one.

FRAME CONVERSION IS THE TRAP. ESPN reports HOME win probability. Our model
reports POSSESSION-TEAM win probability. Comparing them directly would score
a frame error as a modelling difference on every play where the away team has
the ball -- roughly half of them. Both are converted to the HOME frame here.
"""
import json
import os
import sys

sys.path.insert(0, "/app/cfb")
from cfb_live_fv import GameState, build_features  # noqa: E402
from cfb_train import REG_FEATURES  # noqa: E402

import xgboost as xgb  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

booster = xgb.Booster()
booster.load_model("/app/artifacts/cfb_wp_regulation.json")

eng = create_engine(os.environ["DATABASE_URL"])

SQL = """
WITH final AS (          -- last recorded score per game = the outcome
  SELECT DISTINCT ON (game_id) game_id, home_score, away_score, home, away
  FROM espn_cfb_game_state
  WHERE home_score IS NOT NULL
  ORDER BY game_id, first_seen_at DESC
),
spread AS (              -- the pregame line we recorded (static, verified)
  SELECT game_id, avg(live_spread)::float sp
  FROM espn_cfb_game_state WHERE live_spread IS NOT NULL GROUP BY 1
)
SELECT p.game_id, p.play_id, p.period, p.clock_minutes, p.clock_seconds,
       p.down, p.distance, p.yards_to_goal,
       p.pos_team_score, p.def_pos_team_score, p.drive_is_home_offense,
       p.is_overtime, p.ot_possession_number,
       w.home_win_pct::float AS espn_home_wp,
       s.sp AS closing_spread,
       f.home_score, f.away_score
FROM espn_cfb_live_plays p
JOIN espn_cfb_win_probability w ON w.game_id = p.game_id AND w.play_id = p.play_id
JOIN final  f ON f.game_id = p.game_id
JOIN spread s ON s.game_id = p.game_id
WHERE p.down IS NOT NULL AND p.period IS NOT NULL
  AND w.home_win_pct IS NOT NULL
  AND f.home_score <> f.away_score          -- a tie has no winner to predict
"""

with eng.connect() as c:
    rows = [dict(r._mapping) for r in c.execute(text(SQL))]

print(f"plays with BOTH our inputs and ESPN's WP: {len(rows):,}"
      f"   games: {len({r['game_id'] for r in rows}):,}")
if len(rows) < 500:
    print("TOO FEW to score -- refusing to report a comparison.")
    sys.exit(0)

ours, theirs, ys = [], [], []
by_game = {}          # accumulated IN THIS LOOP; see the note below
skipped_ot = skipped_feat = 0
for r in rows:
    if r["is_overtime"]:
        skipped_ot += 1       # the OT head is separate; not scored here
        continue
    st = GameState(
        period=r["period"], clock_minutes=r["clock_minutes"] or 0,
        clock_seconds=r["clock_seconds"] or 0, down=r["down"],
        distance=r["distance"], yards_to_goal=r["yards_to_goal"],
        pos_team_score=r["pos_team_score"] or 0,
        def_pos_team_score=r["def_pos_team_score"] or 0,
        drive_is_home_offense=bool(r["drive_is_home_offense"]),
        pos_team_timeouts=3, def_pos_team_timeouts=3,
        is_overtime=False, ot_possession_number=None)
    f = build_features(st, r["closing_spread"])
    # `receives_2h_kickoff` is ALWAYS None from state alone -- it needs to know
    # who took the opening kickoff, which GameState does not carry. The trainer
    # passes it through as missing (xgb missing=nan) and never splits on it, so
    # filtering rows on it rejects EVERY row. Mirror the trainer exactly.
    vec = [float("nan") if f.get(c) is None else f.get(c) for c in REG_FEATURES]
    if f.get("spread_time") is None or f.get("score_differential") is None:
        skipped_feat += 1     # these two are load-bearing; missing is fatal
        continue
    p_pos = float(booster.predict(
        xgb.DMatrix([vec], feature_names=REG_FEATURES,
                    missing=float("nan")))[0])
    # BOTH into the HOME frame, or half the plays score a frame error.
    p_home = p_pos if r["drive_is_home_offense"] else 1.0 - p_pos
    y = 1 if r["home_score"] > r["away_score"] else 0
    ours.append(p_home)
    theirs.append(r["espn_home_wp"])
    ys.append(y)
    by_game.setdefault(r["game_id"], []).append(
        ((p_home - y) ** 2, (r["espn_home_wp"] - y) ** 2))

n = len(ys)
print(f"scored {n:,} plays   "
      f"(skipped {skipped_ot:,} overtime, {skipped_feat:,} incomplete state)")
if skipped_feat:
    print(f"  NOTE: {skipped_feat} non-overtime plays lacked a load-bearing\n"
          f"  feature. Reported separately because the old combined counter\n"
          f"  could not distinguish the harmless case from the one that used\n"
          f"  to misalign the per-game split.")
if n < 500:
    print("TOO FEW after filtering -- refusing to report.")
    sys.exit(0)


def brier(ps):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def acc(ps):
    return sum(1 for p, y in zip(ps, ys) if (p >= 0.5) == (y == 1)) / len(ys)


bo, bt = brier(ours), brier(theirs)
print("\n=== OURS vs ESPN, same plays, same outcomes, HOME frame ===")
print(f"  Brier    ours {bo:.4f}   espn {bt:.4f}   "
      f"{'OURS BETTER' if bo < bt else 'ESPN BETTER'} by {abs(bo - bt):.4f}")
print(f"  accuracy ours {acc(ours) * 100:.1f}%   espn {acc(theirs) * 100:.1f}%")

# game-clustered: the independent unit is the game, never the play.
# by_game was filled in the scoring loop above, where each row and its own
# prediction are in scope together. Do NOT rebuild it by zipping a
# re-derived row list against `ours` -- the scoring loop skips on OT AND on
# missing features, so any filter applied here that is not identical
# silently shifts every subsequent play into the wrong game.
diffs = [sum(a for a, _ in v) / len(v) - sum(b for _, b in v) / len(v)
         for v in by_game.values()]
g = len(diffs)
m = sum(diffs) / g
sd = (sum((d - m) ** 2 for d in diffs) / (g - 1)) ** 0.5 if g > 1 else 0.0
half = 1.96 * sd / (g ** 0.5) if g > 1 else 0.0
print(f"\n  game-clustered Brier difference (negative = we win):")
print(f"    {m:+.4f}  CI [{m - half:+.4f}, {m + half:+.4f}]  over {g} games"
      f"   {'EXCLUDES ZERO' if (m - half) * (m + half) > 0 else 'spans zero'}")
print(f"    games we beat ESPN on: {sum(1 for d in diffs if d < 0)}/{g}")
if g < 25:
    print("    UNDERPOWERED (< 25 games) -- treat as directional only.")
