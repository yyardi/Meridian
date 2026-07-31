# httpx + tenacity + token bucket

**Roles:** httpx makes HTTP requests, tenacity retries them, the token bucket keeps us under rate limits.

## httpx

Chosen over `requests` for real timeouts, connection pooling, and a sync/async API that's identical if we ever need async.

```python
httpx.Client(
    base_url="https://gateway.polymarket.us",
    timeout=httpx.Timeout(20.0),
    headers={"User-Agent": "meridian-recorder/0.1 (+research)"},
)
```

**Always set an explicit timeout.** A request with no timeout can hang forever, and a recorder blocked on a dead socket looks identical to a recorder that's working — it just silently stops collecting.

### Synchronous by choice

A full WNBA slate is ~150 requests; at 10 req/s that's ~9 seconds per cycle, measured. The cycle runs every 15 minutes.

Async would make it ~2 seconds and add concurrency bugs to a process whose single most important property is surviving unattended for months. Not a good trade.

## Rate limiting: token bucket

Polymarket US documents **20 requests/second per IP**. We run at **10** — half the ceiling, because there's no upside to crowding it.

```python
class TokenBucket:
    def acquire(self, tokens=1.0) -> float:
        """Block until tokens are available. Returns seconds waited."""
```

A token bucket allows a short burst then settles to the average rate. Compared to a fixed `sleep(0.1)` between calls, it handles variable response times correctly — slow responses effectively refill the bucket, so you don't serialise unnecessarily.

Measured: 98 requests in 9.02s ≈ 10.9 req/s, comfortably under 20.

## tenacity

Declarative retries instead of hand-rolled loops:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((RateLimitedError, TransientHTTPError)),
    reraise=True,
)
```

Matches what the Polymarket docs ask for on 429: stop, wait ≥1s, exponential backoff, max 3 retries.

### Retry only what's retryable

```python
class RateLimitedError(Exception):   # 429 — back off
class TransientHTTPError(Exception): # 5xx / network — retry
```

A 404 is **not** retried — the market doesn't exist and won't start existing. Retrying deterministic failures wastes the rate-limit budget and delays real work.

### One documented trap

Rejections reading `Global Rate Limit Exceeded` during high-latency windows are **transient latency rejects, not real rate limiting.** The docs are explicit that you should not throttle in response. Treating them as rate limits would make the recorder progressively slower during exactly the busy periods when data matters most.

## Failure isolation

Retries handle transient failures. Everything else is caught at the narrowest useful scope:

- **Book fetch fails** → log, keep the top-of-book snapshot, continue
- **One market fails** → log, roll back that market, continue with the other 149
- **Board fetch fails** → log, return empty, let the loop retry next cycle

The ordering principle: never lose the whole cycle for one bad row. See [../infra/architecture.md](../infra/architecture.md).
