"""Measured concurrent gateway draw per recorder process, vs the configured caps.

WHY (manager, 2026-09-03): the configured per-process Polymarket-gateway caps sum
to 31 req/s against a 20 req/s per-IP ceiling — 155% oversubscribed. But the
configured cap is a WORST case (all processes peaking at once); the actual
concurrent draw may never approach it. This turns "155% configured" into
"measured peak X, headroom Y" so the caps-vs-stagger-vs-accept decision before
Sept 17 rests on a measurement, not a sum of caps. It is the substrate-count move
(rule 20): count the phenomenon before deciding.

WHAT IT MEASURES, from the DB artifacts each recorder writes (the request-rate
proxy is defensible: the recorder makes exactly one gateway request per board
poll — get_league_events — and one per depth fetch — get_book, recorder.py):
  * poll requests   = distinct market_snapshots.captured_at for the process
  * book requests   = one per snapshot that has book_levels, at the book's
                      captured_at (the depth fetch instant)
Per process (league x is_live) the request instants are binned into a sliding 1s
window; the max is the measured peak req/s.

SCOPE (manager): the regime that bites — WNBA-live AND NFL-live at once — does not
exist in any tape before Sept 17. So this measures what CAN be measured and
PROJECTS the rest, labelled:
  1. August WNBA-live actual peak vs cap 12 (the decisive one: if a 12-capped
     process peaks at 3, the configured 31 is mostly fiction).
  2. Any window's pregame recorders + (once running) NFL-live: the always-on floor.
  3. NFL-live actual once games start (Sept 9+) — RE-RUN this with --since after
     the 9th; the field is a required deliverable, not an assumption.
Then the Sept-17 figure is an ADDITIVE PROJECTION (sum of per-process peaks),
labelled, assumption stated.

WHY ADDITIVE PROJECTION IS LEGITIMATE HERE (and depth-extrapolation was not):
extrapolating in-play depth from a 15x pregame->in-play regime gradient was
illegitimate because the quantity itself changes across the gradient. Projecting
REQUEST LOAD additively across independent processes is defensible: separate
processes making independent gateway calls genuinely SUM at the instant they
coincide, and the sum is CONSERVATIVE because coincidence is the worst case, not
the expectation. Same species of reasoning (project the unmeasured), opposite
verdict, for a reason that is about the quantity, not the caution.

CAVEATS (stated, not hidden):
  * The stats-sweepers (cap 2 each) hit different endpoints and write neither
    table, so they are NOT reconstructable here — reported at their configured
    cap as a constant floor, flagged as unmeasured.
  * captured_at is the write/response instant, a close proxy for the request
    instant at steady state (rate limits act on sends; completions lag by the
    request duration). Peaks are therefore ~exact at steady cadence.
  * PREGAME book fetches share the cycle's captured_at (price+depth fetched
    together), so pregame book requests cluster at the poll instant -> the
    pregame book peak is OVERSTATED (conservative). The LIVE recorders split the
    depth loop (per-fetch stamp), so the decisive WNBA-live number is faithful.

    python analysis/gateway_concurrent_draw.py --since 2026-08-18 --until 2026-08-23
    python analysis/gateway_concurrent_draw.py --selftest         # no DB
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt

UTC = dt.timezone.utc

#: (league, is_live) -> (process name, configured gateway cap req/s). Manager's
#: reading off the running containers, 2026-09-03.
PROCESS_CAPS: dict[tuple[str, bool], tuple[str, int]] = {
    ("wnba", False): ("meridian-recorder", 5),
    ("wnba", True): ("meridian-live-recorder", 12),
    ("nfl", False): ("meridian-nfl-recorder", 6),
    ("nfl", True): ("meridian-nfl-live-recorder", 4),
}
#: Not reconstructable from market_snapshots/book_levels (different endpoints);
#: carried at configured cap as a flagged constant floor.
SWEEPER_CAPS: dict[str, int] = {
    "meridian-nfl-stats-sweeper": 2, "meridian-wnba-stats-sweeper": 2,
}
GATEWAY_CEILING_REQ_S = 20


def peak_concurrent(timestamps: list[dt.datetime], window_s: float = 1.0) -> tuple[int, dt.datetime | None]:
    """Max number of timestamps within any half-open window of width window_s.
    Pure; the known-answer selftest pins it. Returns (peak, window_start)."""
    if not timestamps:
        return 0, None
    ts = sorted(timestamps)
    best, best_at = 0, None
    w = dt.timedelta(seconds=window_s)
    starts = ts  # a maximal window can always be taken to start at a timestamp
    for i, t0 in enumerate(starts):
        j = bisect.bisect_left(ts, t0 + w)   # first index with ts[j] >= t0+w
        count = j - i
        if count > best:
            best, best_at = count, t0
    return best, best_at


def additive_projection(peaks: dict[str, int]) -> int:
    """The Sept-17 worst case: independent processes' peaks SUM at coincidence.
    Conservative (coincidence is the worst case, not the expectation)."""
    return sum(peaks.values())


# --------------------------------------------------------------------------- #
#  DB reconstruction (runs on prod; imports are lazy so --selftest needs no DB)
# --------------------------------------------------------------------------- #

def _route(slug: str) -> str | None:
    from core.leagues import league_of_slug
    lg = league_of_slug(slug)
    return lg.slug if lg is not None else None


def _request_instants(session, t0: dt.datetime, t1: dt.datetime):
    """Reconstruct per-process gateway request instants in [t0, t1).
    Returns {(league, is_live): [datetime, ...]}."""
    from collections import defaultdict

    from sqlalchemy import text

    out: dict[tuple[str, bool], list[dt.datetime]] = defaultdict(list)

    # poll requests: one get_league_events per distinct (captured_at, is_live);
    # a representative slug routes the cycle to its league.
    polls = session.execute(text("""
        SELECT DISTINCT ON (captured_at, is_live)
               captured_at, is_live, market_slug
        FROM market_snapshots
        WHERE captured_at >= :t0 AND captured_at < :t1
        ORDER BY captured_at, is_live, market_slug
    """), {"t0": t0, "t1": t1}).all()
    for r in polls:
        lg = _route(r.market_slug)
        if lg is not None:
            out[(lg, bool(r.is_live))].append(r.captured_at)

    # book requests: one get_book per snapshot that has book_levels, at the
    # book's own fetch instant (COALESCE to the parent for pre-split rows).
    books = session.execute(text("""
        SELECT DISTINCT ON (bl.snapshot_id)
               ms.market_slug AS market_slug, ms.is_live AS is_live,
               COALESCE(bl.captured_at, ms.captured_at) AS req_at
        FROM book_levels bl
        JOIN market_snapshots ms ON ms.id = bl.snapshot_id
        WHERE COALESCE(bl.captured_at, ms.captured_at) >= :t0
          AND COALESCE(bl.captured_at, ms.captured_at) < :t1
        ORDER BY bl.snapshot_id
    """), {"t0": t0, "t1": t1}).all()
    for r in books:
        lg = _route(r.market_slug)
        if lg is not None:
            out[(lg, bool(r.is_live))].append(r.req_at)
    return out


def run_db(t0: dt.datetime, t1: dt.datetime) -> int:
    from core.storage.base import get_engine
    from core.storage import get_sessionmaker

    with get_sessionmaker(get_engine())() as s:
        instants = _request_instants(s, t0, t1)

    print(f"=== MEASURED CONCURRENT GATEWAY DRAW  [{t0.isoformat()} .. "
          f"{t1.isoformat()})  ceiling {GATEWAY_CEILING_REQ_S} req/s ===\n")
    peaks: dict[str, int] = {}
    measured_processes = 0
    for key, (name, cap) in PROCESS_CAPS.items():
        ts = instants.get(key, [])
        peak, at = peak_concurrent(ts, 1.0)
        peaks[name] = peak
        if ts:
            measured_processes += 1
        note = ""
        if key[1] is False:
            note = "  (pregame: book fetches cycle-clustered -> peak OVERSTATED)"
        state = "no data in window" if not ts else (
            f"peak {peak} req/s at {at.isoformat() if at else '?'} "
            f"({peak / cap:.0%} of cap {cap})")
        print(f"  {name:28} cap {cap:>2}  |  {state}{note}")

    print("\n  stats-sweepers (NOT reconstructable from these tables — "
          "different endpoints; carried at configured cap):")
    for name, cap in SWEEPER_CAPS.items():
        peaks[name] = cap
        print(f"  {name:28} cap {cap:>2}  |  UNMEASURED — using cap as floor")

    proj = additive_projection(peaks)
    print(f"\n  ADDITIVE WORST-CASE PROJECTION (all processes' peaks coincide): "
          f"{proj} req/s vs ceiling {GATEWAY_CEILING_REQ_S}")
    print(f"  configured-cap sum for comparison: "
          f"{sum(c for _, c in PROCESS_CAPS.values()) + sum(SWEEPER_CAPS.values())} req/s")
    print(f"  headroom under the additive worst case: "
          f"{GATEWAY_CEILING_REQ_S - proj} req/s")
    if measured_processes < len(PROCESS_CAPS):
        print("\n  NOTE: not every recorder had data in this window (a dark board "
              "draws nothing), so an unmeasured recorder contributes its MEASURED "
              "0 to the projection above — NOT its configured cap. That UNDERstates "
              "Sept-17 until each process has been measured live. Re-run over a "
              "window where each is live (NFL-live needs --since after Sept 9) "
              "before trusting the projection as the worst case.")
    print("\n  LABEL: the Sept-17 simultaneous-live regime exists in no tape yet; "
          "this projection is ADDITIVE across independent processes (their calls "
          "genuinely sum at coincidence; conservative because coincidence is the "
          "worst case). Legitimate where depth-extrapolation was not, because the "
          "quantity (request load) does not change across the projection — only "
          "its coincidence does.")
    return 0


# --------------------------------------------------------------------------- #
#  selftest: known-answer on the pure peak function (rule 16 on the tool itself)
# --------------------------------------------------------------------------- #

def _selftest() -> int:
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {label:56} {'OK' if cond else 'FAIL'}")

    base = dt.datetime(2026, 8, 20, 19, 0, 0, tzinfo=UTC)

    def at(*secs):
        return [base + dt.timedelta(seconds=s) for s in secs]

    # empty
    chk("empty -> (0, None)", peak_concurrent([]) == (0, None))
    # three within one second -> peak 3
    p, _ = peak_concurrent(at(0.0, 0.3, 0.9))
    chk("3 within 1s -> peak 3", p == 3)
    # the 1s window is half-open: t=0.0 and t=1.0 are NOT in the same window
    p, _ = peak_concurrent(at(0.0, 1.0))
    chk("half-open: 0.0 and 1.0 -> peak 1", p == 1)
    # a tight cluster of 12 in 0.5s then quiet -> peak 12 (the cap-12 shape)
    cluster = at(*[i * 0.04 for i in range(12)]) + at(30, 60, 90)
    p, when = peak_concurrent(cluster)
    chk("12 in 0.5s among spread -> peak 12", p == 12)
    chk("peak located at the cluster start", when == base)
    # spread evenly: 10 requests over 10s -> peak 1/s
    p, _ = peak_concurrent(at(*[float(i) for i in range(10)]))
    chk("10 over 10s (1/s) -> peak 1", p == 1)
    # additive projection sums independent peaks
    chk("additive projection sums", additive_projection({"a": 3, "b": 4, "c": 2}) == 9)

    print("\nGATEWAY-DRAW SELFTEST:",
          "PASS — the peak-req/s window and the additive projection are pinned to "
          "known answers; the DB layer reconstructs request instants from "
          "captured_at (see module docstring for the proxy + caveats)."
          if ok else "FAIL")
    return 0 if ok else 1


def _parse_day(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--since", type=_parse_day, help="window start (ISO date/datetime, UTC)")
    ap.add_argument("--until", type=_parse_day, help="window end (ISO date/datetime, UTC)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.since or not args.until:
        ap.error("--since and --until are required (or use --selftest)")
    return run_db(args.since, args.until)


if __name__ == "__main__":
    raise SystemExit(main())
