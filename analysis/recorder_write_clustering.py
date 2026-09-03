"""Row-write clustering per recorder — a batching-SHAPE diagnostic. NOT a rate
or request-dispatch measure.

WHAT THIS IS NOT (read first — this replaces a wrong framing, 2026-09-03): an
earlier version of this file was named/read as "concurrent gateway draw" and its
output was compared to the 20 req/s ceiling. That was WRONG. `captured_at` is a
row COMPLETION-time stamp, so several depth fetches whose rows land in the same
second are binned together and read as simultaneous DISPATCH — a reconstruction
artifact, on the LIVE path as much as the pregame path (an earlier caveat named
this for pregame and then wrongly called the live per-fetch stamp "faithful";
per-fetch is per-COMPLETION, which still clusters). Run against August the old
framing reported 60 req/s on a 12-cap live recorder and a 196 req/s additive
"projection" against a 20 ceiling — all of which the venue refutes directly.

THE RATE QUESTION HAS A DIRECT INSTRUMENT — USE THAT, NOT THIS: count the
venue's own HTTP 429 / rate-limit rejections. It needs no reconstruction, and as
of 2026-09-03 it is ZERO across every recorder's entire container life, including
August live WNBA slates run flat out. Dispatching 60 req/s against a 20 ceiling
for weeks would have produced constant rejections; it produced one book-fetch
failure total. The standing rate check is the 429 count (checklist 4d, 3ca5c3c);
Sept 17 is a WATCH for 429s, not a timestamp reconstruction. Lesson (this one is
shared): a sum of configured caps is not a dispatch claim, and neither is a
count of row-write completions — verify rate against the venue's own answer.

WHAT THIS ACTUALLY MEASURES, and why it is still worth keeping: the peak number
of rows a recorder COMPLETES within a 1s window — i.e. how tightly its writes
cluster. That is a real property of the recorder's batching shape: a change in
how a recorder batches its poll + depth writes would move this number, so it is a
useful regression signal for "did the write pattern change", and a coarse input
to DB write-load (not gateway request-load) discussion. It is NOT comparable to a
per-IP request ceiling and this file no longer pretends it is.

Reconstruction: one `get_league_events` per poll writes a cluster of
market_snapshots sharing one `captured_at`; each `get_book` writes book_levels at
its own `captured_at` (per-fetch on the live loop; the shared cycle stamp on the
combined pregame loop). We count row-completion instants per process
(league x is_live) and report the peak per 1s window.

    python analysis/recorder_write_clustering.py --since 2026-08-18 --until 2026-08-23
    python analysis/recorder_write_clustering.py --selftest         # no DB
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt

UTC = dt.timezone.utc

#: (league, is_live) -> the recorder process that writes those rows. Caps are NOT
#: listed here on purpose: this file measures write clustering, which is not
#: comparable to a request-dispatch cap (see docstring). The rate check is the
#: venue 429 count, elsewhere.
PROCESSES: dict[tuple[str, bool], str] = {
    ("wnba", False): "meridian-recorder",
    ("wnba", True): "meridian-live-recorder",
    ("nfl", False): "meridian-nfl-recorder",
    ("nfl", True): "meridian-nfl-live-recorder",
}


def peak_in_window(timestamps: list[dt.datetime], window_s: float = 1.0) -> tuple[int, dt.datetime | None]:
    """Max number of timestamps within any half-open window of width window_s —
    here, the peak rows COMPLETING per window (write clustering), not dispatch.
    Pure; the known-answer selftest pins it. Returns (peak, window_start)."""
    if not timestamps:
        return 0, None
    ts = sorted(timestamps)
    best, best_at = 0, None
    w = dt.timedelta(seconds=window_s)
    for i, t0 in enumerate(ts):
        j = bisect.bisect_left(ts, t0 + w)   # first index with ts[j] >= t0+w
        count = j - i
        if count > best:
            best, best_at = count, t0
    return best, best_at


# --------------------------------------------------------------------------- #
#  DB reconstruction (runs on prod; imports are lazy so --selftest needs no DB)
# --------------------------------------------------------------------------- #

def _route(slug: str) -> str | None:
    from core.leagues import league_of_slug
    lg = league_of_slug(slug)
    return lg.slug if lg is not None else None


def _write_instants(session, t0: dt.datetime, t1: dt.datetime):
    """Row-completion instants per process in [t0, t1): poll writes (distinct
    market_snapshots.captured_at) + depth writes (one per snapshot with
    book_levels, at the book's captured_at). {(league, is_live): [datetime,...]}."""
    from collections import defaultdict

    from sqlalchemy import text

    out: dict[tuple[str, bool], list[dt.datetime]] = defaultdict(list)

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
        instants = _write_instants(s, t0, t1)

    print(f"=== RECORDER ROW-WRITE CLUSTERING  [{t0.isoformat()} .. "
          f"{t1.isoformat()})  ===")
    print("    (peak rows COMPLETING per 1s window — a batching-shape signal, "
          "NOT request dispatch and NOT comparable to the req/s ceiling;\n"
          "     the rate check is the venue 429 count, which is zero — see "
          "checklist 4d)\n")
    for key, name in PROCESSES.items():
        ts = instants.get(key, [])
        peak, at = peak_in_window(ts, 1.0)
        state = "no rows in window" if not ts else (
            f"peak {peak} rows/s completing at "
            f"{at.isoformat() if at else '?'}  ({len(ts)} writes total)")
        tag = "  [pregame: poll+depth share the cycle stamp -> extra clustering]" \
            if key[1] is False else ""
        print(f"  {name:28}  |  {state}{tag}")
    print("\n  This is a write-SHAPE diagnostic: a jump here means a recorder's "
          "batching changed, not that it is being rate-limited. For rate, count "
          "429s at the venue.")
    return 0


# --------------------------------------------------------------------------- #
#  selftest: known-answer on the pure window function (rule 16 on the tool)
# --------------------------------------------------------------------------- #

def _selftest() -> int:
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {label:52} {'OK' if cond else 'FAIL'}")

    base = dt.datetime(2026, 8, 20, 19, 0, 0, tzinfo=UTC)

    def at(*secs):
        return [base + dt.timedelta(seconds=s) for s in secs]

    chk("empty -> (0, None)", peak_in_window([]) == (0, None))
    chk("3 within 1s -> peak 3", peak_in_window(at(0.0, 0.3, 0.9))[0] == 3)
    chk("half-open: 0.0 and 1.0 -> peak 1", peak_in_window(at(0.0, 1.0))[0] == 1)
    p, when = peak_in_window(at(*[i * 0.04 for i in range(12)]) + at(30, 60, 90))
    chk("12 completing in 0.5s among spread -> peak 12", p == 12 and when == base)
    chk("10 over 10s -> peak 1", peak_in_window(at(*[float(i) for i in range(10)]))[0] == 1)

    print("\nWRITE-CLUSTERING SELFTEST:",
          "PASS — the peak-per-1s-window is pinned to known answers. It counts "
          "row completions (write clustering), NOT gateway dispatch; the rate "
          "instrument is the venue 429 count." if ok else "FAIL")
    return 0 if ok else 1


def _parse_day(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--since", type=_parse_day, help="window start (ISO, UTC)")
    ap.add_argument("--until", type=_parse_day, help="window end (ISO, UTC)")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    if not args.since or not args.until:
        ap.error("--since and --until are required (or use --selftest)")
    return run_db(args.since, args.until)


if __name__ == "__main__":
    raise SystemExit(main())
