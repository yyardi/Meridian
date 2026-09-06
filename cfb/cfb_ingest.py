"""cfb_ingest.py -- CFBD historical plays -> GameState, for training.

FCS COMES FROM THE SAME ENDPOINT WITH THE SAME SCHEMA (verified by meridian-a1:
/plays?year=2024&week=1&classification=fbs -> 17,239 plays; classification=fcs
-> 15,610 plays, identical fields). So there is ONE source and one parser, and
source cannot be collinear with division -- the objection to merging two
sources is dissolved, not overruled.

FIELD PROVENANCE. VERIFIED present by direct API call: away, clock, defense,
defenseConference, defenseScore, defenseTimeouts, distance, down, driveId,
driveNumber, gameId, home, offense. ASSUMED (listed in ASSUMED_FIELDS, and the
mapper RAISES rather than defaulting if any is absent): period, offenseScore,
offenseTimeouts, yardsToGoal. A default here would silently become a feature.

TRAIN/SERVE SPREAD ASYMMETRY -- check, do not assume. Training takes the
closing spread from CFBD; serving takes it from our sportsbook_odds. Different
books and different timestamps would put a different feature in front of the
model at train and serve time. verify_spread_sources() compares them on
overlapping games and REFUSES agreement below a tolerance.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cfb_live_fv import GameState

ASSUMED_FIELDS = ("period", "offenseScore", "offenseTimeouts", "yardsToGoal")
VERIFIED_FIELDS = ("clock", "defense", "defenseScore", "defenseTimeouts",
                   "distance", "down", "gameId", "home", "offense")


class MissingField(KeyError):
    """Raised rather than defaulting -- a default becomes a feature silently."""


def _need(row: dict, key: str):
    if key not in row or row[key] is None:
        raise MissingField(f"CFBD play missing {key!r}; refusing to default it. "
                           f"Row keys: {sorted(row)[:12]}...")
    return row[key]


def cfbd_row_to_state(row: dict) -> GameState:
    for f in VERIFIED_FIELDS + ASSUMED_FIELDS:
        _need(row, f)
    clock = row["clock"]
    mins = clock["minutes"] if isinstance(clock, dict) else int(str(clock).split(":")[0])
    secs = clock["seconds"] if isinstance(clock, dict) else int(str(clock).split(":")[1])
    period = int(row["period"])
    return GameState(
        period=period, clock_minutes=int(mins), clock_seconds=int(secs),
        down=int(row["down"]), distance=int(row["distance"]),
        yards_to_goal=int(row["yardsToGoal"]),
        pos_team_score=int(row["offenseScore"]), def_pos_team_score=int(row["defenseScore"]),
        drive_is_home_offense=(row["offense"] == row["home"]),
        pos_team_timeouts=int(row["offenseTimeouts"]),
        def_pos_team_timeouts=int(row["defenseTimeouts"]),
        is_overtime=period >= 5,
        ot_possession_number=row.get("driveNumber") if period >= 5 else None,
    )


def label_pos_team_won(row: dict, final_home: int, final_away: int) -> int:
    """Target: did the POSSESSION team win? Ties -> excluded by caller."""
    home_won = final_home > final_away
    return int(home_won if row["offense"] == row["home"] else not home_won)


def verify_spread_sources(cfbd_pairs, ours_pairs, tol=0.51, min_overlap=30):
    """cfbd_pairs/ours_pairs: {game_key: closing_spread}. Returns (ok, report)."""
    common = set(cfbd_pairs) & set(ours_pairs)
    if len(common) < min_overlap:
        return False, (f"REFUSE: only {len(common)} overlapping games (< {min_overlap}). "
                       "Cannot certify the two spread sources agree.")
    diffs = [abs(cfbd_pairs[g] - ours_pairs[g]) for g in common]
    bad = [d for d in diffs if d > tol]
    ok = len(bad) == 0
    return ok, (f"overlap={len(common)} max|diff|={max(diffs):.2f} "
                f"disagreements>{tol}={len(bad)} -> "
                f"{'AGREE — safe to train on CFBD and serve on ours' if ok else 'DISAGREE — train/serve spread asymmetry is REAL, do not proceed'}")


def _selftest():
    row = dict(gameId=1, home="Purdue", away="Indiana State", offense="Purdue",
               defense="Indiana State", clock={"minutes": 7, "seconds": 30},
               period=3, down=2, distance=6, yardsToGoal=41,
               offenseScore=14, defenseScore=10, offenseTimeouts=2, defenseTimeouts=3)
    s = cfbd_row_to_state(row)
    assert s.drive_is_home_offense is True and s.pos_team_score == 14 and s.period == 3
    assert label_pos_team_won(row, 35, 7) == 1 and label_pos_team_won(row, 7, 35) == 0
    away_row = dict(row, offense="Indiana State", defense="Purdue")
    assert label_pos_team_won(away_row, 35, 7) == 0, "possession-team label must flip with possession"
    # * a missing ASSUMED field must RAISE, never default
    for f in ASSUMED_FIELDS:
        bad = dict(row); bad.pop(f)
        try:
            cfbd_row_to_state(bad); raise AssertionError(f"defaulted missing {f}")
        except MissingField:
            pass
    # * overtime routes and carries no clock
    ot = cfbd_row_to_state(dict(row, period=5, driveNumber=2))
    assert ot.is_overtime and ot.ot_possession_number == 2
    # * spread-source verifier refuses on thin overlap and detects disagreement
    ok, msg = verify_spread_sources({i: -3.5 for i in range(10)}, {i: -3.5 for i in range(10)})
    assert not ok and "REFUSE" in msg, "thin overlap must refuse"
    ok2, _ = verify_spread_sources({i: -3.5 for i in range(40)}, {i: -3.5 for i in range(40)})
    ok3, m3 = verify_spread_sources({i: -3.5 for i in range(40)}, {i: -7.0 for i in range(40)})
    assert ok2 and not ok3 and "DISAGREE" in m3
    print("selftest OK -- mapping, possession label, missing-field refusal, OT routing, spread-source verifier")


if __name__ == "__main__":
    _selftest()
