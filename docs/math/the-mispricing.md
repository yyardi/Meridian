# The mispricing — 2026-09-04

**The first positive finding this program has produced.** It is not a
market-making result yet; it is the FAIR VALUE that market making requires and
that our quoter has never had.

## The measurement

One observation per resolved market, taken independently of where our engine
filled — the fill-conditioned version of this test gives the OPPOSITE SIGN
(+5.86¢), which is exactly how badly selected our fills are, and is why this
was measured unconditionally.

| sampled at | mean price | actual settlement | bias |
|---|---:|---:|---:|
| **first observation** | 49.62¢ | 42.74¢ | **−6.88¢** |
| **last observation** | 42.68¢ | 42.74¢ | **+0.06¢** |

**Game-clustered over 88 games: −6.88¢, CI [−12.22, −1.53]. Excludes zero.**

**Early prices are systematically ~7¢ too high, and by the end of a market's
life they are calibrated to six hundredths of a cent.** The board converges to
truth; the error lives at the start and decays.

Direction matches the Kalshi literature (retail overbets YES; the resulting
behavioural surplus is what pays market makers there). Persistence by market
age: −4.71¢ at 0–1h, −2.05¢ at 6–24h, −6.14¢ at 24–48h. *The 1–6h bucket reads
−25.84¢ on a 16% settle rate and is a selected subset — do not use it.*

## Why our quoter cannot capture any of it

**The first observation carries a median spread of 18¢.** Crossing it costs ~9¢
to capture ~7¢, so a TAKER cannot have this — the same trap that killed the
phantom dip signal (+0.62¢ at an unreachable price, −2.70¢ after crossing).

**But a maker does not cross. A maker posts.** In a 40/58 market with a fair
value of 43, you offer at 50: inside the spread, seven cents above fair. Being
lifted there is the trade.

**Our quoter joins the touch and has NO independent fair value.** It prices off
the market's own mid, which is the very thing measured to be wrong. A market
maker without a pricing model is a mirror that pays for the privilege:

- it quotes **symmetrically**, so it cannot express "YES is rich here";
- it quotes **at the touch**, so in an 18¢ book it stands 9¢ from fair on both
  sides rather than posting inside on the favoured side;
- it has **no inventory skew, no width response to uncertainty, no pull on
  information** — the three things every real maker does.

**The conclusion "touch-joining loses" stands and was never the interesting
question.** It is a statement about the most naive maker that can be written.

## What this licenses building

1. **An independent fair value.** We already have one: the PULSE projection.
   It has never been wired into the quoter.
2. **Asymmetric quoting around fair value**, not around the market's mid.
3. **Post inside the spread** where the book is wide, on the side the bias
   favours; the 16–18¢ early books are room, not danger.
4. **Toxicity gate.** The Kalshi study finds one-sided order flow predicts
   maker losses; we now record trade tape and Kalshi volume, so this is
   measurable rather than aspirational.

## What would refute it

Selection into `resolved_outcomes`; a first observation that is a listing stub
rather than a live book; and the possibility that the wide early spread is wide
*because* nobody will trade there — in which case posting inside it fills only
when someone informed arrives, and the edge is illusory. **The forward test is
posting inside and measuring the fill rate.**

**No in-sample result justifies capital. The forward test is the evidence.**
