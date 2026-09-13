#!/usr/bin/env python3
"""SLATE ALARM v5 — venue price-freeze detector, productionised.

v4 counted that rows ARRIVE. It read FINE through the total venue freeze of
2026-09-05 17:39Z because write cadence was healthy the whole time. v5 asks
whether the CONTENT changed.

DESIGN NOTES THAT ARE LOAD-BEARING — read before changing a constant.

1. WINDOW LENGTH IS THE DOMINANT PARAMETER, NOT THE THRESHOLD.
   `pairs > 1` means "this market changed price at least once in the window",
   so the healthy share is a function of window length. The historical figures
   (74.4% healthy, 81-97% range) were measured on ONE-HOUR buckets
   (freeze_history.sql groups by date_trunc('hour', ...) despite its header
   comment saying 10-minute). Projecting those onto a 10-minute window via the
   implied per-minute rate gives a healthy share of ~20-44%, not 74-97%.
   Consequence, with 8 live markets:
       10-min window : P(zero movers | healthy) = 16.3%   -> pages 1 window in 6
       30-min window : P(zero movers | healthy) =  0.43%
   Hence WINDOW_MIN = 30, swept every RUN_EVERY_MIN = 10 (sliding), which keeps
   detection latency ~40 min against a freeze that went 109 min undetected.

2. THE FREEZE IS A POINT MASS AT ZERO, NOT A DISTRIBUTION SHIFT.
   Observed freeze: mid step exactly 0.000000 across 602,119 observations ->
   0.0% of markets moved. So the detector is a test for the point mass, not a
   threshold placed in the middle of the healthy distribution. FLOOR_PCT is set
   just above zero: with >=8 markets a single mover already exceeds it. This is
   why the fat healthy left tail (blowouts genuinely stop moving) does not
   matter — we require essentially NOBODY to move.

3. THREE STATES, NEVER TWO. INSUFFICIENT is not OK.
   An empty or thin slate has no price movement and is not an incident. The
   upstream SQL returns NULL for pct when no market has quotes; a naive
   `< threshold` on NULL is false, so it fails safe BY ACCIDENT. Here it is
   explicit. A previous instrument of mine collapsed a three-state comparison
   into a boolean and reported a fault on a working recorder; do not repeat it.

4. PER-LEAGUE, NOT POOLED. A freeze on one league and not another is
   diagnostic (venue-wide vs market-specific) and pooling hides it. Note this
   multiplies the false-positive rate by the number of live leagues.

5. PERSISTENCE. K_CONSECUTIVE=2 sweeps must agree before paging. The windows
   slide and overlap by 2/3, so they are NOT independent and the FP rate does
   NOT fall quadratically — this buys less than it looks like. It is here to
   suppress single-sweep flukes, not as the primary FP control. The primary FP
   control is the 30-minute window.

6. MIN_MARKETS IS THE FALSE-POSITIVE CONTROL, AND IT IS THE ONLY ONE THAT
   MATTERS. A false page requires EVERY quoted market to sit still, so the
   probability collapses with market count. On a typical 47-market CFB slate
   P(zero movers | healthy, 30 min) = 1.2e-14 — unreachable. The entire FP
   budget is spent on slates hovering just above the floor:
       floor=8  -> up to 18.6 false pages/month   (rejected)
       floor=12 -> up to  1.2 false pages/month   (accepted)
       floor=14 -> up to  0.3 false pages/month
   The upper figure assumes K_CONSECUTIVE buys nothing (perfectly correlated
   sweeps); the independent bound is ~3e-4/month.
   THE COST OF THIS CHOICE, STATED PLAINLY: slates with 8-11 quoted markets are
   reported INSUFFICIENT, so a genuine freeze on a thin slate is INVISIBLE to
   this alarm. That is a real blind spot, accepted deliberately to keep the
   pager credible. healthy_distribution.sql sizes it (the `readable = false`
   rows).

MEASUREMENT STATUS — GUARDED (prod, 2026-09-06; 30-min buckets, 600s stream
guard, freeze excluded at 17:38):

  league | band              | buckets | thinnest | worst | median | pct_below_floor
  cfb    | 42+               |      33 |       42 |  68.8 |   83.4 |          0.000
  wnba   | BELOW FLOOR 1-11  |      18 |        1 |   0.0 |   95.5 |         11.111
  wnba   | NEAR FLOOR 12-24  |     182 |       12 |  44.4 |  100.0 |          0.000
  wnba   | 25-41             |      68 |       25 |  82.8 |  100.0 |          0.000
  wnba   | 42+               |      12 |       47 |  95.7 |  100.0 |          0.000

  ★ BOTH CONSTANTS VALIDATED, AND THIS TIME ON THE REGIME THEY GOVERN.
    MIN_MARKETS = 12: the 12-24 band is the MOST POPULATED on the tape (182
    buckets) — the blind spot was never theoretical — and it holds ZERO
    sub-floor buckets. An earlier unguarded run showed 2.010% here and was read
    as evidence; it was entirely stale-flag artefact.
    FLOOR_PCT = 5.0: worst judged bucket 44.4% against a 5% floor, an 8.9x
    margin. Smaller than the 13.8x quoted from the contaminated dense-only
    sample, real, and still comfortable.

  ★ THE ONLY BAND STILL SHOWING SUB-FLOOR BUCKETS IS THE ONE THE ALARM REFUSES
    TO JUDGE (1-11 markets -> INSUFFICIENT). That is the three-valued design
    doing exactly its job, and it is why INSUFFICIENT must never be collapsed
    into OK.

  ★★ THE 600s GUARD IS NOT AN OPTIMISATION AND MUST NOT BE REMOVED AS A
    SIMPLIFICATION. `is_live` is never cleared, so unguarded this alarm reads
    dead streams as quoted-and-not-moving: the near-floor band measures 2.010%
    sub-floor unguarded versus 0.000% guarded. That is the difference between an
    alarm that pages roughly 22 times a month on healthy data and one that does
    not page at all. 17 near-floor buckets (199 -> 182) were composed ENTIRELY of
    dead streams — denominator inflation at the population level, the same
    defect test_alarm_v5_guard.sh catches at the market level.

  ★ K_CONSECUTIVE IS KEPT FOR DETECTION LATENCY, NOT FALSE-POSITIVE CONTROL.
    With zero sub-floor buckets in every judged band there are no episodes to
    space out, so lengthening the streak would buy nothing and cost latency.

MY PROJECTION WAS FALSIFIED AND THE ERROR WAS DERIVABLE IN ADVANCE. I predicted
49.4% by fitting ONE common rate to the hourly figure and projecting down.
P(move) = 1 - exp(-lam*T) is CONCAVE in lam, so heterogeneous rates FLATTEN the
dependence on window length: the fully-heterogeneous limit gives 74.4% at any
T, the homogeneous one 49.4%. The truth had to lie between, and I quoted the
lower endpoint as a point estimate. I named the common-rate assumption in this
docstring and did not compute its direction — naming a caveat is not bounding
it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass

WINDOW_MIN = 30          # see note 1 — do not shorten without re-measuring
RUN_EVERY_MIN = 10       # sliding sweep cadence
FLOOR_PCT = 5.0          # see note 2 — "essentially nobody moved"
MIN_MARKETS = 12         # see note 6 — set by the FP budget, not by intuition
K_CONSECUTIVE = 2        # see note 5 — kept for DETECTION LATENCY, not for FP control
MIN_SPAN_MIN = (K_CONSECUTIVE - 1) * RUN_EVERY_MIN   # streak must span this much real time
MAX_GAP_FACTOR = 2.0     # sweeps further apart than this x RUN_EVERY_MIN are not contiguous
SCHEDULE_LOOKBACK_MULT = 3   # venue arm looks back wider than the window it guards
STREAM_GAP_S = 600       # a row counts only if its market produced another within this
STATE_PATH = os.environ.get("MERIDIAN_ALARM_STATE", "/tmp/meridian_alarm_v5_state.json")

OK, ALARM, INSUFFICIENT, ABSENT, COLLAPSED = "OK", "ALARM", "INSUFFICIENT", "ABSENT", "COLLAPSED"
#: ★ NOT A STATE — AN AXIS. For every state above, "I could not determine" must
#: be distinguishable from "no". UNDETERMINED PAGES: a monitor blind while it
#: believes work is happening is itself a failure, or "cannot see" becomes a way
#: to be silent — the recursion this whole chain exists to stop.
UNDETERMINED = "UNDETERMINED"

#: Leagues that MUST be accounted for on every sweep. Derived from config, NOT
#: from the rows, because the rows are the thing that goes missing.
EXPECTED_LEAGUES = tuple(
    x for x in os.environ.get("MERIDIAN_EXPECTED_LEAGUES", "cfb,wnba,nfl").split(",") if x
)
#: A league silent in the window but active within this many hours was recording
#: recently, so its silence is a fault rather than an empty schedule.
RECENT_ACTIVITY_H = 6
#: A market polled at least this often in the window is being watched at LIVE
#: cadence rather than merely swept. Valid anywhere in [3, 300]: the collapsed
#: state reads 0 at every value in that corridor while healthy and restored stay
#: non-zero. That corridor is the reason to trust it — it is a regime boundary,
#: not a tuned constant, and it is the only constant here not fitted to one or
#: two observations. (Quant D, 2026-09-06.)
LIVE_ROWS_PER_HOUR = 12

# ★ WHY THIS QUERY EXISTS — the defect it closes (found by Debugger, 2026-09-06):
# the metrics query is `FROM mv JOIN cad`, so a league with no surviving rows
# produces NO ROW AT ALL, and the caller iterated over the rows it got. A dead
# recorder therefore yielded an empty result, which printed "quiet slate" and
# exited 0. Worse with a second league still streaming: `rows` was non-empty and
# the dead league was simply absent from the loop, printing nothing whatsoever.
#
# THE THREE-VALUED DESIGN DID NOT PREVENT THIS BECAUSE THE THIRD STATE WAS
# PER-ROW. INSUFFICIENT covers "this league reported and was too thin to judge".
# Nothing covered "this league did not report", because absence has no row to
# carry a state. The expected set must come from somewhere other than the
# observations — here, from config plus this independent activity probe.
#: EXTERNAL EXPECTATION. Written by a DIFFERENT container (cfb-espn-recorder)
#: than the price recorder this alarm watches, so a price-recorder failure does
#: not silence it — which is what makes "should anything be live right now?"
#: answerable at all. THE LIMIT, in ABSENT's own terms and one dependency
#: further out: both containers share a host, a docker daemon and a database, so
#: a failure at ANY of those layers takes both and this goes quiet. That is the
#: single most likely outage mode, not a rare coincidence, and it is covered
#: only by the off-host deadman (specced, blocked on the operator).
SCHEDULE_SQL = """
-- ★ TWO ARMS, OR-ed, BECAUSE EITHER ONE ALONE HAS A LIVE BLIND SPOT.
-- The first version of this query used the ESPN arm only, on the reasoning that
-- a DIFFERENT container writes it. That reasoning was incomplete and the state
-- was blind on the night it shipped: 2026-09-06, the ESPN recorder polled
-- successfully, identified two live games, and wrote ZERO rows. `live_games`
-- returned 0, the guard failed, and COLLAPSED could not fire -- silenced by
-- exactly the failure class it exists to catch.
--
-- THE RULE THAT FELL OUT, AND IT IS THE ONE TO KEEP: "a different container
-- writes it" is not enough. An expectation must SURVIVE the incidents the
-- monitor detects. An expectation that dies with the thing it certifies is not
-- an expectation.
--
-- ESPN arm dies with the ESPN recorder; venue arm dies with the venue recorder.
-- Each covers the other's failure. Only simultaneous loss is silent, and that
-- is the off-host deadman's job (specced, blocked on the operator).
--
-- The venue arm deliberately looks back WIDER than the alarm's own window
-- (SCHEDULE_LOOKBACK_MULT x): if it used the same window, a venue collapse
-- would silence the very signal that detects a venue collapse. The width buys a
-- bounded detection period after onset, then degrades quietly.
WITH espn_arm AS (
  SELECT count(DISTINCT game_id) AS n
  FROM espn_cfb_game_state
  WHERE state = 'in'
    AND first_seen_at > now() - make_interval(mins => %(win)s)
),
venue_arm AS (
  SELECT count(DISTINCT game_id) AS n
  FROM (
    SELECT game_id, market_slug, count(*) AS rows_seen
    FROM market_snapshots
    WHERE captured_at > now() - make_interval(mins => %(wide)s)
    GROUP BY 1, 2
    HAVING count(*) >= %(live_rows)s
  ) fast
)
SELECT greatest((SELECT n FROM espn_arm), (SELECT n FROM venue_arm)) AS live_games;
"""

ACTIVITY_SQL = """
SELECT split_part(market_slug, '-', 2) AS league,
       count(DISTINCT game_id)                                    AS games,
       max(captured_at)                                           AS last_row
