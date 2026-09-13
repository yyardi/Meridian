"""The paper book, read from disk for the SCOREBOARD page.

The producer is ``cfb/run_paper_book.py``: every registered shadow strategy,
one P&L line per week, priced at the last quote before kickoff and settled
from the venue's own settlement endpoint. It prints two fixed-width text
tables — per strategy x week, then ALL WEEKS with a verdict — and places
nothing. A cron on the prod box leaves that output under
``$MERIDIAN_READS_DIR`` as ``paper_book*.txt``; this module finds the newest
such file and turns the two tables into JSON for ``/api/paper-book``.

This is a reader, not a re-computation. Every number the page shows is the
producer's own, the interval is carried verbatim beside its parsed parts, and
a line whose shape the parser does not recognise is returned under
``unparsed`` rather than dropped — a format drift in the producer must show
on the page, not silently thin the table.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

#: Where the prod box's cron leaves its reads (scripts/prod_weekend_read.sh
#: writes the same directory). ``MERIDIAN_READS_DIR`` overrides; the api
#: container sees this path only if compose mounts it there.
DEFAULT_READS_DIR = "/opt/meridian/artifacts/reads"

#: The producer's output files, by name. The newest by mtime is served.
PAPER_BOOK_GLOB = "paper_book*.txt"

#: The one line the page carries above the tables. The last clause is the point.
LEGEND = ("paper P&L per $1 bet, venue-settled, taker fee charged; "
          "POSITIVE excludes 0 at G>=25 is a candidate, nothing is armed")

WEEKLY_COLUMNS = ["strategy", "week", "bets", "games", "unsettled",
                  "staked", "pnl", "net_per_dollar", "ci"]
ALL_WEEKS_COLUMNS = ["strategy", "bets", "games", "staked", "pnl",
                     "net_per_dollar", "ci", "verdict"]

# The producer's formats: ``{x:>+9.2f}`` for money and
# ``'%+.2f [%+.2f, %+.2f]'`` for the interval. A one-game week has an infinite
# half-width (G=1 in its clustered()), printed as ``[-inf, +inf]``, so the
# number class must admit inf/nan. Those become null in JSON — Starlette
# refuses NaN/Infinity — while the verbatim ``ci`` string keeps what was printed.
_SIGNED = r"[+-](?:\d+\.\d+|inf|nan)"
_CI = (rf"(?P<ci>(?P<ci_mean>{_SIGNED}) "
       rf"\[(?P<ci_lo>{_SIGNED}), (?P<ci_hi>{_SIGNED})\])")
_STRATEGY = r"^(?P<strategy>\S+)\s+"
_WEEK = r"(?P<week>\d{4}-\d{2}-\d{2})\s+"

_WEEK_FULL = re.compile(
    _STRATEGY + _WEEK
    + r"(?P<bets>\d+)\s+(?P<games>\d+)\s+(?P<unsettled>\d+)\s+(?P<staked>\d+)\s+"
    + rf"(?P<pnl>{_SIGNED})\s+(?P<net_per_dollar>{_SIGNED})\s+{_CI}"
    + r"(?P<underpowered>\s+G<25)?\s*$")
#: A week whose markets are all unsettled: the producer prints counts and stops.
_WEEK_UNSETTLED = re.compile(
    _STRATEGY + _WEEK + r"(?P<bets>\d+)\s+(?P<games>\d+)\s+(?P<unsettled>\d+)\s*$")
_WEEK_NO_MARKETS = re.compile(_STRATEGY + r"-\s+0\s+(?P<note>no markets on tape)\s*$")
_ALL_ROW = re.compile(
    _STRATEGY
    + rf"(?P<bets>\d+)\s+(?P<games>\d+)\s+(?P<staked>\d+)\s+(?P<pnl>{_SIGNED})\s+"
    + rf"(?P<net_per_dollar>{_SIGNED})\s+{_CI}\s+(?P<verdict>\S.*?)\s*$")

_WEEKLY_HEADER = re.compile(r"^strategy\s+week\s+bets\b")
_ALL_HEADER = re.compile(r"^strategy, ALL WEEKS\s+bets\b")
_FOOTER_START = "P&L is per"


def reads_dir() -> Path:
    """Read per call, not at import — containers set the environment late."""
    override = (os.environ.get("MERIDIAN_READS_DIR") or "").strip()
    return Path(override) if override else Path(DEFAULT_READS_DIR)


def latest_paper_book(directory: Path | None = None) -> Path | None:
    """The newest ``paper_book*.txt`` by modification time; None when absent."""
    d = reads_dir() if directory is None else directory
    if not d.is_dir():
        return None
    files = [p for p in d.glob(PAPER_BOOK_GLOB) if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: (p.stat().st_mtime, p.name))


def verdict_kind(verdict: str) -> str:
    """The producer's four verdict strings, as a class the page can colour."""
    if verdict.startswith("POSITIVE"):
        return "positive"
    if verdict.startswith("NEGATIVE"):
        return "negative"
    if verdict.startswith("UNDERPOWERED"):
        return "underpowered"
    if verdict.startswith("spans"):
        return "spans"
    return "unknown"


