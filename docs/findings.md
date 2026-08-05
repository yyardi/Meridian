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

*Started 2026-08-03. Append, don't rewrite.*
