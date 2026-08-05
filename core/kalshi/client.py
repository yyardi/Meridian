"""Read-only HTTP client for Kalshi's public market-data endpoints.

No auth, no keys, no signing — every endpoint here is unauthenticated GET on
the public trade API, and the class exposes ``get`` semantics only. An order
is not something this client is discouraged from placing; it is not
expressible, same principle as :class:`core.polymarket.client
.PolymarketAuthedClient`.

Rate limits: Kalshi's published scheme is token-based per authenticated
account (Basic: 200 read tokens/s at 10 tokens/request = 20 sustained req/s;
docs.kalshi.com/getting_started/rate_limits, read 2026-08-05). No number is
published for unauthenticated traffic, so we assume Basic applies at best and
run at a 5 req/s bucket — the recorder's real demand is ~3 requests per game
per minute. On 429 the docs promise no Retry-After header and prescribe
exponential backoff, which tenacity provides.
"""

from __future__ import annotations

from typing import Any, Iterator

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import KALSHI, KalshiConfig
from core.polymarket.client import RateLimitedError, TransientHTTPError
from core.ratelimit import TokenBucket

log = structlog.get_logger(__name__)


class KalshiPublicClient:
    def __init__(self, config: KalshiConfig | None = None) -> None:
        self.config = config or KALSHI
        self._bucket = TokenBucket(self.config.requests_per_second, self.config.burst_capacity)
        self._client = httpx.Client(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(self.config.http_timeout_seconds),
            headers={"User-Agent": "meridian-recorder/0.1 (+research)"},
            follow_redirects=True,
        )

    def __enter__(self) -> KalshiPublicClient:
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
                raise RateLimitedError(f"429 on {path}")
            if resp.status_code >= 500:
                raise TransientHTTPError(f"{resp.status_code} on {path}")
            resp.raise_for_status()
            return resp.json()

        return _do()

    def iter_events(
        self, series_ticker: str, *, status: str | None = "open", limit: int = 200
    ) -> Iterator[dict[str, Any]]:
        """Yield every event in a series, following the cursor to the end."""
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"series_ticker": series_ticker, "limit": limit}
            if status:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            page = self._get("/events", params=params)
            events = page.get("events") or []
            yield from events
            cursor = page.get("cursor") or None
            # An empty page means the cursor is exhausted even if non-empty —
            # trust the data, not the cursor, to terminate.
            if not cursor or not events:
                return

    def get_markets(self, event_ticker: str) -> list[dict[str, Any]]:
        """All contracts in one event, with top-of-book, last price, and rules.

        One request covers everything the snapshot and contract tables need —
        there is no per-market book call in this recorder.
        """
        raw = self._get("/markets", params={"event_ticker": event_ticker, "limit": 200})
        return raw.get("markets") or []
