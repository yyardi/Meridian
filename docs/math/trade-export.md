# WNBA trade export — every fill, one row, waiting for a reason

```bash
python -m core.audit.trade_export              # this season, CSV + xlsx
python -m core.audit.trade_export --all-seasons
```

Writes to `$MERIDIAN_DATA_DIR/exports/`, timestamped, **never overwriting**.

## What it is for

`core/audit/hand_trades.py` already scores this history and answers *"how did
the trading do"* at the round-trip level. This answers a different question:
**why was each trade taken.** That answer exists only in the operator's head,
so the sheet ships two empty columns — `reason` and `hypothesis_tag` — for
them to fill in by hand.

Nothing pre-fills them. A guessed rationale that later gets promoted into a
pre-registered hypothesis is how a system talks itself into its own priors.
The annotated file is the input to the next round of hypotheses, which is also
why re-running writes a new file: those annotations exist nowhere else, and a
clobbering re-run would destroy the only copy of the thing being built.

## The numbers, as of 2026-08-17

| | |
|---|---|
| activities scanned | 681 (to `eof`, 0 unparsed) |
| **WNBA fills, 2026 season** | **94** |
| of which placed through this system's confirm button | 3 |
| settlement rows | 35 |
| rows in the file | 129 |
| markets · games | 58 · 43 |
| realized P&L, gross of fees | **+$7.15** |
| fees as reported by the venue | $5.35 |

94, not 188 — see the correction below.

## The row set, stated exactly

One row per **fill**, plus one row per **settlement** that closed a position.

The settlements are not padding. Most WNBA positions here ended at 0/1 rather
than by a closing trade, so a file of fills alone would carry a realized-P&L
column that silently omits how most of the money actually resolved. They are
labelled `event_type = settlement` and filter out in one click.

Both sources are included — the operator's app trades and the system's own
human-confirmed button orders — split by a `source` column keyed on **venue
order id**, the fill watcher's attribution rule. Never by market, price, size
or timing similarity: the operator hand-trades the same markets at the same
prices. `hand_trades` excludes button orders because it is scoring the human;
this file is the account's whole history, and a trade the operator clicked
SEND on is still a trade the operator made.

## Scoring

C11's frame, one level finer than the round-trip module — per fill rather than
per episode. YES costs the price paid; NO costs `1 - price`, because the venue
reports every price in the YES frame (V14). Average cost basis within the open
position:

```
realized = closed_contracts x (proceeds_per_contract - average_cost_per_contract)
```

A fill that only *opens* exposure realizes nothing and the column is **blank**
— not zero, which would be a claim that the trade broke even. A fill that
crosses zero is split: the closing part realizes, then the remainder opens a
new position in the other direction, exactly as the round-trip reconstruction
splits it.

P&L is **gross of fees**, matching how C11 scored everything else here. The
venue's per-execution commission is its own column and is never netted in
silently.

A market whose settlement the public gateway cannot report leaves its position
open and unrealized — reported, never guessed.

Two conventions worth naming because they look like omissions:

* **`game` is `NY-PHX 2026-08-05`, not `NY @ PHX`.** Slug order does not
  reliably encode home/away — measured across 285 closed markets the first
  slug team was away 267 times and home 18. An `@` would be silently wrong for
  those games and unfalsifiable to a reader.
* **`position` is the exposure, not the contract name.** Selling the Under is
  being long the Over. The label comes from the same helpers the picks page
  uses, so the sheet and the board cannot disagree about what `-pos-` means.

## An open disagreement, shipped rather than reconciled

The venue reports its own `realizedPnl` on 29 of the 94 fills. It is carried
verbatim in `venue_realized_pnl_usd`, next to the two fields it is computed
from — verified on the live payload, `realizedPnl == cost - costBasis`.

**It agrees with our number on none of the 29.** Four conventions were tested
against it — FIFO and average cost, each gross and net of the per-execution
commission — and none matches more than 3 of 29. The gap is not rounding: on
moneyline markets it is a few cents, about the size of the fee, but on spread
markets ours is roughly half the venue's.

So the venue's `costBasis` is built some other way, it is undocumented, and an
afternoon of guessing would produce a number that looks reconciled without
being understood. Both ship, side by side, with their inputs. Ours is
reproducible from the rules above; the venue's is the account's book of
record. Resolving it takes one question to the venue, not more arithmetic.

## Correction: the fill count halved (V22)

The first run of this export reported 188 fills. The real number is 94.

`hand_trades.parse_activity` — the parser this module reuses — walked both
`trade.aggressorExecution` and `trade.passiveExecution`, on a belief written
into its own docstring: *"the feed nulls the side that is not ours."* All 455
trade activities carry both. They are the two counterparties of one trade, so
every real fill was booked against a phantom offsetting one.

It was invisible because the phantom leg is *equal and opposite*: net exposure
still returned to zero, round trips still closed, nothing looked broken.
`trade.isAggressor` is the discriminator, verified four independent ways. Full
detail and the blast radius in `docs/findings.md` **V22**; the corrected audit
numbers are in `docs/math/hand-trade-audit.md`.
