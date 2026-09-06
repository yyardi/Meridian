"""NOT_WRITING: the process identified work and completed none.

Observed live 2026-09-06, CFB ESPN recorder, ~50 minutes, container Up:

    espn_cycle league=cfb live_games=2 plays_attempted=0 wp_attempted=0 state_rows=0
    warning cfb_summary_failed error='Unconsumed column names: league'

Neither COLLAPSED nor ABSENT sees this. A rate cannot: the denominator is zero
rows over zero markets, so there is nothing to compute a statistic over. It is
the identifiability limit of every arrival-derived check -- except the recorder
has NOT stopped. It is polling ESPN successfully, identifying two live games,
and writing nothing.

THIS IS NOT A THRESHOLD, IT IS AN INVARIANT THE CODE GUARANTEES.
`poll_game()` ends with

    ns = 0
    if state:
        s.add(CfbGameState(league=self.league, **state))
        ns = 1

unconditionally -- `CfbGameState` carries no UniqueConstraint, only an index,
so every successful poll inserts exactly one state row. Therefore in a healthy
cycle `state_rows == live_games` EXACTLY. `cycle()` catches per game, logs a
warning and continues, so a swallowed exception leaves `tot_s` short while the
cycle returns cleanly and every heartbeat stays green.

    NOT_WRITING  <=>  live_games > 0  AND  ( state_rows < live_games
                                             OR plays_attempted == 0 )
                      for N consecutive cycles

TWO INVARIANTS, BECAUSE NEITHER COVERS THE OTHER -- measured, not argued:

    3 of 5 games throw   state 2/5, plays 40   A fires, B blind
    parse returns empty  state 5/5, plays  0   B fires, A blind

a1 proposed B alone and my first draft was A alone. Each is blind to a real
failure the other catches, so the check is their disjunction. `<` rather than
`== 0` in A for the same reason: a partial failure is the same defect.

a1's constraint that ON CONFLICT DO NOTHING makes rowcount undeterminable
(psycopg returns -1) is correct and does NOT reach `state_rows`: that counter
is `ns = 1` set in Python after `s.add()`, never a rowcount. And because
`poll_game` returns after `s.commit()`, all three counters are post-commit --
a1 verified this by reading the code, and it is a CONDITION of the contract,
not a property of it: catching per-statement inside the writer would end it.

WHY THE NUMERATOR IS INDEPENDENT. `live_games` is the recorder's own statement
that work exists; `state_rows` is its statement that it did none. Both are
already in one log line and nothing compares them. This is the fix to a general
form I wrote earlier today -- a monitor computing a statistic over what ARRIVED
is blind to what did not -- and a ratio of identified-to-completed is not such
a statistic.

THE SOFT INPUT IS `live_games`, AND IT FAILS QUIET. `refresh_live` builds the
set from the recorder's OWN scoreboard call and `continue`s on failure, so if
every scoreboard request fails, `live` ends up empty, `live_games = 0`, and
this check goes silent. The recorder can hide a write failure by failing one
step earlier.

`core/storage/models.py` already says so, about the sibling column: "What the
writer itself believed about game state this cycle. Readers with an
independent game signal (ESPN) should prefer their own." For the ESPN recorder
the independent signal is the VENUE side -- CFB markets priced at live cadence
means games are live -- which is the mutual-monitoring link, needed here for a
second and independent reason.

A NOTE ON THE `parse_game_state` -> None BRANCH (a1). A summary with no
`header.competitions` yields `state=None`, `ns=0`, and A fires. That is NOT a
false positive: a game the scoreboard calls live, whose summary yields no
state row, means nothing was recorded for a live game. The consequence is
identical to the failure being detected; only the cause differs. Making the
parse RAISE does not change whether A fires -- `cycle()` catches it and the
counter is short either way -- it changes whether the log names the cause. Do
that for diagnosis; do not tune N around it.

LIMIT, and it is the module's own warning turned on this check: `state_rows` is
an IN-PROCESS COUNTER, not confirmation that rows landed. `_write`'s docstring
says it outright -- "whether rows actually landed is answered by querying the
table, never by this counter." So NOT_WRITING catches "the process knows it
failed". It does NOT catch "the process believes it succeeded and nothing
landed"; that is COLLAPSED's job, which reads the table. The two are
complementary and neither subsumes the other:

    NOT_WRITING   INTROSPECTIVE   the process's self-report
    COLLAPSED     EXTROSPECTIVE   what is actually in the table
"""
from __future__ import annotations