def league_of(strategy: str) -> str:
    """The producer keys every strategy ``<league>_...`` in its STRATEGIES
    table; the prefix is the league the page's tab filters on."""
    return strategy.split("_", 1)[0]


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    v = float(s)
    return v if math.isfinite(v) else None


def _weekly_row(line: str) -> dict | None:
    m = _WEEK_FULL.match(line) or _WEEK_UNSETTLED.match(line) or _WEEK_NO_MARKETS.match(line)
    if m is None:
        return None
    g = m.groupdict()
    if "note" in g:            # the no-markets shape: a name and a note, nothing else
        return _week(g["strategy"], week=None, bets=0, games=None, unsettled=None,
                     note=g["note"])
    row = _week(g["strategy"], week=g["week"], bets=int(g["bets"]),
                games=int(g["games"]), unsettled=int(g["unsettled"]),
                note=None if "staked" in g else "unsettled only")
    if "staked" in g:
        row.update(staked=int(g["staked"]), pnl=_num(g["pnl"]),
                   net_per_dollar=_num(g["net_per_dollar"]), ci=g["ci"],
                   ci_mean=_num(g["ci_mean"]), ci_lo=_num(g["ci_lo"]),
                   ci_hi=_num(g["ci_hi"]), underpowered=bool(g["underpowered"]))
    return row


def _week(strategy, *, week, bets, games, unsettled, note) -> dict:
    return {"strategy": strategy, "league": league_of(strategy), "week": week,
            "bets": bets, "games": games, "unsettled": unsettled,
            "staked": None, "pnl": None, "net_per_dollar": None, "ci": None,
            "ci_mean": None, "ci_lo": None, "ci_hi": None,
            "underpowered": False, "note": note}


def _all_weeks_row(line: str) -> dict | None:
    m = _ALL_ROW.match(line)
    if m is None:
        return None
    g = m.groupdict()
    return {"strategy": g["strategy"], "league": league_of(g["strategy"]),
            "bets": int(g["bets"]), "games": int(g["games"]),
            "staked": int(g["staked"]), "pnl": _num(g["pnl"]),
            "net_per_dollar": _num(g["net_per_dollar"]), "ci": g["ci"],
            "ci_mean": _num(g["ci_mean"]), "ci_lo": _num(g["ci_lo"]),
            "ci_hi": _num(g["ci_hi"]), "verdict": g["verdict"],
            "verdict_kind": verdict_kind(g["verdict"])}


def parse_paper_book(text: str) -> dict:
    """The producer's stdout, as ``preamble`` (the coverage lines before the
    first table), ``weekly`` and ``all_weeks`` (``{columns, rows}``),
    ``footer`` (the producer's closing prose — distinct from `LEGEND`, the
    page's own line) and ``unparsed`` (table-section lines of no known shape,
    kept so the page can show them)."""
    preamble: list[str] = []
    footer: list[str] = []
    unparsed: list[str] = []
    weekly: list[dict] = []
    all_weeks: list[dict] = []
    section = "preamble"
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if _WEEKLY_HEADER.match(line):
            section = "weekly"
            continue
        if _ALL_HEADER.match(line):
            section = "all_weeks"
            continue
        if line.startswith(_FOOTER_START):
            section = "footer"
        if section == "preamble":
            preamble.append(line)
        elif section == "footer":
            footer.append(line)
        else:
            row = _weekly_row(line) if section == "weekly" else _all_weeks_row(line)
            if row is None:
                unparsed.append(line)
            elif section == "weekly":
                weekly.append(row)
            else:
                all_weeks.append(row)
    return {
        "preamble": preamble,
        "weekly": {"columns": WEEKLY_COLUMNS, "rows": weekly},
        "all_weeks": {"columns": ALL_WEEKS_COLUMNS, "rows": all_weeks},
        "footer": footer,
        "unparsed": unparsed,
    }
