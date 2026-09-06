#!/usr/bin/env python3
"""Will this slate record? One command, run by a human at T-30. Exits non-zero.

WHY THIS AND NOT THE ALARM. Nothing specced tonight is running: COLLAPSED
lands when the alarm deploys, the alarm is not deployed, NOT_WRITING is a
contract, the probe is a spec. We have lost two consecutive slates to
recording failures -- venue for 17 hours on 09-05, ESPN for 53 minutes on
09-06 -- and both times the OTHER side was perfectly healthy and every
instrument called the slate fine. This needs no deploy, no threshold, no
approval, which is why it can exist before Saturday.

THE ONE THING IT DOES THAT NOTHING ELSE DOES: it checks BOTH sides against an
INDEPENDENT schedule and reports them SEPARATELY. Always two lines, even when
both pass. Both failures were one-sided, and a single green/red would have
been green on the healthy side each time -- which is exactly the information
that would have caught either incident.

SCOPE. A readiness check, not a monitor: one question at one moment. No
window, no threshold, no baseline, no history. Coverage is EXISTENCE (has this
side ever seen this game), not rate -- rate is the alarm's job and wanting one
here means drifting into it.

LOUD FAILURE. If the schedule cannot be fetched the check FAILS. It never
passes quietly: "I could not determine" is not "nothing to do", which is the
rule the whole chain is built on.
"""
from __future__ import annotations

import sys

EXIT_OK, EXIT_FAIL = 0, 1


def readiness(schedule_state: str, scheduled: set[str], espn_seen: set[str],
              venue_seen: set[str], mappable: set[str]) -> tuple[int, list[str]]:
    """(exit_code, lines). ALWAYS a line per side, pass or fail.

    `mappable` is the third input, and running this on the real 09-05 slate is
    what found it. The two sides do not share an id space -- ESPN writes event
    ids (401856635), the venue writes its own (16487) -- and `cfb_game_map`
    bridges them by FUZZY match (`slug_fuzzy_date_pm1`, confidence 0.833-0.960).
    Measured: 50 scheduled games, 99 venue ids, 55 map rows, and only 37 of the
    scheduled games mappable at all.

    Without this input the check reports "VENUE FAIL 19/50" when the truth is
    "the map cannot join 31 of them" -- CANNOT CHECK reported as IS FAILING,
    which at T-30 on a Saturday sends someone to debug the wrong recorder. It
    is the same not-measured-versus-measured-zero conflation as everywhere
    else in this chain, arriving through a join.
    """
    if schedule_state != "OK":
        return EXIT_FAIL, [
            "SCHEDULE  UNKNOWN -- could not reach ESPN; refusing to pass",
            "MAP       unchecked", "ESPN      unchecked", "VENUE     unchecked"]

    if not scheduled:
        # NOT a quiet pass: derive `scheduled` from the PROBE, never from an
        # intersection with our own tables. My first adversary took it from
        # `espn_ids & venue_ids`, got 0 across disjoint id spaces, and PASSED
        # -- a broken map would have passed this check silently.
        return EXIT_OK, ["SCHEDULE  0 games -- nothing to record",
                         "MAP       n/a", "ESPN      n/a", "VENUE     n/a"]

    n = len(scheduled)
    lines = [f"SCHEDULE  {n} games (independent ESPN probe)"]
    bad = False

    unmappable = scheduled - mappable
    if unmappable:
        bad = True
        lines.append(f"MAP       FAIL  {n - len(unmappable)}/{n} mappable; "
                     f"{len(unmappable)} games cannot be joined to the venue")
    else:
        lines.append(f"MAP       OK    {n}/{n} mappable")

    for name, seen, scope in (("ESPN", espn_seen, scheduled),
                              ("VENUE", venue_seen, scheduled & mappable)):
        missing = scope - seen
        if not scope:
            lines.append(f"{name:<9s} ?     cannot check -- nothing joinable")
        elif not missing:
            lines.append(f"{name:<9s} OK    {len(scope)}/{len(scope)} covered"
                         + ("" if scope == scheduled else " (of mappable)"))
        else:
            bad = True
            sample = ", ".join(sorted(missing)[:3])
            lines.append(f"{name:<9s} FAIL  {len(scope) - len(missing)}/"
                         f"{len(scope)} covered; missing {len(missing)}: "
                         f"{sample}" + (" ..." if len(missing) > 3 else ""))
    return (EXIT_FAIL if bad else EXIT_OK), lines


def main(argv: list[str]) -> int:
    """Wiring is a1's -- this is the shape and the exit contract.

        schedule_state, scheduled = probe()          # groups 80|81 UNION
        espn_seen  = game_ids in espn_cfb_game_state for today
        venue_seen = game_ids in the venue price table for today
    """
    raise SystemExit("wire the three queries; see main.__doc__")


if __name__ == "__main__":       # pragma: no cover
    sys.exit(main(sys.argv[1:]))