#: consecutive failing cycles before the state is asserted. The ONLY parameter,
#: and it exists solely to tolerate a transient: N=2 survives one bad cycle,
#: N=3 survives two. Larger buys nothing -- the live incident ran ~150
#: consecutive cycles. At the 20s cadence N=3 detects in 60s.
CONSECUTIVE_CYCLES = 3


def classify_cycle(live_games: int, state_rows: int,
                   plays_attempted: int) -> str:
    """One cycle against TWO invariants, because neither covers the other.

    A. state_rows == live_games   -- postcondition of a successful poll.
       Catches a swallowed exception, INCLUDING a partial one (3 of 5 games).
    B. plays_attempted > 0        -- catches a parse that produces nothing
       while state still writes: the basketball-parser-on-football shape,
       which A cannot see because state_rows would be complete.

    a1's proposed rule is B alone; my first draft was A alone. Each catches a
    failure the other misses, so the check is their conjunction.
    """
    if live_games <= 0:
        return "OK"                      # nothing scheduled, nothing owed
    if state_rows > live_games:
        # impossible by construction (ns <= 1 per game). If it happens the
        # invariant is wrong and that is itself worth surfacing, never OK.
        return "INVARIANT_BROKEN"
    if state_rows < live_games:
        return "FAILING"                 # A
    return "OK" if plays_attempted > 0 else "FAILING"   # B


def assess_stream(cycles, n: int = CONSECUTIVE_CYCLES) -> str:
    """cycles: (live_games, state_rows, plays_attempted) triples."""
    run = 0
    for live, rows, plays in cycles:
        c = classify_cycle(live, rows, plays)
        if c == "INVARIANT_BROKEN":
            return "INVARIANT_BROKEN"
        run = run + 1 if c == "FAILING" else 0
        if run >= n:
            return "NOT_WRITING"
    return "OK"


# ------------------------------ adversary ------------------------------ #
fails = 0


def case(name, cycles, expect, why):
    global fails
    got = assess_stream(cycles)
    ok = got == expect
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<40s} -> {got:<16s} ({why})")


print("ADVERSARIAL CONTROL -- NOT_WRITING\n")

# THE LIVE INCIDENT, verbatim from the log line, 150 cycles of it.
case("THE LIVE INCIDENT (2 games, 0/0)", [(2, 0, 0)] * 150, "NOT_WRITING",
     "must fire on what is running right now")

case("healthy slate", [(18, 18, 900)] * 50, "OK", "silent when work completes")
case("empty slate", [(0, 0, 0)] * 50, "OK", "nothing scheduled is not a failure")
case("single transient", [(5, 5, 90)] * 10 + [(5, 0, 0)] + [(5, 5, 90)] * 10,
     "OK", "one bad cycle must not page")
case("two transients, not consecutive",
     [(5, 5, 90)] * 5 + [(5, 0, 0)] + [(5, 5, 90)] * 5 + [(5, 0, 0)]
     + [(5, 5, 90)] * 5, "OK", "N counts CONSECUTIVE cycles, not total")
case("sustained: 3 in a row", [(5, 5, 90)] * 5 + [(5, 0, 0)] * 3,
     "NOT_WRITING", "exactly N consecutive is the trigger")
case("PARTIAL: 3 of 5 games throw", [(5, 2, 40)] * 10, "NOT_WRITING",
     "invariant A only -- a1's plays==0 rule is blind here")
case("EMPTY PARSE: state fine, 0 plays", [(5, 5, 0)] * 10, "NOT_WRITING",
     "invariant B only -- my state_rows rule is blind here")
case("games ending mid-run", [(3, 3, 50), (2, 2, 30), (1, 1, 10), (0, 0, 0)],
     "OK", "a shrinking slate is not a failure")
case("state_rows exceeds live_games", [(2, 5, 30)] * 3, "INVARIANT_BROKEN",
     "impossible by construction -- never silently OK")

# DISABLED-CONTROL: the incident stream with state_rows forced to match.
# If this still fired, the check would not be reading its input.
forced = assess_stream([(2, 2, 30)] * 150)
ok = forced == "OK"
fails += 0 if ok else 1
print(f"\n  {'PASS' if ok else 'FAIL'}  disabled-control: incident stream with "
      f"state_rows forced to live_games -> {forced}")

print(f"\n{'ALL CASES PASS' if not fails else f'*** {fails} FAILED ***'}")
