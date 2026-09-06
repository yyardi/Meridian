"""An independent schedule probe: the monitor fetches ESPN itself.

WHY. Every schedule source the alarm has used is produced by the system it
monitors. `espn_cfb_game_state` is written by the ESPN recorder, so when that
recorder fails -- which is the incident -- `live_games` goes to 0 and COLLAPSED
goes quiet at exactly the moment it should fire. Silenced by the failure it
exists to catch. A different WRITER is not independence; independence means the
signal still exists when the monitored thing is broken.

The monitor's own call to ESPN's public scoreboard depends on nothing of ours.

    depends on the ESPN recorder    dies with it
    OR the venue recorder           survives an ESPN failure, dies with DB/host
    the monitor's own fetch         survives all of it

BUT IT IMPORTS THE SAME TRAP ONE LEVEL UP, which is the whole point of this
file: A FAILED FETCH RETURNS NO GAMES, AND "no games" IS INDISTINGUISHABLE
FROM "nothing scheduled". If the monitor folds a failure into zero, then an
ESPN outage, a rate limit, a DNS failure or a bad `groups` parameter all
silence it. So:

  * a fetch that does not succeed is its own state, never zero;
  * UNKNOWN must ESCALATE, not stay quiet. A monitor blind for N cycles is
    itself a failure -- otherwise "cannot see" becomes a way to be silent,
    which is the recursion this design exists to stop;
  * ALL GROUPS MUST SUCCEED or the result is UNKNOWN. A partial union is a
    LOWER BOUND, not a count.

That last rule is not hypothetical. `refresh_live` does

    except Exception:
        log.warning("espn_scoreboard_failed", ...)
        continue

so a failed group is skipped and the survivors are returned as if complete --
and the code's own comment records the consequence: defaulting to FBS "was
every live game on 2026-09-06 and this recorder saw zero for three hours."
Measured tonight: groups=80 -> 1 live, groups=81 -> 1 live, UNION -> 2. A
monitor that `continue`s past a failed group reports half a slate as a clean
number. Reimplementing that would be repeating the defect in the instrument
built to catch it.
"""
from __future__ import annotations

#: IMPORTED, NEVER COPIED (c7). A duplicated (80, 81) drifts silently the
#: first time a league is added, and the monitor would then see a fraction of
#: the slate while reporting a clean number. Same rule check_staged_secrets.py
#: uses for its patterns: load from the one source of truth, and fail LOUDLY
#: rather than fall back to a copy -- a fallback copy is how the divergence
#: becomes invisible.
try:
    from core.feeds.espn_cfb_recorder import SCOREBOARD_GROUPS as GROUPS
except ImportError as _exc:                            # pragma: no cover
    raise ImportError(
        "schedule probe cannot import SCOREBOARD_GROUPS from "
        "core.feeds.espn_cfb_recorder. Do NOT add a local copy: a divergent "
        "group tuple silently halves slate coverage. Fix the import."
    ) from _exc
#: consecutive UNKNOWN probes before the monitor declares itself blind.
BLIND_CYCLES = 3


class Unknown(Exception):
    """The probe could not determine the schedule. Never a count."""


def live_games(fetch, league: str = "cfb") -> int:
    """Distinct games in state 'in', unioned over every group.

    `fetch(group) -> payload` is injected so the failure paths are testable.
    Raises Unknown if ANY group fails: a partial union is a lower bound and
    reporting it as a count is the silent-halving defect.
    """
    ids: set[str] = set()
    for grp in GROUPS.get(league, (None,)):
        try:
            payload = fetch(grp)
        except Exception as exc:                       # noqa: BLE001
            raise Unknown(f"group {grp}: {exc}") from exc
        events = payload.get("events")
        if events is None:                             # malformed, not empty
            raise Unknown(f"group {grp}: no events key")
        for ev in events:
            st = ((ev.get("status") or {}).get("type") or {}).get("state")
            if st == "in":
                ids.add(str(ev["id"]))
    return len(ids)


def probe(fetch, league: str = "cfb") -> tuple[str, int | None]:
    try:
        return "OK", live_games(fetch, league)
    except Unknown:
        return "UNKNOWN", None


def assess_probes(results: list[tuple[str, int | None]],
                  n: int = BLIND_CYCLES) -> str:
    """UNKNOWN escalates. A monitor that cannot see must say so, loudly."""
    run = 0
    for state, _ in results:
        run = run + 1 if state == "UNKNOWN" else 0
        if run >= n:
            return "MONITOR_BLIND"
    return "OK"
