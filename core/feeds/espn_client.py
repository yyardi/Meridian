"""Shared HTTP client for ESPN's undocumented public APIs.

Two hosts, different jobs:

* ``site.api.espn.com``       — scoreboards, team schedules
* ``sports.core.api.espn.com`` — deeper reference data, including *historical*
  odds (the scoreboard strips odds from past games)

ESPN publishes no rate limits and offers no stability guarantee. We treat it as
untrusted input: slow request rate, validate at the boundary, and never let one
bad payload take down a batch.

We send **no User-Agent override**. ESPN 403s custom and browser-like agents and
serves library defaults — see `ESPNConfig.user_agent` for the measurements. The
docstring here previously claimed a "descriptive User-Agent" while the code sent
a spoofed Chrome string; both are now false and neither would work.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import ESPN, ESPNConfig
from core.ratelimit import TokenBucket

log = structlog.get_logger(__name__)


class ESPNTransientError(Exception):
    """5xx or network failure — retryable."""


class ESPNNotFound(Exception):
    """404 — the resource does not exist. Never retried."""


class ESPNClient:
    def __init__(self, config: ESPNConfig | None = None) -> None:
        self.config = config or ESPN
        self._bucket = TokenBucket(self.config.requests_per_second, self.config.burst_capacity)
        # An empty user_agent means "leave httpx's own default alone" — ESPN 403s
        # custom and browser-like agents but serves library defaults. See
        # ESPNConfig.user_agent for the measurements.
        headers = {"User-Agent": self.config.user_agent} if self.config.user_agent else {}
        self._client = httpx.Client(
            timeout=httpx.Timeout(self.config.http_timeout_seconds),
            headers=headers,
            follow_redirects=True,
        )

    def __enter__(self) -> ESPNClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(ESPNTransientError),
            reraise=True,
        )
        def _do() -> dict[str, Any]:
            self._bucket.acquire()
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                raise ESPNTransientError(str(exc)) from exc

            if resp.status_code == 404:
                # Deterministic: retrying wastes budget and delays real work.
                raise ESPNNotFound(url)
            if resp.status_code >= 500 or resp.status_code == 429:
                raise ESPNTransientError(f"{resp.status_code} on {url}")
            resp.raise_for_status()
            return resp.json()

        return _do()

    # ---------------------------------------------------------------- #
    # site.api.espn.com
    # ---------------------------------------------------------------- #

    def _site(self, path: str) -> str:
        return f"{self.config.site_base_url}/apis/site/v2/sports/{self.config.league_path}/{path}"

    def get_teams(self) -> dict[str, Any]:
        return self.get(self._site("teams"))

    def get_team_schedule(self, team_id: str, season: int) -> dict[str, Any]:
        """A whole season of games for one team, in a single request.

        Note this includes preseason, regular season AND postseason — callers
        must filter on seasonType.
        """
        return self.get(self._site(f"teams/{team_id}/schedule"), params={"season": season})

    def get_scoreboard(self, date_yyyymmdd: str) -> dict[str, Any]:
        return self.get(self._site("scoreboard"), params={"dates": date_yyyymmdd})

    # ---------------------------------------------------------------- #
    # sports.core.api.espn.com
    # ---------------------------------------------------------------- #

    def get_event_odds(self, event_id: str) -> dict[str, Any]:
        """Historical odds for one event.

        The event id appears twice in the path — as both event and
        competition. That is ESPN's shape, not a typo.
        """
        # NOTE: the core API path differs from the site API path — it inserts
        # "leagues/". site: sports/basketball/wnba
        #             core: sports/basketball/leagues/wnba
        # Using the site form here returns 404 and silently yields no odds.
        sport, _, league = self.config.league_path.partition("/")
        url = (
            f"{self.config.core_base_url}/v2/sports/{sport}/leagues/{league}"
            f"/events/{event_id}/competitions/{event_id}/odds"
        )
        return self.get(url)
