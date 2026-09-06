"""cfb_train.py -- fit the live win-probability model. TWO HEADS, not one.

WHY TWO. Overtime has no clock, so game_seconds_remaining, spread_time and
diff_time_ratio are UNDEFINED there -- build_features() omits them rather than
imputing zero. A single model would therefore receive missing values in the
highest-leverage state in the sport and impute them. So:

  REGULATION head : regulation + clutch (identical feature set; clutch is a
                    reporting stratum, not a separate model -- I am not
                    inventing a blending scheme the recipe does not specify)
  OVERTIME head   : no time features at all; ot_possession_number instead

MONOTONICITY is asserted, not assumed: win probability must not DECREASE as
score_differential rises. _check_monotone() probes the fitted model and fails
the run if it does. A model that says scoring more points is worse is broken in
a way calibration will not catch.

TRAIN/SERVE SKEW: features come from cfb_live_fv.build_features() only -- the
same function the server calls. Timeouts are degraded to serving resolution
when degrade_timeouts=True (default), because CFBD is per-play and our live
feed is per-poll.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfb_live_fv import build_features, regime_of, XGB_PARAMS, XGB_ROUNDS, MONOTONE

REG_FEATURES = ["score_differential", "game_seconds_remaining", "half_seconds_remaining",
                "diff_time_ratio", "spread_time", "down", "distance", "yards_to_goal",
                "pos_team_timeouts", "def_pos_team_timeouts", "posteam_is_home",
                "receives_2h_kickoff"]
OT_FEATURES = ["score_differential", "down", "distance", "yards_to_goal",
               "pos_team_timeouts", "def_pos_team_timeouts", "posteam_is_home",
               "ot_possession_number"]


def split_by_regime(states, spreads, labels, groups, degrade_timeouts=True, poll_timeouts=None):
    """-> {'regulation': (X, y, g, cols), 'overtime': (...)}"""
    out = {"regulation": ([], [], []), "overtime": ([], [], [])}
    for i, s in enumerate(states):
        deg = poll_timeouts[i] if (degrade_timeouts and poll_timeouts) else None
        f = build_features(s, spreads[i], degrade_timeouts_to=deg)
        head = "overtime" if f["regime"] == "overtime" else "regulation"
        cols = OT_FEATURES if head == "overtime" else REG_FEATURES
        out[head][0].append([f.get(c) for c in cols])
        out[head][1].append(labels[i])
        out[head][2].append(groups[i])
    return {k: (v[0], v[1], v[2], OT_FEATURES if k == "overtime" else REG_FEATURES)
            for k, v in out.items() if v[0]}


def _check_monotone(predict_fn, cols, base_row, feature="score_differential", steps=(-21, -7, 0, 7, 21)):
    """A model where scoring more points LOWERS win probability is broken."""
    if feature not in cols: return True, "feature absent from this head"
    idx = cols.index(feature)
    probs = []
    for d in steps:
        r = list(base_row); r[idx] = d
        probs.append(predict_fn([r])[0])
    ok = all(b >= a - 1e-6 for a, b in zip(probs, probs[1:]))
    return ok, f"{feature}: " + " -> ".join(f"{d:+d}:{p:.3f}" for d, p in zip(steps, probs))


def fit(head_data, num_round=XGB_ROUNDS, params=None):
    import xgboost as xgb
    X, y, _, cols = head_data
    p = dict(params or XGB_PARAMS)
    p["monotone_constraints"] = "(" + ",".join(str(MONOTONE.get(c, 0)) for c in cols) + ")"
    d = xgb.DMatrix(X, label=y, feature_names=cols, missing=float("nan"))
    booster = xgb.train(p, d, num_boost_round=num_round)
    def predict(rows):
        return booster.predict(xgb.DMatrix(rows, feature_names=cols, missing=float("nan")))
    ok, msg = _check_monotone(predict, cols, X[0])
    if not ok:
        raise RuntimeError(f"MONOTONICITY VIOLATED after fit -- {msg}")
    return booster, predict, msg


def _selftest():
    from cfb_live_fv import GameState
    reg = GameState(period=2, clock_minutes=5, clock_seconds=0, down=1, distance=10,
                    yards_to_goal=60, pos_team_score=7, def_pos_team_score=3,
                    drive_is_home_offense=True, pos_team_timeouts=3, def_pos_team_timeouts=2)
    ot = GameState(period=5, clock_minutes=0, clock_seconds=0, down=1, distance=10,
                   yards_to_goal=25, pos_team_score=28, def_pos_team_score=28,
                   drive_is_home_offense=False, pos_team_timeouts=1,
                   def_pos_team_timeouts=1, is_overtime=True, ot_possession_number=1)
    d = split_by_regime([reg, ot], [-3.5, -3.5], [1, 0], ["g1", "g1"])
    assert set(d) == {"regulation", "overtime"}, "both heads must be produced"
    assert "spread_time" in d["regulation"][3] and "spread_time" not in d["overtime"][3], \
        "OT head must not carry time features"
    assert "ot_possession_number" in d["overtime"][3]
    # * the OT row must not have leaked a numeric clock into the regulation head
    assert len(d["regulation"][0]) == 1 and len(d["overtime"][0]) == 1
    # * monotonicity checker must CATCH a violating model
    cols = REG_FEATURES; base = [0] * len(cols)
    bad = lambda rows: [0.9 - 0.01 * rows[0][cols.index("score_differential")]]
    ok, msg = _check_monotone(bad, cols, base)
    assert not ok, "monotonicity checker failed to catch an inverted model"
    good = lambda rows: [0.5 + 0.01 * rows[0][cols.index("score_differential")]]
    ok2, _ = _check_monotone(good, cols, base)
    assert ok2
    print("selftest OK -- two heads split, OT carries no time features, monotonicity checker catches inversion")


if __name__ == "__main__":
    _selftest()
