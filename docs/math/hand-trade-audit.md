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
the filter.

> The earlier version of this note reported "28 obvious hand fills
> (May–August, NBA/IPL/EPL/ATP) carry `AUTOMATIC`, so the flag marks some app
> flow". That observation was an artifact of the double-count corrected below:
> those rows were the **counterparty's**. Measured over the full history, 3 of
> *our* fills are not marked `MANUAL` — all WNBA, all on 2026-08-07 — against
> 392 on the counterparty legs, spanning exactly the leagues that puzzled the
> original note. Venue order id remains the filter, for the reason above.

## The numbers, as of 2026-08-17

681 activities · 455 fills · 0 unparsed · 291 closed round trips across ~8
months and several sports. Regenerated after the fill-attribution fix (V22)
— see the correction note at the foot of this page.

| slice | n | staked | returned | ROI | win rate @ avg entry |
|---|---|---|---|---|---|
| **everything** | 291 | $2,404 | $2,222 | **−7.5%** | 51% @ 0.48 |
| live (in-game) | 174 | $973 | $918 | −5.7% | 52% @ 0.44 |
| pregame | 117 | $1,430 | $1,304 | −8.8% | 50% @ 0.51 |
| moneyline (other sports) | 177 | $1,894 | $1,722 | −9.1% | 47% @ 0.49 |
| basketball totals · live | 14 | $59 | $89 | +51.5% | 64% @ 0.44 |
| basketball winner · live | 20 | $82 | $61 | −25.8% | 55% @ 0.41 |
| basketball spread · live | 5 | $41 | $25 | −39.2% | 40% @ 0.59 |

Slice labels are the venue's own `sportsMarketType`, so `basketball_*` rows
are WNBA and NBA together and `moneyline`/`totals` are the other sports'
naming. Reproduce with `python -m core.audit.hand_trades --json`.

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

---

## Correction, 2026-08-17 (V22)

**Every number above changed.** `parse_activity` walked both
`aggressorExecution` and `passiveExecution`, on the belief that "the feed nulls
the side that is not ours". It does not: both legs are present on 455 of 455
trades and they are the two counterparties of one trade — same price, opposite
side. Every real fill was therefore booked against a phantom offsetting one.

`trade.isAggressor` selects ours (397 True / 58 False). Three independent
confirmations: of the five venue order ids this system has placed, three land
on the selected leg and zero on the other; the venue redacts `outcomeSide` on
the counterparty leg (365 of 455) and never on ours (0 of 455); and two
separately written reconstructions — this module's and the WNBA trade sheet's
FIFO one — agree to the cent on the WNBA slice.

What it cost, full history: ROI read **−4.5%** where the truth is **−7.5%**,
and win rate **26%** against **51%**. The error flattered the record, which is
the direction nobody audits.

**Why it survived a green suite and a published table.** The phantom leg is the
same price on the opposite side, so it inflates staked and returned by nearly
equal amounts and leaves ROI roughly intact — it hid in the one number anyone
checks. And every test built `Fill` objects directly, so nothing exercised the
parser. The fixtures now carry both legs, and a redacted `outcomeSide` on the
selected leg is refused rather than silently scored as a NO position, which
would invert the row rather than drop it.

The previously published table (250 trips, −7.2%, 48% @ 0.48) was mildly
affected rather than badly wrong, for the same cancelling reason. Its fill
count — 477 over a window containing 410 trades — is only reachable by taking
some second legs, so that run did double-count, just not universally. The
distortion being small then and large now suggests the feed widened from
partial to universal two-sidedness; that is the best-supported reading and not
a proven one, since this module and this page landed in a single squashed
commit and no earlier revision exists to check.
