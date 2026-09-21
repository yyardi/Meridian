#!/usr/bin/env python3
"""Read the board and write the day's launches, so no day depends on a
hand-written crontab.

    python3 scripts/schedule_slate.py --hours 26            # print the cron block
    python3 scripts/schedule_slate.py --hours 26 --dry-run  # same, plus the plan in words

Why this exists. For three days running the launches were typed by hand into
cron the night before, and on the third day nobody typed them: NFL Sunday
started at 17:00Z with no recorder, no detector and nothing on the desk
until 18:22Z. The board already knows every game and its kickoff, the
launchers already exist, and the rules for which instrument goes on which
game are short. This turns those rules into one function that a daily cron
runs, and prints a block the host wrapper installs.

The rules, in one place:

* Every game with a ladder gets the STREAM detector at tip minus two
  minutes. It reads the venue's own pushes, costs nothing against the
  request budget, and is the instrument the measured edge lives on.
* A per-league STREAM RECORDER covers each kickoff window (games within
  three hours of the window's first tip), from ten minutes before the first
  tip until the last game in the window should be over.
* Football games with a real ladder also get the REST executor for the
  desk, capped at three per 90-minute kickoff bucket because REST costs
  request budget the live recorder needs; the first two of those carry the
  REST-vs-stream comparator.
* Basketball and baseball get the read-only sampler (no tickets; the fill
  test is not registered on them) alongside the stream detector.
* The verdict -- the slate scan and the settlement P&L -- runs half an hour
  after the last game should be over, and a self-clean drops every TEMP
  line at the next 08:00Z after that.

Everything here is arithmetic over the board; the only side effect is the
cron block on stdout. The host wrapper (scripts/schedule_slate.sh) installs
it, because crontab lives on the host and this runs in the api image.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UTC = dt.timezone.utc

#: How long a game of each league may run, in minutes, from kickoff. These
#: bound the detector and executor runs and the recorder window. Football's
#: 230 is the value that has been launched by hand since 2026-09-19 and has
#: never cut a game short; the rest are conservative.
GAME_MINUTES = {"nfl": 230, "cfb": 230, "wnba": 170, "nba": 170, "mlb": 200}
DEFAULT_MINUTES = 200
#: Launch this many minutes before kickoff.
LEAD_MIN = 2
#: A recorder window starts this many minutes before its first kickoff.
RECORDER_LEAD_MIN = 10
#: Games tipping within this many hours of a recorder's START share its
#: window. This MUST equal --lookahead-hours in launch_stream_slate.sh: the
#: recorder resolves its slate once, at start, and subscribes only games
#: tipping inside that lookahead, so a window wider than it would leave the
#: later games unrecorded and a narrower one would open sockets for nothing.
RECORDER_LOOKAHEAD_H = 4
#: REST executors per 90-minute kickoff bucket, and how many of those carry
#: the comparator. Five REST clients ran cleanly on 2026-09-19; the live
#: recorder holds 12 of the venue's 20 requests a second.
REST_PER_BUCKET = 3
WS_PER_BUCKET = 2
REST_BUCKET_MIN = 90
#: A football ladder this thin is not a desk ticket source.
REST_MIN_RUNGS = 30
#: Below this many rungs a ladder has too few pairs to be worth a detector.
MIN_RUNGS = 4
#: Detector floor and freshness gate, from the measured edge.
FLOOR_USD = 25
FRESH_S = 2
#: The verdict runs this long after the last game should be over.
VERDICT_AFTER_MIN = 30

FOOTBALL = ("nfl", "cfb")
MEASURED_ONLY = ("wnba", "nba", "mlb")


@dataclass(frozen=True)
class Launch:
    at: dt.datetime
    script: str
    args: str
    tag: str

    @property
    def command(self) -> str:
        return f"{self.script} {self.args}".rstrip()


@dataclass
class Plan:
    launches: list[Launch] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    verdict_at: dt.datetime | None = None
    clean_at: dt.datetime | None = None

    @property
    def games(self) -> int:
        return len({l.args.split()[0] for l in self.launches if l.script == "launch_stream_exec.sh"})


def _minutes(league: str) -> int:
    return GAME_MINUTES.get(league, DEFAULT_MINUTES)


def _utc(t: dt.datetime) -> dt.datetime:
    return t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)


def plan(games: list[dict], now: dt.datetime) -> Plan:
    """The launches for ``games`` (each {game, league, tip, rungs}), from
    the rules in the module docstring. Pure: no clock but ``now``, no I/O.

    A game whose launch time is already past is SKIPPED and named, never
    launched late by cron (cron cannot fire in the past) and never silently
    dropped: the operator must see what a mid-slate run could not cover.
    """
    now = _utc(now)
    out = Plan()
    live = [dict(g, tip=_utc(g["tip"])) for g in games if int(g.get("rungs") or 0) >= MIN_RUNGS]
    live.sort(key=lambda g: (g["tip"], g["game"]))
    last_over: dt.datetime | None = None

    # -- per game: detector, and REST or sampler by league --------------------
    buckets: dict[tuple[str, dt.datetime], int] = {}
    for g in live:
        league, tip, rungs = g["league"], g["tip"], int(g["rungs"])
        # `key` is the game WITH its date, which the launchers need; `game`
        # is the board's short form for the phone and has none. A dry run
        # against the live board on 2026-09-21 built `aec-mlb-tor-bal` from
        # `game` and would have launched nothing.
        slug, mins = f"aec-{g.get('key') or g['game']}", _minutes(league)
        at = tip - dt.timedelta(minutes=LEAD_MIN)
        over = tip + dt.timedelta(minutes=mins)
        last_over = over if last_over is None or over > last_over else last_over
        if at <= now + dt.timedelta(minutes=1):
            out.skipped.append(f"{g['game']} tips {tip:%H:%M}Z, launch time already past")
            continue
        tag = f"TEMP {tip:%Y-%m-%d}"
        out.launches.append(Launch(at, "launch_stream_exec.sh", f"{slug} {mins} {FLOOR_USD} {FRESH_S}", tag))
        if league in FOOTBALL and rungs >= REST_MIN_RUNGS:
            # The bucket is the 90-minute slot of the day the kickoff falls
            # in: a 17:00 wave and a 20:05 wave are different slots, so each
            # gets its own three REST executors rather than sharing.
            b = (league, tip.date(), (tip.hour * 60 + tip.minute) // REST_BUCKET_MIN)
            n = buckets.get(b, 0)
            if n < REST_PER_BUCKET:
                ws = " ws" if n < WS_PER_BUCKET else ""
                out.launches.append(Launch(at, "launch_ladder.sh", f"{slug} {mins}{ws}", tag))
                buckets[b] = n + 1
        elif league in MEASURED_ONLY:
            out.launches.append(Launch(at, "launch_sampler.sh", f"{slug} {mins}", tag))

    # -- per league: recorder windows ----------------------------------------
    for league in sorted({g["league"] for g in live}):
        tips = [g["tip"] for g in live if g["league"] == league]
        i = 0
        while i < len(tips):
            start = tips[i] - dt.timedelta(minutes=RECORDER_LEAD_MIN)
            j = i
            while j + 1 < len(tips) and tips[j + 1] <= start + dt.timedelta(hours=RECORDER_LOOKAHEAD_H):
                j += 1
            end = tips[j] + dt.timedelta(minutes=_minutes(league))
            if start > now + dt.timedelta(minutes=1):
                mins = int((end - start).total_seconds() // 60)
                out.launches.append(Launch(start, "launch_stream_slate.sh",
                                           f"{league} {mins} {league}-{start:%m%d%H%M}",
                                           f"TEMP {tips[i]:%Y-%m-%d}"))
            else:
                out.skipped.append(f"{league} recorder window from {start:%H:%M}Z already past")
            i = j + 1

    # -- the verdict and the self-clean ---------------------------------------
    if last_over is not None:
        out.verdict_at = last_over + dt.timedelta(minutes=VERDICT_AFTER_MIN)
        if out.verdict_at > now:
            out.launches.append(Launch(out.verdict_at, "slate_verdict.sh", "", f"TEMP verdict"))
        clean = out.verdict_at.replace(hour=8, minute=0, second=0, microsecond=0)
        if clean <= out.verdict_at + dt.timedelta(hours=1):
            clean += dt.timedelta(days=1)
        out.clean_at = clean
    out.launches.sort(key=lambda l: (l.at, l.script, l.args))
    return out


def cron_block(p: Plan, reads_dir: str) -> str:
    """The lines to append to the crontab. Every launch line ends in
    ``# TEMP <date>`` so the self-clean can drop them; the self-clean line
    contains the word TEMP inside its own quotes and so removes itself."""
    lines = [f"# ===== slate scheduled by schedule_slate.py at {dt.datetime.now(UTC):%Y-%m-%d %H:%MZ}"]
    for l in p.launches:
        lines.append(f"{l.at.minute} {l.at.hour} {l.at.day} {l.at.month} * "
                     f"sudo -n {reads_dir}/{l.command} >> {reads_dir}/cron.log 2>&1   # {l.tag}")
    if p.clean_at is not None:
        c = p.clean_at
        lines.append(f'{c.minute} {c.hour} {c.day} {c.month} * crontab -l | grep -v "TEMP" | crontab -')
    return "\n".join(lines) + "\n"


def describe(p: Plan) -> str:
    by = {}
    for l in p.launches:
        by[l.script] = by.get(l.script, 0) + 1
    parts = [f"{p.games} games, {len(p.launches)} launches: "
             + ", ".join(f"{k.replace('launch_', '').replace('.sh', '')} x{v}" for k, v in sorted(by.items()))]
    if p.launches:
        parts.append(f"first {p.launches[0].at:%H:%M}Z, verdict {p.verdict_at:%H:%M}Z, clean {p.clean_at:%m-%d %H:%M}Z")
    for s in p.skipped:
        parts.append(f"SKIPPED: {s}")
    return "\n".join(parts)


def hours_until(now: dt.datetime, utc_hour: int) -> float:
    """Hours from ``now`` to the NEXT ``utc_hour``:00Z, at least one hour.

    The daily run happens at 12:10Z and should cover the day's slate up to
    the next run, not a fixed span: a fixed 26 hours run at 19:41Z reached
    the following afternoon's baseball and pushed the verdict for Monday
    Night Football to 20:55Z the next day. Noon UTC is before any US game
    and after every late one has settled.
    """
    now = _utc(now)
    nxt = now.replace(hour=utc_hour, minute=0, second=0, microsecond=0)
    if nxt <= now + dt.timedelta(hours=1):
        nxt += dt.timedelta(days=1)
    return (nxt - now).total_seconds() / 3600.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=None,
                    help="how far ahead to read the board; default is up to the next --until-utc-hour")
    ap.add_argument("--until-utc-hour", type=int, default=12,
                    help="the window ends at the next occurrence of this UTC hour (the daily run's own time)")
    ap.add_argument("--reads-dir", default="/opt/meridian/artifacts/reads",
                    help="where the launchers live ON THE HOST (the cron lines run there)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan in words too")
    a = ap.parse_args()
    from scripts.game_schedule import slate
    now = dt.datetime.now(UTC)
    hours = a.hours if a.hours is not None else hours_until(now, a.until_utc_hour)
    p = plan(slate(hours), now)
    if a.dry_run:
        print(describe(p), file=sys.stderr)
    sys.stdout.write(cron_block(p, a.reads_dir))
    if p.launches:
        try:
            from core import notify
            notify.push("schedule", f"Scheduled {p.games} games",
                        describe(p)[:900], tags="calendar", timeout=15)
        except Exception:  # noqa: BLE001 -- a push is never worth a failed schedule
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
