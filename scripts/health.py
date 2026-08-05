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
        "meridian-kalshi-recorder": "Kalshi recorder (second venue)",
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
            db_bytes = c.execute(text(
                "select pg_database_size(current_database())"
            )).scalar()
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

    # Supabase's free plan enforces the *reported* database size at 500 MB and
    # returns 402 on every request past the grace period. 400 MB leaves room to
    # notice and act before the venue does. (DELETE alone does not shrink this
    # number — see the 2026-08-05 cleanup: VACUUM FULL is what returns space.)
    mb = (db_bytes or 0) / 1e6
    status = OK if mb < 400 else WARN
    checks.append(Check(status, "supabase size",
                        f"{mb:.0f} MB / 500 MB plan limit"
                        + ("" if mb < 400 else " — archive & VACUUM FULL soon")))
    return checks


def check_local_ticks(game_live: bool) -> list[Check]:
    """The database the 200ms recorder writes to. The dashboard cannot see it.

    Ruled by the heartbeat, not the data (B11): the recorder beats every cycle
    whether or not a game is on, so a stale beat means DEAD **regardless of
    game state** — "idle" is only claimable with a fresh beat. And a live game
    with a fresh beat but zero rows is DEGRADED, loudly: alive-and-writing-
    nothing is the exact state the old check read as healthy for 23 hours.
    """
    from core import heartbeat as hb

    try:
        engine = create_engine(LOCAL_URL)
        with engine.connect() as c:
            latest = c.execute(text("select max(captured_at) from market_snapshots")).scalar()
            recent = c.execute(text(
                "select count(*) from market_snapshots "
                "where captured_at > now() - interval '5 minutes'"
            )).scalar()
            beat = c.execute(text(
                "select extract(epoch from now() - beat_at), interval_seconds "
                "from service_heartbeats where service = :s"
            ), {"s": hb.SERVICE_LIVE}).one_or_none()
    except Exception as exc:
        return [Check(DEAD, "local ticks", f"unreachable: {str(exc)[:60]}")]

    beat_age, beat_interval = (float(beat[0]), float(beat[1])) if beat else (None, None)
    ruling = hb.verdict(beat_age, beat_interval,
                        game_live=game_live, rows_recent=recent)

    tick_age = _age(latest)
    if ruling == hb.DEAD:
        limit = hb.stale_after_seconds(beat_interval) if beat_interval else None
        detail = (
            f"no heartbeat for {_fmt_age(beat_age)} (limit {limit:.0f}s) — DEAD, "
            "idle is not claimable without a pulse"
            if beat_age is not None
            else "recorder has NEVER beaten — dead, or predates the heartbeat; "
                 "restart it (docker compose up -d --build live-recorder)"
        )
        return [Check(DEAD, "local ticks (200ms)", detail)]
    if ruling == hb.DEGRADED:
        return [Check(WARN, "local ticks (200ms)",
                      f"DEGRADED — GAME IS LIVE, heartbeat fresh "
                      f"({_fmt_age(beat_age)}), and ZERO rows in 5min. "
                      "Alive but writing nothing: the B11 failure, in progress.")]
    if game_live:
        return [Check(OK, "local ticks (200ms)",
                      f"{_fmt_age(tick_age)} · {recent} rows in 5min — GAME IS LIVE")]
    return [Check(OK, "local ticks (200ms)",
                  f"{_fmt_age(tick_age)} · idle, and provably so "
                  f"(heartbeat {_fmt_age(beat_age)})")]


def check_app_heartbeats() -> list[Check]:
    """Per-cycle beats for the writers on the app database (B11).

    One rule for all of them, from `core.heartbeat.verdict`: a beat older than
    3x the interval the service itself last reported means the process is not
    running, whatever its schedule says. A service with no row at all has
    either never run this code or is dead — treated as DEAD on purpose.
    """
    from core import heartbeat as hb
    from core.storage.base import get_engine

    try:
        with get_engine().connect() as c:
            rows = c.execute(text(
                "select service, extract(epoch from now() - beat_at), "
                "interval_seconds, rows_written, cycle_seconds "
                "from service_heartbeats"
            )).all()
    except Exception as exc:
        return [Check(DEAD, "heartbeats", f"query failed: {str(exc)[:60]}")]

    seen = {r[0]: r for r in rows}
    checks: list[Check] = []
    for service in hb.APP_DB_SERVICES:
        row = seen.get(service)
        if row is None:
            checks.append(Check(DEAD, f"beat: {service}",
                                "NEVER beaten — dead, or predates the heartbeat; "
                                "rebuild + restart the container"))
            continue
        _, age, interval, rows_written, cycle_s = row
        age, interval = float(age), float(interval)
        if hb.verdict(age, interval) == hb.DEAD:
            checks.append(Check(DEAD, f"beat: {service}",
                                f"last beat {_fmt_age(age)} — over 3x its "
                                f"{interval:.0f}s cycle. The process is not running."))
        else:
            wrote = "n/a" if rows_written is None else f"{rows_written} rows"
            checks.append(Check(OK, f"beat: {service}",
                                f"{_fmt_age(age)} · cycle {interval:.0f}s · "
                                f"{wrote} last cycle"))
    return checks


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
    """Both order counters, read from the `orders` table.

    `orders_autonomous` must read 0 forever. It is a **tripwire, not the
    defence** — the defence is the CHECK constraint
    `ck_orders_accepted_requires_human`, which makes an accepted non-human
    order unrepresentable. So this checks the constraint still exists too: a
    counter that reads 0 because the rows are impossible and one that reads 0
    because nobody has tried yet look identical, and only one of them is a
    guarantee.
    """
    from core.storage.base import get_engine

    checks: list[Check] = []
    try:
        with get_engine().connect() as c:
            human, autonomous, rejected = c.execute(text("""
                select
                  count(*) filter (where accepted and mode = 'HUMAN_CONFIRM'),
                  count(*) filter (where accepted and mode <> 'HUMAN_CONFIRM'),
                  count(*) filter (where not accepted)
                from orders
            """)).one()
            constraint = c.execute(text("""
                select count(*) from pg_constraint
                where conname = 'ck_orders_accepted_requires_human'
            """)).scalar()
    except Exception as exc:
        return [Check(WARN, "order counters", f"could not verify: {str(exc)[:50]}")]

    checks.append(Check(
        OK, "orders (human-confirmed)",
        f"{human} placed · {rejected} rejected/attempted",
    ))
    checks.append(Check(
        OK if not autonomous else DEAD, "orders (autonomous)",
        f"{autonomous} (must be 0)",
    ))
    checks.append(Check(
        OK if constraint else DEAD, "  ^ enforced by",
        "CHECK ck_orders_accepted_requires_human"
        if constraint else "CONSTRAINT MISSING — the 0 above guarantees nothing",
    ))
    return checks


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
        ("Host", check_sleep_guard()),
        ("Containers", check_containers()),
        ("Data feeds", check_espn() + check_book_lines()),
        ("Heartbeats", check_app_heartbeats()),
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
