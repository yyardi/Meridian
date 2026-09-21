"""Read a live game's ladder from the venue, every rung inside a few seconds.

This is the sampling half of `cfb/run_live_ladder.py` and
`cfb/run_ladder_executor.py`, moved here so the dashboard can call it: the api
image COPYs core/ and not cfb/, so anything the api needs lives under
core/ladder/ and the cfb scripts import it back. Behaviour is unchanged; the
cfb modules re-export these names and their tests still pin them.

What is here: the slug -> line parse (verified on 84,646 settled pairs,
STATUS 0bk), the recorder-backed slug listing for a game, the slate-level
listing of every unfinished game in a league on a date, the simultaneous
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

#: One venue slug, split into the game it belongs to and the rung it is.
#:
#: The three-letter head is the venue's market-kind code (`aec-` winner,
#: `asc-` spread, `tsc-` total); the game is everything up to and including
#: the date; the optional tail is the spread rung. Anchored at both ends and
#: ending the game at a date ON PURPOSE: a totals slug
#: (`tsc-mlb-col-det-2026-09-13-8pt5`) and a numbered event
#: (`asc-cfb-cencon-toledo-2026-09-12-2`) must NOT parse, because a totals
#: ladder runs the other way round -- a larger spread line is EASIER to cover
#: and dearer, a larger total line is HARDER to clear and cheaper -- so
#: feeding one to `scan.scan_ladder` reports the correct board as broken.
_RUNG = re.compile(
    r"^[a-z]{3}-(?P<game>[a-z0-9]+(?:-[a-z0-9]+)+-\d{4}-\d{2}-\d{2})"
    r"(?:-(?P<sign>neg|pos)-(?P<pts>\d+)pt(?P<tenth>\d))?$")

#: The market families a ladder is made of, in every league the venue quotes
#: one for. `slugs_for` names the same six inline in its SQL and is left that
#: way because a test reads that function's source for them; a drift test
#: (tests/test_stream_recorder.py) pins the two sets equal, so a family added
#: to one and not the other fails rather than silently halving a slate.
LADDER_MARKET_TYPES = (
    "football_team_full_game_winner", "football_team_full_game_spread",
    "baseball_team_full_game_winner", "baseball_team_full_game_spread",
    "basketball_team_full_game_winner", "basketball_team_full_game_spread",
)

#: How long after kickoff a game of this league can still be being played.
#:
#: Deliberately generous, and the asymmetry is the argument: too LONG costs a
#: handful of settled games' slugs on a stream that is free (it costs no
#: request budget at all, which is the whole reason for the stream), while too
#: SHORT silently drops live games from the slate. A wall clock measured on
#: one league and applied to another is how 491 live CFB minutes were lost
#: once already -- 25% of CFB games exceed the ~2h a WNBA game takes.
LIVE_WINDOW_HOURS = {"cfb": 6.0, "nfl": 5.0, "mlb": 6.0, "wnba": 4.0, "nba": 4.0}

#: For a league not in the table: the longest window any of them needs.
DEFAULT_LIVE_WINDOW_HOURS = 6.0


def line_of(slug: str, winner_prefix: str) -> float | None:
    """The slug-frame line: 0 for the winner market, signed N.5 for a spread
    (neg -> negative), None for anything else (totals, other games)."""
    if slug.startswith(winner_prefix):
        return 0.0
    m = LINE.search(slug)
    if not m:
        return None
    return (-1.0 if m.group(1) == "neg" else 1.0) * (float(m.group(2)) + float(m.group(3)) / 10)


def game_and_line(slug: str) -> tuple[str, float] | None:
    """``('cfb-mia-wake-2026-09-18', 10.5)`` from one ladder slug, or None.

    `line_of` needs the game's WINNER slug handed to it to know which market
    is line 0. A slate recorder has hundreds of slugs arriving off a stream
    and no per-message context, so the game and the line are read out of the
    slug itself here -- one parse, one place, and the sign convention stays
    the one `line_of` uses (neg -> negative). Returns None for anything that
    is not a winner or spread rung, so a totals slug cannot reach a scanner
    whose orientation is wrong for it.
    """
    m = _RUNG.match(slug)
    if not m:
        return None
    if m.group("pts") is None:
        return m.group("game"), 0.0
    line = float(m.group("pts")) + float(m.group("tenth")) / 10
    return m.group("game"), (-line if m.group("sign") == "neg" else line)


def slugs_for(prefix: str, engine=None) -> list[str]:
    """The ladder's slugs from the recorder's own listing of this game.

    ``engine`` may be a SQLAlchemy engine, a database URL, or None. None reads
    ``DATABASE_URL`` from the environment exactly as the scripts always have;
    the api passes its own engine because its process is configured
    differently and must not depend on the scripts' variable being set.
    """
    from sqlalchemy import text
    with _engine(engine).connect() as c:
        rows = c.execute(text(
            "SELECT DISTINCT market_slug FROM market_snapshots "
            # The month-boundary floor is what prunes partitions; the 2-day
            # one is the recency the caller means. `slate_slugs` below has
            # carried both since it was written; this one carried only the
            # second and scanned every partition on an unindexable LIKE,
            # once per newly watched game, against a database at 47 % CPU.
            "WHERE captured_at >= date_trunc('month', now() - interval '2 days') "
            "AND captured_at >= now() - interval '2 days' AND market_slug LIKE :p "
            "AND sports_market_type IN ('football_team_full_game_winner','football_team_full_game_spread',"
            "'baseball_team_full_game_winner','baseball_team_full_game_spread',"
            "'basketball_team_full_game_winner','basketball_team_full_game_spread')"),
            {"p": f"%{prefix}%"}).all()
    return sorted(r[0] for r in rows)


def _engine(engine):
    """A SQLAlchemy engine from an engine, a URL, or the scripts' environment.

    One resolver for both listings, so the slate query cannot acquire a
    second, differently-defaulted way of reaching the database. A missing
    ``DATABASE_URL`` still raises KeyError rather than defaulting silently.
    """
    from sqlalchemy import create_engine
    if engine is None:
        return create_engine(os.environ["DATABASE_URL"])
    if isinstance(engine, str):
        return create_engine(engine)
    return engine


def slate_slugs(league: str, date: str | None = None, engine=None, *,
                within_hours: float | None = None, lookahead_hours: float = 3.0,
                now: dt.datetime | None = None) -> dict[str, list[str]]:
    """Every unfinished game of one league and its FULL spread+winner ladder.

    `slugs_for` answers "which rungs does this game have"; a slate recorder
    asks the other question first -- "which games are there" -- for 49 CFB
    games at once. Same table, same six families, one query instead of 49.

    Returns ``{game_prefix: [slugs]}`` with the prefixes in KICKOFF ORDER, so
    a caller that has to cut the slate down (`--max-games`) keeps the games
    that start soonest rather than an alphabetical accident.

    UNFINISHED is `game_start_time` inside a window, not a settlement flag:
    the venue's own state is on the market rather than the game, and a game
    that has ended simply stops updating. So the window opens
    `within_hours` before now (LIVE_WINDOW_HOURS, per league) and closes
    `lookahead_hours` ahead of it, which picks up the pregame board too.

    ``date`` is the UTC date of the KICKOFF and narrows the window further; a
    23:30 ET Saturday kickoff is 03:30Z on the Sunday and belongs to the
    Sunday. Omitted, the window alone decides, which is what a runner started
    mid-slate wants.
    """
    from sqlalchemy import text
    now = now or dt.datetime.now(dt.timezone.utc)
    hours = within_hours if within_hours is not None else LIVE_WINDOW_HOURS.get(
        league, DEFAULT_LIVE_WINDOW_HOURS)
    start = now - dt.timedelta(hours=hours)
    end = now + dt.timedelta(hours=lookahead_hours)
    if date:
        day = dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        start, end = max(start, day), min(end, day + dt.timedelta(days=1))
    # Inlined rather than bound: the list is this module's own constant, never
    # a caller's string. The league and the window ARE caller input and are
    # bound.
    families = ",".join(f"'{t}'" for t in LADDER_MARKET_TYPES)
    with _engine(engine).connect() as c:
        rows = c.execute(text(
            "SELECT DISTINCT market_slug, game_start_time FROM market_snapshots "
            # Two captured_at floors doing two different jobs: the month
            # boundary is the only one that prunes partitions (a mid-month
            # floor filters rows and costs MORE), the 2-day one is the
            # recency the caller actually means.
            "WHERE captured_at >= date_trunc('month', now() - interval '2 days') "
            "AND captured_at >= now() - interval '2 days' "
            "AND market_slug LIKE :p "
            f"AND sports_market_type IN ({families}) "
            "AND game_start_time IS NOT NULL "
            "AND game_start_time >= :from_ts AND game_start_time < :to_ts"),
            {"p": f"%-{league}-%", "from_ts": start, "to_ts": end}).all()
    by_game: dict[str, set[str]] = {}
    kickoff: dict[str, dt.datetime] = {}
    for slug, started in rows:
        parsed = game_and_line(slug)
        if parsed is None:
            continue
        game = parsed[0]
        by_game.setdefault(game, set()).add(slug)
        if started is not None and (game not in kickoff or started < kickoff[game]):
            kickoff[game] = started
    # A game with no readable kickoff sorts last rather than raising on a
    # None/datetime comparison, and never displaces a game that has one.
    order = sorted(by_game, key=lambda g: (g not in kickoff, kickoff.get(g) or start, g))
    return {g: sorted(by_game[g]) for g in order}


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
