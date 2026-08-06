# How fast can we act? (Not: how fast can we see?)

**Partly measured, and the measurable part is the one that dominates.** The
venue's own order-processing time is unmeasured and cannot be measured without
placing an order.

Gates **QUOTE**: a 3¢ spread is not capturable if a stale quote sits exposed.

## Why this is the question

Adverse selection is decided by cancel speed, not poll speed. Your resting bid
is filled precisely when someone wants to sell, so the only defence is pulling
the quote before the market runs through it. Everything measured so far is
about how fast we can *see* the market. This is about how fast we can *act*.

Exposure decomposes into three terms:

$$
T_{\text{exposed}} = \underbrace{T_{\text{detect}}}_{\text{our poll loop}} + \underbrace{T_{\text{decide}}}_{\text{negligible}} + \underbrace{T_{\text{cancel}}}_{\text{network} + \text{venue}}
$$

## What is measured

**Detection — ours, and it dominates.** The price loop polls every 200ms and a
board call takes 158ms median (226ms p90). A quote change is therefore observed
somewhere between 158ms and ~430ms after it happens, averaging ~260ms.

**Network floor to the authenticated host** — measured with GET requests only,
no order placed:

| | |
|---|---|
| DNS | 2ms |
| TCP connect | 13ms |
| TLS handshake | 28ms |
| **Cold connect total** | **41ms** |
| **Warm round-trip, keep-alive** | **36ms median, 45ms p90** |

For comparison the public gateway warm RTT is 21ms. Both hosts resolve to the
same Cloudflare IP (`172.64.149.216`), so they are the same edge — the auth
host is not further away, it just does more.

## The finding that matters

**Our own polling loop is roughly 7× the network cost of cancelling.**

```
detect   ~260ms average   (200ms interval + 158ms board latency)
cancel     36ms network   + unknown venue processing
```

Even if venue-side processing were a generous 100ms, detection is still the
larger term by a factor of ~2. **The bottleneck in reacting to a quote going
stale is us, not the venue** — which is the opposite of the usual assumption
and is the reason the price loop went from 1s to 200ms
([live-cadence.md](../infra/live-cadence.md)).

It also bounds what QUOTE could ever be. At a 200ms loop a resting quote is
exposed for roughly a third of a second after the market moves against it.
Against the measured mid travel — 5.6¢ over a 30s horizon in the first
adverse-selection sample — a third of a second is a small slice, which is
mildly encouraging. But that is arithmetic on a one-game sample, not a result;
see [adverse-selection.md](adverse-selection.md).

## Authenticated read latency — measured 2026-08-04

**Resolved, and the number is in.** Read-only signed GETs, warm keep-alive
connection. No order placed, modified or cancelled.

| Endpoint | Round-trip median | p90 | Venue-side |
|---|---|---|---|
| `/v1/account/balances` | 94ms | 119ms | **3ms** |
| `/v1/portfolio/positions` | 91ms | 100ms | **3ms** |
| `/v1/portfolio/activities` | 181ms | 227ms | 76ms |
| cold connect + one read | 242ms | | |

Reproduce with `scripts/probe_authed_read.py` (read-only; it has no verb but
GET). The scheme is implemented in `core/polymarket/client.py`.

**Venue-side read processing is now measured directly: 3ms.** Every response
carries an `x-pm-server-latency` header giving the venue's own backend time.
That is not an inference — it is the venue reporting its own cost, and unlike
every other number here it is network-independent. The claim that venue
processing "cannot be measured without placing an order" was true for *writes*;
the read side was free all along and nobody had looked.

**Authentication itself costs +12ms.** Measured by interleaving signed and
unsigned requests on one warm connection, so both legs see identical network:
authenticated 200 at 97ms median against a 401 short-circuit at 85ms.

### Do not compare these absolutes to the table above

Those are from 2026-08-02, these from 2026-08-04. Measured in the same session
as this section:

| | 2026-08-02 | 2026-08-04 |
|---|---|---|
| gateway board call | 158ms | 173ms |
| small-request warm RTT | 21–36ms | 79–85ms |

The board call is stable; small-request RTT is 2–4× worse *uniformly across
both hosts*, which is a property of the measuring network that day, not of the
venue. **Compare deltas, not absolutes.** The +12ms auth cost and the 3ms
venue-side figure both survive, because both were taken against a same-session
baseline. Expect different absolutes on a re-run and the same deltas.

### The signing scheme, and why six attempts failed

**⚠️ This section previously stated the scheme was L2 HMAC-SHA256 with five
`POLY_*` headers. That was wrong.** The original guess in this doc — "Ed25519
or HMAC-SHA512" — was half right and got overwritten by a confident correction
that was not. Polymarket **US** uses three headers and **Ed25519**:

```
X-PM-Access-Key   the 36-char UUID key id
X-PM-Timestamp    unix MILLISECONDS (±30s of server time)
X-PM-Signature    base64(Ed25519_sign(timestamp + METHOD + path))
```

The secret is a standard-base64 **64-byte Ed25519 private key**: bytes 0–31 are
the seed, bytes 32–63 the public key. There is no passphrase, no Polygon
address, no HMAC, and no body term. The five-header HMAC scheme is the
*international* CLOB at `clob.polymarket.com` — a different venue.

Why the six earlier attempts could not have found this: `Missing required API
key headers` is returned for every path, every signature, and every header set
— **including a request carrying all five correct `POLY_*` headers**. It is not
evidence about signing at all, only that the header *family* is unrecognised.
The 401s were never a cryptography problem to solve.

