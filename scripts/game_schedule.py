#!/usr/bin/env python3
"""Push the day's slate once: which games have a ladder, and when they start.

    python3 scripts/game_schedule.py --hours 24              # the day's slate, once
    python3 scripts/game_schedule.py --starting-within 15    # ping what tips soon
    python3 scripts/game_schedule.py --hours 24 --dry-run    # print, send nothing

Two modes because one message a day is forgettable: the morning slate says
what is coming, and the tipoff ping -- run from cron every few minutes, one
ping per game ever, recorded in schedule_pinged.txt -- says it is starting now.

Why this replaced the per-ticket alerts: the desk on :8008 shows every live
ticket with its own liveness, so a phone buzzing at each one was telling the
operator something the screen already said, sixty times an hour. What the
screen cannot say is what is on later today. One message, in the morning,
naming every game with a spread ladder and its kickoff -- so nobody has to go
and look up a schedule -- is the notification that is actually worth having.

It reads the recorder's own market listing rather than any external schedule:
a game Meridian cannot see is a game Meridian cannot trade, so the venue's
board IS the schedule that matters here. Games with fewer than MIN_RUNGS
spread rungs are counted but not listed by name; a two-rung ladder has three
pairs and is not where an opportunity lives.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import notify  # noqa: E402
from core.ladder.live import LADDER_MARKET_TYPES, _engine  # noqa: E402

#: A ladder this short is listed in the counts but not by name: with n rungs
#: there are n(n-1)/2 pairs, so three rungs is three chances and thirty is 435.
MIN_RUNGS = 4

#: Above this many games in one league the message stops naming them and
#: starts naming KICKOFF SLOTS instead. Eight names is already most of a
#: push; forty-nine is four times the character budget.
NAME_LIMIT = 8


def _by_kickoff(games: list[dict]) -> list[tuple, ]:
    """[(tip, [games])] in time order. Games that start together are one
    entry: that is how a slate is actually read, and it is what makes a
    49-game morning fit in a notification."""
    slots: dict = {}
    for g in games:
        slots.setdefault(g["tip"], []).append(g)
    return sorted(slots.items())

#: `game` is the key WITHOUT its date, for the phone (shorter lines);
#: `key` is the full game key the launchers take, `cfb-mia-wake-2026-09-18`.
#: The scheduler must use `key`: a dry run on 2026-09-21 built every slug
#: from `game` and would have launched `aec-mlb-tor-bal` with no date,
#: which the recorder has never heard of.
SQL = """
SELECT substring(market_slug from '^a[es]c-(.*)-[0-9]{4}-[0-9]{2}-[0-9]{2}') AS game,
       substring(market_slug from '^a[es]c-(.*-[0-9]{4}-[0-9]{2}-[0-9]{2})')  AS key,
       split_part(market_slug, '-', 2)                                       AS league,
       min(game_start_time)                                                  AS tip,
       count(DISTINCT market_slug)                                           AS rungs
FROM market_snapshots
WHERE captured_at >= date_trunc('month', now() - interval '12 hours')
  AND captured_at >= now() - interval '12 hours'
  AND sports_market_type = ANY(:families)
  AND game_start_time BETWEEN now() - interval '1 hour' AND now() + CAST(:hours AS interval)
