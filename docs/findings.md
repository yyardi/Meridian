# Findings log

Things we learned by running the system, not by planning it. **Append here whenever
something turns out to be wrong, surprising, or different from what the docs claim.**

Three kinds of entry, kept apart on purpose:

- **Venue facts** — how Polymarket US actually behaves. These constrain strategy.
- **Bugs** — what broke, what it cost, what would have caught it.
- **Corrections** — claims made in this project that turned out to be false.

The third section matters most. A wrong number that nobody retracts gets built on.

---

## 1. Venue facts

Measured on the live board, not assumed.

| # | Finding | Measured | When | Consequence |
|---|---|---|---|---|
| V1 | **Depth at the touch is tiny** | \$5 under 20¢ · \$24 at 20–35¢ · \$118 at 35–65¢ | 2026-08-02 | Cheap contracts cannot absorb size. A \$50 order at 16¢ is 10× the book |
| V2 | **Tick size is 1¢ everywhere** | tick 0.01, min qty 0.01, **96 / 96 markets** | 2026-08-02 | 16.1¢ is not a placeable price. No sub-cent queue jumping. At 16¢ one tick is **6.25%** of contract value |
| V3 | **Cheap contracts move less often** | 7¢ move hit **57%** of the time under ~20¢ vs **88%** near-money | 2026-08-02 | The exit the model assumes is far less likely on exactly the rungs it prefers |
| V4 | **Spread blows out in-game** | 3.1% of live ticks >10¢ · 0.6% >25¢ · worst 50¢ · Q4 p90 (9¢) fatter than Q1–Q3 (7¢) | 2026-08-02 | Quoting into Q4 is quoting into the gap. Gates hypothesis #5 |
| V5 | **In-game price travel** | moneyline 35.5¢ median vs 48¢ for ladder rungs, n=4 games | 2026-08-02 | Weak — one ML market per game against ~9 rungs, and a median washes out close games |
| V6 | **ESPN publishes no live in-game odds** | measured directly | 2026-08-01 | There is no book leg to compare against during a game. [infra/live-odds.md](infra/live-odds.md) |
| V7 | **Polymarket US MLB is 1¢ wide with half-cent ticks** | 30 events, 405 markets | 2026-08-01 | No venue gap in MLB. Decided we stay WNBA. [roadmap.md](roadmap.md) |
| V8 | **Network RTT to the venue is 36ms; our detection is 161ms** | | 2026-08-02 | Our poll loop, not the network, is the latency floor. Write latency still unmeasured — it gates QUOTE. [math/write-latency.md](math/write-latency.md) |
| V9 | **The venue publishes its taker fee coefficient, and it is 0.06 everywhere** | `fee_coefficient` = 0.060000 across **874,267 rows / 241 markets** — totals, spreads and winners alike | 2026-08-04 | $\Theta_{\text{taker}}$ is no longer an assumption. Third-party claims of a sports-specific 0.05 are wrong for this board. **No corresponding maker field exists** — see C7 |
| V10 | **Polymarket US authenticates with Ed25519 and three headers — not the CLOB's five-header HMAC** | `X-PM-Access-Key` · `X-PM-Timestamp` (ms) · `X-PM-Signature` = base64(Ed25519(ts+METHOD+path)) | 2026-08-04 | Authenticated reads work. Ended seven months of 401s that were never a signing problem. See below |
| V11 | **Authenticated read latency: 91–94ms round-trip, 3ms venue-side** | n=44 warm GETs across 3 endpoints; venue self-reports backend time in `x-pm-server-latency` | 2026-08-04 | The number [math/write-latency.md](math/write-latency.md) was missing. **Venue-side read processing is measured without placing an order** |
| V12 | **The authenticated host throttles at ~5 req/s** | 429 at ~5/s vs the gateway's documented 20/s ceiling | 2026-08-04 | Position/balance state cannot be refreshed at the 200ms price loop's cadence. Constrains QUOTE |
| V13 | **The "$0 traded" invariant is now enforced by Postgres, not by the absence of a code path** | `ck_orders_accepted_requires_human` | 2026-08-04 | A human-confirm order path exists. What guarantees safety changed shape — see below |
| V14 | **YES = OVER (490 settled markets vs 22 artifacts), and NO orders send the YES-side price** | `price.value = 1 − cost`; a resting NO buy sits at the **ask** | 2026-08-04 | UNDER/SELL picks are orderable. Buying YES on an UNDER row would have paid 0.81 for a 0.16 bet — the opposite side. See below |
| V15 | **A price is meaningless without its side** | picks table mixed frames: `UNDER 155.5 · BUY AT 0.20 · bid 0.80/ask 0.83`, vs the venue's 0.17/0.20 | 2026-08-04 | Rows now quote one frame throughout; `yes_frame` retained for reconciliation. See below |
| V16 | **The shadow sizer sizes every pick as a YES buy** | `shadow_run.py` passes `probability=model`, `price=ask` for NO rows too | 2026-08-04 | Most of `shadow_orders` carries a size for the opposite trade. **Not yet fixed** — see below before quoting stake-weighted numbers |
| V17 | **Order write latency: 93–124ms round-trip, 14–23ms venue-side** | n=3 real orders (both intents: buy_yes ×2, buy_no ×1 in the V14 frame), all accepted, 2026-08-05 | 2026-08-05 | The last unmeasured term in [math/write-latency.md](math/write-latency.md). Venue write processing ≈ 5–8× read (3ms) — detection (~260ms) still dominates. Cancel latency still unmeasured; venue-side cancels (done in the app) are invisible to the `orders` table until a fill watcher reconciles |
| V18 | **The HUMAN_CONFIRM invariant amended: pre-authorized exits** (user-approved 2026-08-05) | `pre_authorized` flag on `orders`, pinned to HUMAN_CONFIRM by `ck_orders_pre_authorized_requires_human` | 2026-08-05 | The fill watcher may submit an attached exit whose every term a human fixed on the ticket. `orders_autonomous` keeps its meaning and must remain 0. See below |
| V19 | **The activities feed: nested executions, authoritative embedded order state, 2dp-rounded quantities, paginated by `cursor` — and zero-fill cancels emit NO activity** | read live 2026-08-06; our 1.4645-contract order reports `cumQuantity 1.46, state ORDER_STATE_FILLED`; `/v1/orders` 501, `/v1/orders/{id}` 404; query params are honoured but NOT signed | 2026-08-06 | Fill reconciliation must read `trade.<side>Execution.order.{state,cumQuantity}` — summing fills or comparing to our ordered size strands >2dp orders as PARTIAL forever. Cancels of unfilled orders are invisible; settlement (`ACTIVITY_TYPE_POSITION_RESOLUTION`) is the only terminal signal for never-filled orders. See below |
| V20 | **`event_score` is `first_team-second_team`, matching the market slug — and YES on a winner market = the first team wins** | all 12 finished games with both a final `event_score` and a settled winner price: **12 / 12** agree in sign | 2026-08-07 | The frame every live-margin calculation depends on. Had the venue reported home-first while quoting the slug's first team, ~half would disagree. Pinned in `tests/test_win_curve.py`; used by [math/win-curve.md](math/win-curve.md) and `core/live_fv.py` |
| V21 | **⚠️ UNVERIFIED — the cancel endpoint.** Built dark as `DELETE /v1/orders/{id}` (REST convention; V19 rules out the read side, and no cancel has ever been sent by this system) | awaiting one live cancel of a 1-share resting order, human-placed and human-clicked | 2026-08-07 | The button records the venue's verbatim response into `orders.cancel_response` plus round-trip and venue-side latency — the **last unmeasured number** in [math/write-latency.md](math/write-latency.md). **After the first live cancel, replace this row with what the venue actually answered.** A 2xx marks the row CANCELLED; anything else changes nothing (an unacknowledged cancel proves nothing; settlement remains the terminal backstop). Cancels stay human-initiated only — no machine path references the verb, pinned in `tests/test_cancel_path.py` |
| V22 | **V7's MLB result reproduces, and the comparison that produced it was never horizon-matched** | live MLB board 2026-08-07: 50 events / 505 markets, tick **0.005 (58%)**, near-money median spread **1.00¢**, fee 0.06 (100%). But MLB was observed at a median **+27.7h** to tip-off against WNBA's +0.0h, and **no** horizon bucket has data on both sides | 2026-08-07 | V7 stands — MLB is tighter even allowing for horizon, and carries half-cent ticks WNBA does not. What was missing is that spread swings **12×** with time to tip-off on the same board (WNBA: 1.00¢ inside 3h, 12.00¢ at 12–24h), so a far-dated board reads as thin, and thin is what this project buys. [`core/survey.py`](../core/survey.py) now reports every spread per horizon bucket and refuses to imply a comparison when the buckets do not overlap. [infra/board-survey.md](infra/board-survey.md) |
| V23 | **Polymarket and Kalshi quote the same price to within one tick — and their totals ladders are deliberately staggered a point apart** | **773** line-identical pairs within 60s across **10 games / 61 contracts** (gate MET): median \|gap\| **0.00¢**, **97.2% within one cent**, median signed gap exactly zero in **9 of 10 games**. Disagreement sits 3–6h out (0.50¢) and is **0.00¢ inside 3h**. Both venues list 9 totals rungs at 3-pt spacing; in **7 of 10 games they sit exactly 1.0pt apart** (26 line-identical totals of 90 vs 90). **Full sample 2026-08-10: 36 games (3.6× the gate), 3,651 pairs, lag p50 15.8s** — median \|gap\| **0.0000**, exactly zero in **35 of 36 games** (the 36th −0.005, a half-tick), zero in every horizon bucket; clustered mean \|gap\| 0.29¢ [0.22, 0.36]. Sign persistence 1.0 on **1 signed game of 36** — vacuous | 2026-08-07 / 2026-08-10 | **The founding thesis FAILS at pregame resolution — there is no venue gap to translate**, confirmed at 3.6× the gate. The 10-game power concern below is now moot at n=36. Tradability/fees stay separately registered; the roadmap fork (in-game resolution · another league · abandon the route) is the **operator's decision, queued**. Independently cross-checked twice: ≤0.04¢ magnitude agreement (2026-08-07) and an independent totals preview agreeing at 0.0000 (2026-08-10). `report()` implementation is uncommitted working-tree code — **flag for PR review**. [math/venue-gap.md](math/venue-gap.md) |

