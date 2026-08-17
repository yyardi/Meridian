# Hand-trade audit — the human's app trading, scored at prices

**DESCRIPTIVE.** This is an audit of what happened, not a gated hypothesis: no
pre-registration, no target, and therefore — by this project's own rules — no
verdict. It exists because the operator's in-game trading was the one
live-money activity in the project whose result was a feeling rather than a
number.

Reproduce:

```bash
.venv/bin/python -m core.audit.hand_trades          # or --json
```

## Method

[`core/audit/hand_trades.py`](../../core/audit/hand_trades.py) walks the full
`/v1/portfolio/activities` feed (the schema observed live 2026-08-07, a
superset of findings V19), keeps only **hand** fills, and reconstructs round
trips per market from signed YES exposure: an episode runs zero → nonzero →
zero, closed by opposing trades, by settlement, or both. A fill that crosses
zero splits; the crossing opens a new round trip in the other direction.
Settlement payout (YES pays 0 or 1) comes from the venue's **public settlement
endpoint** — never inferred from the resolution activity's before/after
bookkeeping, whose sign conventions are undocumented.

Scoring is C11's frame, the only honest one after the 52.4%-breakeven category
error: **money at the actual price**. YES cost = price paid; NO cost = 1 −
price (the venue reports all prices YES-frame, V14). A round trip wins if it
returned more dollars than it staked, and every win rate is printed next to
its stake-weighted average entry cost — which *is* its breakeven.

Exclusion of the system's own button orders is by **venue order id only**,
matched against the `orders` table — the fill watcher's attribution rule.
Never by market/price/size similarity: the human trades the same markets at
similar prices. The venue's `manualOrderIndicator` is recorded but is *not*
the filter — 28 obvious hand fills (May–August, NBA/IPL/EPL/ATP, months before
this system could place an order) carry `AUTOMATIC`, so the flag marks some
app flow, not machine trading.

## The numbers, as of 2026-08-07

619 activities · 477 hand fills · 3 button fills excluded · 250 closed round
trips across ~7 months and several sports.

| slice | n | staked | returned | ROI | win rate @ avg entry |
|---|---|---|---|---|---|
| **everything** | 250 | $2,313 | $2,147 | **−7.2%** | 48% @ 0.48 |
| live (in-game) | 146 | $894 | $836 | −6.5% | 50% @ 0.44 |
| pregame | 104 | $1,420 | $1,311 | −7.6% | 45% @ 0.50 |
| moneyline (all sports) | 168 | $1,905 | $1,749 | −8.2% | 47% @ 0.49 |
| totals · live | 31 | $140 | $153 | +9.4% | 68% @ 0.50 |
| WNBA totals · live | 9 | $59 | $86 | +47.2% | 67% @ 0.53 |
| WNBA winner · live | 7 | $41 | $22 | −46.9% | 43% @ 0.44 |

Fees: the venue's per-execution commission fields are summed and reported
separately; headline ROI is gross, matching how C11 scored the button record.

Read the table the C4/C11 way before reading anything into it: **n is round
trips, not independent observations** — trips cluster within games and days,
and the positive cells are single-digit-to-low-double-digit n with dollar
stakes in the tens. The table says what happened; at these sample sizes it
does not say what will happen.

## Caveats

* Open positions and any market whose settlement the gateway cannot report are
  listed unscored — never guessed.
* Quantities are the venue's 2dp-rounded numbers (V19).
* "Live" means the fill's `transactTime` ≥ the market's `gameStartTime`, both
  venue-reported.
* The feed shows only this account's side of each trade; a truncated feed
  (`MAX_PAGES`) would be reported loudly — the full history currently fits in
  7 pages.
