# structlog

**Role:** structured logging. The recorder's only window into itself.

## Why it matters more than usual here

The recorder runs unattended for months. Its **dominant failure mode is silent death** — it stops at 2am, nobody notices for two weeks, and that data is gone permanently.

Logs are the only evidence of what happened. They need to be queryable, not prose.

## Structured, not formatted

```python
log.info("cycle_complete", markets_seen=97, snapshots=97,
         market_errors=0, duration_s=9.02)
```

Emits:

```json
{"event": "cycle_complete", "markets_seen": 97, "snapshots": 97,
 "market_errors": 0, "duration_s": 9.02, "level": "info",
 "timestamp": "2026-07-31T21:37:20.431635Z"}
```

Versus a formatted string, this lets you ask real questions:

```bash
jq 'select(.event=="cycle_complete" and .market_errors > 0)' recorder.log
jq 'select(.duration_s > 30)' recorder.log     # is it slowing down?
```

Grepping prose for "error" finds some of them. Querying fields finds all of them.

## Two renderers, one config

```python
structlog.dev.ConsoleRenderer()   # local: coloured, human-readable
structlog.processors.JSONRenderer()  # production: machine-parseable
```

Selected with `--json-logs`. Same call sites, different output — no separate logging paths to drift apart.

## What we log

| Event | Fields | Why |
|---|---|---|
| `cycle_complete` | counts, duration | the heartbeat — absence means death |
| `market_record_failed` | slug, error, traceback | which market, and why |
| `book_fetch_failed` | slug, error | depth missing but snapshot kept |
| `board_fetch_failed` | error | the one unrecoverable failure |
| `sleeping` | seconds | confirms cadence logic |
| `rate_limit_wait` | seconds | are we near the ceiling? |

`cycle_complete` is the important one: a monitor watching for its absence catches a dead recorder. See [../infra/hosting.md](../infra/hosting.md).

## Quieting httpx

httpx logs every request at INFO. At ~150 requests/cycle that buries the cycle summary:

```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```

Logs nobody reads because they're too noisy are equivalent to no logs.

## Never log secrets

`POLYMARKET_SECRET_KEY` must never reach a log line. Logs get shipped, stored, and shared far more casually than credentials should be.
