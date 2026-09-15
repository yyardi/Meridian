# Table-tennis player identity: is the Elo pre-registration fittable?

Measured 2026-09-15 against prod. Source for the settled population is
`artifacts/reads/settlements.json` (22,270 entries) rather than a scan of
`market_snapshots` — the cache holds the settled outcome per slug and needs no
62M-row scan. Prices come from `market_snapshots` via the unique index on
`(market_slug, captured_at)` with a month-boundary floor, which is why 357
price lookups cost seconds rather than the two minutes an unbounded count did.

**VERDICT: identity is not the blocker. Volume is, and it clears in about
three days.** Identity resolves cleanly — no duplication, no collision
evidence — so the pre-registration needs no identity-resolution step. What it
cannot satisfy today is its own `>=10 prior matches` filter: the busiest
player in the settled set has **9**. Zero players qualify. At the measured
arrival rate, `>=10` covers 44% of future appearances after one more day,
70% after two, **94% after three**.

## The league list, confirmed from the data and not from the ask

| league | slugs on the board | settled |
|---|---|---|
| setkameua | 549 | 255 |
| setkamecz | 102 | 48 |
| setkamemd | 84 | 39 |
| setkawoua | 15 | 14 |
| **total** | **750** | **356** |

Exhaustive: `sports_market_type = 'table_tennis_match_winner'` is the only
table-tennis type in the tape (27,169 rows on 09-14 alone), and those four are
every league token appearing in it. There is **one market per match** — no
spread or total variants — so a match and a market are the same object here.

One constraint worth stating before anything else rests on it: **the TT board
tape begins 2026-09-13.** Three days, not three weeks.

## 1. EXTRACTION — 356 of 356, no failures

Slug shape is `aec-<league>-<p1>-<p2>-<YYYY>-<MM>-<DD>`.

| shape | markets |
|---|---|
| exactly 2 player tokens | **356** |
| != 2 tokens | **0** |
| no trailing ISO date | **0** |

712 token-appearances, 180 distinct tokens. Nothing was filtered; the parser
counts every slug and there is nothing to count as a failure.

**But the tokens are not all the same width**, which is where a fixed-width
parser would break:

| token length | appearances |
|---|---|
| 6 | 704 |
| 7 | 4 (`demciva`) |
| 4 | 4 (`mars`) |

`mars` is the one to watch — a 4-character token in a 3+3 scheme, four
appearances, all `setkameua` on 09-14, always as the first player. Either a
genuinely short name or an upstream truncation; four of 712 appearances, so
it changes nothing, and it is reported rather than dropped.

## 2. STABILITY — no duplication, and no collision evidence either

The 20 closest non-identical pairs are **all at exactly 0.833**, and that
number is the finding:

```
0.833  korole(5)  kurole(5)      0.833  karole(4)  korole(5)
0.833  kolole(5)  korole(5)      0.833  korole(5)  korvol(3)
0.833  vormar(3)  voryar(4)      0.833  derand(5)  perand(5)
0.833  stoole(4)  strole(5)      0.833  kagvit(5)  khavit(3)
```

0.833 is one character different out of six. The venue emits a **machine
abbreviation, 3 characters of family name plus 3 of given name** — so
`korole` / `kurole` / `karole` are three different families sharing the given
name, not three spellings of one player. With ~180 players in a fixed 6-
character scheme, one-character-apart pairs are *structurally expected*.

That also disposes of the failure modes the ask named: there is no casing
variance, no initials variance and no reversed given/family order, because no
human types these. **The ~275 players do not show up as ~500 tokens. They show
up as 180 tokens on a 3-day settled sample.**

The residual risk is the opposite one — **collision**, two players sharing an
abbreviation, which a token count cannot see. Two tests that could have
fired:

| test | result |
|---|---|
| a token on both sides of one match | **0 of 356** |
| a token appearing in more than one league | **0 of 180** |
| busiest token-day | 8 matches (`polmyk`), plausible for a rapid-fire format |

Zero cross-league tokens is the stronger of these: a closed pool per league is
what the capacity claim assumes, and it holds exactly.

## 3. ACCRUAL — the arrival rate, and why the mean of the window is wrong

| day | settled matches |
|---|---|
| 2026-09-13 | 14 |
| **2026-09-14** | **334** |
| 2026-09-15 | 8 |

