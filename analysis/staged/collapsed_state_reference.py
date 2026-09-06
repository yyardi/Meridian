"""COLLAPSED as a REFINEMENT OF ABSENT, plus its adversary.

v5 already fires on this incident, fast and correctly, and calls it ABSENT.
That is right about the symptom and wrong about the cause: the recorder had not
stopped -- a low-frequency sweep kept writing while the live writer was gone.
Remediation differs (restart the live recorder vs everything is down), so the
cause is worth naming.

WHY IT MUST BE A SECOND LOOK ON A LONGER WINDOW, measured:
during the collapse the fraction of windows containing NO rows at all is

    5 min  86.6%      15 min 60.7%      30 min 21.4%      60 min 0.0%

so at v5's own cadence a collapsed recorder and a stopped one are the SAME
observation. The distinction only exists over a window long enough to contain
one sweep cycle. Hence: do not change when ABSENT fires. When it fires, look
back 60 minutes and ask whether anything is still writing at sweep cadence.
"""
from __future__ import annotations

import pandas as pd

WINDOW_S = 3600.0
#: one poll per 254s per market. Log-symmetric between the two regimes that
#: matter: healthy 0.0552 Hz and collapsed 0.00028 Hz -- 14x margin each way.
#: The RESTORED recorder sits 49x above it, so it is not a constraint.
COLLAPSED_HZ = 0.0039
#: denominator floor for a RATE. Deliberately NOT c7's MIN_MARKETS (=12),
#: which is a false-positive budget on a SHARE statistic -- different
#: quantities, so they are named apart to stop a later 'unification'.
MIN_MARKETS_RATE = 20


def poll_rate(rows: int, markets: int, window_s: float = WINDOW_S) -> float:
    if markets <= 0 or window_s <= 0:
        return 0.0
    return rows / (window_s * markets)


def refine_absent(rows: int, markets: int, window_s: float = WINDOW_S) -> str:
    """Called ONLY when v5 has already returned ABSENT.

    STOPPED   nothing wrote in the last hour -- the whole path is down.
    COLLAPSED something is still writing, but at sweep cadence: the
              high-frequency writer is gone while the table stays non-empty,
              which is why every arrival check stayed green for 17 hours.
    OK        the hour looks healthy; ABSENT was a short-window artifact.
    """
    if rows == 0:
        return "STOPPED"
    if markets < MIN_MARKETS_RATE:
        return "OK"
    return ("COLLAPSED" if poll_rate(rows, markets, window_s) < COLLAPSED_HZ
            else "OK")


E = "/Users/yayardia/Documents/Quant/Meridian/backups/exports/"
d = pd.read_csv(E + "cfb_prices_20260906T194301Z.csv.gz",
                parse_dates=["captured_at"]).sort_values("captured_at")


def hour(a, b):
    x = d[(d.captured_at >= a) & (d.captured_at < b)]
    return len(x), x.market_slug.nunique()


fails = 0


def case(name, rows, mkts, expect, why, window_s=WINDOW_S):
    global fails
    got = refine_absent(rows, mkts, window_s)
    ok = got == expect
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<36s} rows={rows:>7d} "
          f"mkts={mkts:>5d} rate={poll_rate(rows, mkts, window_s):.5f}Hz -> "
          f"{got:<9s} ({why})")


print("ADVERSARIAL CONTROL -- observed BOTH firing and silent\n")

r, m = hour("2026-09-05 21:00", "2026-09-05 22:00")
case("real healthy hour", r, m, "OK", "silent on good data")

r, m = hour("2026-09-06 00:00", "2026-09-06 01:00")
case("real COLLAPSE hour", r, m, "COLLAPSED", "fires on the incident")

r, m = hour("2026-09-06 04:00", "2026-09-06 05:00")
case("real collapse, 5h later", r, m, "COLLAPSED", "still fires while degraded")

# the RESTORE hour is not in cfb_prices -- that export was cut at 19:43Z,
# before the fix. It lives in the separate cfb_restored export. Reading the
# wrong file here cost one FAIL and was my error, not the design's.
_rest = pd.read_csv(E + "cfb_restored_20260906T204928Z.csv.gz",
                    parse_dates=["captured_at"])
_span = (_rest.captured_at.max() - _rest.captured_at.min()).total_seconds()
case("after the RESTORE (span-correct)", len(_rest),
     _rest.market_slug.nunique(), "OK",
     "export spans 339s NOT an hour -- dividing by 3600 understated it 10.6x",
     window_s=_span)

case("true STOP: nothing writing", 0, 0, "STOPPED", "distinguishes from collapse")

rh, mh = hour("2026-09-05 21:00", "2026-09-05 22:00")
case("BUSY: slate doubles, rate holds", rh * 2, mh * 2, "OK",
     "a busy poller is not a dying one")
case("small slate, healthy cadence", int(0.10 * WINDOW_S * 60), 60, "OK",
     "an absolute rows/s cut would false-alarm here")
case("tiny slate, below MIN_MARKETS", 5, 5, "OK", "too small to judge")

# DISABLED-CHECK CONTROL: force the statistic healthy on collapsed inputs.
# If the state does not change, the classifier is ignoring its input --
# the failure Debugger found in three of five of their own checks.
r, m = hour("2026-09-06 00:00", "2026-09-06 01:00")
forced = refine_absent(int(0.10 * WINDOW_S * m), m)
ok = forced == "OK"
fails += 0 if ok else 1
print(f"\n  {'PASS' if ok else 'FAIL'}  disabled-control: collapsed hour with "
      f"the rate forced healthy -> {forced}")
print("        (if it stayed COLLAPSED the classifier would ignore its input)")

r, m = hour("2026-09-06 00:00", "2026-09-06 01:00")
print(f"\n  margins: collapse hour sits {COLLAPSED_HZ / poll_rate(r, m):.0f}x "
      f"BELOW the threshold; healthy hour "
      f"{poll_rate(rh, mh) / COLLAPSED_HZ:.0f}x ABOVE it.")
print(f"\n{'ALL CASES PASS' if not fails else f'*** {fails} FAILED ***'}")
