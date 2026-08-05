#!/usr/bin/env python
"""Measure authenticated read latency against Polymarket US. **Read-only.**

    .venv/bin/python scripts/probe_authed_read.py

This exists to fill the gap in `docs/math/write-latency.md`: every latency
number in that doc is for *seeing* the market, and before this the
authenticated read path had never returned anything but 401.

What it does and does not do
----------------------------
It sends Ed25519-signed **GET** requests and times them. It places, modifies
and cancels **nothing** — `PolymarketAuthedClient` has no verb but `get`, so
there is no code path from this script to an order. The "$0 has ever been
traded" invariant is untouched, as are `ExecutionMode` and the kill switch.

The scheme, which is not the one in the CLOB docs
-------------------------------------------------
Polymarket US uses three headers, Ed25519, and **millisecond** timestamps:

    X-PM-Access-Key · X-PM-Timestamp · X-PM-Signature
    signature = base64(Ed25519_sign(timestamp + METHOD + path))

Not the five POLY_* headers with HMAC-SHA256 from
docs.polymarket.com/developers/CLOB — that is the international CLOB, a
different venue. See `docs/findings.md` V9.

Reading a failure
-----------------
`Missing required API key headers` means the header *names* are wrong, not the
signature — the venue returns it for every path and every signature, including
requests carrying all five correct POLY_* headers. The error strings are the
useful signal and they discriminate cleanly:

    Missing required API key headers  -> wrong header family
    API key timestamp expired         -> seconds instead of milliseconds, or skew
    Invalid API key signature         -> wrong algorithm, key, or message
    404 with a JSON body              -> authenticated; the route is just wrong
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys

import httpx
import structlog

from core.polymarket.client import (
    US_HEADERS,
    AuthedResponse,
    MissingCredentialsError,
    PolymarketAuthedClient,
    USCredentials,
    verify_key_material,
)
from core.ratelimit import TokenBucket

#: Non-mutating reads. None of these can change account state.
#:
#: `/v1/portfolio` and `/v1/balance` — the paths `write-latency.md` recorded as
#: 401 — do not exist. They return 404 *once authenticated*, which is how we
#: learned the 401s had never been about them. The real paths are below.
PROBE_PATHS = (
    "/v1/account/balances",
    "/v1/portfolio/positions",
    "/v1/portfolio/activities",
)

OK, WARN, DEAD = "OK  ", "WARN", "DEAD"
_COLOUR = {OK: "\033[32m", WARN: "\033[33m", DEAD: "\033[31m"}
_RESET = "\033[0m"


def _tag(status: str) -> str:
    return f"{_COLOUR[status]}[{status}]{_RESET}"


def _rule(char: str = "=") -> str:
    return char * 72


def describe(result: AuthedResponse) -> str:
    server = (
        f" · venue {result.server_latency_ms:.0f}ms"
        if result.server_latency_ms is not None
        else ""
    )
    status = OK if result.status_code == 200 else DEAD
    return (
        f"{_tag(status)} GET {result.path:<28} {result.status_code} "
        f"in {result.elapsed_ms:.0f}ms{server}"
    )


def dump_exchange(result: AuthedResponse, base_url: str) -> None:
    """The exact request and response, credentials redacted. Printed on any
    non-200, because at that point the instruction is to report, not guess."""
    print(f"\n{_rule('-')}")
    print("EXACT REQUEST  (credential values redacted, lengths preserved)")
    print(f"{_rule('-')}")
    print(f"  GET {base_url}{result.path}")
    for name in US_HEADERS:
        print(f"  {name}: {result.request_headers.get(name, '<ABSENT>')}")
    print(f'\n  signed message = X-PM-Timestamp + "GET" + "{result.path}"')
    print("  signature      = base64(Ed25519_sign(seed=b64decode(secret)[:32], message))")

    print(f"\n{_rule('-')}")
    print("EXACT RESPONSE")
    print(f"{_rule('-')}")
    print(f"  HTTP {result.status_code}   ({result.elapsed_ms:.0f}ms)")
    for key in ("content-type", "server", "cf-ray", "x-pm-trace-id", "x-pm-server-latency"):
        if key in result.response_headers:
            print(f"  {key}: {result.response_headers[key]}")
    print(f"\n  body: {result.body_text.strip()[:600] or '<empty>'}")


def measure(
    client: PolymarketAuthedClient, path: str, repeats: int, bucket: TokenBucket
) -> tuple[list[float], list[float], int]:
    """Warm round-trips on a kept-alive connection.

    Returns (round_trip_ms, venue_ms, throttled_count). The connection is
    already warm because the discovery probe ran first, so no sample pays
    DNS/TCP/TLS — `write-latency.md` reports warm and cold separately, and
    mixing them is how a p90 becomes a handshake.

    Every request signs a fresh timestamp; signatures are single-use within a
    30-second window.

    A 429 is dropped from the sample rather than recorded. It is a real
    response but it is not a *read* — timing it would measure the rate
    limiter, not the backend. The count is returned so the caller can say so
    out loud instead of silently reporting a thinner sample.
    """
    round_trip: list[float] = []
    venue: list[float] = []
    throttled = 0

    for _ in range(repeats):
        bucket.acquire()
        try:
            result = client.get(path)
        except httpx.HTTPError:
            break
        if result.status_code == 429:
            throttled += 1
            continue
        if result.status_code != 200:
            break
        round_trip.append(result.elapsed_ms)
        if result.server_latency_ms is not None:
            venue.append(result.server_latency_ms)
    return round_trip, venue, throttled


def _p90(ordered: list[float]) -> float:
    return ordered[max(0, int(len(ordered) * 0.9) - 1)]


def report(path: str, round_trip: list[float], venue: list[float], throttled: int) -> None:
    rt = sorted(round_trip)
    line = (
        f"  {path:<28} n={len(rt):<3} "
        f"median {statistics.median(rt):5.0f}ms · p90 {_p90(rt):5.0f}ms · "
        f"min {rt[0]:5.0f}ms"
    )
    if venue:
        v = sorted(venue)
        line += f"   | venue median {statistics.median(v):3.0f}ms"
    if throttled:
        line += f"   ({throttled} × 429 dropped)"
    print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only authenticated latency probe")
    parser.add_argument("--repeats", type=int, default=15,
                        help="warm samples per path (default 15)")
    parser.add_argument("--base-url", default=None,
                        help="override the authenticated host")
    parser.add_argument("--rps", type=float, default=2.0,
                        help="request pacing (default 2.0 — the authenticated host "
                             "throttles far below the gateway's 20/s)")
    parser.add_argument("--verbose", action="store_true",
                        help="show the per-request structlog line")
    args = parser.parse_args()

    if not args.verbose:
        # One line per request buries a 15-sample table. The measurement is the
        # output here, not the log.
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)
        )

    print("\n\033[1mPOLYMARKET US — AUTHENTICATED READ PROBE\033[0m")
    print("read-only: GET requests only, no order placed, modified or cancelled")
    print(_rule())

    try:
        creds = USCredentials.from_env()
    except MissingCredentialsError as exc:
        print(f"\n{_tag(DEAD)} {exc}\n")
        return 2

    fp = creds.fingerprint()
    print("\n\033[1mCredentials\033[0m  (fingerprints only — no value printed or logged)")
    print(f"  key id  {fp['key_id_len']} chars")
    print(f"  secret  {fp['secret_len']} chars · sha256:{fp['secret_sha256_8']}")

    # Local structural check before spending a request: re-derive the public key
    # from the seed and compare it to the copy in bytes 32..63. A truncated or
    # mis-decoded secret fails here instead of arriving as an opaque 401.
    if not verify_key_material(creds.secret):
        print(f"  {_tag(DEAD)} not an intact 64-byte Ed25519 key "
              "(seed does not derive the embedded public key)")
        return 2
    print(f"  {_tag(OK)} Ed25519 key material intact "
          "(seed re-derives the embedded public key)")

    bucket = TokenBucket(args.rps, max(1, int(args.rps)))

    with PolymarketAuthedClient(creds, base_url=args.base_url) as client:
        print(f"\n\033[1mProbe\033[0m  {client.base_url}  (paced at {args.rps}/s)")
        results = []
        for path in PROBE_PATHS:
            bucket.acquire()
            try:
                result = client.get(path)
            except httpx.HTTPError as exc:
                print(f"  {_tag(DEAD)} GET {path:<28} transport error: {exc}")
                continue
            print("  " + describe(result))
            results.append(result)

        authenticated = [r for r in results if r.status_code == 200]
        if not authenticated:
            for result in results:
                dump_exchange(result, client.base_url)
            print(f"\n{_rule()}")
            print("Verdict: \033[31mNOT AUTHENTICATED\033[0m — reported above rather "
                  "than retried\nwith another convention. See the error-string guide "
                  "in this file's docstring.\n")
            return 1

        print(f"\n\033[1mAuthenticated read latency\033[0m  "
              f"(warm, keep-alive, n={args.repeats} per path)")
        all_rt: list[float] = []
        for result in authenticated:
            round_trip, venue, throttled = measure(
                client, result.path, args.repeats, bucket
            )
            if not round_trip:
                print(f"  {_tag(WARN)} {result.path}: no clean sample "
                      f"({throttled} × 429)")
                continue
            report(result.path, round_trip, venue, throttled)
            all_rt.extend(round_trip)

        print(f"\n{_rule()}")
        if all_rt:
            ordered = sorted(all_rt)
            print(f"Authenticated read, all paths pooled: "
                  f"\033[1mmedian {statistics.median(ordered):.0f}ms · "
                  f"p90 {_p90(ordered):.0f}ms\033[0m  (n={len(ordered)})")
        print("\nVerdict: \033[32mAUTHENTICATED\033[0m — record the median in "
              "docs/math/write-latency.md.\nThis is a *read*. Venue-side *order* "
              "processing remains unmeasured and\nstill requires placing an order.\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
