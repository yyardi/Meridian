"""E2 — what structurally distinguishes the games where we LOSE to ESPN?

The asymmetry is the signature of a few broken games, not broad weakness:
loss mean +0.0873 against loss MEDIAN +0.0088, largest +0.3085. A handful of
games carry the whole gap.

RULED OUT BEFORE RUNNING. Overtime PLAYS are already excluded from the ESPN
comparison (run_vs_espn.py skips is_overtime), so they cannot explain a gap in
a sample that does not contain them. Whether a game REACHED overtime is a
different and still-live hypothesis, flagged separately below.

This also recomputes the per-game split by a route independent of
run_vs_espn.py -- accumulating inside the scoring loop rather than zipping a
re-derived row list -- so the 37/48 figure gets checked rather than repeated.

FLAGS, each a candidate structural cause:
  went_to_ot      the game reached OT at all (close, genuinely hard to price)
  garbage_q4      fraction of Q4 plays at |margin| >= 24
  max_margin      blowout depth
  final_margin    how close it actually finished
  down0           ESPN's down=0 sentinel, which passes `down IS NOT NULL`
  desync          pos/def score does not reconcile with home/away score.
                  An INDEPENDENT validity check, not an integrity one: it can
                  only pass if drive_is_home_offense and the score pair agree,
                  so it catches possession mislabels AND live-score divergence
                  without trusting either field on its own.
"""
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

# league filter: the tables are FOOTBALL-shaped, so NFL rows live here too.
# Harmless today (NFL opens 09-10) and wrong the moment it is not.
SQL = """
WITH final AS (
  SELECT DISTINCT ON (game_id) game_id, home_score, away_score
  FROM espn_cfb_game_state
  WHERE home_score IS NOT NULL AND league = 'cfb'
  ORDER BY game_id, first_seen_at DESC
),
spread AS (
  SELECT game_id, avg(live_spread)::float sp
  FROM espn_cfb_game_state
  WHERE live_spread IS NOT NULL AND league = 'cfb' GROUP BY 1
)
SELECT p.game_id, p.play_id, p.period, p.clock_minutes, p.clock_seconds,
       p.down, p.distance, p.yards_to_goal, p.pos_team_score,
       p.def_pos_team_score, p.drive_is_home_offense, p.is_overtime,
       p.home_score AS play_home, p.away_score AS play_away,
       w.home_win_pct::float AS espn_wp, s.sp AS closing_spread,
       f.home_score, f.away_score,
       COALESCE(m.division, 'unmapped') AS division
FROM espn_cfb_live_plays p
JOIN espn_cfb_win_probability w ON w.game_id=p.game_id AND w.play_id=p.play_id
JOIN final f ON f.game_id = p.game_id
JOIN spread s ON s.game_id = p.game_id
LEFT JOIN cfb_game_map m ON m.espn_game_id = p.game_id
WHERE p.league = 'cfb'
  AND p.down IS NOT NULL AND p.period IS NOT NULL
  AND w.home_win_pct IS NOT NULL
  AND f.home_score <> f.away_score
"""

with eng.connect() as c:
    rows = [dict(r._mapping) for r in c.execute(text(SQL))]
print(f"plays with both our inputs and ESPN's WP: {len(rows):,}   "
      f"games: {len({r['game_id'] for r in rows}):,}")
if len(rows) < 500:
    print("TOO FEW to audit — refusing to report.")
    sys.exit(0)

games = {}
skip_ot = skip_feat = 0
for r in rows:
    g = games.setdefault(r["game_id"], {
        "ours": [], "espn": [], "y": [], "ot": False, "maxmarg": 0,
        "q4": [], "div": r["division"], "d0": 0, "desync": 0, "final": None})

    if r["down"] == 0:
        g["d0"] += 1
    # desync is counted over EVERY row, including the ones the model skips,
    # because a bad row that never reaches the model still says the feed for
    # that game was unreliable.
    ph, pa = r["play_home"], r["play_away"]
    ps, ds = r["pos_team_score"], r["def_pos_team_score"]
    if None not in (ph, pa, ps, ds) and r["drive_is_home_offense"] is not None:
        want = (ps, ds) if r["drive_is_home_offense"] else (ds, ps)
        if want != (ph, pa):
            g["desync"] += 1

    if r["is_overtime"]:
        g["ot"] = True
        skip_ot += 1
        continue
    if not r["down"]:                    # the down=0 sentinel is not a down
        skip_feat += 1
        continue

    st = GameState(period=r["period"], clock_minutes=r["clock_minutes"] or 0,
                   clock_seconds=r["clock_seconds"] or 0, down=r["down"],
                   distance=r["distance"], yards_to_goal=r["yards_to_goal"],
                   pos_team_score=ps or 0, def_pos_team_score=ds or 0,
                   drive_is_home_offense=bool(r["drive_is_home_offense"]),
                   pos_team_timeouts=3, def_pos_team_timeouts=3,
                   is_overtime=False, ot_possession_number=None)
    f = build_features(st, r["closing_spread"])
    # identical to the scoring loop in run_vs_espn.py -- both are load-bearing
    if f.get("spread_time") is None or f.get("score_differential") is None:
        skip_feat += 1
        continue
    vec = [float("nan") if f.get(c) is None else f.get(c) for c in REG_FEATURES]
    p_pos = float(booster.predict(xgb.DMatrix(
        [vec], feature_names=REG_FEATURES, missing=float("nan")))[0])
    p_home = p_pos if r["drive_is_home_offense"] else 1.0 - p_pos
    y = 1 if r["home_score"] > r["away_score"] else 0

    g["ours"].append(p_home)
    g["espn"].append(r["espn_wp"])
    g["y"].append(y)
    g["final"] = (r["home_score"], r["away_score"])
    marg = abs((ph or 0) - (pa or 0))
    g["maxmarg"] = max(g["maxmarg"], marg)
    if r["period"] == 4:
        g["q4"].append(marg)

