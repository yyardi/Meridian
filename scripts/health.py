#!/usr/bin/env python
"""One command that answers "is everything actually working right now?"

Run it before every game night:

    .venv/bin/python scripts/health.py

Why this exists: the dashboard reads Supabase only, and the 200ms tick recorder
writes locally. On 2026-08-03 that recorder was dead for 23 hours while the
dashboard looked perfectly healthy, and two games of unrecoverable tick data
were lost. Anything that reports on one database cannot see the other.

The checks themselves live in `core/healthchecks.py`, because the alerter
container evaluates the same set every 5 minutes and pushes to the phone —
two definitions of "healthy" would drift, and the one that pages must not.
This script adds only what a container cannot see: docker ps and pmset.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys

from core.healthchecks import (
    DEAD,
    OK,
    WARN,
    Check,
    check_app_heartbeats,
    check_book_lines,
    check_disk,
    check_espn,
    check_fill_watcher,
    check_local_pg_size,
    check_local_ticks,
    check_real_orders,
    check_retention,
    check_supabase,
    todays_games,
)

UTC = dt.timezone.utc


def check_containers() -> list[Check]:
    expected = {
        "meridian-recorder": "pregame recorder (feeds the dashboard)",
        "meridian-live-recorder": "200ms tick recorder (PULSE)",
        "meridian-live-odds-recorder": "live odds",
        "meridian-kalshi-recorder": "Kalshi recorder (second venue)",
        "meridian-scheduler": "scheduler (predictions)",
        "meridian-api": "dashboard + order path + fill watcher",
        "meridian-alerter": "phone alerts (ntfy)",
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


def check_sleep_guard() -> list[Check]:
    """A sleeping Mac is a hole in an unrecoverable stream.

    Checks the assertions actually held by the OS rather than whether a
    `caffeinate` process exists — a caffeinate started without flags only
    prevents idle sleep, and would look identical in `ps`.
    """
    try:
        out = subprocess.run(
            ["pmset", "-g", "assertions"],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout
    except Exception as exc:
        return [Check(WARN, "sleep guard", f"could not query pmset: {exc}")]

    def held(name: str) -> bool:
        for line in out.splitlines():
            if name in line and line.strip().split()[-1] != "0":
                return True
        return False

    idle = held("PreventUserIdleSystemSleep")
    if not idle:
        return [Check(WARN, "sleep guard", "NOT running — see step 1 (caffeinate -dims)")]

    on_battery = "Battery Power" in subprocess.run(
        ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=15, check=False,
    ).stdout
    if on_battery:
        # -s is documented as valid only on AC power.
        return [Check(WARN, "sleep guard", "held, but ON BATTERY — plug in before tipoff")]
    return [Check(OK, "sleep guard", "caffeinate active, on AC power")]


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
        ("Host", check_sleep_guard() + check_disk()),
        ("Containers", check_containers()),
        ("Data feeds", check_espn() + check_book_lines()),
        ("Heartbeats", check_app_heartbeats()),
        ("Databases", check_supabase(live) + check_local_ticks(live)
                      + check_local_pg_size() + check_retention()),
        ("Safety", check_real_orders() + check_fill_watcher()),
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
