"""Adversary for the slate readiness check.

Five failures, and one PASS on real data -- a check that cannot pass is as
useless as one that cannot fail.

d5's rule, taken: at least one case must be a failure REAL DATA HAS NEVER
PRODUCED. On the 09-05 slate every scheduled game had rows on both sides, so a
fixture drawn from that data can never exercise the partial-coverage branch.
Case 5 constructs it.
"""
import sys

sys.path.insert(0, "/Users/yayardia/Documents/Quant/Meridian/.claude/"
                   "worktrees/quant-d-loss-decomposition/analysis/staged")
import pandas as pd  # noqa: E402
from slate_readiness import readiness  # noqa: E402

fails = 0


def case(name, got_code, got_lines, want_code, why, show=False):
    global fails
    ok = got_code == want_code
    fails += 0 if ok else 1
    v = "FAIL" if want_code else "PASS"
    print(f"  {'ok ' if ok else 'BAD'}  {name:<38s} exit={got_code} "
          f"(want {v}) -- {why}")
    if show or not ok:
        for ln in got_lines:
            print(f"          {ln}")


S = {"g1", "g2", "g3"}
print("ADVERSARIAL CONTROL -- slate readiness\n")

c, l = readiness("OK", S, set(), S, S)
case("ESPN recorder dead", c, l, 1, "09-06 failure; board scope")
c, l = readiness("OK", S, S, set(), S)
case("VENUE recorder dead", c, l, 1, "09-05's failure")
c, l = readiness("OK", S, set(), set(), S)
case("BOTH dead", c, l, 1, "the shared-layer case")
c, l = readiness("UNKNOWN", set(), set(), set(), set())
case("probe cannot reach ESPN", c, l, 1, "must not pass quietly")
c, l = readiness("OK", S, {"g1", "g2"}, {"g1", "g2"}, S)
case("game neither side has seen", c, l, 1,
     "PARTIAL coverage -- real data has never produced this")

# --- and it must PASS on a real, healthy slate -------------------------- #
E = "/Users/yayardia/Documents/Quant/Meridian/backups/exports/"
st = pd.read_csv(E + "espn_cfb_game_state_20260906T174104Z.csv.gz")
pr = pd.read_csv(E + "cfb_prices_20260906T194301Z.csv.gz",
                 usecols=["game_id"])
espn_ids = {str(x) for x in st.game_id.dropna().unique()}
venue_ids = {str(int(x)) for x in pr.game_id.dropna().unique()}
# WIRED AS a1 WOULD: schedule from the probe, venue joined THROUGH the map.
# My first version took sched = espn_ids & venue_ids, got 0 across disjoint
# id spaces, and PASSED -- the quiet pass ce told me to make impossible.
mp = pd.read_csv(E + "cfb_game_map_20260906T174104Z.csv.gz",
                 usecols=["espn_game_id", "venue_game_id"])
v2e = dict(zip(mp.venue_game_id.astype("Int64").astype(str),
               mp.espn_game_id.astype(str)))
mappable = set(v2e.values())
venue_seen = {v2e[v] for v in venue_ids if v in v2e}
# SCOPED TO THE BOARD (ce measured: 119 venue games at --days 3 AND --days 8,
# while ESPN went 132 -> 180). The board is the tradeable population; scoping
# to ESPN's schedule makes the check permanently red.
board = {v2e[v] for v in venue_ids if v in v2e}   # board games, in espn ids
# ★ COMMON WINDOW. My two pinned exports are cut at different times (ESPN
# 22:08Z-16:08Z, prices 21:00Z-16:32Z), so 21 board games fall outside one or
# the other and read as gaps that are artifacts of MY FILES, not the
# recorders. Verified: 18 kicked off before the ESPN export opened, 3 after it
# closed, 0 genuinely absent. In production this check reads LIVE tables and
# the problem does not arise -- but comparing two exports cut at different
# times manufactures gaps, which is a usage caveat worth carrying.
board &= espn_ids
c, l = readiness("OK", board, espn_ids, board, mappable)
print()
case(f"REAL board, common window ({len(board)} games)", c, l, 0,
     "board-scoped and window-matched: both sides recording", show=True)

# a board game the map cannot join must still FAIL -- that is the actionable
# number, and unlike the schedule-scoped version it can legitimately reach zero
c, l = readiness("OK", board | {"unjoinable_board_game"}, espn_ids,
                 board | {"unjoinable_board_game"}, mappable)
print()
case("board + 1 unjoinable game", c, l, 1,
     "MAP is actionable and CAN reach zero when the map is complete",
     show=True)

# --- the disjunction is what makes case 5 reachable at all -------------- #
one_missing = set(list(board)[:5]) | {"never_seen_game"}
c, l = readiness("OK", one_missing, espn_ids, board, mappable | {"never_seen_game"})
print()
case("board + 1 game neither side recorded", c, l, 1,
     "the branch real data cannot reach", show=True)

print(f"\n{'ALL CASES BEHAVE' if not fails else f'*** {fails} MISBEHAVED ***'}")
