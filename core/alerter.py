"""Phone alerts: the health checks, evaluated every 5 minutes, pushed via ntfy.

The operator is away for two weeks. Every failure mode this project has
actually had — dead recorder, ESPN 403, pooler rewrite, full disk risk — was
caught by a human happening to look. This process is the looking.

Design rules, each earned:

* **Same checks as the terminal.** It evaluates `core.healthchecks.shared_checks`
  — the exact set `scripts/health.py` prints — so the phone and the terminal
  cannot disagree about what "healthy" means.
* **Transitions, not states.** A push fires when a check *becomes* DEAD, when
  a WARN has *persisted* 30 minutes, or when a new pending exit *enters*
  FAILED. A check that stays DEAD does not re-push every 5 minutes: an alarm
  that spams is an alarm that gets muted, which is worse than no alarm.
  Recoveries push once too — going quiet after a DEAD push is itself ambiguous.
* **Two WARNs push immediately** rather than after 30 minutes: disk under
  20 GB and Supabase over 400 MB. Both are slow burns where the useful action
  window is measured in days, and both end in data loss if missed.
* **The 9:00 CT digest ALWAYS sends, green or not.** It is the alerter's own
  heartbeat: a missing digest means the alerter is dead, so silence is never
  ambiguous — B11's lesson applied to the alarm itself. (It also beats
  `service_heartbeats` every cycle so the terminal and /api/status see it,
  but the digest is the proof a phone can check from a beach.)

ntfy.sh: topic from MERIDIAN_NTFY_TOPIC (treat it like a password — anyone who
knows it can read the alerts), server override via MERIDIAN_NTFY_SERVER.

    python -m core.alerter            # run forever (the container entrypoint)
    python -m core.alerter --once     # one evaluation, one push decision pass
    python -m core.alerter --test     # send a test push and exit
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from zoneinfo import ZoneInfo

import httpx
import structlog
from sqlalchemy import text

from core import heartbeat as hb
from core.healthchecks import (
    DEAD,
    OK,
    WARN,
    Check,
    local_url,
    shared_checks,
    todays_games,
    worst_of,
)
from core.storage import get_engine, get_sessionmaker

log = structlog.get_logger(__name__)

UTC = dt.timezone.utc
CENTRAL = ZoneInfo("America/Chicago")

CYCLE_SECONDS = 300.0
#: A WARN that persists this long is a condition, not a blip.
WARN_PERSIST_SECONDS = 30 * 60
#: These WARNs push on arrival — slow burns that end in data loss if missed.
IMMEDIATE_WARN_CHECKS = {"disk free", "supabase size"}
DIGEST_HOUR_CT = 9


class Notifier:
    """One ntfy topic. Failures are logged and swallowed — the alerter must
    keep evaluating even when the push channel is down, and the missed digest
    is what tells the operator the channel broke."""

    def __init__(self, topic: str, server: str | None = None):
        self.topic = topic
        self.server = (server or os.environ.get("MERIDIAN_NTFY_SERVER")
                       or "https://ntfy.sh").rstrip("/")
        self.pushes_sent = 0
        self.push_failures = 0

    #: ntfy's numeric priorities. Strings in headers would also work, but this
    #: module uses the JSON publish endpoint throughout — see `push`.
    _PRIORITY = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}

    def payload(self, title: str, body: str, priority: str, tags: str) -> dict:
        return {
            "topic": self.topic,
            "title": title,
            "message": body,
            "priority": self._PRIORITY.get(priority, 3),
            "tags": [t for t in tags.split(",") if t],
        }

    def push(self, title: str, body: str, *, priority: str = "default",
             tags: str = "") -> bool:
        # JSON publish (POST to the server root), NOT the header style: HTTP
        # headers are ascii-only, and the first real digest title carried an
        # em dash — the push failed on encoding while the code marked the
        # digest sent. JSON bodies are UTF-8 and immune to that class of bug.
        try:
            r = httpx.post(
                self.server,
                json=self.payload(title, body, priority, tags),
                timeout=20,
            )
            r.raise_for_status()
            self.pushes_sent += 1
            log.info("push_sent", title=title, priority=priority)
            return True
        except Exception as exc:
            self.push_failures += 1
            log.error("push_failed", title=title, error=str(exc))
            return False


class Alerter:
    def __init__(
        self,
        notifier: Notifier,
        *,
        cycle_seconds: float = CYCLE_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self._notify = notifier
        self.cycle_seconds = cycle_seconds
        self._clock = clock
        #: name -> (status, since_monotonic, warn_pushed)
        self._state: dict[str, tuple[str, float, bool]] = {}
        self._known_failed_exits: set[int] = set()
        self._first_cycle = True
        self._last_digest_date: dt.date | None = None
        self._heartbeat = hb.Heartbeat(
            get_sessionmaker(get_engine()), hb.SERVICE_ALERTER
        )

    # ---- transition logic (pure against injected clock; unit-tested) ------ #

    def process(self, checks: list[Check]) -> list[tuple[str, str, str, str]]:
        """Decide pushes from one evaluation. Returns (title, body, priority, tags).

        The first cycle establishes a baseline instead of "transitioning" every
        check from nothing — otherwise every restart would replay the full
        board as alerts. Anything already broken at startup is reported by the
        startup push, which the caller sends separately.
        """
        now = self._clock()
        pushes: list[tuple[str, str, str, str]] = []

        for chk in checks:
            prev = self._state.get(chk.name)
            prev_status = prev[0] if prev else None

            if prev is None or prev_status != chk.status:
                self._state[chk.name] = (chk.status, now, False)
                if self._first_cycle:
                    continue
                if chk.status == DEAD:
                    pushes.append((f"DEAD: {chk.name}", chk.detail, "urgent", "skull"))
                elif chk.status == WARN and chk.name in IMMEDIATE_WARN_CHECKS:
                    pushes.append((f"WARN: {chk.name}", chk.detail, "high", "warning"))
                elif prev_status == DEAD:
                    pushes.append((f"Recovered: {chk.name}", chk.detail,
                                   "default", "white_check_mark"))
                continue

            # Status unchanged. The one time-based rule: a WARN that has sat
            # for 30 minutes is a condition, not a blip. Pushed once.
            status, since, warn_pushed = prev
            if (status == WARN and not warn_pushed
                    and chk.name not in IMMEDIATE_WARN_CHECKS
                    and now - since >= WARN_PERSIST_SECONDS):
                self._state[chk.name] = (status, since, True)
                pushes.append((f"WARN 30min+: {chk.name}", chk.detail,
                               "high", "warning"))

        self._first_cycle = False
        return pushes

    def new_failed_exits(self) -> list[tuple[int, str]]:
        """Pending exits that entered FAILED since last look. A FAILED exit is
        a position the human believes is protected and is not — it pushes per
        row, not per state, so a second failure never hides behind the first."""
        try:
            with get_engine().connect() as c:
                rows = c.execute(text(
                    "select id, coalesce(error, 'no error recorded') "
                    "from pending_exits where state = 'FAILED'"
                )).all()
        except Exception as exc:
            log.error("failed_exit_query_failed", error=str(exc))
            return []
        fresh = [(int(i), e) for i, e in rows if int(i) not in self._known_failed_exits]
        self._known_failed_exits.update(i for i, _ in fresh)
        return fresh

    # ---- the digest -------------------------------------------------------- #

    def digest_due(self, now_utc: dt.datetime) -> bool:
        """9:00 America/Chicago, once per CT day. If the alerter was down at
        9:00 it sends on the next cycle after coming back — a late digest beats
        a missing one, because a missing one means 'the alerter is dead'."""
        now_ct = now_utc.astimezone(CENTRAL)
        return now_ct.hour >= DIGEST_HOUR_CT and self._last_digest_date != now_ct.date()

    def build_digest(self, checks: list[Check]) -> str:
        lines = [f"Verdict: {worst_of(checks).strip()}"]

        bad = [c for c in checks if c.status != OK]
        for c in bad:
            lines.append(f"[{c.status.strip()}] {c.name}: {c.detail}")
        if not bad:
            lines.append("All checks green.")

        lines.append("")
        lines.extend(self._digest_heartbeats())
        lines.extend(self._digest_data())
        lines.extend(self._digest_retention())
        return "\n".join(lines)

    def _digest_retention(self) -> list[str]:
        """Archive receipts from the last 3 days — approval condition on the
        rolling job: every run's receipt appears in the digest."""
        out: list[str] = []
        try:
            with get_engine().connect() as c:
                rows = c.execute(text(
                    "select partition_name, rows_archived, dropped_at is not null "
                    "from retention_log where created_at > now() - interval '3 days' "
                    "order by id"
                )).all()
        except Exception as exc:
            return [f"Retention receipts: query failed ({str(exc)[:60]})"]
        if rows:
            out.append("Retention receipts (3d):")
            for name, n, dropped in rows:
                out.append(f"  {name}: {n} rows archived"
                           + (" + deleted" if dropped else " (dump only)"))
        return out

    def _digest_heartbeats(self) -> list[str]:
        out = ["Heartbeats:"]
        try:
            with get_engine().connect() as c:
                rows = c.execute(text(
                    "select service, extract(epoch from now() - beat_at) "
                    "from service_heartbeats order by service"
                )).all()
            from sqlalchemy import create_engine
            with create_engine(local_url()).connect() as c:
                rows += c.execute(text(
                    "select service, extract(epoch from now() - beat_at) "
                    "from service_heartbeats where service = :s"
                ), {"s": hb.SERVICE_LIVE}).all()
        except Exception as exc:
            return [f"Heartbeats: query failed ({str(exc)[:60]})"]
        for service, age in rows:
            out.append(f"  {service}: {_fmt_secs(float(age))}")
        return out

    def _digest_data(self) -> list[str]:
        out: list[str] = []
        try:
            from core.healthchecks import supabase_growth

            g = supabase_growth()
            if g and "error" not in g:
                cap = ("n/a" if g["days_to_cap"] is None
                       else f"{g['days_to_cap']:.1f} days")
                out.append(f"Supabase: {g['size_mb']:.0f} MB · "
                           f"~{g['est_mb_per_day']:.0f} MB/day · "
                           f"cap (500 MB) in {cap}")
            else:
                out.append(f"Supabase growth: could not estimate "
                           f"({(g or {}).get('error', 'no data')})")
        except Exception as exc:
            out.append(f"Supabase growth: {str(exc)[:60]}")
        try:
            from sqlalchemy import create_engine
            with create_engine(local_url()).connect() as c:
                games = c.execute(text(
                    "select count(distinct event_slug) from market_snapshots "
                    "where book_tier is not null "
                    "and captured_at > now() - interval '24 hours'"
                )).scalar()
            out.append(f"Games with live ticks, last 24h: {games}")
        except Exception as exc:
            out.append(f"Tick count failed: {str(exc)[:60]}")

        try:
            from core.kalshi.analysis import gate_status
            with get_sessionmaker(get_engine())() as s:
                gate = gate_status(s)
            out.append(
                f"Kalshi gate: {gate['matched_games']}/{gate['required']} matched games"
                + (" — GATE MET" if gate["gate_met"] else "")
            )
        except Exception as exc:
            out.append(f"Kalshi gate query failed: {str(exc)[:60]}")

        try:
            with get_engine().connect() as c:
                human, rejected = c.execute(text(
                    "select count(*) filter (where accepted), "
                    "count(*) filter (where not accepted) from orders"
                )).one()
                exits = dict(c.execute(text(
                    "select state, count(*) from pending_exits group by state"
                )).all())
            out.append(f"Orders: {human} accepted · {rejected} rejected")
            out.append("Exits: " + (", ".join(
                f"{k} {v}" for k, v in sorted(exits.items())) or "none"))
        except Exception as exc:
            out.append(f"Order counts failed: {str(exc)[:60]}")
        return out

    # ---- the loop ---------------------------------------------------------- #

    def run_cycle(self) -> None:
        _games, live = todays_games()
        checks = shared_checks(live)

        if self._first_cycle:
            # Startup doubles as the reboot notification: a Mac that comes back
            # up restarts this container, and this push is how the operator
            # learns the reboot happened at all.
            body = self.build_digest(checks)
            sent = self._notify.push(
                "Meridian alerter online (startup or reboot)",
                body, priority="default", tags="arrows_counterclockwise",
            )
            # The startup push carries the full digest; if today's 9:00 CT has
            # already passed, that counts as today's digest rather than sending
            # the same content twice a minute apart. Only if it actually SENT —
            # a failed push must leave the digest owed.
            if sent and self.digest_due(dt.datetime.now(UTC)):
                self._last_digest_date = dt.datetime.now(UTC).astimezone(CENTRAL).date()

        for title, body, priority, tags in self.process(checks):
            self._notify.push(title, body, priority=priority, tags=tags)

        for exit_id, error in self.new_failed_exits():
            self._notify.push(
                f"EXIT FAILED: pending_exit #{exit_id}",
                f"A position the human believes is protected is NOT.\n{error}",
                priority="urgent", tags="rotating_light",
            )

        now = dt.datetime.now(UTC)
        if self.digest_due(now):
            verdict = worst_of(checks)
            sent = self._notify.push(
                f"Meridian daily digest — {verdict.strip()}",
                self.build_digest(checks),
                priority="default" if verdict == OK else "high",
                tags="newspaper",
            )
            # Only a DELIVERED digest counts. Marking a failed one sent would
            # silently void the always-sends guarantee — which is exactly what
            # happened on 2026-08-07 when the em-dash title broke the header
            # encoding. A failed digest retries next cycle, every cycle, until
            # one lands.
            if sent:
                self._last_digest_date = now.astimezone(CENTRAL).date()

        self._heartbeat.beat(interval_seconds=self.cycle_seconds)

    def run_forever(self) -> None:
        log.info("alerter_started", cycle_seconds=self.cycle_seconds,
                 topic=self._notify.topic, server=self._notify.server)
        while True:
            started = time.monotonic()
            try:
                self.run_cycle()
            except Exception as exc:
                # Same rule as every recorder: nothing kills the loop.
                log.error("alerter_cycle_failed", error=str(exc), exc_info=True)
            time.sleep(max(5.0, self.cycle_seconds - (time.monotonic() - started)))


def _fmt_secs(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s ago"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m ago"
    return f"{seconds / 3600:.1f}h ago"


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-alerter")
    parser.add_argument("--once", action="store_true",
                        help="one evaluation + push pass, then exit")
    parser.add_argument("--test", action="store_true",
                        help="send a test push and exit")
    args = parser.parse_args()

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

    topic = (os.environ.get("MERIDIAN_NTFY_TOPIC") or "").strip()
    if not topic:
        # Fail fast and loudly. An alerter running without a channel is worse
        # than none: it *looks* covered. The container will restart-loop, which
        # `docker compose ps` and health.py both surface.
        print("MERIDIAN_NTFY_TOPIC is not set — the alerter has no phone to "
              "push to. Set it in .env and subscribe to the topic in the ntfy "
              "app.", file=sys.stderr)
        return 2

    notifier = Notifier(topic)
    if args.test:
        ok = notifier.push("Meridian test push",
                           "If you can read this, alerts reach your phone.",
                           tags="bell")
        return 0 if ok else 1

    alerter = Alerter(notifier)
    if args.once:
        alerter.run_cycle()
        return 0
    alerter.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
