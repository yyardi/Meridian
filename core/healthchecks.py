"""The health checks themselves, importable by every reader.

Extracted from `scripts/health.py` (which keeps only the host-side checks —
docker ps, pmset — that cannot run inside a container) so that the alerter
container evaluates **the same rules** the operator sees at the terminal. Two
implementations of "is it healthy" would drift, and the copy that pages the
phone is the one that must not.

Every check returns OK, WARN or DEAD with the number behind it, so a green
line is never taken on trust.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
from dataclasses import dataclass

import httpx
from sqlalchemy import create_engine, text

UTC = dt.timezone.utc

OK, WARN, DEAD = "OK  ", "WARN", "DEAD"

#: The disk-free line under which the WARN fires. Local Postgres grows nightly
#: (2.3 GB on 2026-08-07) and retention is a known outstanding item — this
#: warns early enough to act from a phone, and deliberately does NOT trigger
#: any automatic deletion: tick data is unrecoverable, cleanup is a human call.
MIN_DISK_FREE_GB = 20.0

#: Percentage-used ceiling for the server volume. The AWS runbook promises this
#: alarm, and it is a different question from MIN_DISK_FREE_GB: 20 GB free is
#: comfortable on the laptop's 1 TB and nearly full on the server's 100 GB.
#: A ratio travels between machines; an absolute does not.
MAX_DISK_USED_PCT = 80.0



def local_url() -> str:
    """The local (tick) database. `localhost:5433` from the host; containers
    override with MERIDIAN_LOCAL_DATABASE_URL=...@postgres:5432/..."""
    return os.environ.get(
        "MERIDIAN_LOCAL_DATABASE_URL",
        "postgresql+psycopg://meridian:meridian@localhost:5433/meridian",
    )


@dataclass
class Check:
    status: str
    name: str
    detail: str

    def render(self) -> str:
        colour = {OK: "\033[32m", WARN: "\033[33m", DEAD: "\033[31m"}[self.status]
        return f"{colour}[{self.status}]\033[0m {self.name:<28} {self.detail}"


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


def primary_snapshot_verdict(
    snap_age: float | None,
    hb_age: float | None,
    hb_interval: float | None,
    *,
    game_live: bool,
) -> str:
    """The rule for the pregame snapshot line, heartbeat-first (B11).

    The old rule — DEAD when data is older than 45 minutes — was written when
    the recorder's slowest cadence was 15 minutes; its idle cadence is 60, so
    every quiet overnight hour tripped an urgent DEAD/Recovered pair (measured
    2026-08-08: eight false urgent pushes in one night). Alarm fatigue is the
    failure mode that kills monitoring, so data age alone can never say DEAD:

    * heartbeat stale or missing        -> DEAD (the process is gone — B11 rule)
    * game live and data > 45 min old   -> DEAD (should be on the 15-min leg,
                                          and stale pregame quotes feed picks)
    * heartbeat fresh, no game          -> OK, idle at its own cadence
    """
    from core import heartbeat as hb

    if hb.verdict(hb_age, hb_interval) == hb.DEAD:
        return DEAD
    if game_live and (snap_age or 0) > 2700:
        return DEAD
    return OK


def check_primary_db(game_live: bool = False) -> list[Check]:
    """The primary database — local Postgres since the 2026-08-17
    Supabase exit (one database, one source of truth)."""
    from core import heartbeat as hb
    from core.storage.base import get_engine

    checks: list[Check] = []
    try:
        engine = get_engine()
        with engine.connect() as c:
            snap = c.execute(text("select max(captured_at) from market_snapshots")).scalar()
            beat = c.execute(text(
                "select extract(epoch from now() - beat_at), interval_seconds "
                "from service_heartbeats where service = :s"
            ), {"s": hb.SERVICE_PREGAME}).one_or_none()
            pred_ts, pred_n = c.execute(text(
                "select max(created_at), count(*) from predictions "
                "where created_at > now() - interval '24 hours'"
            )).one()
    except Exception as exc:
        return [Check(DEAD, "primary db", f"unreachable: {str(exc)[:60]}")]

    snap_age = _age(snap)
    hb_age, hb_interval = (float(beat[0]), float(beat[1])) if beat else (None, None)
    status = primary_snapshot_verdict(snap_age, hb_age, hb_interval,
                                       game_live=game_live)
    hb_dead = hb.verdict(hb_age, hb_interval) == hb.DEAD
    detail = f"{_fmt_age(snap_age)} · heartbeat {_fmt_age(hb_age)}"
    if status != OK:
        detail += (" — recorder heartbeat stale, the process is gone" if hb_dead
                   else " — GAME IS LIVE and pregame data is stale")
    checks.append(Check(status, "primary snapshots", detail))

    pred_age = _age(pred_ts)
    # Predictions ride the 20-min fast leg. 90 min means the leg is not running.
    status = OK if (pred_age or 1e9) < 5400 else WARN
    checks.append(Check(status, "predictions", f"{_fmt_age(pred_age)} · {pred_n} in 24h"))

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
        engine = create_engine(local_url())
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
            # The interval is the SLEEP AFTER a cycle, not a period, so the
            # real sampling cadence is (cycle + interval) and it stretches
            # silently as a slate grows. This line used to print the
            # configured interval labelled "cycle", which is the misreading
            # itself; show the effective period, with its parts.
            if cycle_s is None:
                cadence = f"interval {interval:.0f}s"
            else:
                cadence = (f"every ~{float(cycle_s) + interval:.0f}s "
                           f"(cycle {float(cycle_s):.0f}s + sleep "
                           f"{interval:.0f}s)")
            checks.append(Check(OK, f"beat: {service}",
                                f"{_fmt_age(age)} · {cadence} · "
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


def check_fill_watcher() -> list[Check]:
    """The read-back loop for real orders (V17): accepted orders can be
    cancelled venue-side or fill without the `orders` table hearing about it,
    and pending exits only fire if the watcher is alive.

    Judged only when it has work: accepted-but-unreconciled orders or PENDING
    exits. A host with nothing to reconcile gets an informational line, not a
    verdict — the watcher deliberately only runs where ordering is enabled.
    """
    from core import heartbeat as hb
    from core.storage.base import get_engine

    try:
        with get_engine().connect() as c:
            open_orders = c.execute(text("""
                select count(*) from orders
                where accepted and venue_order_id is not null
                  and (fill_status is null
                       or fill_status not in ('FILLED','CANCELLED','EXPIRED'))
            """)).scalar()
            pending_exits, failed_exits = c.execute(text("""
                select count(*) filter (where state = 'PENDING'),
                       count(*) filter (where state = 'FAILED')
                from pending_exits
            """)).one()
            beat = c.execute(text(
                "select extract(epoch from now() - beat_at), interval_seconds "
                "from service_heartbeats where service = :s"
            ), {"s": hb.SERVICE_FILL_WATCHER}).one_or_none()
    except Exception as exc:
        return [Check(WARN, "fill watcher", f"could not verify: {str(exc)[:50]}")]

    checks: list[Check] = []
    # A FAILED exit means a position the human believes is protected is not.
    # That is DEAD regardless of anything else on this page.
    if failed_exits:
        checks.append(Check(DEAD, "attached exits",
                            f"{failed_exits} FAILED — a position the human believes "
                            "is protected is NOT. Act now."))

    needs_watcher = (open_orders or 0) > 0 or (pending_exits or 0) > 0
    if not needs_watcher:
        checks.append(Check(OK, "fill watcher",
                            "nothing to reconcile (no open orders, no pending exits)"))
        return checks

    age = float(beat[0]) if beat else None
    interval = float(beat[1]) if beat else None
    if hb.verdict(age, interval) == hb.DEAD:
        checks.append(Check(DEAD, "fill watcher",
                            f"{open_orders} open order(s) / {pending_exits} pending "
                            f"exit(s) and the watcher's last beat is {_fmt_age(age)} — "
                            "venue truth is diverging from the orders table"))
    else:
        checks.append(Check(OK, "fill watcher",
                            f"beat {_fmt_age(age)} · watching {open_orders} open "
                            f"order(s), {pending_exits} pending exit(s)"))
    return checks


def check_disk() -> list[Check]:
    """Free space on the disk holding the databases.

    Local Postgres grows nightly and retention is deliberately unbuilt — tick
    data is unrecoverable and cleanup is a human decision, so the job here is
    to raise the flag with weeks of runway, not to act. `MERIDIAN_DISK_PATH`
    lets the alerter container point this at a bind-mounted host directory,
    whose statvfs reports the host disk rather than the Docker VM's overlay.
    """
    path = os.environ.get("MERIDIAN_DISK_PATH", "/")
    try:
        total, _used, free = shutil.disk_usage(path)
    except Exception as exc:
        return [Check(WARN, "disk free", f"could not stat {path}: {str(exc)[:50]}")]
    free_gb = free / 1e9
    status = OK if free_gb >= MIN_DISK_FREE_GB else WARN
    return [Check(status, "disk free",
                  f"{free_gb:.0f} GB free of {total / 1e9:.0f} GB"
                  + ("" if status == OK else
                     f" — under {MIN_DISK_FREE_GB:.0f} GB; time to archive "
                     "(retention is the known outstanding item)"))]


def check_disk_headroom(path: str | None = None) -> list[Check]:
    """Disk as a PERCENTAGE, which is the number that travels between machines.

    `check_disk` warns below an absolute floor, and that floor was chosen for
    a laptop: 20 GB free is comfortable on 1 TB and nearly full on the server's
    100 GB volume. Both are reported, because "12% free" and "11 GB free" fail
    to alarm in opposite situations.

    A full disk stops postgres, which stops the recorder, mid-slate — and
    unrecorded ticks are the one loss this project cannot undo. Hence a
    ratio warning with room to act rather than a last-gigabyte one.
    """
    path = path or os.environ.get("MERIDIAN_DISK_PATH", "/")
    try:
        total, used, free = shutil.disk_usage(path)
    except Exception as exc:
        return [Check(WARN, "disk headroom", f"could not stat {path}: {str(exc)[:50]}")]
    pct = 100.0 * used / total if total else 0.0
    status = OK if pct < MAX_DISK_USED_PCT else WARN
    detail = (f"{pct:.0f}% used ({free / 1e9:.0f} GB free of {total / 1e9:.0f} GB)")
    if status != OK:
        detail += (f" — over {MAX_DISK_USED_PCT:.0f}%; a full disk stops postgres "
                   "and the recorder mid-slate")
    return [Check(status, "disk headroom", detail)]


def check_local_pg_size() -> list[Check]:
    """Informational: how big the tick database has grown. The alarm lives in
    `check_disk` — this line is what tells you *where* the space went."""
    try:
        engine = create_engine(local_url())
        with engine.connect() as c:
            size = c.execute(text(
                "select pg_database_size(current_database())"
            )).scalar()
    except Exception as exc:
        return [Check(WARN, "local pg size", f"could not query: {str(exc)[:50]}")]
    return [Check(OK, "local pg size", f"{(size or 0) / 1e9:.1f} GB (bounded by "
                                       "monthly archive-then-detach — see tick "
                                       "retention line)")]


def check_retention() -> list[Check]:
    """The tick archive's retention machinery (core/retention.py).

    Watches three things, all from the local database so host and container
    readers see the same truth: (1) rows stranded in a DEFAULT partition —
    safe, but it means a monthly partition is missing; (2) months past the
    keep window plus grace that are still attached — the archive job is
    overdue; (3) that the current month's partition exists ahead of tonight's
    writes. Not-yet-partitioned reads as one WARN, not an error storm: the
    conversion is an explicit operator step.
    """
    import datetime as _dt

    from core import retention as ret

    try:
        engine = create_engine(local_url())
        with engine.connect() as c:
            if not ret.is_partitioned(c, "market_snapshots"):
                return [Check(WARN, "tick retention",
                              "tables not partitioned — run "
                              "`python -m core.retention migrate --yes` "
                              "(between slates)")]
            now = _dt.datetime.now(UTC)
            checks: list[Check] = []
            overdue: list[str] = []
            default_rows = 0
            current_ok = True
            for parent in ret.PARENTS:
                parts = ret.attached_partitions(c, parent)
                months = [p.month for p in parts if p.month]
                cutoff = now - _dt.timedelta(days=ret.KEEP_DAYS + ret.GRACE_DAYS)
                overdue += [f"{parent}:{ret.month_label(m)}"
                            for m in months if ret.next_month(m) <= cutoff]
                if ret.month_start(now) not in months:
                    current_ok = False
                for p in parts:
                    if p.is_default:
                        default_rows += c.execute(text(
                            f"select count(*) from {p.name}")).scalar() or 0
            last = c.execute(text(
                "select max(verified_at) from retention_log"
            )).scalar()
    except Exception as exc:
        return [Check(WARN, "tick retention", f"could not check: {str(exc)[:60]}")]

    if overdue:
        checks.append(Check(WARN, "tick retention",
                            f"archive OVERDUE for {', '.join(overdue[:4])} — run "
                            "`python -m core.retention archive --yes`"))
    if not current_ok:
        checks.append(Check(WARN, "tick retention",
                            "current month partition MISSING — writes are going "
                            "to DEFAULT (safe); run `python -m core.retention ensure`"))
    if default_rows:
        checks.append(Check(WARN, "tick retention",
                            f"{default_rows} rows in DEFAULT partitions — a month "
                            "partition was missing when they arrived; nothing lost, "
                            "but they cannot be archived until redistributed"))
    if not checks:
        checks.append(Check(OK, "tick retention",
                            "partitioned · nothing overdue · last archive "
                            f"verify {_fmt_age(_age(last)) if last else 'never (none due yet)'}"))
    return checks


def primary_db_growth() -> dict | None:
    """Primary-DB size and estimated MB/day — for the digest. (The 500 MB
    cap language died with Supabase; growth is bounded by local retention
    and watched by the disk check.)

    Growth is estimated from each big table's last-24h row count times its
    current bytes-per-row, so no size history table is needed. `book_levels`
    counts through its parent snapshot because its own `captured_at` is NULL
    on the pregame path — the miss that hid a 20 MB/day writer on 2026-08-07.
    """
    from core.storage.base import get_engine

    per_table = {
        "market_snapshots": "captured_at", "predictions": "created_at",
        "kalshi_snapshots": "captured_at", "sportsbook_odds": "captured_at",
        "shadow_orders": "created_at",
    }
    try:
        with get_engine().connect() as c:
            total = c.execute(text(
                "select pg_database_size(current_database())")).scalar() or 0
            mb_day = 0.0
            for tbl, col in per_table.items():
                size, nrows, n24 = c.execute(text(f"""
                    select pg_total_relation_size('{tbl}'),
                           greatest((select reltuples::bigint from pg_class
                                     where relname = '{tbl}'), 1),
                           (select count(*) from {tbl}
                             where {col} > now() - interval '24 hours')
                """)).one()
                mb_day += (size / max(nrows, 1)) * (n24 or 0) / 1e6
            b_size, b_rows, b24 = c.execute(text("""
                select pg_total_relation_size('book_levels'),
                       greatest((select reltuples::bigint from pg_class
                                 where relname = 'book_levels'), 1),
                       (select count(*) from book_levels b
                          join market_snapshots s on s.id = b.snapshot_id
                         where s.captured_at > now() - interval '24 hours')
            """)).one()
            mb_day += (b_size / max(b_rows, 1)) * (b24 or 0) / 1e6
    except Exception as exc:
        log_note = str(exc)[:80]
        return {"error": log_note}
    return {
        "size_mb": round(total / 1e6, 1),
        "est_mb_per_day": round(mb_day, 1),
    }


def shared_checks(game_live: bool) -> list[Check]:
    """Everything that does not require the host shell — the set the alerter
    evaluates every 5 minutes, identical to the terminal view."""
    return (
        check_espn()
        + check_book_lines()
        + check_app_heartbeats()
        + check_primary_db(game_live)
        + check_local_ticks(game_live)
        + check_disk()
        + check_local_pg_size()
        + check_retention()
        + check_real_orders()
        + check_fill_watcher()
    )


def worst_of(checks: list[Check]) -> str:
    worst = OK
    for chk in checks:
        if chk.status == DEAD:
            return DEAD
        if chk.status == WARN:
            worst = WARN
    return worst
