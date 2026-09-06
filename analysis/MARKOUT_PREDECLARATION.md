# Markout — horizons and predictions, declared BEFORE the first number

Written 2026-09-04, **before any markout was computed on any substrate.** It
exists as a file rather than a message because a pre-declaration that lives in a
chat thread is not one (WAVE_STANDARD, and the R4-amendment provenance pattern).

## Why markout at all

The metric ruling in `docs/math/adverse-selection-measured.md` names it and
nothing in the repo computes it:

> **SECONDARY: markout at pre-named horizons.** Lower variance, real power at
> this n, and it is the metric that **exhibits the mechanism** — phantoms profit
> because price reverts, real fills lose because it continues.

Settlement is PRIMARY and stays primary. Its stated limit is that on a binary
held to expiry it is dominated by directional variance, so the effective sample
is games, not fills — which is why 13,651 real fills buy only a ±1.4¢ interval.
Markout is measured per fill against a price a few seconds later, so the game's
eventual outcome is not in it. If it has materially lower variance it changes
what tomorrow's slate can resolve.

## Horizons — FIXED NOW, four of them

**10s, 30s, 60s, 300s** after the fill instant.

Chosen for reasons that are not about any observed number:
* **10s** — inside the quoter's own requote cadence; the shortest horizon at
  which a distinct mid reliably exists on this feed.
* **30s** — the horizon the original adverse-selection study used
  (`docs/math/adverse-selection.md`), so this is comparable to the one prior
  reading we have.
* **60s** — one minute, the round unit.
* **300s** — five minutes; long enough to be past a possession or a drive, short
  enough to still be inside the game state that produced the fill.

**No horizon will be added, dropped, or re-centred after the numbers are seen.**
If 30s is the only one that speaks, all four still print.

## Definition

Mid at horizon comes from `market_snapshots` (the price loop — **not**
`book_levels`, see the substrate ruling), taken as the LAST snapshot at or
before `filled_at + h`, with a staleness cap of h/2 so a horizon is never
satisfied by a quote from before the fill. Fills whose horizon mid is missing or
stale are **UNMATCHED at that horizon** and counted, never dropped silently.

    markout_bid = mid(t+h) − quote_price
    markout_ask = quote_price − mid(t+h)

Same frame convention as `score_fill` (V14): an ask is the NO side, so its
markout is the negation. Fees zero, as in the study — a rebate only flatters.

## Predictions, so this can be wrong

Recorded now so the result can fail against them rather than be narrated after.

1. **Phantoms have POSITIVE markout at every horizon; real fills NEGATIVE.**
   This is the mechanism restated in a different unit. If phantoms are not
   positive, the mean-reversion story is wrong.
2. **The phantom/real markout gap is LARGEST at the shortest horizon and
   decays.** A phantom is a momentary dip that reverts; the reversion should be
   substantially complete inside a minute. If the gap grows with horizon,
   something other than reversion is producing it.
3. **Markout's per-game sd is materially below settlement's 4.10¢ (CFB).**
   This is the whole reason for computing it. If it is not lower, markout adds
   nothing and settlement remains the only metric.
4. **Real-fill markout at 30s is negative but SMALLER in magnitude than the
   −3.4¢ settlement loss.** Settlement carries the full directional outcome;
   30 seconds carries only the immediate information in the flow.

Prediction 3 is the one that matters for tomorrow. Predictions 1 and 2 are
mechanism checks — they can only corroborate a story we already have, and per
the asymmetry ruling that is worth less than a test that could refute one.

## What this CANNOT do

Markout is not money. A maker who is marked-out favourably and still settles
badly has lost money, and settlement is what the account sees. **Markout may not
be promoted to primary on the grounds that it has tighter intervals** — that is
choosing the metric by its variance, which is how capture survived as long as it
did. It is a diagnostic and a power lever, nothing more.

Nothing here gates. No in-sample result justifies capital.
