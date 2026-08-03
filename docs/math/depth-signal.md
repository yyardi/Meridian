# Depth signal — does a whale predict the next move?

**Status: NO DATA.** 46 whale appearances across 6 games, against a
pre-registered minimum of 100 across 10. The detector is built and accruing.

Module: [`core/quote/depth_signal.py`](../../core/quote/depth_signal.py) · Informs **QUOTE**

## The question

Median top-of-book notional on this venue is **$460** in the current sample
(**$177** in the earlier one). Against that, a $5,000 resting order is not a
nuance — there is no reading in which it is noise. Somebody with size has an
opinion and has left it on the screen.

**When a large resting order appears, does the price then move toward the side
it appeared on?**

For QUOTE this is directly useful. A market maker does not have to forecast
games; it has to avoid being run over. If a whale on the bid predicts the mid
rising, that is a reason to skew quotes up — and skewing a resting order is
*free*, unlike crossing the spread.

## Definitions

A **whale** is a single resting level with notional $p \times q \ge \$5{,}000$.
Notional, not contracts: 10,000 contracts at 2¢ and 200 at 99¢ are very
different objects and only one is a bet.

**Appearing** means it was not there at the previous sampled observation. A
whale that has been resting ten minutes is not news. This matters more than it
sounds: at 1s sampling, counting presence rather than arrival would emit
hundreds of copies of a single wall and blow through any $n$-based gate on
nothing.

$$
\text{signal}(H) = \text{side} \cdot \big(m(t+H) - m(t)\big), \qquad \text{side} = \pm 1
$$

so positive always means "price moved toward the size".

## The pre-registered gate

Fixed 2026-08-02, before any number was computed.

| | |
|---|---|
| **PASS** | mean signed move at **+60s** > 0, **and** 95% CI (clustered by game) excludes zero, **and** n ≥ 100 appearances, **and** ≥ 10 games |
| **FAIL** | sample size met, but the mean or the interval fails |
| **NO DATA** | sample size not met |

**The economic bar is deliberately not the 6¢ round trip**, unlike
[run-overreaction.md](run-overreaction.md). This signal would skew a resting
quote, which costs nothing, rather than cross the spread. The right test is
whether the signal is *real*; its size is reported against the ~1.5¢
half-spread so that "real" and "useful" stay distinguishable. A signal worth
0.2¢ is real and useless, and the report says so.

## Two things that would otherwise corrupt this

**Sparse sampling must not read as an empty book.** The live recorder samples
depth often on the rungs nearest the money and rarely on the deep ones. If "not
looked at" read as "the whale left", every resumption of sampling would invent
a fresh appearance. `market_snapshots.book_tier` records which tier a row was
sampled under, so the two are distinguishable — see
[../infra/live-cadence.md](../infra/live-cadence.md).

**Depth carries its own timestamp.** `book_levels.captured_at` is when the book
call returned, which is *not* the parent snapshot's `captured_at` now that
depth runs on a slower loop than price. Inheriting the parent's would backdate
depth by seconds and let a book fetched *after* a move appear to have preceded
it. The whole question is about ordering, so this is load-bearing rather than
tidy.

## What the first sample looks like

Six games, gate is ten. Not a result.

| | |
|---|---|
| Top-of-book notional | median $460 · p90 $24,870 · p99 $44,827 · max $86,651 |
| Appearances | 46 (6 bid-side, 40 ask-side) |
| Mean whale notional | $14,836 |
| Observable at +30s / +60s | **0 / 0** |

The primary horizon has **no observations at all** — at a 910s median gap,
almost no appearance has a sample inside 120s of it. So this experiment has not
merely fallen short of its gate; at the old cadence it was close to
unmeasurable. It is the one of the three that most needs the 1s recorder.

The 6/40 bid/ask split is worth watching but means nothing yet.

## What would change the verdict

Ten games under the 1s recorder, where +30s and +60s become densely observed
rather than empty.