### V10 in detail — the 401 was never a cryptography problem

Seven months of `Missing required API key headers`, six header conventions, and
a doc section confidently describing the wrong algorithm. The error string is
returned for **every path, every signature, and every header set — including a
request carrying all five correct `POLY_*` headers.** It carries exactly one
bit of information: the header *family* is unrecognised. It says nothing about
the signature, and nothing about whether the route exists.

Two lessons worth more than the credential:

**An error message that never varies is not evidence.** Six conventions were
tried against an oracle that could not distinguish them. That is not six
experiments, it is one experiment run six times. The tell was available from
the start: the same 401 came back for `/`, which no auth scheme should treat as
a valid route.

**The discriminator was CORS, not cryptography.** `api.polymarket.us` answers
an `OPTIONS` preflight with a fixed, server-declared allowlist naming the
headers it actually accepts — `X-PM-Access-Key, X-PM-Timestamp,
X-PM-Signature`. The server will tell you what it wants if you ask with the
right verb. (The gateway host merely echoes the requested headers back, so the
same trick there is worthless — worth knowing before trusting it twice.)

Once the header names were right the error string moved at every step and each
message named its own fix:

```
Missing required API key headers  ->  wrong header family
API key timestamp expired         ->  seconds; it wants milliseconds
Invalid API key signature         ->  HMAC; it wants Ed25519
404 with a JSON body              ->  authenticated. The path was just wrong
```

That last transition is the one that mattered: `/v1/portfolio` and
`/v1/balance` — the paths every prior attempt probed — **do not exist**. The
real ones are `/v1/account/balances` and `/v1/portfolio/positions`. Because
auth runs ahead of routing, a 404 is unreachable until you are authenticated,
so nobody could have learned this from a 401.

The credential needs no passphrase and no signer address; the 88-char secret is
a standard-base64 64-byte Ed25519 key (bytes 0–31 seed, 32–63 public key). That
structure is locally checkable — re-deriving the public key from the seed
confirms the secret is intact before spending a request, which turns one class
of opaque 401 into a clear local error (`verify_key_material`).

### V13 — the "$0 traded" invariant changed shape on 2026-08-04

Not a measurement. A change to what the safety property *is*, recorded here
because the old one is quoted throughout this repo and is no longer true as
stated.

**Before:** no order could be placed because no code path existed.
`PolymarketAuthedClient` exposed `get` and `close` and nothing else, so
"nothing has ever traded" was a fact about the shape of the code. That is the
strongest kind of guarantee and it cost nothing, because the system genuinely
had nothing to send.

**Now:** a human-confirmed order path exists. `POST /api/orders` can reach the
venue. The old guarantee is spent and something had to buy it back.

**What replaced it:** a Postgres CHECK constraint.

```sql
ck_orders_accepted_requires_human:  accepted = false OR mode = 'HUMAN_CONFIRM'
```

An accepted order in any other mode is **unrepresentable in the database** —
not discouraged, not caught by a guard someone can forget to call. Every write,
from every process, migration and psql session, goes through it. Verified by
test against a live Postgres, including that `human_confirm` in the wrong case
is refused.

`orders_autonomous` on `/api/status` is therefore a **tripwire, not the
defence**. It reads 0 because the rows are impossible; if it ever reads
non-zero the constraint is gone, which is a different and much worse emergency
than a stray order. `scripts/health.py` checks the constraint's existence
alongside the counter for exactly this reason — a counter reading 0 because
nobody tried and one reading 0 because trying is impossible look identical.

Five independent gates sit in front of the venue, any one sufficient to refuse:

| # | Gate | Refuses with |
|---|---|---|
| 1 | `MERIDIAN_ORDER_TOKEN` set server-side **and** matched | 403 |
| 2 | `mode` exactly `HUMAN_CONFIRM` | 403 |
| 3 | price and size match a ShadowOrder the system already computed | 409 |
| 4 | market type passes the executor's own policy | 403 |
| 5 | Postgres CHECK constraint | IntegrityError |

Gate 1 fails closed: an unset token disables ordering rather than skipping the
check, because deploying without the variable set is the realistic mistake and
the safest configuration must not be the most permissive one.

Gate 3 is the one that is easy to omit and shouldn't be. Without it a token
holder could submit any price at any size and the endpoint would be a generic
trading API with a password. With it, the endpoint can only ever transmit a
decision the model already made and the shadow pipeline already recorded.

**Still true:** `ExecutionMode` defaults to SHADOW, `kill_switch` defaults to
True, `Executor.execute` has no code path to the venue, and market orders
remain unrepresentable — now in the database as well as in `core/executor.py`.

### V14 — YES means OVER, and NO orders are priced from the YES side

Two facts that only became load-bearing once a button could turn a label into
an order.

**1. YES = OVER, verified rather than assumed.** A totals market is one binary
contract per line; there is no separate UNDER slug. Checked against every
settled totals market with a matching final score: **490 consistent with
YES=OVER, 22 inconsistent** — and the 22 are date-join artifacts, not real
counterexamples. The cleanest demonstration is a single game: GSV-TOR on
2026-07-08 finished **158**, and settlement flips exactly at the line.

| line | 154.5 | 157.5 | 160.5 | 163.5 | 166.5 |
|---|---|---|---|---|---|
| settled | 1 | 1 | 0 | 0 | 0 |

If YES meant UNDER, the low lines and the high lines would both have to settle
the same way. They do not. **This convention is correct and was never in
doubt — it is recorded here so nobody has to re-derive it under time pressure.**

**2. Betting UNDER means buying NO, and NO is priced from the YES side.**
The venue documents it explicitly:

> "The `price.value` field always represents the long side's price, regardless
> of which order intent you use." · "To trade the NO side at any price X, set
> `price.value = 1.00 - X`."

So there are two numbers per NO order and they are not interchangeable:

| outcome | rests at | `price.value` | you pay |
|---|---|---|---|
| YES (OVER) | bid | bid | bid |
| NO (UNDER) | **ask** | **ask** | **1 − ask** |

Buying NO is selling YES, so a *resting* NO buy joins the YES **ask** rather
than the bid. Measured on the live 2026-08-04 board, all 16 orderable rows
satisfy `price.value + cost = 1.00` and every resting cost beats the crossing
cost.

Intent mapping, checked cell by cell against the docs:

```
BUY  YES -> ORDER_INTENT_BUY_LONG      SELL YES -> ORDER_INTENT_SELL_LONG
BUY  NO  -> ORDER_INTENT_BUY_SHORT     SELL NO  -> ORDER_INTENT_SELL_SHORT
```

`outcomeSide` + `action` is sent alongside `intent`; the venue documents that
**the pair takes precedence when both are present**, so the authoritative field
is the one that names the outcome literally.

