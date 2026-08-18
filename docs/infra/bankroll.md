# Bankroll — the account balance, read from the venue

Every dollar figure this system computes is a fraction of a bankroll: the
Kelly stake, the ticket's SIZE and STAKE columns, the per-order cap.

Until 2026-08-17 that bankroll was `35.68` — a literal in
`core/scheduler.py`, true on the day someone last looked at the app, passed
into `shadow_run` and multiplied through every size on the board. The account
was at **$23.82** by then. Every stake was ~50% too large, the error grew with
every fill and every withdrawal, and nothing on any screen said so.

A number that decays without anybody noticing is not a parameter. It is a bug
with a decimal point.

## Where it comes from

`GET /v1/account/balances` on the authenticated host, through
`PolymarketAuthedClient` — which exposes `get` and `close` and no other verb,
so there is no code path from the bankroll to an order. Credentials are read
from the environment and never logged; the client logs a fingerprint only.

The response, observed live 2026-08-17 (200, ~30ms at the venue):

```json
{"balances":[{"currentBalance":23.8204,"currency":"USD","buyingPower":23.8204,
  "assetNotional":0,"assetAvailable":0,"pendingCredit":0,"openOrders":0,
  "unsettledFunds":0,"pendingWithdrawals":[],"marginRequirement":0}]}
```

`/v1/balance` and `/v1/portfolio` do not exist — they 404 once authenticated,
which is how the old 401s were finally diagnosed (V10).

## What "bankroll" means, and why it is the smaller number

```
bankroll = min(currentBalance, buyingPower)
```

Kelly's `f*` is a fraction of *total wealth*, which argues for
`cash + assetNotional`. But every field except the first two has been zero on
every observation so far, so **the arithmetic relating them is unverified**,
and Kelly is brutally asymmetric to over-betting: twice the optimal fraction
has zero expected growth (`docs/math/kelly.md`). Under-betting costs growth
linearly. Over-betting can cost the account.

So the smallest defensible reading wins — a strict lower bound on wealth under
any interpretation of the other fields. The moment `assetNotional`,
`openOrders` or `unsettledFunds` is non-zero, `core/bankroll.py` logs
`bankroll_components_nonzero` loudly. That observation is what would let this
definition be tightened honestly; until then it stays conservative.

## Failure is a refusal, not a guess

There is no default and no fallback constant. If the venue cannot be reached
and no stored reading is fresh enough, `current()` raises
`BankrollUnavailable`, and:

* `shadow_run` writes **nothing** rather than sizing against a guess;
* `/api/picks` and `/api/status` return `bankroll: null` with the reason;
* the picks page says *"Bankroll unknown"* and the dashboard header shows `?`
  in red.

A fabricated bankroll produces a plausible stake on a plausible ticket. That
is indistinguishable, on screen, from a real one — which is exactly the
failure this replaced.

A **stale** reading is treated the same way: anything older than 30 minutes is
refreshed before use, never served as if current.

## Cadence and storage

The scheduler refreshes it on both legs — the 6-hour daily pass and the
20-minute fast leg — because the balance moves on every fill, settlement and
withdrawal. A bankroll refreshed once every six hours is the stale-constant
bug with extra steps. On demand: `GET /api/bankroll?refresh=true`, or
`python -m core.bankroll --refresh`.

Readings are appended to `account_balances`, one row per poll — the history is
the equity curve, and storing the derived `bankroll` next to the raw venue
fields is what makes a past sizing decision reproducible six months later.
~26k rows a year at 20-minute polling, which is nothing.

## Where it flows

| consumer | what changed |
|---|---|
| `core/kelly_sizing.py` | unchanged — it always took `bankroll` as an argument; the caller was the liar |
| `core/shadow_run.py` | `bankroll=None` means "ask the venue"; `--bankroll` survives for what-if runs |
| `core/scheduler.py` | no longer passes a number at all |
| `core/api.py` `_stake_cap()` | the per-order cap is now `min($25 fat-finger limit, balance)` |
| `/api/status`, `/api/picks` | carry a `bankroll` block |
| picks page, dashboard header | show the balance and its age |

The `$25` per-order cap deserves its own note: it was written when the balance
was $35, and by 2026-08-17 it exceeded the entire account. A cap larger than
the bankroll is not a guard, it is decoration — a single ticket could have
staked more money than exists, and the human would have learned about it from
a venue rejection.

## The regression test

`tests/test_bankroll.py` greps `core/`, `scripts/`, `static/` and
`strategies/` and fails on either `35.68` or any bankroll assigned from a
literal. Comments and docstrings are blanked first — every file that fixed
this bug describes it, so a scanner that cannot tell prose from code is one
that stays red until somebody weakens it into a rubber stamp. A meta-test
checks the stripping still sees a real constant.

One allowlisted exception: `core/backtest/engine.py:starting_bankroll`. A
walk-forward backtest starts from a stated hypothetical so its equity curve is
reproducible; tying it to today's balance would make last month's backtest
un-rerunnable. It never sizes a live order.
