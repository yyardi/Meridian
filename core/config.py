"""Runtime configuration for the shared core.

Everything is env-overridable so the same image runs locally and in
production with only environment differences.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RecorderConfig:
    """Polymarket US recorder settings."""

    # Public gateway. NOT api.polymarket.us (authenticated) and emphatically
    # NOT clob.polymarket.com (Polymarket International — wrong platform).
    gateway_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "POLYMARKET_GATEWAY_URL", "https://gateway.polymarket.us"
        )
    )
    league_slug: str = field(default_factory=lambda: os.environ.get("MERIDIAN_LEAGUE", "wnba"))
    event_limit: int = field(default_factory=lambda: _env_int("MERIDIAN_EVENT_LIMIT", 50))

    # Documented ceiling is 20 req/s per IP; we run at half that. The recorder
    # is a long-lived background job with no latency requirement, so there is
    # no upside to crowding the limit.
    requests_per_second: float = field(
        default_factory=lambda: _env_float("MERIDIAN_RPS", 10.0)
    )
    burst_capacity: int = field(default_factory=lambda: _env_int("MERIDIAN_BURST", 10))

    http_timeout_seconds: float = field(
        default_factory=lambda: _env_float("MERIDIAN_HTTP_TIMEOUT", 20.0)
    )
    max_retries: int = field(default_factory=lambda: _env_int("MERIDIAN_MAX_RETRIES", 3))

    # Adaptive cadence.
    near_tipoff_hours: float = field(
        default_factory=lambda: _env_float("MERIDIAN_NEAR_TIPOFF_HOURS", 6.0)
    )
    interval_near_tipoff_seconds: int = field(
        default_factory=lambda: _env_int("MERIDIAN_INTERVAL_NEAR", 15 * 60)
    )
    interval_idle_seconds: int = field(
        default_factory=lambda: _env_int("MERIDIAN_INTERVAL_IDLE", 60 * 60)
    )

    capture_depth: bool = field(default_factory=lambda: _env_bool("MERIDIAN_CAPTURE_DEPTH", True))
    max_book_levels: int = field(default_factory=lambda: _env_int("MERIDIAN_MAX_BOOK_LEVELS", 50))


@dataclass(frozen=True)
class ESPNConfig:
    """ESPN feed settings.

    ESPN's API is undocumented and publishes no rate limits. We stay
    deliberately slow (a few requests/second) and send a descriptive
    User-Agent: this is a free public source and the polite thing to do is
    also the thing least likely to get us blocked.
    """

    site_base_url: str = field(
        default_factory=lambda: os.environ.get("ESPN_SITE_URL", "https://site.api.espn.com")
    )
    core_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "ESPN_CORE_URL", "https://sports.core.api.espn.com"
        )
    )
    league_path: str = field(
        default_factory=lambda: os.environ.get("ESPN_LEAGUE_PATH", "basketball/wnba")
    )
    requests_per_second: float = field(default_factory=lambda: _env_float("ESPN_RPS", 3.0))
    burst_capacity: int = field(default_factory=lambda: _env_int("ESPN_BURST", 3))
    http_timeout_seconds: float = field(default_factory=lambda: _env_float("ESPN_TIMEOUT", 30.0))
    max_retries: int = field(default_factory=lambda: _env_int("ESPN_MAX_RETRIES", 3))
    #: Empty means "send httpx's own default", which is what works.
    #:
    #: ESPN began 403ing on 2026-08-04, and the rule is the opposite of the usual
    #: one: it rejects User-Agents that look *custom or browser-like* and accepts
    #: library defaults. Measured, deterministic over repeats:
    #:
    #:     python-httpx/0.28.1                       -> 200
    #:     (no User-Agent header at all)             -> 200
    #:     Mozilla/5.0 ... Chrome/120.0 Safari/537.36 -> 403   <- the old default
    #:     Meridian/1.0 (WNBA research; contact ...)  -> 403
    #:
    #: So the honest UA and the spoofed one both fail, and the fix is to stop
    #: setting the header. Override with ESPN_USER_AGENT if ESPN changes the rule
    #: again — this is an undocumented API with no stability guarantee.
    user_agent: str = field(
        default_factory=lambda: os.environ.get("ESPN_USER_AGENT", "")
    )


# ESPN season types. Load-bearing: preseason must never reach the database,
# and postseason drives playoff down-weighting of the record feature.
SEASON_TYPE_PRESEASON = 1
SEASON_TYPE_REGULAR = 2
SEASON_TYPE_POSTSEASON = 3


RECORDER = RecorderConfig()
ESPN = ESPNConfig()
