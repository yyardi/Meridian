"""COLLAPSED, v2 -- denominator-free. Supersedes the poll_hz version.

c7 held the wiring because `poll_rate(rows, markets, window)` needs a market
count and every available source is poisoned: `is_live` is never cleared
(C16), and a post-guard count collapses alongside the numerator. They were
right to hold, and the fix is not a better denominator -- it is not needing one.

WHY poll_hz WAS THE WRONG STATISTIC, measured. In the healthy hour the rows
per market are BIMODAL, not skewed:

    p10 2 | p25 2 | p50 2 | p75 115 | p90-p100 1012      mean 198.6

59% of markets get <=2 rows an hour (the sweep touching them) and a second
mode sits at 1,012/hour = one poll per 3.56s (the genuinely live ones). So
total-rows/total-markets is a MIXTURE whose value tracks the live/total ratio,
which moves with the slate. That is c7's denominator disease one level deeper:
it was in the numerator too.

THE STATISTIC: count the markets polled ABOVE SWEEP CADENCE. No denominator,
no market count, no `is_live`, no mixture -- and the question it asks is
exactly the state's definition: is the high-frequency writer doing anything?

    healthy hour   2,586 live markets     collapse hour   0
    restored         166 (all of them)    collapse +5h    0

AND THE EMPTY-SLATE HOLE, which c7 found and which caught one of my own cases:
`rows > 0 AND n_live == 0` also describes a night with no games, because the
sweep still writes pregame boards. My "+11h" case was exactly that -- 12:00Z
is 08:00 ET Sunday -- so it passed for the wrong reason.

`espn_cfb_game_state` closes it: a schedule source already in the database,
written by a DIFFERENT container that stayed healthy through this incident.

    COLLAPSED  <=>  live_games > 0  AND  rows > 0  AND  n_live == 0

    09-05 22:00Z         18 games  n_live 2,332  OK
    09-05 23:00-06:00Z  2-32       n_live     0  COLLAPSED x8 consecutive
    09-06 07:00-15:00Z    0        n_live     0  OK   <- empty slate, silent
    09-06 16:00Z          1        n_live     0  COLLAPSED

Categorical, not a cut on a continuous statistic. LIVE_ROWS_PER_HOUR only has to sit between the sweep
(1-2/hour) and live polling (1,012/hour); collapsed reads 0 at every cut from
3 to 300/hour, so it is a corridor, not a tuned constant.

A partial failure -- a few markets live, thousands dropped -- is deliberately
NOT COLLAPSED. That is a coverage problem and belongs to the coverage check;
this state means the fast writer is gone entirely.
"""
from __future__ import annotations

import pandas as pd

#: A market polled faster than this is being served by the live writer.
#: Sits in a two-order corridor between sweep (1-2/h) and live (1012/h).
LIVE_ROWS_PER_HOUR = 12


def n_live_markets(counts: dict[str, int], window_s: float) -> int:
    """Markets with more rows than sweep cadence would produce.

    `counts` is market -> row count in the window; the caller already has it
    from the same query that produces `rows`. No external market count.
    """
    need = LIVE_ROWS_PER_HOUR * window_s / 3600.0
    return sum(1 for n in counts.values() if n > need)


def refine_absent(counts: dict[str, int], window_s: float,
                  live_games: int) -> str:
    """Called only when v5 has already returned ABSENT.

    STOPPED   nothing wrote in the window -- the whole path is down.
    COLLAPSED games are live, rows ARE arriving, and no market is polled above
              sweep cadence: the fast writer is gone while the table stays
              non-empty, which is why every arrival check stayed green for 17
              hours.
    OK        something is polled live, OR nothing is scheduled.

    `live_games` comes from `espn_cfb_game_state` (state == 'in') -- a
    DIFFERENT container from the price recorder, which is what makes it a real
    external expectation rather than our own write stream restated.

    LIMIT, in ABSENT's own terms: if the ESPN recorder is also down,
    `live_games` reads 0 and this goes quiet. It FAILS QUIET, NOT LOUD.
    Separate containers, so one failure does not couple them, and an ESPN
    outage raises its own ABSENT -- but simultaneous loss of both is silent
    and no source in this system fixes that.
    """
    if not counts or sum(counts.values()) == 0:
        return "STOPPED"
    if live_games <= 0:
        return "OK"                       # nothing scheduled: not a collapse
    return "COLLAPSED" if n_live_markets(counts, window_s) == 0 else "OK"