GROUP BY 1, 2, 3
HAVING count(DISTINCT market_slug) >= 1
ORDER BY 4, 1
"""


def slate(hours: float, engine=None) -> list[dict]:
    """Every game with a spread ladder tipping inside the window."""
    from sqlalchemy import text
    eng = engine if engine is not None else _engine(None)
    with eng.connect() as c:
        rows = c.execute(text(SQL), {"families": list(LADDER_MARKET_TYPES),
                                     "hours": f"{hours} hours"}).all()
    return [{"game": r[0], "key": r[1], "league": r[2], "tip": r[3], "rungs": int(r[4])}
            for r in rows]


def compose(games: list[dict], now: dt.datetime) -> tuple[str, str]:
    """(title, body). Times in UTC, with hours-from-now beside them, because
    the operator reads this on a phone in an unknown timezone."""
    listed = [g for g in games if g["rungs"] >= MIN_RUNGS]
    if not listed:
        return ("Meridian: no ladder today",
                f"No game with {MIN_RUNGS}+ spread rungs in the window. "
                f"{len(games)} thin ones listed." if games else "Nothing on the board.")
    by_league: dict[str, list[dict]] = {}
    for g in listed:
        by_league.setdefault(g["league"], []).append(g)
    lines = []
    for league in sorted(by_league):
        group = by_league[league]
        lines.append(f"{league.upper()} ({len(group)})")
        if len(group) > NAME_LIMIT:
            # A 49-game Saturday does not fit in a push and a truncated list
            # is the worst of both: it names eight games and hides the wave.
            # The question was what time things are running, so answer THAT --
            # kickoff slots with a count, which is the whole day in six lines.
            for tip, slot in _by_kickoff(group):
                when = "live" if tip <= now else f"+{(tip - now).total_seconds() / 3600:.1f}h"
                big = max(slot, key=lambda g: g["rungs"])
                # A slot of one has nothing to summarise, so it reads like the
                # small-league line rather than "1 games".
                what = (f"{len(slot)} games, incl {big['game']}" if len(slot) > 1
                        else f"{big['game']}  {big['rungs']} rungs")
                lines.append(f"  {tip:%H:%M}Z {when:>6}  {what}")
        else:
            for g in group:
                tip = g["tip"]
                when = "live" if tip <= now else f"+{(tip - now).total_seconds() / 3600:.1f}h"
                lines.append(f"  {tip:%H:%M}Z {when:>6}  {g['game']}  {g['rungs']} rungs")
    thin = len(games) - len(listed)
    if thin:
        lines.append(f"({thin} thin ladders not listed)")
    return (f"Meridian slate: {len(listed)} games", "\n".join(lines)[:1400])


def seen_path(out_dir: str | None = None) -> str:
    d = out_dir or os.environ.get("MERIDIAN_READS_DIR") or "/opt/meridian/artifacts/reads"
    return os.path.join(d, "schedule_pinged.txt")


def already_pinged(game: str, path: str) -> bool:
    """One ping per game, ever. The file is the memory, not the process: this
    runs from cron every few minutes and must not re-ping a game because the
    last run exited."""
    try:
        with open(path, encoding="utf-8") as f:
            return any(line.strip() == game for line in f)
    except OSError:
        return False


def mark_pinged(game: str, path: str) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(game + "\n")
    except OSError:                       # a ping is worth more than a record
        pass


def compose_tipoff(games: list[dict], now: dt.datetime) -> tuple[str, str]:
    """The about-to-start message. Short: it is read on a lock screen."""
    lines = []
    for g in games:
        mins = max(0, round((g["tip"] - now).total_seconds() / 60))
        lines.append(f"{g['game']} in {mins}m ({g['tip']:%H:%M}Z) · {g['rungs']} rungs")
    head = games[0]["game"] if len(games) == 1 else f"{len(games)} games"
    return (f"Starting soon: {head}", "\n".join(lines)[:900])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24.0,
                    help="slate mode: how far ahead to list")
    ap.add_argument("--starting-within", type=float, default=None,
                    help="TIPOFF mode: ping games starting inside this many minutes, "
                         "once each. Run it from cron every few minutes.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)

    if a.starting_within is not None:
        # A game already under way is not "starting soon": the window is
        # forward-only, or a cron every 5 minutes would ping a live game
        # until it ended.
        soon = [g for g in slate(a.starting_within / 60.0)
                if g["rungs"] >= MIN_RUNGS and g["tip"] > now]
        path = seen_path()
        fresh = [g for g in soon if not already_pinged(g["game"], path)]
        if not fresh:
            print("nothing starting that has not been pinged")
            return 0
        title, body = compose_tipoff(fresh, now)
        if a.dry_run:
            print(title); print(body); return 0
        result = notify.push("schedule", title, body, priority="high", tags="stadium", timeout=15)
        if result == notify.SENT:
            for g in fresh:
                mark_pinged(g["game"], path)
        print(result)
        return 0

    games = slate(a.hours)
    title, body = compose(games, now)
    if a.dry_run:
        print(title)
        print(body)
        return 0
    # kind "schedule": in scope by default alongside tickets, so this arrives
    # while the nightly summaries stay muted (docs/ops/notifications.md).
    print(notify.push("schedule", title, body, tags="calendar", timeout=15))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
