#!/usr/bin/env python
"""One command that answers "is everything actually working right now?"

Run it before every game night:

    .venv/bin/python scripts/health.py

Why this exists: the dashboard reads Supabase only, and the 200ms tick recorder
writes locally. On 2026-08-03 that recorder was dead for 23 hours while the
dashboard looked perfectly healthy, and two games of unrecoverable tick data
were lost. Anything that reports on one database cannot see the other.

Every check prints OK, WARN or DEAD with the number behind it, so a green line
is never taken on trust.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from dataclasses import dataclass

import httpx
from sqlalchemy import create_engine, text

UTC = dt.timezone.utc

LOCAL_URL = "postgresql+psycopg://meridian:meridian@localhost:5433/meridian"

OK, WARN, DEAD = "OK  ", "WARN", "DEAD"
_COLOUR = {OK: "\033[32m", WARN: "\033[33m", DEAD: "\033[31m"}
_RESET = "\033[0m"


@dataclass
class Check:
    status: str
    name: str
    detail: str

    def render(self) -> str:
        tag = f"{_COLOUR[self.status]}[{self.status}]{_RESET}"
        return f"{tag} {self.name:<28} {self.detail}"


def _age(ts: dt.datetime | None) -> float | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (dt.datetime.now(UTC) - ts).total_seconds()


def _fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "never"
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m ago"
    return f"{seconds / 3600:.1f}h ago"


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #


def check_containers() -> list[Check]:
    expected = {
        "meridian-recorder": "pregame recorder (feeds the dashboard)",
        "meridian-live-recorder": "200ms tick recorder (PULSE)",
        "meridian-live-odds-recorder": "live odds",
        "meridian-scheduler": "scheduler (predictions)",
        "meridian-postgres": "local Postgres",
    }
    try:
        out = subprocess.run(
            ["docker", "compose", "ps", "--format", "{{.Name}} {{.Status}}"],
            capture_output=True, text=True, timeout=30, check=False,
        ).stdout
    except Exception as exc:                                   # pragma: no cover
        return [Check(DEAD, "docker", f"could not query: {exc}")]

    running = {
        line.split(maxsplit=1)[0]: line.split(maxsplit=1)[1]
        for line in out.strip().splitlines() if line.strip()
    }
    checks = []
    for name, what in expected.items():
        status_text = running.get(name)
        if status_text is None:
            checks.append(Check(DEAD, name.replace("meridian-", ""), f"NOT RUNNING — {what}"))
        elif not status_text.startswith("Up"):
            checks.append(Check(DEAD, name.replace("meridian-", ""), status_text))
        else:
            checks.append(Check(OK, name.replace("meridian-", ""), f"{status_text} — {what}"))
    return checks


def check_supabase() -> list[Check]:
    """The database the dashboard reads."""
    from core.storage.base import get_engine

    checks: list[Check] = []
    try:
        engine = get_engine()
        with engine.connect() as c:
            snap = c.execute(text("select max(captured_at) from market_snapshots")).scalar()
            pred_ts, pred_n = c.execute(text(
                "select max(created_at), count(*) from predictions "
                "where created_at > now() - interval '24 hours'"
            )).one()
    except Exception as exc:
        return [Check(DEAD, "supabase", f"unreachable: {str(exc)[:60]}")]

    snap_age = _age(snap)
    # The pregame recorder runs every ~15 min; 45 is three missed cycles.
    status = OK if (snap_age or 1e9) < 2700 else DEAD
    checks.append(Check(status, "supabase snapshots", _fmt_age(snap_age)))

    pred_age = _age(pred_ts)
    # Predictions ride the 20-min fast leg. 90 min means the leg is not running.
    status = OK if (pred_age or 1e9) < 5400 else WARN
    checks.append(Check(status, "predictions", f"{_fmt_age(pred_age)} · {pred_n} in 24h"))
    return checks


def check_local_ticks(game_live: bool) -> list[Check]:
    """The database the 200ms recorder writes to. The dashboard cannot see it."""
    try:
        engine = create_engine(LOCAL_URL)
        with engine.connect() as c:
            latest = c.execute(text("select max(captured_at) from market_snapshots")).scalar()
            recent = c.execute(text(
                "select count(*) from market_snapshots "
                "where captured_at > now() - interval '5 minutes'"
            )).scalar()
    except Exception as exc:
        return [Check(DEAD, "local ticks", f"unreachable: {str(exc)[:60]}")]

    age = _age(latest)
    if game_live:
        # During a game this recorder should be writing constantly. Silence here
        # is the failure that cost two games of data.
        status = OK if (age or 1e9) < 120 else DEAD
        detail = f"{_fmt_age(age)} · {recent} rows in 5min — GAME IS LIVE"
    else:
        status = OK
        detail = f"{_fmt_age(age)} · idle (no game in progress — expected)"
    return [Check(status, "local ticks (200ms)", detail)]


def check_espn() -> list[Check]:
    """ESPN 403s custom User-Agents. This is the canary for that."""
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    try:
        r = httpx.get(url, timeout=20)
    except Exception as exc:
        return [Check(DEAD, "espn", f"unreachable: {str(exc)[:60]}")]
    if r.status_code != 200:
        return [Check(DEAD, "espn", f"HTTP {r.status_code} — check ESPN_USER_AGENT")]
    events = r.json().get("events", [])
    return [Check(OK, "espn", f"HTTP 200 · {len(events)} game(s) today")]


def todays_games() -> tuple[list[str], bool]:
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
    try:
        events = httpx.get(url, timeout=20).json().get("events", [])
    except Exception:
        return [], False
    lines, live = [], False
    for ev in events:
        state = ev["status"]["type"]
        if state["state"] == "in":
            live = True
        lines.append(f"  {ev['shortName']:<16} {ev['date']}  {state['name']}")
    return lines, live


def check_book_lines() -> list[Check]:
    """Without a book line the model has no anchor and nothing is actionable."""
    from core.storage.base import get_engine

    try:
        with get_engine().connect() as c:
            ts, n = c.execute(text(
                "select max(captured_at), count(*) from sportsbook_odds "
                "where captured_at > now() - interval '2 hours'"
            )).one()
    except Exception as exc:
        return [Check(DEAD, "book lines", f"query failed: {str(exc)[:60]}")]
    age = _age(ts)
    status = OK if (age or 1e9) < 3600 else WARN
    return [Check(status, "book lines (anchor)", f"{_fmt_age(age)} · {n} rows in 2h")]


def check_real_orders() -> list[Check]:
    """The number that must stay 0 until the gates pass."""
    from core.storage.base import get_engine

    try:
        with get_engine().connect() as c:
            n = c.execute(text(
                "select count(*) from shadow_orders where mode is distinct from 'SHADOW'"
            )).scalar()
    except Exception:
        return [Check(WARN, "autonomous orders", "could not verify")]
    return [Check(OK if not n else DEAD, "autonomous orders", f"{n} (must be 0)")]


def main() -> int:
    games, live = todays_games()

    stamp = dt.datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"\n\033[1mMERIDIAN HEALTH\033[0m  {stamp}")
    print("=" * 72)

    print("\n\033[1mToday's games\033[0m")
    print("\n".join(games) if games else "  none scheduled")
    if live:
        print("  \033[33m>> A GAME IS LIVE — the tick recorder must be writing.\033[0m")

    groups: list[tuple[str, list[Check]]] = [
        ("Containers", check_containers()),
        ("Data feeds", check_espn() + check_book_lines()),
        ("Databases", check_supabase() + check_local_ticks(live)),
        ("Safety", check_real_orders()),
    ]

    worst = OK
    for title, checks in groups:
        print(f"\n\033[1m{title}\033[0m")
        for chk in checks:
            print("  " + chk.render())
            if chk.status == DEAD:
                worst = DEAD
            elif chk.status == WARN and worst == OK:
                worst = WARN

    print("\n" + "=" * 72)
    verdict = {OK: "\033[32mALL GOOD\033[0m",
               WARN: "\033[33mDEGRADED — read the WARN lines\033[0m",
               DEAD: "\033[31mSOMETHING IS DOWN — read the DEAD lines\033[0m"}[worst]
    print(f"Verdict: {verdict}\n")
    return 0 if worst != DEAD else 1


if __name__ == "__main__":
    sys.exit(main())