E = "/Users/yayardia/Documents/Quant/Meridian/backups/exports/"
d = pd.read_csv(E + "cfb_prices_20260906T194301Z.csv.gz",
                parse_dates=["captured_at"])
rest = pd.read_csv(E + "cfb_restored_20260906T204928Z.csv.gz",
                   parse_dates=["captured_at"])
fails = 0


def counts_between(a, b):
    w = d[(d.captured_at >= a) & (d.captured_at < b)]
    return w.groupby("market_slug").size().to_dict()


def case(name, counts, window_s, expect, why, live_games=99):
    global fails
    got = refine_absent(counts, window_s, live_games)
    ok = got == expect
    fails += 0 if ok else 1
    nl = n_live_markets(counts, window_s)
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<38s} mkts={len(counts):>5d} "
          f"live={nl:>5d} -> {got:<9s} ({why})")


print("ADVERSARIAL CONTROL v2 -- denominator-free\n")

case("real healthy hour", counts_between("2026-09-05 21:00",
                                         "2026-09-05 22:00"), 3600, "OK",
     "silent on good data")
case("real COLLAPSE hour", counts_between("2026-09-06 00:00",
                                          "2026-09-06 01:00"), 3600,
     "COLLAPSED", "fires on the incident")
case("collapse +5h", counts_between("2026-09-06 04:00",
                                    "2026-09-06 05:00"), 3600, "COLLAPSED",
     "still fires while degraded")
# CORRECTED: 12:00Z is 08:00 ET Sunday with NO live football. This case used
# to assert COLLAPSED and passed for the wrong reason -- it was firing on an
# empty slate, which is exactly the hole c7 identified. With the schedule
# source it is OK, and the real ongoing-incident case is 16:00Z below.
case("EMPTY SLATE (was a false PASS)", counts_between("2026-09-06 12:00",
     "2026-09-06 13:00"), 3600, "OK",
     "0 live games -- healthy recorder must not read COLLAPSED",
     live_games=0)
case("ongoing incident, 1 game live", counts_between("2026-09-06 16:00",
     "2026-09-06 17:00"), 3600, "COLLAPSED",
     "still fires when a game IS live and nothing is polled", live_games=1)

_span = (rest.captured_at.max() - rest.captured_at.min()).total_seconds()
case("after the RESTORE, quiet Sunday", rest.groupby("market_slug").size()
     .to_dict(), _span, "OK",
     "166 live markets -- a SLATE BOUNDARY cannot inflate a count")
case("true STOP", {}, 3600, "STOPPED", "distinguished from collapse")
case("ESPN source also down", counts_between("2026-09-06 00:00",
     "2026-09-06 01:00"), 3600, "OK",
     "FAILS QUIET: no schedule source -> no claim", live_games=0)

# THE CASE THAT KILLED THE PREVIOUS DESIGN: a slate boundary. RECENT_ACTIVITY_H
# inflated the denominator 30.3x here and pushed a HEALTHY recorder from 49.7x
# above the cut to 1.6x. A count has no denominator to inflate.
big = counts_between("2026-09-05 21:00", "2026-09-05 22:00")
case("BUSY: slate doubles", {**big, **{f"x{k}": v for k, v in big.items()}},
     3600, "OK", "a busy poller is not a dying one")

# DISABLED-CONTROL: collapsed inputs with the counts forced live.
coll = counts_between("2026-09-06 00:00", "2026-09-06 01:00")
forced = refine_absent({k: 500 for k in coll}, 3600, live_games=28)
ok = forced == "OK"
fails += 0 if ok else 1
print(f"\n  {'PASS' if ok else 'FAIL'}  disabled-control: collapsed hour with "
      f"counts forced live -> {forced}")
print("        (if it stayed COLLAPSED the classifier would ignore its input)")

print(f"\n{'ALL CASES PASS' if not fails else f'*** {fails} FAILED ***'}")
