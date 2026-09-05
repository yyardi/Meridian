# sandbox/ — the algorithm, readable

**`strategy.py` is the whole trading decision. 145 lines, no third-party
imports.** Read it top to bottom in five minutes.

The repo is 283 files and ~68,000 lines. Almost none of it is the strategy:

| area | files | lines | what it is |
|---|---:|---:|---|
| tests | 88 | 23,566 | |
| analysis | 38 | 16,406 | one-off investigations; findings live in `docs/math/` |
| core/pulse | 16 | 10,056 | **no decision written since 2026-08-31** |
| **core/quote** | **8** | **4,248** | the engine that runs `strategy.py`'s logic in production |
| core/backtest | 12 | 3,234 | |
| core/feeds | 13 | 3,169 | recorders |
| core/kalshi | 6 | 2,002 | second venue, recording only |
| core/storage | 4 | 1,750 | |

## What the strategy actually does

```python
if is_quotable(book):          # is the spread narrow enough to stand in?
    return quote_at_touch(book) # copy the market's own bid and ask
```

**That is it. We have no fair value.** We post where the market already is and
try to earn the spread. This is the central weakness, not a simplification for
the reader: *a maker without a pricing model is a mirror that pays for the
privilege.*

PULSE was tested as the missing opinion and is **worse than the market mid**
(40.53¢ mean error vs 39.01¢, and worse still where it disagrees most), so it
cannot fill the hole.

## What is measured, and encoded in the file

- **Real fills lose 2.0–3.2¢** (against trade prints, `docs/math/trade-prints-resolve-it.md`)
- **The venue PAYS makers** 0.31¢ at mid-book, a third of that at the extremes —
  and nothing has ever conditioned quote placement on that
- **One-sided fills are the loss mechanism**: −10.91¢ at ≥80% one-way against
  −1.68¢ balanced. `OneSidedGuard` is the only measured mitigation we have
- **Never cross.** Crossing turns the trade from +7.19¢ to −6.49¢

## The lever nobody has pulled

`quote_away()` is in the file and **untested**. Every variant we have run
changes *when* to quote. **None has changed HOW FAR FROM THE TOUCH.** That is
the one control a maker actually has, and Glosten-Milgrom says it is the one
that should matter.

## Running it

```bash
python3 scripts/sandbox.py --sport cfb --strategy quote-guarded --wallet 10000
```
