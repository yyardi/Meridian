"""SOURCE-DEATH cases: for every input a monitor reads, kill the SOURCE while
the condition it reports on is TRUE.

c7's point, and the count is against me: my adversaries are 9-for-9 against
fixture errors and 0-for-3 against the real defects tonight (the rate anchor,
the poisoned denominator, the schedule source). All three were found by
cross-examination, because an adversary written by the same author feeds the
implementation the premises the author already holds. It cannot test a premise
it shares.

Every case in both suites varies WHAT THE WORLD IS DOING. None varies WHETHER
THE INSTRUMENT CAN STILL SEE IT. These do.

The expected result is RED. That is the point: these are the defects we
discussed in prose for two hours, expressed as failing tests.
"""
import sys
import types

HERE = ("/private/tmp/claude-501/-Users-yayardia-Documents-Quant-Meridian/"
        "3779e560-5fd2-4c93-8122-5897803b1985/scratchpad")
sys.path.insert(0, HERE)

stub = types.ModuleType("core.feeds.espn_cfb_recorder")
stub.SCOREBOARD_GROUPS = {"cfb": (80, 81), "nfl": (None,)}
for n in ("core", "core.feeds"):
    sys.modules.setdefault(n, types.ModuleType(n))
sys.modules["core.feeds.espn_cfb_recorder"] = stub

import collapsed2 as C          # noqa: E402  COLLAPSED
import notwriting as NW         # noqa: E402  NOT_WRITING
import schedule_probe as SP     # noqa: E402  the probe

red = 0


def source_death(monitor, input_name, condition, got, must_not_be):
    """The world is BROKEN and the input's SOURCE is dead. Staying quiet is
    the failure -- a monitor that cannot see must not report health."""
    global red
    bad = got == must_not_be
    red += 1 if bad else 0
    mark = "RED " if bad else "ok  "
    print(f"  {mark} {monitor:<14s} input={input_name:<22s} -> {str(got):<14s}")
    print(f"       world: {condition}")
    if bad:
        print(f"       FAILS: reported {must_not_be!r} while blind")


print("SOURCE-DEATH ADVERSARY -- expected to go RED\n")

# 1. COLLAPSED reads live_games from espn_cfb_game_state ROWS.
#    Tonight: that recorder writes nothing while two games are genuinely live.
counts = {f"m{i}": 1 for i in range(500)}          # sweep cadence: collapsed
source_death("COLLAPSED", "live_games (ESPN rows)",
             "venue collapsed AND ESPN recorder dead; games ARE live",
             C.refine_absent(counts, 3600.0, live_games=0), "OK")

# 2. NOT_WRITING reads live_games from the recorder's OWN scoreboard call.
#    refresh_live `continue`s on failure, so a total scoreboard failure
#    empties the set and the recorder hides its own write failure.
source_death("NOT_WRITING", "live_games (own board)",
             "writer failing AND scoreboard call failing; games ARE live",
             NW.assess_stream([(0, 0, 0)] * 150), "OK")

# 3. The probe reads the ESPN scoreboard over HTTP -- the ONE input where a
#    source-death case already exists, and only because ce demanded it.
def dead(_):
    raise RuntimeError("connection refused")


state, _n = SP.probe(dead)
source_death("probe", "scoreboard (HTTP)",
             "ESPN unreachable; games ARE live",
             state, "OK")

print(f"\n{red} of 3 monitors report health while blind.")
print("\nThe defect is NOT in the functions -- it is in the CONTRACT. An int")
print("`live_games` cannot express 'I could not measure', so 'no games' and")
print("'no source' are the same value. The codebase already states the rule,")
print("about a column neither of us wired: service_heartbeats.rows_written --")
print('"NULL means not measured, which is different from 0".')
print("\nFIX: every monitor input must be tri-state (count | UNKNOWN), and")
print("UNKNOWN must escalate. That is rule 1 and 2 of the probe, applied to")
print("EVERY input rather than only the one ce pushed on.")
