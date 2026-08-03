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

## What is NOT measured, and why

**Venue-side order processing: unknown.** Submitting, acknowledging, and
cancelling an order all require sending one. No order was placed, modified or
cancelled; shadow mode and the kill switch are untouched.

**Authenticated read latency: also unknown.** Read-only GETs to
`/v1/portfolio`, `/v1/positions`, `/v1/orders` and `/v1/balance` were attempted
under six standard header conventions and all returned 401. The signing scheme
is not documented anywhere in this repo — the executor makes zero authenticated
calls by design — and it cannot be inferred from the response, because
`Missing required API key headers` comes back for *every* path including `/`.
Auth runs ahead of routing, so the 401s do not even confirm which routes exist.

The credential shape suggests request signing rather than a static header: the
key id is 36 characters (a UUID) and the secret is 88 (64 bytes base64), which
is an Ed25519 or HMAC-SHA512 key, and "headers" is plural. Expect
key-id + timestamp + signature.

## The smallest safe test, for the user to decide on

This would break the "**$0 has ever been traded**" invariant, so it is written
down rather than run.

1. Get the signing spec from `polymarket.us/developer`. **Then re-run the
   authenticated read probe** — `/v1/portfolio` is non-mutating and would give
   auth + backend read latency for free, with no order and no risk. Do this
   first; it may be enough on its own.
2. Only if step 1 proves insufficient: place **one** limit buy at a
   deliberately unmarketable price — say 0.01 on a market trading near 0.50 —
   at the venue minimum size, then cancel it immediately. Measure submit RTT,
   acknowledgement latency, and cancel RTT.

   - Maximum exposure if it somehow filled: **1 contract at 1¢**.
   - It is still a real order on a real account, and it ends the $0 record.
   - It cannot be done from `core/executor.py`, which has no code path to the
     venue at all.

**Recommendation: do step 1, and do not do step 2 yet.** Step 2 buys a number
that only matters once a gate has passed, and
[adverse-selection.md](adverse-selection.md) is currently NO DATA at 1 game
against a 10-game bar. Spending the $0 record to measure cancel latency for a
strategy that has not cleared its first gate is the wrong order.