FROM market_snapshots
WHERE captured_at > now() - make_interval(hours => %(hours)s)
GROUP BY 1;
"""

SQL = """
-- ★ THE STREAM-RUNNING GUARD IS LOAD-BEARING. `is_live` IS NEVER CLEARED:
-- 6,591 markets carry a frozen last row, so the flag records an INSTANT, not a
-- state. A market whose stream died therefore reads as "quoted, not moving" —
-- INDISTINGUISHABLE from a frozen venue by the exact statistic this alarm uses.
-- Without this guard the alarm would (a) count dead streams toward
-- MIN_MARKETS, inflating the denominator so thin slates look readable, and
-- (b) drag pct_markets_price_moved toward zero, i.e. false-page for the same
-- reason the unguarded measurement was contaminated.
--
-- WHY IT DOES NOT BLIND THE ALARM TO THE THING IT EXISTS TO CATCH: during the
-- 2026-09-05 freeze the RECORDER kept writing at 8.4 batches/min, so gaps were
-- ~7s and every row passes a 600s guard. Frozen-but-streaming is retained and
-- still alarms; dead-stream is dropped. That is precisely the discrimination
-- we need. ASSERTED, NOT ASSUMED: scripts/test_alarm_v5_guard.sh plants four
-- market types in an ephemeral postgres and runs THIS SQL string verbatim —
-- frozen-but-streaming still ALARMs, dead streams vanish entirely, a league of
-- 12 movers + 6 dead reads 12 (not 18), and 6 movers + 6 dead reads 6 and is
-- correctly refused as INSUFFICIENT instead of being padded to a judgeable 12.
-- NOTE: --selftest does NOT cover this; it exercises classify() only.
WITH raw AS (
  SELECT market_slug, game_id, captured_at, best_bid, best_ask,
         split_part(market_slug, '-', 2) AS league,
         lead(captured_at) OVER (PARTITION BY market_slug ORDER BY captured_at) AS next_at
  FROM market_snapshots
  WHERE is_live = true
    AND captured_at > now() - make_interval(mins => %(win)s)
),
w AS (
  SELECT * FROM raw
  WHERE next_at IS NOT NULL
    AND next_at - captured_at <= make_interval(secs => %(stream_gap)s)
),
mv AS (
  SELECT league, market_slug, count(DISTINCT (best_bid, best_ask)) AS pairs
  FROM w
  WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL
  GROUP BY 1, 2
),
cad AS (
  SELECT league,
         count(DISTINCT game_id)                                   AS live_games,
         count(DISTINCT captured_at)                               AS batches,
         extract(epoch FROM (max(captured_at) - min(captured_at))) / 60.0 AS span_min
  FROM w GROUP BY 1
)
SELECT mv.league,
       count(*)                                                    AS quoted_markets,
       count(*) FILTER (WHERE pairs > 1)                           AS movers,
       round(100.0 * count(*) FILTER (WHERE pairs > 1) / count(*), 1) AS pct_moved,
       round(avg(pairs)::numeric, 2)                               AS avg_distinct_prices,
       cad.live_games,
       round(cad.batches::numeric / nullif(cad.span_min, 0), 1)    AS batches_per_min,
       round(cad.span_min::numeric, 1)                             AS span_min
