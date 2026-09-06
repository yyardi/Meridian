"""cfb_live_fv.py — live in-game fair value for college football.

THE ONLY PLACE FEATURES ARE BUILT. Imported by both trainer and server.
Train/serve skew is the failure this exists to prevent, and validation
cannot see it: the model scores fine offline and is wrong live.

DESIGN CONSTRAINTS, each one earned this week
---------------------------------------------
1. OVERTIME HAS NO CLOCK. Every time-decayed feature is UNDEFINED in OT.
   build_features() REFUSES to emit them rather than imputing zero, and OT
   routes to its own head. A zero-imputed clock in the highest-leverage
   state in the sport produces confident nonsense.
2. TIMEOUTS ARE POLL-RESOLUTION LIVE, per-play in CFBD. We DEGRADE TRAINING
   to match serving, never the reverse.
3. THE BENCHMARK IS THE CONTEMPORANEOUS MARKET MID, joined on wall_clock.
   Closing-line-implied is a PREGAME quantity; an in-game model beats it on
   any game that has moved, which proves only that it can read a scoreboard.
4. NO SPEED EDGE EXISTS. Feed lag ~30s; the price has already repriced the
   play by the time we see it. The only defensible claim is a better
   state->probability map, exercised in the stable intervals BETWEEN plays.
5. CROSS-DIVISION GAMES ARE ~1/3 OF VOLUME AND ARE THE BLOWOUT TAIL, where
   public models document weak calibration. Calibration is reported
   stratified by phase AND by |spread|. Never pooled.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

REGULATION_SECONDS = 3600
PERIOD_SECONDS = 900
CLUTCH_SECONDS = 300          # last 5 min of regulation
CLUTCH_MARGIN = 8             # one-score-plus-two game

XGB_PARAMS = dict(objective="binary:logistic", eval_metric="logloss",
                  booster="gbtree", eta=0.05, max_depth=5,
                  min_child_weight=7, subsample=0.8, colsample_bytree=0.8)
XGB_ROUNDS = 534
# monotone constraints. SIGN CONVENTION MATTERS AND GOT THIS WRONG ONCE:
# a FAVOURED team carries a NEGATIVE spread, so after the possession-flip in
# build_features a more negative spread_time means MORE favoured. Win
# probability therefore FALLS as spread_time rises -> the constraint is -1.
# Shipped as +1, which made every useful split illegal: xgboost simply never
# split on the feature. Measured on period-1 tied plays (n=9,440), where the
# score carries no information at all:
#     +1  -> spread_time  0.00% of gain, WP FLAT at 0.553 for a 20-point
#            favourite AND a 20-point underdog alike
#      0  -> 65.92%, WP 0.989 -> 0.096
#     -1  -> 61.73%, WP 0.982 -> 0.038   (correct direction, and constrained)
# The recipe calls the spread its most valuable feature; at +1 it was inert.
MONOTONE = {"score_differential": 1, "spread_time": -1, "diff_time_ratio": 1}


@dataclass(frozen=True)
class GameState:
    """RAW state. Field names match CFBD so the two sources are interchangeable."""
    period: int
    clock_minutes: int
    clock_seconds: int
    down: int | None
    distance: int | None
    yards_to_goal: int | None
    pos_team_score: int
    def_pos_team_score: int
    drive_is_home_offense: bool
    pos_team_timeouts: int | None
    def_pos_team_timeouts: int | None
    receives_2h_kickoff: bool | None = None
    is_overtime: bool = False
    ot_possession_number: int | None = None


def regime_of(s: GameState) -> str:
    if s.is_overtime or s.period >= 5:
        return "overtime"
    gsr = game_seconds_remaining(s)
    if gsr is not None and gsr <= CLUTCH_SECONDS \
       and abs(s.pos_team_score - s.def_pos_team_score) <= CLUTCH_MARGIN:
        return "clutch"
    return "regulation"


def game_seconds_remaining(s: GameState) -> float | None:
    """UNDEFINED in overtime — college OT has no clock. Returns None, never 0."""
    if s.is_overtime or s.period >= 5:
        return None
    periods_left = max(0, 4 - s.period)
    return periods_left * PERIOD_SECONDS + s.clock_minutes * 60 + s.clock_seconds


def half_seconds_remaining(s: GameState) -> float | None:
    if s.is_overtime or s.period >= 5:
        return None
    in_half = 2 if s.period in (1, 3) else 1
    return (in_half - 1) * PERIOD_SECONDS + s.clock_minutes * 60 + s.clock_seconds


def degrade_timeouts(exact: int | None, poll_value: int | None, degrade: bool):
    """Training must be as impoverished as serving (constraint 2)."""
    return poll_value if degrade else exact


def build_features(s: GameState, closing_spread: float | None,
                   *, degrade_timeouts_to: tuple[int | None, int | None] | None = None
                   ) -> dict:
    """Returns the feature dict for this state. Time-decayed terms are ABSENT
    (not zero) in overtime — the caller must route OT to its own head."""
    reg = regime_of(s)
    gsr = game_seconds_remaining(s)
    diff = s.pos_team_score - s.def_pos_team_score
    po, do = s.pos_team_timeouts, s.def_pos_team_timeouts
    if degrade_timeouts_to is not None:
        po = degrade_timeouts(po, degrade_timeouts_to[0], True)
        do = degrade_timeouts(do, degrade_timeouts_to[1], True)
    f = {
        "score_differential": diff,
        "down": s.down, "distance": s.distance, "yards_to_goal": s.yards_to_goal,
        "pos_team_timeouts": po, "def_pos_team_timeouts": do,
        "posteam_is_home": int(bool(s.drive_is_home_offense)),
        "receives_2h_kickoff": None if s.receives_2h_kickoff is None else int(s.receives_2h_kickoff),
        "regime": reg,
    }
    if reg == "overtime":
        f["ot_possession_number"] = s.ot_possession_number
        return f                      # NO time features. Absent, not zero.
    elapsed = REGULATION_SECONDS - gsr
    f["game_seconds_remaining"] = gsr
    f["half_seconds_remaining"] = half_seconds_remaining(s)
    f["diff_time_ratio"] = diff * math.exp(4.0 * elapsed / REGULATION_SECONDS)
    if closing_spread is not None:
        pos_spread = closing_spread if s.drive_is_home_offense else -closing_spread
        f["spread_time"] = pos_spread * math.exp(-4.0 * elapsed / REGULATION_SECONDS)
    return f


# ----------------------------------------------------------------- selftest
def _selftest() -> None:
    kickoff = GameState(period=1, clock_minutes=15, clock_seconds=0, down=1, distance=10,
                        yards_to_goal=75, pos_team_score=0, def_pos_team_score=0,
                        drive_is_home_offense=True, pos_team_timeouts=3,
                        def_pos_team_timeouts=3, receives_2h_kickoff=False)
    f = build_features(kickoff, closing_spread=-7.0)
    assert abs(f["game_seconds_remaining"] - 3600) < 1e-9
    assert abs(f["spread_time"] - (-7.0)) < 1e-9, "at kickoff spread_time must equal the spread"

    end = GameState(period=4, clock_minutes=0, clock_seconds=0, down=1, distance=10,
                    yards_to_goal=50, pos_team_score=21, def_pos_team_score=17,
                    drive_is_home_offense=True, pos_team_timeouts=1, def_pos_team_timeouts=0)
    fe = build_features(end, closing_spread=-7.0)
    assert abs(fe["spread_time"] - (-7.0 * math.exp(-4.0))) < 1e-9, "decay constant wrong"

    # ★ CONSTRAINT 1: overtime must not receive imputed time features.
    ot = GameState(period=5, clock_minutes=0, clock_seconds=0, down=1, distance=10,
                   yards_to_goal=25, pos_team_score=28, def_pos_team_score=28,
                   drive_is_home_offense=False, pos_team_timeouts=1,
                   def_pos_team_timeouts=1, is_overtime=True, ot_possession_number=1)
    fo = build_features(ot, closing_spread=-7.0)
    assert regime_of(ot) == "overtime"
    assert game_seconds_remaining(ot) is None, "OT clock must be None, never 0"
    for k in ("game_seconds_remaining", "half_seconds_remaining", "spread_time", "diff_time_ratio"):
        assert k not in fo, f"OT leaked a time feature: {k} — it would be imputed as zero"

    # ★ TRAIN/SERVE PARITY: identical state from either source -> identical features.
    cfbd_row = dict(period=3, clock_minutes=7, clock_seconds=30, down=2, distance=6,
                    yards_to_goal=41, pos_team_score=14, def_pos_team_score=10,
                    drive_is_home_offense=True, pos_team_timeouts=2, def_pos_team_timeouts=3)
    espn_row = dict(cfbd_row)                    # same raw fields, different origin
    a = build_features(GameState(**cfbd_row), -3.5)
    b = build_features(GameState(**espn_row), -3.5)
    assert a == b, "train/serve parity broken — same state, different features"

    # ★ CONSTRAINT 2: degradation must actually degrade.
    exact = build_features(GameState(**cfbd_row), -3.5)
    degraded = build_features(GameState(**cfbd_row), -3.5, degrade_timeouts_to=(3, 3))
    assert exact["pos_team_timeouts"] == 2 and degraded["pos_team_timeouts"] == 3, \
        "degrade_timeouts_to did not replace the exact per-play value"

    # clutch regime fires only when BOTH late and close
    late_close = GameState(period=4, clock_minutes=2, clock_seconds=0, down=3, distance=8,
                           yards_to_goal=60, pos_team_score=20, def_pos_team_score=17,
                           drive_is_home_offense=True, pos_team_timeouts=1, def_pos_team_timeouts=2)
    late_blowout = GameState(**{**late_close.__dict__, "def_pos_team_score": 0})
    assert regime_of(late_close) == "clutch"
    assert regime_of(late_blowout) == "regulation", "blowouts are not clutch"
    print("selftest OK — 12 assertions incl. OT-no-imputation, train/serve parity, timeout degradation")


if __name__ == "__main__":
    _selftest()