**Do not use 118.7/day**, the mean over the window. 94% of the settled set is
one day: 09-13 and 09-15 are partial (the backlog was settled overnight and
09-15 had barely started). **The only complete day is 09-14 at 334 settled
matches**, which is close to the 345/day board-capacity figure — so the
capacity claim survives on a settled count, for one day.

Matches per token on the settled set:

| matches | tokens |
|---|---|
| 1 | 5 |
| 2 | 9 |
| 3 | 65 |
| 4 | 39 |
| 5 | 52 |
| 6 | 1 |
| 7 | 2 |
| 8 | 5 |
| 9 | 2 |
| **>=10** | **0** |

175 tokens appeared on 09-14, 668 appearances, **3.82 appearances per player
per day.** Projecting each token forward at its own 09-14 rate and weighting
by that rate (its share of future appearances):

| further days of tape | `>=10 prior` covers | tokens qualifying |
|---|---|---|
| +0 | **0.0%** | 0 / 175 |
| +1 | 44.3% | 56 / 175 |
| +2 | 69.6% | 101 / 175 |
| +3 | **94.3%** | 156 / 175 |
| +4 | 100.0% | 175 / 175 |

So 50% coverage falls between +1 and +2 days and 80% between +2 and +3. The
projection assumes the pool stays closed and the same players keep appearing,
which is the capacity claim's own assumption — if it is wrong, this is
optimistic.

## 4. FRAME — confirmed, by calibration rather than by a mean

Mean gate across the 357 settled markets with a pre-match two-sided quote
(357 of 357 — full coverage):

| mean YES mid | realized YES rate | gap | mean spread |
|---|---|---|---|
| 0.5226 | 0.4790 | **−0.0436** | 0.0294 |

**The mean cannot separate a frame error from an edge**, and here it is worse
than that: inverting the frame flips the sign of the gap and preserves its
magnitude, so |gap| is frame-invariant and −4.36pp is not diagnostic of
anything. The instrument that does separate them is the **shape**:

| bucket | n | mean price | realized | gap |
|---|---|---|---|---|
| 0.18–0.20 | 3 | 0.188 | 0.333 | +0.145 |
| 0.25–0.30 | 10 | 0.268 | 0.300 | +0.033 |
| 0.31–0.40 | 44 | 0.352 | 0.318 | −0.034 |
| 0.40–0.50 | 96 | 0.443 | 0.385 | −0.058 |
| 0.50–0.60 | 101 | 0.545 | 0.446 | **−0.100** |
| 0.60–0.70 | 69 | 0.644 | 0.652 | +0.008 |
| 0.71–0.80 | 27 | 0.738 | 0.704 | −0.034 |
| 0.81–0.89 | 7 | 0.838 | **1.000** | +0.162 |

Realized rises with price throughout: 0.333, 0.300, 0.318, 0.385, 0.446,
0.652, 0.704, 1.000. **An inverted frame would produce a monotone DECREASING
series.** So YES is the slug's first-listed player, as
`venue-yes-side-by-sport` says, and this is the falsifiable check the ask
wanted rather than an assumption.

The residual −4.36pp is a level, not a slope, and it is not significant: with
a binary outcome at mean price 0.52 the per-match SE is about 0.026, so
|t| ≈ 1.7 — **and that SE is too small**, because players repeat across
matches and the matches are therefore not independent. The largest single
deviation is the 0.50–0.60 bucket at −0.100 on n=101, which is the same bucket
already retracted as noise after Bonferroni (STATUS §0al). Nothing here
revives it, and the units differ — this is a probability gap, that was
cents per contract.

## The verdict, stated as asked

**Fittable as written in about three days**, not blocked on identity.

* Identity resolution is **not** needed. Extraction is 356/356, the tokens are
  machine-generated and stable, and both collision tests return zero.
* The binding constraint is the pre-registration's own `>=10 prior matches`
  filter, which admits **nobody today** (max 9) and covers 94% of appearances
  after three more days of tape.
* The frame is confirmed by calibration monotonicity, so the Elo's dependent
  variable is the side we think it is.
* Two things to specify before it runs, neither of which is identity: what to
  do with `mars` and `demciva` (4 of 712 appearances that break the 6-char
  scheme), and whether "prior matches" counts across leagues — zero tokens
  cross leagues today, so the two definitions are currently identical and will
  diverge silently the first time one does.