### V18 — the amendment: pre-authorized orders inside HUMAN_CONFIRM

Not a measurement; a change to the safety property, recorded here like V13 was,
because the V13 statement ("every order this system sends was clicked by a
human") is no longer literally true and the replacement has to be written down
before someone re-derives the old rule and calls the new behaviour a breach.

**The amendment, user-approved 2026-08-05:**

> A pre-authorized order is one whose market, side, price, and quantity were
> ALL fixed by a human click; the system may submit it later on a defined
> trigger and may do nothing else.

The one pre-authorized order today is the **attached exit**: typed on the
ticket alongside the entry, stored in `pending_exits` at click time, submitted
by the fill watcher when the entry fills, for the venue-reported filled
quantity, at exactly the stored price. The machine chooses the *when*; every
other term is the human's. That is why `orders_autonomous` — "an order whose
terms no human specified" — keeps its definition and must remain 0.

What enforces it, in the same shape as V13:

```sql
ck_orders_accepted_requires_human:        accepted = false OR mode = 'HUMAN_CONFIRM'   -- unchanged
ck_orders_pre_authorized_requires_human:  pre_authorized = false OR mode = 'HUMAN_CONFIRM'  -- new
```

The second constraint means the flag cannot be inherited by a future mode: a
pre-authorized order outside HUMAN_CONFIRM is unrepresentable, so
"pre-authorized" can never become the loophole through which machine-termed
orders reach the venue. `manualOrderIndicator` remains truthfully MANUAL — the
order's terms were entered by hand; the watcher only transmits them.

See [infra/fill-watcher.md](infra/fill-watcher.md) for the watcher and the
exit rules.

### V19 — the activities schema, read from the venue after guessing it wrong

The fill watcher shipped (2026-08-05) with a parser written against an
*assumed* flat schema — flagged as unverified in its own docstring, which
turned out to be the only honest sentence in it. First live day: two entries
filled, neither exit fired. Three stacked causes, worst first:

1. **`AuthedResponse.body_text` was truncated to 2000 chars** in the client —
   built for a latency probe that only printed excerpts. The activities page
   runs tens of KB, so `json.loads` failed on the truncated body **every
   cycle**.
2. **The failure was silent.** The fetch error was recorded on a result object
   nothing logged. The watcher beat its heartbeat proudly (`rows_written: 0`)
   while reconciling nothing — the exact B11 shape ("ran fine, produced
   nothing"), rebuilt from scratch one day after citing B11 in the module
   docstring. `rows_written: 0` was on the dashboard the whole time; nothing
   made it loud.
3. **The schema was nothing like the guess.** Real shape:
   `{"activities":[{"type":"ACTIVITY_TYPE_TRADE","trade":{"aggressorExecution":…,"passiveExecution":{"order":{…}}}}],"nextCursor":…,"eof":…}`.
   Our resting orders appear as the **passive** execution; each execution
   embeds the full order object whose `state` and `cumQuantity` are the
   authoritative record.

Measured facts now load-bearing in `core/fill_watcher.py`:

* **The venue rounds quantities to 2dp.** Our 1.4645-contract order reports
  `cumQuantity 1.46` with `state ORDER_STATE_FILLED`. Any reconciliation of
  the form `filled >= ordered` reads PARTIAL forever; and an exit sized from
  our own `quantity` would **oversell by 0.0045** — the exit must sell the
  venue's count. State beats arithmetic.
* **Zero-fill cancels are invisible.** The two orders hand-cancelled in the
  app on 2026-08-05 appear nowhere in the feed; only `TRADE`,
  `POSITION_RESOLUTION` and `TRANSFER` types have been observed, and there is
  no order-status endpoint (`/v1/orders` → 501, `/v1/orders/{id}` → 404). A
  cancelled unfilled entry therefore stays OPEN with its exit PENDING —
  visible, and the human who cancelled is the one looking.
* **Settlement does arrive** (`positionResolution.marketSlug`) — but only for
  markets where we **held a position**, so a never-filled order gets no
  terminal signal from activities at all. The public
  `/v1/markets/{slug}/settlement` endpoint (no auth) answers for any market
  and is the watcher's terminal fallback: explicit 0/1 → EXPIRED; any failure
  to ask → nothing. The same check deletes (never submits) an exit whose
  market has settled.
* **A 300-event lookback was not enough for one night.** The first live
  night's fills were pushed past 3 pages by the slate's settlements, and
  FILLED orders regressed to OPEN (caught by the second live day's audit).
  The watcher now walks up to 10 paced pages on catch-up and never regresses
  a known fill count.
* **Pagination is `?limit=` + `?cursor=` (from `nextCursor`) + `eof`.** Query
  parameters are honoured but **not signed** — the Ed25519 message covers the
  bare path only, verified by a 200 on `?limit=100&cursor=…`.
* Unexplained, parked: the venue echoes
  `manualOrderIndicator: MANUAL_ORDER_INDICATOR_AUTOMATIC` on orders we
  submitted with `MANUAL` (hand-app orders echo MANUAL). Whether this is a
  display artifact of the echo or a venue-side reclassification is worth one
  support question before QUOTE — it is the CFTC-facing field.

The procedural lesson is C10's, re-learned against a payload instead of a
doc: **a parser for a schema nobody has observed is a guess wearing a test
suite.** The guess even had defensive logging for unrecognised shapes — which
never fired, because the body failed one step earlier, in code whose failure
path was quiet. Loudness has to cover the whole chain, not just the step you
distrust.

### The bug this prevented, and why it was invisible for months

`shadow_run.py` hardcodes `OrderSide.BUY` on the YES contract for every pick.
That was **harmless for as long as nothing was ever sent** — a shadow order is
a record of intent, and the direction error sat in a column nobody traded on.

The moment a SEND button existed, that same code would have bought YES on a row
labelled UNDER. On `UNDER 155.5` (bid 0.81 / ask 0.84) it would have paid
**0.81 for the opposite bet**, against a correct cost of 0.16 — not a rounding
error, the other side of the trade at four times the price.

**The general lesson is about when latent bugs become live ones.** Nothing
changed in the model, the picks page, or the sizing. A dormant assumption
("we only ever buy YES") stopped being true the instant a new caller appeared,
and the failure would have been silent, expensive and irreversible — there is
no cancel path. Worth asking of anything else that has never been exercised:
what breaks the first time it actually runs?

### V15 — one row must quote one side of the book

A binary market's two sides are a single book seen from opposite ends:

$$
\text{NO}_{\text{bid}} = 1 - \text{YES}_{\text{ask}}, \qquad
\text{NO}_{\text{ask}} = 1 - \text{YES}_{\text{bid}}
$$

The picks table was printing both frames in the same row. `UNDER 155.5` read
`BUY AT 0.20 · bid 0.80 / ask 0.83` — the ticket columns already inverted to
the UNDER side, the book columns still quoting OVER. **Every number was
individually correct and the row as a whole was nonsense.** On the venue that
market shows **bid 0.17 / ask 0.20**, which is exactly `1 - ask` and `1 - bid`
of what was on screen.

Fixed by quoting the whole row in the frame of the position it recommends, so
a NO row reads like any other: buy at the ask, sell at the model, edge =
model − ask. The YES-side book is still returned as `yes_frame`, because every
stored price, `shadow_orders`, and the venue's `price.value` all live there and
without it the screen cannot be reconciled against the database. Spread is
frame-invariant and unchanged.

**This is the general hazard with binary markets: a price is meaningless
without its side.** Two frames, both valid, differing by `1 - p`, and mixing
them produces numbers that pass every individual check.

### V16 — the shadow sizer has no concept of the NO side

`shadow_run.py` sizes **every** pick as a YES buy: it passes
`probability=model_probability` and `price=market_ask` to the Kelly sizer, both
YES-frame, for every row regardless of which side the pick recommends.

For a NO position the correct inputs are `probability = 1 - model` and
`price = NO cost`. They are not the same question, and Kelly's answer to the
wrong one is not a smaller or larger version of the right one — it is
unrelated.

Caught because the confirm box prefilled from it: `SELL TOR +11.5` offered a
default of **1.0889 contracts**, taken from a shadow order that was a YES buy
priced off a 0.42 bid eighteen hours earlier, while the live pick was NO at
0.50. Wrong side, wrong price, wrong time.

**Consequences beyond the UI, not yet assessed:**

- Every NO-side row in `shadow_orders` carries a YES-side size. Roughly
  three-quarters of a typical board is NO-side, so this is most of the table.
- Anything reading `shadow_orders.quantity` for a NO pick — P&L attribution,
  stake-weighted CLV, capacity estimates — is reading a size for a trade that
  was never the recommendation.
- The `side` column says `buy` on all of them, so the data cannot currently
  distinguish "bought OVER" from "bought UNDER" at all.

The confirm path now refuses to inherit a size across a side mismatch: NO rows
start at the venue minimum and the SIZE column reads "not sized", which is
honest — the sizer never sized a NO position. **Fixing `shadow_run.py` itself
is not done** and should be, before any stake-weighted number from
`shadow_orders` is quoted again.

### What V1–V3 mean together

The model's edge concentrates on deep out-of-the-money rungs. Those rungs have
**\$5 of depth, a 6.25%-of-value minimum tick, and a 57% chance of ever reaching the
exit.** Each is survivable alone. Together they say the measured edge sits on the
half of the board that cannot be traded at size.

This is not a modelling problem and no amount of model work fixes it. Either the
edge has to appear nearer the money, or size stays at a few dollars per rung.

---

## 2. Bugs

Every one of these was free because nothing traded. That property is the reason
the list is a curiosity rather than a P&L.

| # | Bug | Cost | Root cause | What would have caught it |
|---|---|---|---|---|
| B1 | **`max(captured_at)` silently killed the pipeline** | 2.5 hours of no predictions, `job_ok` logged throughout | A single global max broke the moment a second writer with a different cadence existed | An alert on *predictions written*, not on job exit status |
| B2 | **Board query returned 1 game of 12** | dashboard wrong, invisible | Same root cause as B1, different query | Same |
| B3 | **Connection pool exhaustion (`EMAXCONNSESSION`)** | recorder crash-loop | SQLAlchemy defaults 5+10 **per engine**; Supabase allows 15 **project-wide** | Knowing the pooler's limit is per-project. Now capped at 2+1 and routed to the transaction pooler |
| B4 | **Injury insert `CompileError`** | recorder dead on deploy | Multi-VALUES insert compiles one statement for the batch; rows with different key sets fail | A test with a mixed batch. Written after the fact |
| B5 | **`Cleared` rows lost `team_id`** | would have left recovered players "Out" forever | Reads filter by team; a synthetic row without one is unreachable | A test that clears a player and then reads them back |
| B6 | **Test fixture deleted real data** | genuine rows wiped from the local mirror | Fixture teardown was `delete where source='espn_injuries'` | Scoping test writes to a `TEST_SOURCE`. Fixed |
| B7 | **Supabase parameter limit (65535)** | sync failed | 5,000-row chunks × 23 columns exceeds the wire limit | Deriving chunk size from column count. Fixed |
| B8 | **Recorder crash-loop after a migration** | ~2 min outage, no data lost | Restarted the container without `--build`, so its Alembic could not find the new revision | **Always `docker compose up -d --build` after a schema change** |
| B9 | **`/api/status` took 3.2s** | dashboard sluggish | `count(*)` on tables growing 5 rows/sec | Now 9ms |
| B10 | **Live path never applied shrinkage** | v2/v3 overstated every edge ~4× | The backtest shrank; the live path did not. Two code paths, one of them wrong | Fixed in v4. The version bump is mandatory — `config_hash` would otherwise blend two model generations |
| B11 | **Transaction-pooler rewrite killed the 200ms recorder for 23 hours** | **2 games of tick data, unrecoverable** | `app_database_url()` matched on port `:5432/` alone, not on the host being Supabase, so it rewrote the *local* recorder's URL to 6543 where nothing listens | Fixed: rewrite now requires a Supabase host. See below — the test that should have caught it passed vacuously |
| B12 | **ESPN moved the season type; 18 days of results vanished** | ~51 games missing; the pregame model predicted on team form frozen at 2026-07-31 | `Event.season_type_id` read `event["seasonType"]`; the scoreboard endpoint nests it as `season.type` and carries no such key, so `_rows_for_event` correctly refused every event for having an unknown season type | An assertion on **rows written**, not on the job not raising. `_safe` had nothing to catch and the scheduler heartbeat reports `rows_written: NULL` by design. See below |
| B13 | **Stored bankroll snapshots came back claiming the positions read had failed** | the page showed "positions unread" in red against a real $3.60 open position, and `equity` silently degraded to sizing-cash ($23.22 → $19.62) | `AccountSnapshot` grew `positions`/`positions_read_ok`; `record()` never persisted them and `latest()` never reconstructed them, so a stored row returned the dataclass defaults — and `positions_read_ok=False` asserts a FAILED read, not an empty book. `current()` prefers a fresh stored row, so the serving path got the degraded copy while the poller logged the truth in the same minute | A round-trip assertion over `dataclasses.fields()` — not a hand-written field list, which is the same bug one level up. The first version of that guard monkeypatched `record`/`latest` and passed with the bug re-introduced; it tested the stub |

### B11 in detail — three failures stacked

**The bug.** `app_database_url()` rewrote any URL containing `:5432/` to `:6543/`. Its
own docstring said "rewrites *Supabase's* session port"; the code never checked the
host. `docker-compose.yml` gives the live recorder
`postgresql+psycopg://meridian:meridian@postgres:5432/meridian` — local Postgres,
standard port — so every tick write became `Connection refused`.

**The test that passed vacuously.** `test_local_urls_are_never_rewritten` existed and
was green. It used `localhost:5433`, which never contained `:5432/`, so it could not
fail no matter what the function did. **A test for the right idea, written against a
URL that could not exercise it.** Now asserts both forms.

**Why nothing alerted.** Two compounding reasons:

1. [`core/api.py`](../core/api.py) deliberately excludes the live recorder from the
   health verdict — it is legitimately silent between games, so failing on its age
   would show STALE every night. Correct reasoning, but it makes *dead for a day*
   and *idle at 3pm* indistinguishable.
2. `/api/status` queries **Supabase**, while the live recorder writes **locally**.
   Since the repoint, `live_age_seconds` has been describing a writer that no longer
   writes there. The number was not stale — it was meaningless.

**The fix — built 2026-08-05:** every writer (all four, not just the live recorder)
upserts one `service_heartbeats` row on every cycle whether or not a game is in
progress, into the same database it writes data to. A beat older than 3× the
writer's own reported interval is DEAD regardless of game state; a live game plus
a fresh beat plus zero rows is DEGRADED, loudly. One rule, in
`core/heartbeat.py::verdict`, shared by `scripts/health.py` and `/api/status`.
See [infra/heartbeats.md](infra/heartbeats.md).

**Coverage lost:** local ticks ran to 2026-08-03 04:16 UTC and resumed 2026-08-04
03:02 UTC. The 2026-08-03 evening games — the two that were traded live — have no
200ms data. PULSE Tier 1 stayed at 3 games instead of reaching 5.

### The pattern in B1, B2 and B10

All three are **the same shape**: a computation that was correct once, then quietly
stopped being correct when the world around it changed. None of them threw. All of
them logged success.

The countermeasure is not more tests. It is **asserting on outputs rather than on
exit codes** — predictions written per hour, games on the board, mean shrinkage
applied — so that "ran fine, produced nothing" is loud.

### The pattern in B11 and the 2026-08-17 cluster — checks pointed next to the property

Distinct from B1/B2/B10 above. Those were computations that were **correct once
and stopped being correct** when the world changed. These never tested the thing
they claimed to test, from the first commit. They did not decay; they were born
green and stayed green.

B11 is the expensive member and it predates the rest. The repo already contains a
written confession of the pattern, in the test's own docstring
([`tests/test_schema_roundtrip.py`](../tests/test_schema_roundtrip.py)):

> Both URLs matter and only the second one can regress. `localhost:5433` never
> contained ':5432/' so it passed vacuously while the rewrite was matching on port
> alone — and the recorder, which uses the *other* form, spent 23 hours logging
> `Connection refused` on every tick.

**A test for the right idea, written against an input that could not exercise it.**
23 hours of outage; the cost was two games of 200ms tick data, which cannot be
refetched from anywhere.

B11 also demonstrates the **countermeasure**, not only the failure. Its fix did not
replace the vacuous assertion — it added a second one beside it, on the compose form
that actually broke:

```python
    # Exactly what docker-compose gives the live recorder: standard port,
    # container hostname. This is the one that broke.
    in_compose = "postgresql+psycopg://meridian:meridian@postgres:5432/meridian"
```

One vacuous case plus one real. That is the same move as replacing a hardcoded page
list with a discovery form: keep the case you thought of, and add the one that can
actually fail.

Then eight more in a single day (2026-08-17/18), found by four people working in
parallel on unrelated changes:

| what it checked | what it claimed to check | how it stayed green |
|---|---|---|
| a fixture hardcoding `aggressorExecution: None` with no `isAggressor` key | that the activities parser books one fill per trade | no test exercised the parser at all; the one fixture touching the shape encoded the belief that was wrong |
| ROI between two audit runs | that the two computations agreed | the ratio held to the decimal across a 3-fill, 2-trip change in what it was computed over |
| that writer and reader spell the analytics path identically | that they resolve to the same bytes | they did spell it identically — on two different filesystems. Page broken six weeks, suite green throughout |
| `/api/picks` on a populated board | that the bankroll block is always present | the empty-board early return was the one path nobody looks at, and it omitted the key entirely |
| a push, attempted twice | that the push was refused | the check was the unreliable part; one failure was explicitly transient |
| `localStorage` appears nowhere on the page | that the order token never persists to disk | a proxy that held exactly until the first legitimate durable preference arrived |
| source sliced "from this function to the next known one" | a property of one function | green until someone inserted a function between them, then red for an unrelated reason |
| a hardcoded list of two page filenames | that every league-scoped fetch is guarded | asserted a fact about two filenames; structurally blind to a third page added later |

**Green was not merely uninformative in these. It was load-bearing in the wrong
direction** — each one made somebody confident. The double count survived because
the ROI looked sane. The hardcoded page list survived because both files existed.
A check that cannot fail is worse than no check, because no check does not
reassure anybody.

**The tell, in every case: the assertion was cheap to write because it was about
text rather than about behaviour.** Spelling, presence, a filename, a substring, a
run that exited zero. Behaviour is expensive to assert and is the only thing worth
asserting.

**The countermeasure is one line of process, not more tests: break the thing on
purpose and watch the check go red.** Every guard added on 2026-08-17 was
mutation-tested this way, and two were rewritten because of what it showed — the
page-list check passed with a new unguarded page dropped in, which is the exact
case it existed to catch. Thirty seconds, and it is the only evidence that
separates a guard from a decoration.

Corollary, from the push above: **consistency between two runs of the same check
is not evidence.** Two agreeing readings tell you about the instrument.

Second corollary, and it cost three rounds to learn: **a confident correction is
not evidence either.** Writing this entry produced its own small chain of them —
an inference that two aggregates matching meant two computations agreed (wrong);
a controlled re-run that appeared to confirm it (wrong, different denominator);
and a correction to quote the outage duration rather than the data lost (wrong,
both numbers were in the file, in adjacent columns of the same row). Each was
offered in good faith by someone with more context than the last, and each was
believed because it was more confident than what it replaced.

What resolved every one of them was the same move, and it was never scepticism
about the person: **go to the artifact instead of adjudicating between
summaries.** Read the row. Run the test against the other tree. Check which
figure the file actually records. Green can be load-bearing in the wrong
direction; so can a correction, and a correction arrives with more authority.

Third corollary, from a cluster of eight on 2026-08-25: **the danger zone is the
thing you're not concentrating on while concentrating hard.** Every one of the
eight happened while the person was actively being careful about something
*adjacent*:

| the error | what the person was being careful about at that moment |
|---|---|
| appended a result **above** a registration page's own "never above this line" marker | enforcing that same append-only rule on someone else's stale index line |
| repeated a substring test that matched its own docstring | had fixed that identical bug, in another file, two hours earlier |
| relayed "the pre-declared money clause has saved us twice" — #16 had no money clause at all | insisting that the ledger's claims must survive being checked |
| asserted a ledger row's column count from memory | telling a peer to verify against artifacts rather than memory |
| handed off "1.1–2.1s for the picks endpoint" — localhost not production, and a warm-up curve quoted as a range | a session otherwise spent on measurement discipline |
| trusted `grep -c` reporting 1 of 2 for a phrase that wrapped differently in the two places | checking, character by character, that a registration's clause had not drifted |
| relayed three attrition causes as measured findings; all three were pre-run speculation and the audit refuted every one | being careful about the attrition rate itself, and not about whether its stated causes had been measured |
| concluded that two feed-lag figures contradicted, and that the wrong one was mine; they were a 2-game pilot and a 16-game full run converging | refusing to edit either page, because both sat in uneditable registration blocks |

**The sixth is the one that generalises furthest**, because the unreliable part
was not a memory but an *instrument*. `grep -c` counts matching **lines**, not
occurrences; the phrase being verified wrapped after a different word in each of
its two places, so a correct page reported as half-missing. The near-miss was
not failing to check — the check ran — it was that a red result from a
mis-chosen tool nearly caused an edit to a file that was already right. That is
the first corollary above, arriving from the other direction: *two agreeing
readings tell you about the instrument*, and so does one disagreeing reading.

**The seventh travelled furthest, because the person was a relay.** The other
six damaged one artifact each. An unmeasured claim passed along reaches everyone
downstream at once — and it arrives carrying the **relayer's** credibility rather
than the speculator's, so the people best placed to doubt it are the least
likely to. Relaying is the one posture where the danger zone has a blast radius.
**Say what a claim's evidentiary status was when you received it**, especially
when passing it on costs you nothing.

**The eighth runs the other way, and is the hardest to see.** The first seven
are false negatives — a real defect missed. This one is a **false positive**: a
conclusion that an error existed, and was the concluder's own, when the two
figures were simply a pilot and a full run converging under 8× the data. "Assume
it is mine" is a good prior and it is why people catch things; here it answered
a question nobody had established was open. **The frame was the error** — "which
of these two is wrong" was asked, "do these measure the same sample" was not. A
self-blame prior is invisible as a failure mode, because its output looks like
diligence and nobody pushes back on someone claiming their own mistake.

**Citing a rule feels like applying it, and it is the opposite posture.** Quoting
one puts you in the seat of the judge, where the rule is a thing *other* work is
measured against; applying it puts your own artifact in the dock. The confidence
is what suppresses the check — it feels redundant to someone who has just
recited the rule — so the exposure is highest in the minutes *after* invoking
it, not in ignorance of it.

This is the same move as the countermeasure above, one level up. "Break it on
purpose" works because it converts a claim about text into a claim about
behaviour; **"check yourself too" is unactionable, and naming the location is
not.** The usable form: when you have just cited a rule, invoked a prior lesson,
or relayed someone else's claim, treat that as the trigger to check your own
artifact against it — never as evidence that you already did.

#### Replacement behaviours, because knowing the pattern is not enough

The `grep -c` trap above recurred **within the hour**, on this very page, twenty
minutes after the paragraph documenting it was written, by the person who wrote
it. That is the useful datum: **the countermeasure cannot be knowledge.** The
pattern is already taught here and it did not help. What was missing was a
different default tool.

Measured against this file, where the target phrase wraps across a newline:

| command | result | why |
|---|---|---|
| `grep -c "$P" f` | **0** ✗ | counts matching **lines**, and the phrase spans two |
| `grep -o "$P" f \| wc -l` | **0** ✗ | fixes lines-vs-occurrences, **does not fix wrapping** |
| `tr '\n' ' ' < f \| grep -o "$P" \| wc -l` | **1** ✓ | newlines removed first |
| `python3 -c "import re;print(re.sub(r'\s+',' ',open('f').read()).count('$P'))"` | **1** ✓ | whitespace normalised first |

**The intuitive fix is the one that fails.** Reaching for `grep -o | wc -l`
corrects the wrong half of the problem and returns the same confident zero. Any
phrase longer than a few words in wrapped prose must have its whitespace
normalised *before* it is counted — there is no flag on `grep` that does this.

**`grep -c` also exits non-zero when it finds nothing**, which silently breaks
`&&` chains. Verified:

```
( grep -c "zzz" f.txt && cat > out.txt <<'X'
content
X
echo "written" )
  → prints 0, then "written"; out.txt WAS NEVER CREATED
```

The chain died at the `grep`, so the write never ran — and the trailing `echo`
still fired, because a command on its own line after a heredoc terminator is not
part of the preceding chain. **The confirmation reported on itself rather than on
the artifact.** Confirm by measuring the thing (`wc -c < out.txt`), never by
echoing a literal, and keep a search out of a `&&` chain that has side effects
after it.

#### A negative result's provenance decides what to do with it

Two failures an hour apart, opposite in kind, requiring opposite countermeasures:

| | a **network** call returns nothing | a **local deterministic** tool returns nothing |
|---|---|---|
| status | a **hypothesis** | a **fact** — about the question you actually asked |
| real modes | create/read lag, eventual consistency, auth blips, rate limits | none; it will say the same thing forever |
| countermeasure | **retry**, then believe it | **re-read the question**; retrying is worthless |

A `gh pr view` reporting a PR missing was taken as fact on one lookup; the PR
existed and the read had raced the create. A `grep -c` reporting a phrase absent
was correct about *lines containing it* and silently wrong about the question
intended. **One instrument was flaky and read once; the other was perfectly
reliable and answering something else.**

Retrying the second is the trap, because it returns the same confident zero and
that agreement reads as corroboration — which is the first corollary above
arriving a third time: *two agreeing readings tell you about the instrument.*
**Ask where the negative came from before deciding whether it means anything.**

### Facts that expired — the 2026-08-18 cluster

A third family, distinct from both above. B1/B2/B10 were computations that
decayed. The born-green checks never tested anything. These were **verifications
that were genuinely true when captured and acted on after they expired** — the
check was real, the fact was right, and the world moved between the reading and
the use.

Four in one day, found by three people:

| the expired fact | true when captured | what changed under it | what acting on it would have cost |
|---|---|---|---|
| "PR #8 is clean against #5" — cited publicly to justify merge order | merge-tree, run against the branch as it stood | the branch moved; the file count went 3 → 7 | a merge plan built on a stale compatibility claim |
| "D's `slices` shape wins" — a manager arbitration | both proposals existed when the ruling was drafted | the producer had already superseded both with a consolidation, in a message the arbiter never saw | the renderer rebuilt away from what the producer was actually emitting |
| three green MERGED badges on a PR stack | each PR did merge | two merged into their own (undeleted) base branches; main never received the work | a production rebuild of an image missing the two changes it existed to ship |
| a correct claim retracted because a peer's inference arrived after it | the original measurement was right | nothing — the *newer message* was the wrong one, and the retractor had the data in front of them while the peer did not | a regenerated doc un-regenerated, on the authority of arrival order |

**The root is one thing: treating capture time as if it were use time.** A
verification is a photograph, not a property. The merge-tree was true *of a
commit*; the arbitration was true *of a message state*; MERGED was true *of a
PR object* and silent about main; the retraction treated *newest* as *truest*.

The fourth instance deserves its sting kept, in its author's own words: the
retractor **had the data in front of them and the peer did not, and still
deferred**. Proximity to the evidence made them *faster* to abandon a correct
position — the same root as the other three with the opposite surface
behaviour. Three acted on stale facts; one discarded a fresh one. Owning the
measurement is not the same as trusting it.

Three countermeasures, all cheap:

1. **Cite what a check was run against.** "Clean vs #5" expires invisibly;
   "clean vs 4b73ea0" announces its own staleness the moment either side moves.
2. **When a relay and a direct message disagree, the direct message from the
   party who owns the artifact is the newer fact** — and arrival order is not
   supersession order. The manager's ruling arrived last and was the oldest
   claim in the exchange.
3. **The artifact settles it in one command, and it is never scepticism about
   the person.** `git merge-base --is-ancestor` answered the MERGED badges;
   one grep of the served container answered "is it in production"; reading
   the emitted JSON answered which shape the producer holds. Every dispute
   above survived exactly as long as it was argued from summaries.

The stacked-PR instance also has a mechanical fix: **delete branches on merge.**
GitHub retargets a stacked PR only when its base branch is deleted; the badges
pointed at dead ends precisely because the bases stayed alive.

### Design note — the anchor staleness guard (2026-08-05)

A guard built against the B1/B2/B10 shape *before* it costs anything, prompted
by the 2026-08-04 ESPN odds outage (6 hours, between games, free). `anchored`
in [`core/predictions.py`](../core/predictions.py) meant "a non-live book row
exists" — no age check — so a dead odds feed would have left predictions
flowing against a frozen line, marked actionable.

The rule: a prediction is actionable only if the freshest non-live book row
for its game is **under 60 minutes old** at prediction time
(`MAX_ANCHOR_AGE_SECONDS`). **The threshold is pre-registered — chosen here,
on 2026-08-05, before any measurement against it.** Rationale: the fast leg
polls book lines every 20 minutes, so 60 minutes is three consecutive missed
polls — a feed that is down, not one between cycles.

Two properties carried over from existing policy:

* **Logged, flagged, never silenced** — same as unanchored predictions. A
  stale-anchored row is written with `is_actionable=False`,
  `reduced_confidence`, and `confidence_notes` gaining `anchor stale: {N}m`.
* **The silent version of the failure is loud.** When a run writes
  predictions but every would-be-actionable one was suppressed solely by a
  stale anchor, `PredictionStats.ok` is False and the scheduler logs
  `job_degraded` — the same mechanism B1 forced into existence. Zero
  actionable with zero suppressions stays healthy: a board with no edge is a
  fine outcome, not a fault.

---

### B12 in detail — a guard that returns "nothing to do" looks exactly like a guard that works

`Event.season_type_id` read `event["seasonType"]`. The **scoreboard** endpoint —
the one the daily incremental update calls — carries no such key; it nests the
same number as `season: {"year": 2026, "type": 2, "slug": "regular-season"}`.
The schedule endpoint still uses the old spelling, so only the daily path broke.

`_rows_for_event` refuses an event whose season type is unknown. That guard is
**correct**: a preseason game written into the regular-season record corrupts
every feature derived from it. But it made the property load-bearing, and the
failure was silent in every channel we have:

| signal | what it said |
|---|---|
| `fetch_date("20260810")` | `events=2 rows_written=0` |
| exception | none — `_safe` had nothing to catch |
| scheduler heartbeat | fresh, `rows_written: NULL` **by design** |
| `predictions` | still written every 20 minutes |
| `/api/status` | healthy |

Measured on the live primary, 2026-08-18:

    team_game_logs    max(game_date) = 2026-07-31   (18 days stale)
    player_game_logs  max(game_date) = 2026-07-31
    market_snapshots  51 distinct WNBA events in 2026-08-01..08-18
    sportsbook_odds   current (max game_date 2026-08-19)
    injury_reports    current

So ~51 games of results were missing while the pregame model kept predicting on
team form frozen at 2026-07-31. Both games sampled on 08-10 were `STATUS_FINAL`
with real scores (107-95, 97-88) and were dropped anyway.

**Two consequences worth separating.** The model degraded quietly — nobody was
looking at a wrong number, they were looking at a right number computed from
stale inputs. And the injury work was blocked without appearing blocked:
injury collection began 2026-08-01, the day after the last scoreable game, so
the `availability_mode="report"` arm produced a **bit-identical** A/B — ROI,
CLV and hit-rate deltas all `+0.000000`, bet sequence included, over **0**
overlapping games. A bit-identical result is not a small effect; it
is the arm never engaging, and reading it as "injuries do not matter" would have
been the expensive mistake this finding prevents.

**The class this belongs to** is the one `#13` catalogued: a check pointed at
something that cannot move. `rows_written: NULL` for the scheduler is a
deliberate choice — the jobs report through `_safe`, not row counts — and it is
exactly the field that would have shown this. The fix is not to distrust `_safe`
but to assert on *outputs*: `tests/test_espn_season_type.py` asserts two rows
come back from a completed game, in both payload shapes, rather than asserting
that parsing did not raise. It also pins the two cases where returning nothing
is still right — preseason, and a genuinely absent season type.

Worth asking of every other feed: **what does it look like when this writes
nothing, and would anyone know?**

---

## 3. Corrections

Claims made during this project that were wrong, and what is true instead.
**Do not delete entries here.** A retracted number that vanishes gets re-derived.

| # | The claim | Why it was wrong | What is true |
|---|---|---|---|
| C1 | "77% of frames differ, so 200ms recording is justified" | The statistic rises monotonically with sampling interval **by construction** — it measures the interval, not the market | Changes-per-second is the honest metric. The faster cadence is still justified, on different grounds |
| C2 | "Capacity is not the constraint — \$469k is resting" | That was total across **all** levels of **all** markets | At the touch, on the model's actual picks: **\$5–\$24**. See V1 |
| C3 | "Put the sell order in now" | You can only sell contracts you already hold | The sell is placed after the buy fills, not alongside it |
| C4 | "Row-level confidence intervals" on tick data | Rows within a game are not independent | Sample size is **games**. Row-level CI measured at **11% coverage** against a nominal 95%. [math/clustered-errors.md](math/clustered-errors.md) |
| C5 | "94% hit rate" quoted as performance | The live log includes the no-edge control group by design | Bet win rate on actionable rows only. v2/v3 measured **38.5%** over 5 games |
| C6 | Moneyline exclusion treated as a general result | It is a **pregame forecasting** result: market margin MAE 9.65 beats ours 10.19 | It says nothing about a latency strategy. `PULSE_MARKETS` is deliberately empty, to be set from PULSE's own measurements |
| C7 | "The maker earns a rebate of $-0.0125$" stated as fact | The venue advertises a rebate of *25% of the matched taker fee* — a share of fees collected on the other side, not a guaranteed per-contract credit. **Never observed in this account.** The backtest books it as certain and produces the +1.34% headline | Default is now $\Theta_{\text{maker}} = 0$ **in the code, everywhere** (2026-08-05); the rebate is an explicit sensitivity arm (`--assume-maker-rebate`), off by default, until seen on a statement. Measured: stripping it takes +1.34% to **+0.75%** — the arm reproduces +1.34% exactly, so the entire 0.59pp gap was the booked rebate. The maker-only rule is unaffected — it rests on the fee *avoided*. See below |
| C8 | "3 of 9 recorded games have 200ms coverage" / "20 games with tick data" | Two different docs, two different denominators, neither correct. "20" was games with *any* snapshot, mostly pregame-only | Measured 2026-08-04: **20** games with snapshot data, **10** with live ticks, **3** with full 200ms coverage (+1 partial). Gates are written in games and need 10 |
| C9 | The signing scheme is "Ed25519 or HMAC-SHA512" | Inferred from credential lengths alone, never checked against documentation. Wrong, and sufficient on its own to explain all six 401s | ~~It is **HMAC-SHA256** with five `POLY_*` headers and URL-safe base64.~~ **C9 is itself retracted — see C10.** The original guess was half right |
| C10 | C9's own replacement: "it is HMAC-SHA256 with five `POLY_*` headers" | Read from the **international CLOB** docs (`clob.polymarket.com`) and applied to a different venue. Never tested against `api.polymarket.us` before being written down as fact — and it was believed *because* it explained the 401s, which explained nothing | Polymarket US is **Ed25519**, three `X-PM-*` headers, millisecond timestamps, no passphrase, no address, no body term. Verified by authenticated 200s. See V10 |
| C11 | "v4 live record is 34.8% bet win vs a 52.4% breakeven — the CI excludes breakeven, the model is losing" (asserted repeatedly 2026-08-04/05) | **Category error.** 52.4% is the breakeven for ~50¢ bets; the portfolio's average entry is **32¢**, where breakeven is ~32%. Flat win rate is the wrong metric for a tail portfolio by construction — it is *supposed* to lose most bets and get paid multiples on hits. The same error family as C4/C5, committed by the reviewer this time | Scored in money at actual prices, the same 8 games / 132 bets: staked \$42.74, returned \$46.00, **+7.6% ROI** (game-clustered mean +6.1%, 95% CI **[−44%, +56%]**, taker-price entries, fees excluded). Verdict: **no evidence either way at n=8** — not the measured failure previously claimed. Flat win-rate is retired as a performance metric; money-at-price is the only bar (the prompt-4 rule, which this correction re-proves) |
| C13 | "ANCHOR totals: +0.75% ROI under realistic fills" (the canonical headline since C7) | REALISTIC's adverse-selection concession was a **0.5¢ guess written before any fill had ever been observed**. Measured (2026-08-07): pregame — ANCHOR's own regime — **2.11¢** [1.83, 2.39] per filled quote (E[−dmid \| fill], 28k windows / 30 games at the recorder's 900s cadence); in-game **4.70¢** [4.41, 5.00] (1.9M windows / 13 games). The stylised number was 4–9× too kind | Recalibrated canonical run (same 308 bets / 218 fills / CLV +1.751 — the concession changes no selection): pregame-calibrated **−2.33%** (primary; CI-edge arms −1.79% / −2.86%), in-game-calibrated **−7.27%** (worst case). **The +0.75% does not survive measured reality; ANCHOR's maker edge is negative at every measured concession.** Positive only under OPTIMISTIC (+1.67%), which the engine's own report defines as not-an-edge. See below |
| C12 | Hypothesis #16's gate: "trailing team's historical P minus market-implied P > 2¢" — **pre-registered 2026-08-07 by the manager, met the same day** (+6.84¢, CI [+0.84, +12.83], 19 games), and caught the same day by the pregame-price-anchored control | **The benchmark was team-blind and the price was not.** The league base rate says a team trailing by 1 at the half wins 42% — averaged over every team that has ever trailed by 1. The market knows it is LA, priced 0.085 pregame. The gate could only ever have measured how often good teams trail bad ones; the four largest "edges" are all heavy pregame underdogs | Anchoring the base rate on the pregame price flips the sign: **−2.20¢, CI [−3.90, −0.49]**. Recorded as **PASS on its stated terms and NOT TRADABLE**, because retrofitting the gate after seeing the number is the failure this project exists to avoid. **New standing rule:** any hypothesis of the form "the market disagrees with a historical frequency" must carry the anchoring check *inside* its gate before it runs — a base rate is a fair-value benchmark only if it conditions on everything the price conditions on. Same family as C4/C5/C11. **The error was in the gate's design, not in its execution** — which is the uncomfortable half: pre-registration protects against moving a bar after seeing the number, and protects against nothing if the bar measures the wrong quantity. A confounded gate that passes is worse than no gate, because it arrives wearing the authority of the process. Manager-authored and manager-accepted 2026-08-07. [math/win-curve.md](math/win-curve.md) |

### C14 — the live shadow record under measured fills (re-exam, 2026-08-10)

| # | The claim | Why it retires | What is true |
|---|---|---|---|
| C14 | C11's "+7.6% ROI, no evidence either way at n=8" quoted as the last live-money-positive signal in the project | The sample quintupled and the sign flipped. Registered backlog re-exam of the ANCHOR entry rule under C13's measured fill concessions: shadow data only, money-at-price (C11 frame, 1 contract/bet, maker entries, fees excluded), deduped last-per-market, clustered by game (C4) | **v4 shadow record, 41 games / 543 bets (2026-08-10): negative in every arm.** Zero concession: pooled −1.6%, clustered **−17.7% [−37.3, +1.9]**. Pregame 2.11¢ (ANCHOR's regime): **−23.2% [−41.4, −5.0]**. The dispatched 2.66¢ (the QUOTE study's in-game figure — regime mismatch, computed anyway): −24.5% [−42.3, −6.6]. In-game 4.70¢: −28.8% [−45.6, −12.1]. **The ANCHOR entry rule does not clear its bar under measured fills — the game-clustered CI excludes zero at every measured concession — and only grazes zero with no concession at all.** The win-rate scorecard concurs at n=41 (FAIL, whole interval below breakeven — n now clears the 10-game floor it lacked at C11). Reproduce: `python -m core.scorecard --version v4 --money` |

No gate was changed and nothing new was registered; this is C13's concession
applied to the live shadow record instead of the backtest, on the terms the
backlog item registered. It agrees with C13 in sign and worsens it in size.

### C13 in detail — the fill re-exam: ANCHOR's ROI was resting on a guessed concession

**Method, registered before computing** (2026-08-07): pregame arm = `is_live=false`
snapshots, the adverse-selection module's own quotable band and fill rule,
horizon 900s (the pregame recorder's sweep interval, tolerance 450–1800s),
clustered by game. Backtest mapping fixed in the same breath: the engine rests
AT its entry price with no half-spread cushion, so the concession is the full
conditional mid move, `E[−dmid | filled] = mean(half-spread) − mean(net capture)`
— not the net-capture number itself.

**Measured:**

| Arm | windows / games | net capture per fill | concession E[−dmid \| fill] |
|---|---|---|---|
| In-game (30s, 1s cadence, local) | 1.94M / 13 | −2.74¢ [−3.03, −2.44] | **+4.70¢** [4.41, 5.00] |
| Pregame (900s, sweep cadence, primary DB) | 28.2k / 30 | −0.86¢ [−1.14, −0.58] | **+2.11¢** [1.83, 2.39] |

(The −2.66¢ recorded in STATUS on 2026-08-06 was the same in-game measurement
at 11 games; it has drifted to −2.74¢ at 13 and stays inside the old CI.)
Pregame adverse selection is real but ~2.2× milder than in-game — the flow is
slower and the mid drifts less per unit of resting time. Both arms are computed
from the fill rule that undercounts the fills that hurt, so both are
**optimistic bounds**.

**The canonical backtest under measured concessions** (2024–2026 totals,
min-edge 3.0, identical 308 bets / 218 fills / CLV +1.751 in every arm —
a concession changes prices, never selection):

| Concession | ROI |
|---|---|
| 0.5¢ (the old stylised REALISTIC) | +0.75% |
| 1.83¢ (pregame CI favourable edge) | −1.79% |
| **2.11¢ (pregame point estimate — primary)** | **−2.33%** |
| 2.39¢ (pregame CI worst edge) | −2.86% |
| 4.70¢ (in-game-calibrated — worst case) | −7.27% |
| optimistic (every order fills, no concession) | +1.67% |

The entire pregame CI maps to negative ROI. `FillModel.REALISTIC` now carries
the measured 2.11¢ as its default, so the canonical number a fresh run prints
is **−2.33%**, and the engine's own footer applies: positive only under
OPTIMISTIC is not an edge.

**The live maker fill sample** (every resting button order to date, n=5 —
descriptive, far too small to calibrate `fill_probability`, reported because
they are the first real datapoints): pregame-placed **0/3 filled** (all three
2026-08-05 orders died unfilled — two hand-cancelled, one expired); in-game
placed **2/2 filled**, at 48 and 111 minutes to completion. Note the direction:
the 70% fill assumption looks generous pregame and the fills that DO come are
the in-game ones — the regime with the 4.70¢ concession. Both live fills were
entries the mid moved *through* on the way down before settling lower (both
markets settled at 0), which is one anecdote of exactly the mechanism the
measurement prices.

**What survives:** CLV (+1.751 [+1.446, +2.055]) is untouched — the model
still anticipates sportsbook line movement (with Q1's objection still open on
what that is worth). What died is the claim that resting maker orders collect
that edge on this venue at these concessions. Between C7 (−0.59pp of fictional
rebate) and C13 (−3.1pp of guessed concession), the headline has now given
back +1.34% → −2.33% without a single modelling change — both corrections
were about what a *fill* costs, and both times the optimistic side of an
unmeasured number had been baked into the canonical figure.

### C9 → C10 in detail — a correction that was more wrong than the thing it corrected

Worth keeping visible, because the failure was procedural rather than
technical. C9 retracted a *guess* ("Ed25519 or HMAC-SHA512", inferred from
credential lengths) and replaced it with a *citation* — which felt like a
strict improvement and was not. The citation was for the wrong venue.

Three things went wrong at once, and only the first is about Polymarket:

1. **The right doc for the wrong venue.** `docs.polymarket.com` describes the
   international CLOB. This repo trades Polymarket **US**, a separate,
   CFTC-regulated venue that shares a brand and almost nothing else. The
   original entry even carried the caveat "that is the main CLOB, this venue
   may differ" — the caveat was correct and was written down and was then not
   acted on.
2. **A guess was downgraded because it was a guess.** "Ed25519" was right. It
   was discarded for a cited claim, on the reasonable-sounding principle that
   documentation beats inference. The principle is fine; it needed the citation
   to be about the right system.
3. **The 401 was treated as confirmation.** C9 says the wrong crypto was
   "sufficient on its own to explain all six 401s". That reasoning is backwards
   — a response returned unconditionally cannot support any hypothesis. It felt
   like evidence because it was consistent with the theory, and it was
   consistent with every theory.

The general form: **an explanation that accounts for the observation is not
thereby supported by it, if the observation was going to happen regardless.**
Cheapest guard available here was to check whether the failure mode ever
*changes* — the first probe that made the error string move resolved in
minutes what six conventions could not.

### C7 in detail — the repo disagreed with itself, and the headline used the looser side

**The number does not even reconcile with our own measurement.** $-0.0125$ is 25% of a
$0.05$ taker fee, but V9 measures $\Theta = 0.06$ on every market we record. 25% of
$0.06$ is $0.015$. So the constant was derived from a taker fee this board does not
charge, and its source is unrecorded — `fills.py` cites "the Polymarket US schedule"
with no link and no date.

Three modules, two conventions, and the flagship number sits on the optimistic one:

| Module | Treatment of the maker fee |
|---|---|
| `core/backtest/fills.py` | books the rebate as certain — **this is what produces +1.34%** |
| `core/quote/adverse_selection.py` | *"zero, not a rebate"* |
| `core/window_detector.py` | *"assume zero rather than a credit so the gate cannot be passed"* |

The later microstructure modules were deliberately written to refuse the credit so a
gate could not be passed on an assumption. The backtest — written earlier — never got
the same treatment, and nobody reconciled them.

**Reconciled 2026-08-05.** `fills.py` now defaults $\Theta_{\text{maker}} = 0$; the
old constant survives only as `THETA_MAKER_REBATE`, reachable through an explicit
`assume_rebate` flag (`--assume-maker-rebate` on the CLI, `assume_maker_rebate` in
`BacktestConfig`), off by default. Kelly sizing and the executor's fee estimate
inherit the zero default. Measured on the canonical 2024–2026 totals run
(realistic fills, n=308 bets, 218 filled):

| Arm | ROI | total fees |
|---|---|---|
| default ($\Theta_{\text{maker}} = 0$) | **+0.75%** | 0.00 units |
| `--assume-maker-rebate` | +1.34% | −1.30 units |

The arm reproduces the old headline exactly: the whole **−0.59pp** delta was the
booked rebate, slightly above the +0.3–0.7% band guessed above. Hit rate (53.2%)
and CLV (+1.75 [+1.45, +2.06]) are untouched — the rebate never changed which bets
were made, only what they were credited.

**Why the absence of evidence is genuinely weak evidence here.** A hand-traded
session on 2026-08-03 filled two positions at **one share each**. The expected rebate
on that is $0.0125 \times 0.5 \times 0.5 \times 2 \approx$ **0.6¢**, and rebate
programmes commonly settle periodically rather than at fill. A 2¢ credit did appear
in the account and is **~3× too large to be the rebate**, so it is something else —
most likely price movement or a settlement. Nothing here confirms or refutes the
rebate; it establishes that at one share the question is unanswerable by observation.

**How it gets settled:** the read-only signed GET to `/v1/portfolio` and
`/v1/balance` (see [math/write-latency.md](math/write-latency.md)) reads the account
programmatically. Then a maker fill of meaningful size either shows a credit or does
not.

---

## 4. Open questions this log has raised

### Q1 — Is the headline CLV number measuring a tradable edge? ⚠️ **unresolved contradiction**

Two docs in this repo disagree, and the disagreement is load-bearing.

[STATUS.md](STATUS.md) reports the champion at **+1.75 CLV [+1.45, +2.06]** and calls
it "passes CLV gate" — it is the primary evidence that the model is worth anything.

[math/calibration-problem.md](math/calibration-problem.md) says, of the same metric
at an earlier model version:

> Do not read the +0.55 CLV as an edge. It is measured against the *opening* line,
> and it does not survive spread and fees.

**The code says the objection still applies.** In
[`core/backtest/engine.py:264`](../core/backtest/engine.py):

```python
entry   = float(chosen.open_total)    # the bet is entered at the sportsbook OPEN
closing = float(chosen.close_total)
...
clv = (closing_line - entry_line) if side == "over" else (entry_line - closing_line)
```

So +1.75 means *the model beats the sportsbook opening line*. Two problems with
reading that as edge:

1. **The open is the least efficient price of the day.** Beating it is a low bar,
   and the closing line is the accurate one.
2. **You cannot transact at the sportsbook open.** You trade Polymarket. The
   backtest measures model-vs-sportsbook; the money question is
   Polymarket-vs-sportsbook.

The number grew from +0.55 to +1.75 across model versions. **The methodological
objection did not go away with it, and nobody has re-stated whether it still holds.**

This needs settling before the +2.50% ROI figure in
[math/what-the-edge-is-worth.md](math/what-the-edge-is-worth.md) means anything —
that chain starts from +1.75.

### Other open questions

2. **Where does the edge live on the price axis?** V1–V3 say the tradable half of the
   board is 35–65¢. Nobody has measured whether the model has any edge there.
3. **What is write latency?** V8 leaves it unmeasured, and it decides whether QUOTE
   is possible at all. Blocked on the signing layer.
4. **Does the model's edge survive a 1¢ tick?** At 16¢ the tick is 6.25% of value —
   larger than most edges the model claims.
5. **Is the maker rebate real, and does it pay on our fills?** C7. Half to
   three-quarters of the headline ROI rides on it. Answerable once the signed read
   works — no order required to read a balance.
6. **Does Polymarket price away from a *transactable* venue, or only away from a
   sportsbook open?** Q1 is unanswerable against the open because you cannot trade
   there. Kalshi is CFTC-regulated, carries WNBA markets, and its market-data
   endpoints need no auth — recording it alongside turns the venue-gap thesis from
   an inference into a query. Queued.

---

---

*Started 2026-08-03. Append, don't rewrite.*
