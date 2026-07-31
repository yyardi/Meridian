"""HTTP client for the Polymarket US public gateway.

Public data only — no API key, no signing. The authenticated host
(`api.polymarket.us`) is not touched here.

Design notes
------------
*Synchronous by choice.* A full WNBA slate is ~150 requests; at 10 req/s that
is ~15 seconds per cycle, which is irrelevant for a job that runs every 15
minutes. Async would be faster and strictly more failure modes for a process
whose primary requirement is surviving unattended for months.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import RECORDER, RecorderConfig
from core.polymarket.schemas import BookResponse, EventsResponse
from core.ratelimit import TokenBucket

log = structlog.get_logger(__name__)


class RateLimitedError(Exception):
    """HTTP 429 — a genuine rate limit, worth backing off for."""


class TransientHTTPError(Exception):
    """5xx or network error — retryable."""


class PolymarketGatewayClient:
    def __init__(self, config: RecorderConfig | None = None) -> None:
        self.config = config or RECORDER
        self._bucket = TokenBucket(self.config.requests_per_second, self.config.burst_capacity)
        self._client = httpx.Client(
            base_url=self.config.gateway_base_url,
            timeout=httpx.Timeout(self.config.http_timeout_seconds),
            headers={"User-Agent": "meridian-recorder/0.1 (+research)"},
            follow_redirects=True,
        )

    def __enter__(self) -> PolymarketGatewayClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((RateLimitedError, TransientHTTPError)),
            reraise=True,
        )
        def _do() -> dict[str, Any]:
            waited = self._bucket.acquire()
            if waited > 0.5:
                log.debug("rate_limit_wait", seconds=round(waited, 2), path=path)
            try:
                resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise TransientHTTPError(str(exc)) from exc

            if resp.status_code == 429:
                # Docs: stop, wait >= 1s, exponential backoff, max 3 retries.
                raise RateLimitedError(f"429 on {path}")
            if resp.status_code >= 500:
                raise TransientHTTPError(f"{resp.status_code} on {path}")
            resp.raise_for_status()
            return resp.json()

        return _do()

    def get_league_events(self, league: str | None = None, limit: int | None = None) -> tuple[
        EventsResponse, dict[str, Any]
    ]:
        """Fetch the whole league board in one request.

        Returns (parsed, raw_json) so the raw payload can be persisted verbatim —
        reparsing stored JSON later beats re-fetching data that no longer exists.
        """
        league = league or self.config.league_slug
        limit = limit or self.config.event_limit
        raw = self._get(f"/v2/leagues/{league}/events", params={"limit": limit})
        return EventsResponse.model_validate(raw), raw

    def get_book(self, market_slug: str) -> tuple[BookResponse, dict[str, Any]]:
        raw = self._get(f"/v1/markets/{market_slug}/book")
        return BookResponse.model_validate(raw), raw

    def get_settlement(self, market_slug: str) -> dict[str, Any]:
        """Free, unauthenticated resolution label: {"slug": ..., "settlement": 0|1}."""
        return self._get(f"/v1/markets/{market_slug}/settlement")
