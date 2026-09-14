"""What fraction of live time does the scalp engine's freshness gate pass?

Replays `core.gridiron.scalp.is_stale`'s play-side test over recorded tape,
PER GAME, which is the only grouping the engine ever sees: `LIVE_SQL` filters
by league and takes `DISTINCT ON (game_id)`.

WHY THIS IS A SCRIPT AND NOT A QUERY I RETYPE. The 09-13 baseline is 0.23% of
live time across 13 NFL games, per game 0.09% to 0.40%. Comparing a fresh
slate against that only means something if the population is constructed
identically, and today alone three wrong descriptions came from re-deriving a
query and quietly changing what it grouped by -- including the pooled arrival
spacing this script exists to avoid repeating.

THE ARITHMETIC IS EXACT, NOT SAMPLED. The engine holds the greatest
`wall_clock` among rows ALREADY RECORDED, so the visible maximum is a step
function of the arrival stamps. Within a segment [t0, t1) holding visible
maximum w, the gate passes over [w, w + max_age) intersected with the
segment. `passing_seconds` is that intersection.

IT IS A CEILING, NOT AN ESTIMATE. Five ways this differs from the live path
and all five make the replay generous: `first_seen_at` is a transaction start
while visibility is at COMMIT; the engine's `now` is after its fetch; the
engine samples every 2s while this integrates continuously; only rows that
were recorded appear at all, so recorder downtime is invisible; and the
stretch after a game's last play leaves the denominator. See
docs/math/the-gate-refuses-the-good-rows.md.

    DATABASE_URL=... python cfb/run_gate_replay.py --league nfl \
        --since '2026-09-14 20:00:00+00' --until '2026-09-15 12:00:00+00'
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text

#: The gate being replayed. Read from the engine's own default so this cannot
#: drift from the thing it claims to measure.
from core.gridiron.scalp import params_from_env  # noqa: E402

SEGMENTS_SQL = """
WITH p AS (
  SELECT game_id, first_seen_at, wall_clock,
         max(wall_clock) OVER (PARTITION BY game_id ORDER BY first_seen_at
                               ROWS UNBOUNDED PRECEDING) AS vis_max
  FROM espn_cfb_live_plays
  WHERE league = :lg AND wall_clock IS NOT NULL
    AND first_seen_at >= CAST(:since AS timestamptz)
    AND first_seen_at <  CAST(:until AS timestamptz))
SELECT game_id,
       extract(epoch FROM (t1 - t0))  AS secs,
       extract(epoch FROM (t0 - w))   AS age_at_t0,
       extract(epoch FROM (t1 - w))   AS age_at_t1
FROM (SELECT game_id, first_seen_at AS t0,
             lead(first_seen_at) OVER (PARTITION BY game_id
                                       ORDER BY first_seen_at) AS t1,
             vis_max AS w
      FROM p) s
WHERE t1 IS NOT NULL
"""


def passing_seconds(secs: float, age_at_t0: float, age_at_t1: float,
                    max_age_s: float) -> float:
    """Seconds inside one segment for which the gate passes.

    The visible maximum `w` is fixed across the segment, so the age rises
    linearly from `age_at_t0` to `age_at_t1`. The gate passes while the age
    is in (-inf, max_age] under the old rule; a NEGATIVE age also passed,
    which is the hole `age < -1.0` closed. This function reports the
    POSITIVE-age passing time, which is what a correct gate allows.
    """
    if secs <= 0:
        return 0.0
    lo = max(0.0, age_at_t0)              # the age never goes below 0 usefully
    hi = age_at_t1
    if hi <= lo:
        return 0.0
    # passing ages are [0, max_age]; map back to seconds of the segment
    top = min(hi, max_age_s)
    if top <= lo:
        return 0.0
    # No clamp to `secs`. I wrote one and mutation testing showed removing it
    # broke nothing, because it cannot bind: top - lo <= age_at_t1 -
    # max(0, age_at_t0) <= age_at_t1 - age_at_t0 = secs. A guard that cannot
    # fire is dead code carrying a test that cannot fail.
    return top - lo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="nfl")
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    a = ap.parse_args()

    max_age_s = params_from_env()["max_age_s"]
    eng = create_engine(os.environ["DATABASE_URL"])
    with eng.connect() as c:
        rows = list(c.execute(text(SEGMENTS_SQL),
                              {"lg": a.league, "since": a.since,
                               "until": a.until}))

    per: dict[str, list[float]] = {}
    for r in rows:
        m = r._mapping
        tot, pas = per.setdefault(str(m["game_id"]), [0.0, 0.0])
        tot += float(m["secs"] or 0.0)
        pas += passing_seconds(float(m["secs"] or 0.0),
                               float(m["age_at_t0"] or 0.0),
                               float(m["age_at_t1"] or 0.0), max_age_s)
        per[str(m["game_id"])] = [tot, pas]

    if not per:
        print(f"no {a.league} plays recorded in {a.since} .. {a.until}")
        return 0

    tot = sum(v[0] for v in per.values())
    pas = sum(v[1] for v in per.values())
    print(f"gate MAX_AGE_S = {max_age_s:.0f}s   league {a.league}   "
          f"{len(per)} games   {tot/3600:.2f} live hours")
    print(f"gate passes {100*pas/tot:.2f}% of live time   "
          "(a CEILING -- see the module docstring)")
    pcts = sorted(100 * v[1] / v[0] for v in per.values() if v[0] > 0)
    if pcts:
        lo, hi = pcts[0], pcts[-1]
        band = (hi / lo) if lo > 0 else float("inf")
        print(f"per game {lo:.2f}% .. {hi:.2f}%   "
              f"spread {band:.1f}x   (09-13 NFL baseline: 0.09..0.40, 4.4x)")
        print("  a structural rate looks like a narrow band; a wide one means "
              "one game is carrying the number")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