What actually discriminated was a CORS preflight. `api.polymarket.us` answers
`OPTIONS` with a fixed, server-declared `access-control-allow-headers` naming
the headers it accepts. Once the header names were right the error string
started moving — `timestamp expired` (seconds, not milliseconds), then
`Invalid API key signature` (HMAC, not Ed25519) — and each step named its own
fix. Full account in [findings.md](../findings.md) V10.

### Rate limit: the authenticated host is much tighter

The gateway's documented ceiling is 20 req/s. The authenticated host returned
429 at roughly **5 req/s**, so the probe paces at 2/s. This bears on QUOTE: a
strategy polling authenticated state is capped well below the public board's
cadence, so position state cannot be refreshed at the 200ms price loop's rate.

## Write latency — MEASURED 2026-08-05, the first real order

**The number is in.** The first order in project history (1 share, DAL −10.5,
resting at 0.20, `HUMAN_CONFIRM`, human-clicked on the picks page, ~23:10Z):

| | |
|---|---|
| `submit_latency_ms` | **124ms** |
| `venue_latency_ms` (venue's own header) | **17ms** |
| result | HTTP 200, accepted, `would_rest=True` |

n=1 — a first estimate, not a distribution. Venue-side write processing (17ms)
is ~6× the 3ms read baseline — that ratio is the network-independent part, and
it is matching-engine and risk-check work a balance read doesn't do. The QUOTE
exposure equation is now fully populated and **detection (~260ms) remains the
dominant term** by roughly 2×.

Still unmeasured: **cancel latency** (needs a resting order and a cancel path,
which does not exist yet), and the fill itself — "accepted" and "filled" are
different events, and only `/v1/portfolio/positions` reports the second. On
the no-body signing question: 124ms is consistent with a single round trip
(reads on the same host run 91–98ms), so the no-body variant most likely
succeeded first try — but the 401-then-retry path wasn't logged either way, so
this is inference, not observation.

What changed on 2026-08-04 is that measuring it no longer requires writing
throwaway code. `POST /api/orders` records both halves of the number on every
submission, accepted or rejected:

| Column on `orders` | What it is |
|---|---|
| `submit_latency_ms` | our full round trip, measured around the POST |
| `venue_latency_ms` | the venue's own `x-pm-server-latency` header |

Both are returned in the endpoint's JSON and shown in the confirmation ticket
the moment an order comes back, so the first real order produces the number
without anyone remembering to instrument it.

**This still costs the $0 record**, so it remains the user's decision and is
not something the system does on its own: the only way an order reaches the
venue is a human clicking Confirm on the picks page, with a server-side token
present. See [findings.md](../findings.md) V13 for the five gates.

### How to fill in this table when that happens

```sql
select market_slug, http_status, accepted,
       submit_latency_ms, venue_latency_ms
from orders order by submitted_at desc limit 5;
```

Then record the write here beside the read, and compare `venue_latency_ms`
against the 3ms read baseline — that ratio is the thing worth knowing, because
it is the only part that is network-independent. Pace any repeats: the
authenticated host throttles at ~5 req/s (V12), and the endpoint self-limits to
2/s for that reason.

**One caveat to expect on the first attempt.** Whether a POST's signature must
include the request body is undocumented and untested — the auth docs give the
signed message as `timestamp + METHOD + path` with no body term and say nothing
about POST. If that is wrong the venue answers 401 `Invalid API key signature`
and **nothing is placed**; the client then retries once with the body appended.
A wrong guess there cannot leak an order, only refuse one, so the first click is
safe either way. If the retry is what succeeds, note it here — it is a real
venue fact and nothing in the documentation records it.

## The smallest safe test, for the user to decide on

This would break the "**$0 has ever been traded**" invariant, so it is written
down rather than run.

1. ~~Get the signing spec and re-run the authenticated read probe.~~
   **Done 2026-08-04.** It cost no order and no risk, and it delivered both
   auth+backend read latency and — unexpectedly — venue-side read processing.
   Note the endpoints named in the original plan (`/v1/portfolio`,
   `/v1/balance`) do not exist; they 404 once you are past auth. The real ones
   are `/v1/account/balances` and `/v1/portfolio/positions`.
2. Only if step 1 proves insufficient: place **one** limit buy at a
   deliberately unmarketable price — say 0.01 on a market trading near 0.50 —
   at the venue minimum size, then cancel it immediately. Measure submit RTT,
   acknowledgement latency, and cancel RTT.

   - Maximum exposure if it somehow filled: **1 contract at 1¢**.
   - It is still a real order on a real account, and it ends the $0 record.
   - It cannot be done from `core/executor.py`, which has no code path to the
     venue at all.

**Update 2026-08-04:** step 2 is now *buildable* by a human click rather than
by a script — `POST /api/orders` exists and is limit-only, post-only,
size-capped by the sizer, and gated five ways. That changes who decides, not
whether it should be done. The recommendation below is unchanged.

**Recommendation: step 1 is done; still do not do step 2.** The argument is
unchanged and if anything stronger. Step 2 buys a number that only matters once
a gate has passed, and [adverse-selection.md](adverse-selection.md) is still NO
DATA at 1 game against a 10-game bar. Spending the $0 record to measure cancel
latency for a strategy that has not cleared its first gate is the wrong order.

What step 1 did change: venue-side processing is 3ms for a read, so the
"unknown venue processing" term in the headline decomposition is unlikely to be
the generous 100ms used as a bound above. If a write is even 10× a read it is
30ms, still well under the ~260ms detection term. **That strengthens the
finding that our poll loop, not the venue, is the bottleneck** — without
placing an order.
