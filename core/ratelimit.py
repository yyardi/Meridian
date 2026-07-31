"""Token-bucket rate limiter.

Polymarket US documents 20 requests/second per IP. The recorder runs at half
that. A token bucket (rather than a fixed sleep) allows a short burst at the
start of a cycle while still holding the long-run average under the ceiling.
"""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """Thread-safe token bucket.

    `acquire()` blocks until a token is available, so callers cannot exceed
    `rate` requests/second on average.
    """

    def __init__(self, rate: float, capacity: int | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self.rate = rate
        self.capacity = float(capacity if capacity is not None else max(1, int(rate)))
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        """Block until `tokens` are available. Returns seconds spent waiting."""
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return waited
                deficit = tokens - self._tokens
                sleep_for = deficit / self.rate
            time.sleep(sleep_for)
            waited += sleep_for
