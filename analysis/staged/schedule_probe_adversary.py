"""Adversary for the independent schedule probe.

The probe imports SCOREBOARD_GROUPS strictly and refuses a local copy, so this
harness stubs the module rather than weakening the probe. That the strict
import FAILS on a branch without the recorder is itself one of the cases.
"""
import json
import sys
import types

HERE = "/private/tmp/claude-501/-Users-yayardia-Documents-Quant-Meridian/" \
       "3779e560-5fd2-4c93-8122-5897803b1985/scratchpad"
sys.path.insert(0, HERE)

fails = 0

# --- case 0: the strict import must fail loudly, not silently fall back ---
try:
    import schedule_probe  # noqa: F401
    print("  FAIL  strict import fell back to a copy")
    fails += 1
except ImportError as exc:
    ok = "Do NOT add a local copy" in str(exc)
    print(f"  {'PASS' if ok else 'FAIL'}  strict import fails LOUDLY when the "
          f"shared constant is absent")
    fails += 0 if ok else 1

# now stub it so the rest can run
stub = types.ModuleType("core.feeds.espn_cfb_recorder")
stub.SCOREBOARD_GROUPS = {"cfb": (80, 81), "nfl": (None,)}
for name in ("core", "core.feeds"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["core.feeds.espn_cfb_recorder"] = stub
import schedule_probe as sp  # noqa: E402


def case(name, got, expect, why):
    global fails
    ok = got == expect
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<44s} -> {str(got):<16s} ({why})")


def board(prefix, *states):
    """Ids are PREFIXED PER GROUP. My first version reused g0/g1 across both
    groups, so the union correctly deduped to 1 and my expectation of 2 was
    the thing that was wrong -- distinct groups carry distinct games."""
    return {"events": [{"id": f"{prefix}{i}", "status": {"type": {"state": s}}}
                       for i, s in enumerate(states)]}


print("\nADVERSARIAL CONTROL -- schedule probe\n")

case("both groups OK, 1 live each -> 2", sp.probe(
     lambda g: board(f"grp{g}_", "in", "post")), ("OK", 2),
     "union across groups, distinct ids -- the live case exactly")

case("both groups OK, nothing live", sp.probe(
     lambda g: board(f"grp{g}_", "post", "pre")),
     ("OK", 0), "0 is a MEASUREMENT and must not be UNKNOWN")


def one_group_fails(g):
    if g == 81:
        raise RuntimeError("HTTP 500")
    return board("grp80_", "in")


case("ONE group fails", sp.probe(one_group_fails), ("UNKNOWN", None),
     "a partial union is a LOWER BOUND, never a count")


def all_fail(g):
    raise RuntimeError("DNS failure")


case("all groups fail", sp.probe(all_fail), ("UNKNOWN", None),
     "an outage must never read as 'no games'")

case("malformed payload, no events key", sp.probe(lambda g: {}),
     ("UNKNOWN", None), "missing key is not an empty slate")
case("SAME game listed in both groups", sp.probe(lambda g: board("shared_", "in")),
     ("OK", 1), "union must dedupe, not double-count")

# --- UNKNOWN must ESCALATE, or 'cannot see' becomes a way to be silent ---
case("3 consecutive UNKNOWN", sp.assess_probes([("UNKNOWN", None)] * 3),
     "MONITOR_BLIND", "a blind monitor is itself a failure")
case("2 UNKNOWN then OK", sp.assess_probes(
    [("UNKNOWN", None), ("UNKNOWN", None), ("OK", 3)]), "OK",
    "transients tolerated")
case("many OK(0)", sp.assess_probes([("OK", 0)] * 20), "OK",
     "a genuinely empty slate is not blindness")

# --- and the real endpoint, because a designed source is not a working one ---
try:
    payloads = {}
    for g in (80, 81):
        with open(f"{HERE}/{'board' if g == 80 else 'b81'}.json") as fh:
            payloads[g] = json.load(fh)
    n = sp.live_games(lambda g: payloads[g])
    print(f"\n  LIVE ENDPOINT: union over groups (80, 81) -> {n} live games")
    per = {g: len([e for e in payloads[g]["events"]
                   if e["status"]["type"]["state"] == "in"]) for g in (80, 81)}
    print(f"    per group: {per}  -- the default alone would report "
          f"{per[80]} of {n}")
except Exception as exc:                                # noqa: BLE001
    print(f"\n  (live payloads unavailable: {exc})")

print(f"\n{'ALL CASES PASS' if not fails else f'*** {fails} FAILED ***'}")
