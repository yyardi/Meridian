"""Which stream tapes the nightly verdict has not read yet, dated by their tag.

    python3 verdict_tapes.py --root /opt/meridian/artifacts/reads/stream [--running NAME ...]
    python3 verdict_tapes.py --root ... --mark DIR ...

The verdict used to pick tapes by a clock: directories modified in the last
twenty hours. On 2026-09-24 the planner waited for an ODI before scheduling
the verdict, the schedule rolled a day, and the previous night's WNBA and MLB
tapes aged out of that window unread -- a slate with no ledger row and no
phantom count. A tape is now read ONCE, whenever the verdict runs: a
directory is a candidate until it carries a `_verdicted` marker, and the
verdict writes the marker after the ledger has its rows.

Each tape is DATED BY ITS TAG (`wnba-09232350` is 2026-09-23), never by the
run date: a verdict that runs late must not file last night's slate under
today. Tapes whose recorder is still running are left for the next run, and
legacy hand-named tapes (`nfl-a`, `nfl-b`, smoke and fixture dirs) carry no
tag date and are never candidates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

MARKER = "_verdicted"
#: A tape older than this without a marker is a tape the verdict never ran
#: on; it is listed anyway, dated by its tag, because the whole point is that
#: a late verdict still reads it. Older than this and it is archaeology.
MAX_AGE_DAYS = 7
TAG = re.compile(r"^(?P<league>[a-z0-9]+)-(?P<mm>\d{2})(?P<dd>\d{2})(?P<hh>\d{2})(?P<mi>\d{2})$")


def tag_date(basename: str, mtime: dt.datetime) -> str | None:
    """`wnba-09232350` -> '2026-09-23'. The tag carries no year; the year is
    the tape's mtime year, or the one before when the tag would otherwise
    lie in the future (a December tape read in January)."""
    m = TAG.match(basename)
    if not m:
        return None
    mm, dd = int(m["mm"]), int(m["dd"])
    for year in (mtime.year, mtime.year - 1):
        try:
            d = dt.date(year, mm, dd)
        except ValueError:
            continue
        if d <= mtime.date():
            return d.isoformat()
    return None


def unverdicted(root: str, now: dt.datetime, running: set[str] = frozenset(),
                max_age_days: int = MAX_AGE_DAYS) -> list[tuple[str, str]]:
    """(tag date, absolute dir) for every tape the verdict still owes a read,
    oldest first. `running` names tapes whose recorder is still up (the tag,
    e.g. `mlb-09241625`); those wait for the next run."""
    out = []
    if not os.path.isdir(root):
        return out
    for base in sorted(os.listdir(root)):
        d = os.path.join(root, base)
        if not os.path.isdir(d) or base.startswith(("smoke", "_")) or base.endswith("_fixture"):
            continue
        if os.path.exists(os.path.join(d, MARKER)) or base in running:
            continue
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(d), tz=dt.timezone.utc)
        if now - mtime > dt.timedelta(days=max_age_days):
            continue
        date = tag_date(base, mtime)
        if date is None:
            continue
        out.append((date, d))
    out.sort()
    return out


def mark(dirs: list[str], now: dt.datetime) -> None:
    for d in dirs:
        with open(os.path.join(d, MARKER), "w", encoding="utf-8") as f:
            f.write(now.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--running", nargs="*", default=[], help="tags whose recorder is still up")
    ap.add_argument("--mark", nargs="*", default=None, help="write the marker into these dirs and exit")
    a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    if a.mark is not None:
        mark(a.mark, now)
        print(f"marked {len(a.mark)} tape(s) verdicted at {now:%H:%M:%S}Z")
        return 0
    for date, d in unverdicted(a.root, now, set(a.running)):
        print(f"{date} {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