print(f"skipped {skip_ot:,} overtime, {skip_feat:,} incomplete state")

out = []
for gid, g in games.items():
    if len(g["y"]) < 20:
        continue
    n = len(g["y"])
    bo = sum((p - y) ** 2 for p, y in zip(g["ours"], g["y"])) / n
    be = sum((p - y) ** 2 for p, y in zip(g["espn"], g["y"])) / n
    out.append({
        "game": gid, "n": n, "diff": bo - be, "ours": bo, "espn": be,
        "ot": g["ot"], "d0": g["d0"], "desync": g["desync"], "div": g["div"],
        "final_margin": abs(g["final"][0] - g["final"][1]),
        "max_margin": g["maxmarg"],
        "garbage_q4": (sum(1 for m in g["q4"] if m >= 24) / len(g["q4"]))
                      if g["q4"] else 0.0})

out.sort(key=lambda d: -d["diff"])
losers = [d for d in out if d["diff"] > 0]
winners = [d for d in out if d["diff"] <= 0]
print(f"\ngames scored: {len(out)}   we LOSE {len(losers)}, win {len(winners)}")
print("  (independent recomputation of the 37/48 split — accumulated per game\n"
      "   inside the scoring loop, not zipped against a re-derived row list)")

print("\n=== THE LOSERS, worst first ===")
print(f"  {'game':<12}{'n':>5}{'diff':>9}{'fin':>5}{'maxm':>6}{'gb_q4':>7}"
      f"  {'OT':<4}{'div':<10}{'dn0':>5}{'desync':>7}")
for d in losers:
    print(f"  {d['game']:<12}{d['n']:>5}{d['diff']:>+9.4f}"
          f"{d['final_margin']:>5}{d['max_margin']:>6}{d['garbage_q4']:>7.2f}"
          f"  {'yes' if d['ot'] else '-':<4}{d['div']:<10}"
          f"{d['d0']:>5}{d['desync']:>7}")

print("\n=== DO THE FLAGS SEPARATE LOSERS FROM WINNERS? ===")
print(f"  {'flag':<30}{'losers':>9}{'winners':>9}")
TESTS = (("reached overtime", lambda d: d["ot"]),
         ("garbage Q4 (>=50% at 24+)", lambda d: d["garbage_q4"] >= 0.5),
         ("blowout (max margin >=28)", lambda d: d["max_margin"] >= 28),
         ("close final (<=7)", lambda d: d["final_margin"] <= 7),
         ("has down=0 rows", lambda d: d["d0"] > 0),
         ("has desynced rows", lambda d: d["desync"] > 0))
for label, fn in TESTS:
    lo = sum(1 for d in losers if fn(d)) / max(len(losers), 1)
    wi = sum(1 for d in winners if fn(d)) / max(len(winners), 1)
    print(f"  {label:<30}{lo*100:>8.0f}%{wi*100:>8.0f}%")

print("\n=== division ===")
for dv in sorted({d["div"] for d in out}):
    print(f"  {dv:<12} losers {sum(1 for d in losers if d['div']==dv):>3}"
          f"   winners {sum(1 for d in winners if d['div']==dv):>3}")

tot = sum(d["diff"] * d["n"] for d in out)
if tot:
    top3 = sum(d["diff"] * d["n"] for d in losers[:3])
    print(f"\n=== concentration ===")
    print(f"  top 3 losers carry {100*top3/tot:+.0f}% of the net weighted gap")
    print(f"  net weighted gap {tot:+.1f} play-Brier units "
          f"(negative = we win overall)")

print("\n=== WHAT THIS CANNOT SAY ===")
print("  A flag that separates losers from winners is a CORRELATE, not a")
print("  licence to drop those games. Excluding a state because we are bad at")
print("  it is how a backtest gets flattered. The only honest use is: fix the")
print("  state (a data defect) or special-case it in the MODEL (a real regime)")
print("  and re-run the full comparison including those games.")