FROM mv JOIN cad ON cad.league = mv.league
GROUP BY mv.league, cad.live_games, cad.batches, cad.span_min
ORDER BY mv.league;
"""


@dataclass(frozen=True)
class LeagueRow:
    league: str
    quoted_markets: int
    movers: int
    pct_moved: float | None
    live_games: int
    batches_per_min: float | None
    span_min: float | None


def classify(row: LeagueRow) -> tuple[str, str]:
    """Pure decision function. Three states — INSUFFICIENT is never OK.

    Returns (state, human reason).
    """
    if row.quoted_markets < MIN_MARKETS:
        return INSUFFICIENT, (
            f"{row.quoted_markets} quoted markets < {MIN_MARKETS} floor; "
            "share too chunky to read — not an incident"
        )
    if row.pct_moved is None:
        return INSUFFICIENT, "no market carried a two-sided quote in the window"
    if row.span_min is not None and row.span_min < WINDOW_MIN * 0.5:
        return INSUFFICIENT, (
            f"window only spans {row.span_min:.1f} min of {WINDOW_MIN}; "
            "recorder just started or gapped"
        )
    if row.pct_moved <= FLOOR_PCT:
        return ALARM, (
            f"{row.movers}/{row.quoted_markets} markets moved "
            f"({row.pct_moved:.1f}% <= {FLOOR_PCT}%) over {WINDOW_MIN} min "
            f"while writes continued at {row.batches_per_min}/min — "
            "prices are frozen, feed is not"
        )
    return OK, f"{row.movers}/{row.quoted_markets} moved ({row.pct_moved:.1f}%)"


def assess(rows: list[LeagueRow], activity: dict[str, int],
           live_games: int | None = 0, n_live: int | None = 0,
           total_rows: int | None = 0) -> list[tuple[str, str, str]]:
    """Enumerate EVERY expected league, not only the ones that reported.

    `activity` maps league -> games seen in the last RECENT_ACTIVITY_H hours,
    ignoring is_live and ignoring the alarm window. It is the independent
    expectation: a league that was recording recently and is silent now is
    ABSENT (a fault), not quiet.

    ★ THE HONEST LIMIT, AND IT IS NOT CLOSED BY THIS FUNCTION: with no schedule
    source, "no games scheduled" and "recorder dead longer than
    RECENT_ACTIVITY_H" are indistinguishable. A recorder dead for 22 hours on a
    Sunday and a genuinely empty Sunday produce identical evidence here. The
    real fix is an expectation derived from kickoff times (a1's
    `events_scheduled_in_progress > 0`), which no code implements yet. Until it
    does, this alarm CANNOT certify a quiet slate — it can only say it saw
    nothing and nothing was recent. That is reported as UNKNOWN-quiet, never OK.
    """
    # ★ COLLAPSED, ahead of everything else: a recorder degraded to sweep cadence
    # makes the movement statistic UNDEFINED, not zero — and this alarm's whole
    # history is undefined states reported as values. Categorical, not a cut:
    # rows still arrive, but nothing is polled at live cadence while ESPN says
    # games are in progress. `live_games` comes from a DIFFERENT container, which
    # is what lets it distinguish "nothing is scheduled" from "the writer died".
    # UNVERIFIED CONVERSE: we have a window where prices collapsed and ESPN
    # lived, and none where ESPN died and prices lived, so that direction is
    # designed and untested (Quant D, 2026-09-06).
    # ★ ONE RULE PER INPUT THAT CAN DIE, INCLUDING THE UNMEASURED CASE.
    # The previous version typed n_live as `int | None` and tested `n_live == 0`.
    # `None == 0` is False, so an UNMEASURED collapse fell straight through to
    # the movement verdict — a number computed on data whose validity was never
    # established. The four-state vocabulary was already here; no RULE read the
    # unmeasured value, so blindness was reported as health. Debugger hit the
    # identical shape in a contract that had OK/FAULT/UNKNOWN from its first
    # commit: THE TYPE MAKES THE ANSWER SAYABLE, IT DOES NOT MAKE ANYONE SAY IT.
    blind = [name for name, val in
             (("live_games", live_games), ("n_live", n_live), ("total_rows", total_rows))
             if val is None]
    if blind:
        return [(lg, UNDETERMINED,
                 f"cannot evaluate: {', '.join(blind)} unmeasured. This is NOT 'no' — "
                 "the monitor is blind and that is itself a fault")
                for lg in sorted(set(EXPECTED_LEAGUES) | {r.league for r in rows})]
    if live_games > 0 and total_rows > 0 and n_live == 0:
        return [(lg, COLLAPSED,
                 f"{total_rows} rows arriving but ZERO markets polled above "
                 f"{LIVE_ROWS_PER_HOUR}/h while ESPN reports {live_games} game(s) "
                 "in progress — the fast writer is gone, movement is UNDEFINED "
                 "rather than zero")
                for lg in sorted(set(EXPECTED_LEAGUES) | {r.league for r in rows})]
    seen = {r.league: r for r in rows}
    out: list[tuple[str, str, str]] = []
    for lg in sorted(set(EXPECTED_LEAGUES) | set(seen)):
        if lg in seen:
            verdict, reason = classify(seen[lg])
            out.append((lg, verdict, reason))
        elif activity.get(lg, 0) > 0:
            out.append((lg, ABSENT,
                        f"NO ROWS in the {WINDOW_MIN}-min window, but {activity[lg]} "
                        f"game(s) recorded within {RECENT_ACTIVITY_H}h — the recorder "
                        "was working and has stopped"))
        else:
            out.append((lg, INSUFFICIENT,
                        f"no rows in the window and nothing within {RECENT_ACTIVITY_H}h — "
                        "cannot tell an empty schedule from a long-dead recorder "
                        "(no kickoff-time source wired)"))
    return out


def load_state() -> dict:
    try:
        with open(STATE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, STATE_PATH)


def heartbeat(state: dict) -> None:
    """Proof of life — the EMIT half of the deadman. The watcher is elsewhere.

    ★ THIS FUNCTION CANNOT MAKE THE DEADMAN WORK, AND MUST NOT BE MISTAKEN FOR
    IT. A heartbeat emitted by the process being watched, stored on the box
    being watched, is v4's disease with a new name: every failure that kills the
    sweep also kills the evidence that it died. What makes this real is a
    watcher OFF THIS HOST that pages when the stamp goes stale — set
    MERIDIAN_HEARTBEAT_URL to a dead-man's-switch endpoint, or have something
    external read `last_sweep` from the state file.

    Fires on EVERY completed sweep including OK and INSUFFICIENT: a sweep that
    ran and found a quiet slate is still proof of life. It is deliberately NOT
    wrapped around fetch() — if the query raised, the sweep did not complete and
    must NOT look alive.

    Staleness budget: 3 x RUN_EVERY_MIN (30 min). Tolerates one transient blip
    without paging and bounds undetected alarm-death at roughly the same order
    as the freeze detection latency, so neither leg is much weaker than the other.

    ★ TEST IT BY KILLING IT, NOT BY READING IT. Stop the cron and confirm a page
    arrives. An untested deadman is indistinguishable from no deadman, and it
    fails silently by construction — the one failure mode that cannot announce
    itself.
    """
    from datetime import datetime, timezone

    state["last_sweep"] = datetime.now(timezone.utc).isoformat()
    url = os.environ.get("MERIDIAN_HEARTBEAT_URL")
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=10).read()
    except Exception as exc:  # noqa: BLE001 — a missed ping must not kill the sweep
        print(f"  [heartbeat ping failed] {type(exc).__name__}: {exc}", file=sys.stderr)


def advance_streak(prev: dict | None, verdict: str, now: "datetime") -> dict | None:
    """Pure streak transition. `prev` is {"n","first","last"} or None.

    ★ A STREAK COUNTED IN SWEEPS IS NOT A STREAK SPANNING TIME, and the original
    version conflated them. It did `streak += 1` with no clock, so if cron was
    broken for four hours, two sweeps four hours apart counted as a "consecutive"
    pair and paged on evidence with a hole in the middle. Conversely a doubled-up
    run could satisfy K_CONSECUTIVE inside two minutes. Persistence is only
    meaningful as a claim about ELAPSED EVIDENCE, so it is enforced here in
    minutes and not in increments.

    Sweeps further apart than MAX_GAP_FACTOR x RUN_EVERY_MIN are not contiguous:
    the streak restarts rather than accumulating across the gap.
    """
    from datetime import datetime as _dt

    if verdict != ALARM:
        return None
    stamp = now.isoformat()
    if prev is None:
        return {"n": 1, "first": stamp, "last": stamp}
    gap_min = (now - _dt.fromisoformat(prev["last"])).total_seconds() / 60.0
    if gap_min > MAX_GAP_FACTOR * RUN_EVERY_MIN:
        return {"n": 1, "first": stamp, "last": stamp}
    return {"n": prev["n"] + 1, "first": prev["first"], "last": stamp}


def should_page(streak: dict | None) -> bool:
    """Page only when the streak is both long enough AND old enough.

    MIN_SPAN_MIN is what makes K_CONSECUTIVE mean something. Set it to
    WINDOW_MIN and the confirming evidence becomes NON-OVERLAPPING, which is the
    lever to reach for if the guarded sub-floor rate stays high — consecutive
    30-min windows swept every 10 min share two thirds of their rows, so
    counting sweeps buys far less independence than it appears to.
    """
    from datetime import datetime as _dt

    if streak is None or streak["n"] < K_CONSECUTIVE:
        return False
    span = (
        _dt.fromisoformat(streak["last"]) - _dt.fromisoformat(streak["first"])
    ).total_seconds() / 60.0
    return span >= MIN_SPAN_MIN * 0.9      # tolerance for cron jitter


def page(topic: str, title: str, body: str) -> None:
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode(),
        headers={"Title": title, "Priority": "urgent", "Tags": "rotating_light"},
    )
    urllib.request.urlopen(req, timeout=15).read()


def _anchored(sql: str, anchor: str | None) -> str:
    """REPLAY ONLY — re-point the sweep at a past instant.

    Production keeps `now()`, the DATABASE clock. A client clock must never set
    the window: a skewed laptop would silently shift what "the last 30 minutes"
    means, and that is the same class of defect as stamping rows from the
    recorder's clock. This substitution happens only when --anchor is given,
    and --anchor forces dry-run so a replay can never page.
    """
    return sql.replace("now()", "%(anchor)s::timestamptz") if anchor else sql


def fetch_activity(dsn: str, anchor: str | None = None) -> dict[str, int]:
    import psycopg
    params: dict = {"hours": RECENT_ACTIVITY_H}
    if anchor:
        params["anchor"] = anchor
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(_anchored(ACTIVITY_SQL, anchor), params)
            return {r[0]: int(r[1]) for r in cur.fetchall() if r[0]}


def fetch(dsn: str, anchor: str | None = None) -> list[LeagueRow]:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            params: dict = {"win": WINDOW_MIN, "stream_gap": STREAM_GAP_S}
            if anchor:
                params["anchor"] = anchor
            cur.execute(_anchored(SQL, anchor), params)
            return [
                LeagueRow(
                    league=r[0],
                    quoted_markets=int(r[1]),
                    movers=int(r[2]),
                    pct_moved=float(r[3]) if r[3] is not None else None,
                    live_games=int(r[5]),
                    batches_per_min=float(r[6]) if r[6] is not None else None,
                    span_min=float(r[7]) if r[7] is not None else None,
                )
                for r in cur.fetchall()
            ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="classify and print, never page")
    ap.add_argument("--anchor", metavar="TS", help=(
        "REPLAY: run the sweep as if now() were TS, e.g. '2026-09-05 22:40:00+00'. "
        "Implies --dry-run; a replay must never page."))
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    dsn = os.environ.get("MERIDIAN_ALARM_DSN") or os.environ.get("DATABASE_URL", "")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    if not dsn:
        print("no DSN in MERIDIAN_ALARM_DSN or DATABASE_URL", file=sys.stderr)
        return 2

    if args.anchor:
        args.dry_run = True
        print(f"REPLAY at {args.anchor} (dry-run forced; paging disabled)")
    rows = fetch(dsn, args.anchor)
    activity = fetch_activity(dsn, args.anchor)

    state = load_state()
    streaks = state.get("streaks", {})
    exit_code = 0

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for league, verdict, reason in assess(rows, activity):
        pageable = verdict in (ALARM, ABSENT)
        streak = advance_streak(streaks.get(league), ALARM if pageable else verdict, now)
        if streak is None:
            streaks.pop(league, None)
        else:
            streaks[league] = streak
        run = streak["n"] if streak else 0
        print(f"[{league}] {verdict} ({run}/{K_CONSECUTIVE}) — {reason}")

        if should_page(streak):
            exit_code = 1
            topic = os.environ.get("MERIDIAN_NTFY_TOPIC")
            body = (
                f"{league.upper()} {'RECORDER SILENT' if verdict == ABSENT else 'venue prices FROZEN'}"
                f"\n{reason}\n"
                f"{run} consecutive {WINDOW_MIN}-min sweeps. Books arriving, not changing."
            )
            if args.dry_run or not topic:
                print(f"  [would page] {body}")
            else:
                try:
                    page(topic, f"MERIDIAN: {league.upper()} "
                               f"{'RECORDER SILENT' if verdict == ABSENT else 'PRICE FREEZE'}", body)
                    print("  [paged]")
                except Exception as exc:  # noqa: BLE001 — never let paging kill the sweep
                    print(f"  [PAGE FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)

    state["streaks"] = streaks
    heartbeat(state)
    save_state(state)
    return exit_code


def selftest() -> int:
    """Planted scenarios, including the exact case v4 was blind to."""
    R = LeagueRow
    cases = [
        # (row, expected state, what this guards)
        (R("cfb", 47, 0, 0.0, 12, 8.4, 30.0), ALARM,
         "THE 2026-09-05 FREEZE: writes healthy, zero price movement"),
        (R("cfb", 47, 35, 74.5, 12, 8.4, 30.0), OK,
         "healthy hourly-equivalent share"),
        (R("cfb", 47, 10, 21.3, 12, 8.4, 30.0), OK,
         "healthy 30-min share near the PROJECTED centre — must not page"),
        (R("cfb", 47, 3, 6.4, 12, 8.4, 30.0), OK,
         "quiet but non-zero, just above floor"),
        (R("cfb", 47, 2, 4.3, 12, 8.4, 30.0), ALARM,
         "at/below floor"),
        (R("wnba", 3, 0, 0.0, 1, 8.4, 30.0), INSUFFICIENT,
         "THIN SLATE at 0%: chunky share is not evidence — must NOT page"),
        (R("wnba", 11, 0, 0.0, 4, 8.4, 30.0), INSUFFICIENT,
         "11 markets at 0%: just under the FP-budget floor — the accepted blind spot"),
        (R("wnba", 12, 0, 0.0, 4, 8.4, 30.0), ALARM,
         "12 markets at 0%: exactly at the floor — must page"),
        (R("cfb", 0, 0, None, 0, None, None), INSUFFICIENT,
         "EMPTY SLATE: no games live is not an incident"),
        (R("cfb", 47, 0, None, 12, 8.4, 30.0), INSUFFICIENT,
         "markets present but no two-sided quotes — cannot read, must not page"),
        (R("cfb", 47, 0, 0.0, 12, 8.4, 4.0), INSUFFICIENT,
         "recorder just started: 4 min of a 30 min window is not a freeze"),
    ]
    failures = 0
    for row, expected, why in cases:
        got, reason = classify(row)
        ok = got == expected
        failures += not ok
        print(f"  {'PASS' if ok else '**FAIL**'}  {expected:12s} {why}")
        if not ok:
            print(f"         got {got}: {reason}")

    # MUTATION: prove the price-movement line is what does the work, i.e. that
    # v4's cadence-only view cannot see the freeze. If this "passes", the new
    # column is inert and the alarm is theatre.
    frozen = R("cfb", 47, 0, 0.0, 12, 8.4, 30.0)
    v4_verdict = "FINE" if (frozen.batches_per_min or 0) > 2.0 else "ALARM"
    v4_blind = v4_verdict == "FINE"
    print(f"  {'PASS' if v4_blind else '**FAIL**'}  MUTATION     "
          f"v4 cadence-only reads {v4_verdict} on the freeze "
          f"(must be FINE, else v5 adds nothing)")
    failures += not v4_blind

    # PERSISTENCE — real transitions this time. The previous version incremented
    # a counter defined inside the test and asserted on it: it exercised no
    # product code and could not fail. A test that cannot fail is not a test.
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    def chain(offsets_min, verdicts):
        s = None
        for off, v in zip(offsets_min, verdicts):
            s = advance_streak(s, v, t0 + timedelta(minutes=off))
        return s

    streak_cases = [
        (chain([0], [ALARM]), False, "one sweep below floor does not page"),
        (chain([0, 10], [ALARM, ALARM]), True, "two sweeps 10 min apart DO page"),
        (chain([0, 240], [ALARM, ALARM]), False,
         "two sweeps 4 HOURS apart must NOT page — cron was broken, evidence has a hole"),
        (chain([0, 1], [ALARM, ALARM]), False,
         "two sweeps 1 min apart must NOT page — doubled run, span too short"),
        (chain([0, 10, 20], [ALARM, OK, ALARM]), False,
         "an OK sweep resets the streak"),
    ]
    for streak, expected, why in streak_cases:
        got = should_page(streak)
        ok = got == expected
        failures += not ok
        print(f"  {'PASS' if ok else '**FAIL**'}  PERSISTENCE  {why}")

    print(f"\n{'SELFTEST PASSED' if not failures else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
