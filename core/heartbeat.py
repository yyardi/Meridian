"""Per-cycle heartbeats: one upsert per cycle, one rule for calling a writer dead.

Why (B11, two games of unrecoverable data)
------------------------------------------
Every writer here has a schedule on which silence is legitimate — the live
recorder between games, the pregame recorder overnight — so no reader can
distinguish "idle at 3pm" from "dead for 23 hours" by looking at the data
tables. `/api/status` deliberately excluded the live recorder from its verdict
for exactly this reason, which is how a dead 200ms recorder stayed invisible
through two live games.

The fix is unconditional: every writer upserts one `service_heartbeats` row
every cycle, **game or no game**, into the same database it writes its data to.
Then:

* **DEAD** — heartbeat older than 3x the interval the writer itself reported,
  regardless of game state. Idle is only claimable with a fresh beat.
* **DEGRADED** — a live game, a fresh beat, and zero rows written. Alive and
  producing nothing is the B1 lesson (assert on outputs, not exit codes), and
  it is the state B11 sat in for 23 hours.

The 3x rule gets a floor (`MIN_STALE_SECONDS`): the live recorder's active
interval is 200ms, and declaring it dead 601ms after a beat would flap on any
GC pause or slow local write. The floor is far below every real outage and far
above every real hiccup.

Both readers — `scripts/health.py` and `/api/status` — call `verdict()` here,
so there is exactly one definition of dead.
"""

from __future__ import annotations

import time

import structlog
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.storage import ServiceHeartbeat

log = structlog.get_logger(__name__)

SERVICE_PREGAME = "pregame_recorder"
SERVICE_LIVE = "live_recorder"
SERVICE_LIVE_ODDS = "live_odds_recorder"
SERVICE_SCHEDULER = "scheduler"
SERVICE_KALSHI = "kalshi_recorder"
#: The fill watcher runs inside the API process, only when ordering is enabled
#: (token + credentials present). It is therefore judged by `/api/status` only
#: when that process could have started it — see `core.api._heartbeat_report` —
#: rather than being listed in APP_DB_SERVICES, where its absence would read
#: DEAD on every host that has never enabled ordering.
SERVICE_FILL_WATCHER = "fill_watcher"

#: The writers whose heartbeats live in the app database (Supabase in
#: production). The live recorder's lives in local Postgres, with its data.
APP_DB_SERVICES = (SERVICE_PREGAME, SERVICE_LIVE_ODDS, SERVICE_SCHEDULER, SERVICE_KALSHI)

DEAD = "dead"
DEGRADED = "degraded"
IDLE = "idle"
OK = "ok"

#: Floor under the 3x-interval staleness rule. See module docstring.
MIN_STALE_SECONDS = 30.0


def stale_after_seconds(interval_seconds: float) -> float:
    """How old a beat may be before the service is DEAD."""
    return max(3.0 * float(interval_seconds), MIN_STALE_SECONDS)


def verdict(
    age_seconds: float | None,
    interval_seconds: float | None,
    *,
    game_live: bool = False,
    rows_recent: int | None = None,
) -> str:
    """The rule, in one place.

    `age_seconds` of None means the service has never beaten — indistinguishable
    from dead, and treated as such on purpose: the cost asymmetry (a missed
    outage loses games permanently; a false alarm costs a glance) says round
    ambiguity toward DEAD.

    `rows_recent` is the reader's independent measure of output over its own
    window (e.g. ticks in the last 5 minutes), not the heartbeat's per-cycle
    count — a single 200ms cycle can legitimately land 0 rows on a write-batch
    boundary, and a rule that flaps is a rule that gets ignored. None means
    "not measured", which never triggers DEGRADED.
    """
    if age_seconds is None or interval_seconds is None:
        return DEAD
    if age_seconds > stale_after_seconds(interval_seconds):
        return DEAD
    if game_live and rows_recent == 0:
        return DEGRADED
    if not game_live and not rows_recent:
        return IDLE
    return OK


class Heartbeat:
    """One writer's beat. Never raises; a heartbeat that can kill its service
    would be worse than no heartbeat.

    Failures are logged at most once per `error_log_seconds`: the live recorder
    beats five times a second, and a database outage must not turn into an
    error-log firehose on top of itself.
    """

    def __init__(self, sessionmaker, service: str, *, error_log_seconds: float = 60.0):
        self._Session = sessionmaker
        self.service = service
        self._error_log_seconds = error_log_seconds
        self._last_error_log = float("-inf")
        self._rows_total: int | None = None

    def beat(
        self,
        *,
        interval_seconds: float,
        rows_written: int | None = None,
        cycle_seconds: float | None = None,
        game_live: bool | None = None,
        beat_at=None,
    ) -> bool:
        """Upsert this service's row. Returns False (and logs, throttled) on failure.

        `beat_at` defaults to the database's own `now()`; tests inject a past
        instant to simulate a stopped writer.
        """
        if rows_written is not None:
            self._rows_total = (self._rows_total or 0) + rows_written
        values = {
            "service": self.service,
            "beat_at": beat_at if beat_at is not None else func.now(),
            "interval_seconds": round(float(interval_seconds), 3),
            "cycle_seconds": (
                round(float(cycle_seconds), 3) if cycle_seconds is not None else None
            ),
            "rows_written": rows_written,
            "rows_total": self._rows_total,
            "game_live": game_live,
        }
        try:
            with self._Session() as session:
                session.execute(
                    pg_insert(ServiceHeartbeat)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=[ServiceHeartbeat.service],
                        set_={k: v for k, v in values.items() if k != "service"},
                    )
                )
                session.commit()
            return True
        except Exception as exc:
            now = time.monotonic()
            if now - self._last_error_log >= self._error_log_seconds:
                self._last_error_log = now
                log.error("heartbeat_write_failed", service=self.service, error=str(exc))
            return False
