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

Which of a trade's two executions is ours is decided by `trade.isAggressor`
(V22), guarded by the venue's own redaction pattern: it never omits the
account-holder's outcome side and routinely omits the counterparty's, so a
selected leg with an `UNSPECIFIED` outcome means the field has changed meaning
and the parser refuses rather than inverting every row.

Exclusion of the system's own button orders is by **venue order id only**,
matched against the `orders` table — the fill watcher's attribution rule.
Never by market/price/size similarity: the human trades the same markets at
similar prices. The venue's `manualOrderIndicator` is recorded but is *not*
the filter. It used to be described here as unreliable — 28 obvious hand fills
flagged `AUTOMATIC` months before this system could order. Those were the
**counterparty's** flags. On our own leg `AUTOMATIC` appears exactly three
times, which is exactly the three button orders, so the field has been
truthful all along and V19's parked question is answered. The id rule still
stands on its own merits.

## The numbers, as of 2026-08-17 (corrected — see V22)

681 activities · **452** hand fills · 3 button fills excluded · **289** closed
round trips across ~8 months and several sports.

| slice | n | staked | returned | ROI | win rate @ avg entry |
|---|---|---|---|---|---|
| **everything** | 289 | $2,402 | $2,221 | **−7.5%** | 51% @ 0.48 |
| live (in-game) | 172 | $972 | $917 | −5.7% | 52% @ 0.44 |
| pregame | 117 | $1,430 | $1,304 | −8.8% | 50% @ 0.51 |
| moneyline (all sports) | 177 | $1,894 | $1,722 | −9.1% | 47% @ 0.49 |
| totals · live | 32 | $141 | $151 | +7.0% | 69% @ 0.49 |
| basketball totals · live | 12 | $58 | $88 | +53.3% | 67% @ 0.44 |
| basketball winner · live | 20 | $82 | $61 | −25.8% | 55% @ 0.41 |

Fees: the venue's per-execution commission fields are summed and reported
separately; headline ROI is gross, matching how C11 scored the button record.

Read the table the C4/C11 way before reading anything into it: **n is round
trips, not independent observations** — trips cluster within games and days,
and the positive cells are single-digit-to-low-double-digit n with dollar
stakes in the tens. The table says what happened; at these sample sizes it
does not say what will happen.

### What changed on 2026-08-17, and why

The previous version of this table (250 trips, −7.2%, 48% @ 0.48) was computed
over a feed containing **our counterparty's fills as well as our own**. The
parser walked both executions on every trade, believing the venue nulled the
side that was not ours; all 455 trade activities carry both. Full detail in
`docs/findings.md` **V22**.

Two things are worth noting about the correction.

The headline barely moved — −7.2% to −7.5% — because the phantom leg is
*equal and opposite* and largely cancelled in aggregate. That is precisely why
it survived so long: there was no wrong-looking number to notice. The
composition moved much more (250 → 289 trips, 477 → 452 fills, 48% → 51% win
rate), and the per-slice cells moved most of all.

The old table's two WNBA-specific rows are **withdrawn rather than restated**.
This module buckets by the venue's `sportsMarketType`, which does not
distinguish WNBA from NBA, so those rows were never something it could
produce. WNBA-only, per-fill, corrected numbers now come from
`core.audit.trade_export` — see `docs/math/trade-export.md`.

## Caveats

* Open positions and any market whose settlement the gateway cannot report are
  listed unscored — never guessed.
* Quantities are the venue's 2dp-rounded numbers (V19).
* "Live" means the fill's `transactTime` ≥ the market's `gameStartTime`, both
  venue-reported.
* The feed shows only this account's side of each trade; a truncated feed
  (`MAX_PAGES`) would be reported loudly — the full history currently fits in
  7 pages.
