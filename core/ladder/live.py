"""Read a live game's ladder from the venue, every rung inside a few seconds.

This is the sampling half of `cfb/run_live_ladder.py` and
`cfb/run_ladder_executor.py`, moved here so the dashboard can call it: the api
image COPYs core/ and not cfb/, so anything the api needs lives under
core/ladder/ and the cfb scripts import it back. Behaviour is unchanged; the
cfb modules re-export these names and their tests still pin them.

What is here: the slug -> line parse (verified on 84,646 settled pairs,
STATUS 0bk), the recorder-backed slug listing for a game, the simultaneous
touch sample, and the book-age read off the venue's `transactTime`.

PLACES NOTHING. The only venue method this module calls is the read-only
`get_book` on whatever client it is handed; it imports no client of its own,
and a test pins the absence of any order path.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time

LINE = re.compile(r"-(neg|pos)-(\d+)pt(\d)$")

_TT = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z?$")


def line_of(slug: str, winner_prefix: str) -> float | None:
    """The slug-frame line: 0 for the winner market, signed N.5 for a spread
    (neg -> negative), None for anything else (totals, other games)."""
    if slug.startswith(winner_prefix):
        return 0.0
    m = LINE.search(slug)
    if not m:
        return None
    return (-1.0 if m.group(1) == "neg" else 1.0) * (float(m.group(2)) + float(m.group(3)) / 10)


def slugs_for(prefix: str, engine=None) -> list[str]:
    """The ladder's slugs from the recorder's own listing of this game.

    ``engine`` may be a SQLAlchemy engine, a database URL, or None. None reads
    ``DATABASE_URL`` from the environment exactly as the scripts always have;
    the api passes its own engine because its process is configured
    differently and must not depend on the scripts' variable being set.
    """
    from sqlalchemy import create_engine, text
    if engine is None:
        engine = create_engine(os.environ["DATABASE_URL"])
    elif isinstance(engine, str):
        engine = create_engine(engine)
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT DISTINCT market_slug FROM market_snapshots "
            "WHERE captured_at >= now() - interval '2 days' AND market_slug LIKE :p "
            "AND sports_market_type IN ('football_team_full_game_winner','football_team_full_game_spread',"
            "'baseball_team_full_game_winner','baseball_team_full_game_spread',"
            "'basketball_team_full_game_winner','basketball_team_full_game_spread')"),
            {"p": f"%{prefix}%"}).all()
    return sorted(r[0] for r in rows)


def _print_rung_error(slug: str, error: str) -> None:
    """The scripts' reporter: one line on stdout, as run_live_ladder always did."""
    print(f"  ERR {slug} {error}")


def sample(client, slugs: list[str], winner_prefix: str, meta: dict | None = None,
           *, on_error=_print_rung_error):
    """Fetch every rung's touch from the venue. If ``meta`` is given it is
    filled with each rung's ``transactTime`` -- the venue's LAST-UPDATE stamp
    for that book (verified 2026-09-18: three identical snapshots 3s apart
    carried the same value), so ``now - transactTime`` is how long the rung
    has sat un-requoted.

    Returns ``(rungs, took_s)`` where rungs maps line -> (bid, ask, bid_size,
    ask_size), the shape `core.ladder.scan.scan_ladder` takes. One bad rung
    is skipped, not fatal: the sample is worth having with a hole in it.
    ``on_error(slug, message)`` reports it: the scripts print, the api logs
    through structlog so its stdout stays JSON.
    """
    rungs = {}
    t0 = time.time()
    for s in slugs:
        try:
            book, raw = client.get_book(s)
        except Exception as e:  # noqa: BLE001 -- one bad rung must not kill the sample
            on_error(s, str(e)[:60])
            continue
        md = book.market_data
        if not md.bids or not md.offers:
            continue
        k = line_of(s, winner_prefix)
        if k is None:
            continue
        rungs[k] = (float(md.bids[0].px.value), float(md.offers[0].px.value),
                    float(md.bids[0].qty), float(md.offers[0].qty))
        if meta is not None:
            meta[k] = ((raw or {}).get("marketData") or {}).get("transactTime")
    return rungs, time.time() - t0


def book_age_s(transact_time: str | None, now: float) -> float | None:
    """Seconds since the venue last updated a book. transactTime is the book's
    last-update stamp (not the snapshot time), with nanosecond fractions."""
    if not transact_time:
        return None
    m = _TT.match(transact_time.strip())
    if not m:
        return None
    base = dt.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    frac = float("0." + m.group(2)) if m.group(2) else 0.0
    return round(now - (base.timestamp() + frac), 1)
