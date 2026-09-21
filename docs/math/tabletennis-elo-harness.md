# Table-tennis Elo harness — specifications and decision rule, written before any fit

2026-09-15. This **specifies** open points in
`tabletennis-rating-preregistration.md`; it does not change what was
registered. Written before a single coefficient exists, and before the sample
can even produce one (zero matches are eligible today).

## 1. Token handling: `mars` and `demciva` stay first-class

712 token-appearances in the settled set are 704 at six characters, four at
seven (`demciva`) and four at four (`mars`).

**Decision: they are first-class tokens. No normalisation to six characters,
no padding, no truncation, no exclusion.** A 4-character token is the case a
naive fixed-width implementation breaks on, so it is pinned by a test rather
than tidied away: `test_a_fixed_width_parser_would_lose_a_player` asserts that
slicing tokens at six characters loses `mars` and mangles `demciva`, which is
the reason the parser splits on `-` and counts instead.

Normalising would be the worse error of the two available. Padding `mars` to
six characters invents a token that the venue never emitted, and truncating
`demciva` to `demciv` risks colliding it with a real player.

## 2. Prior-match counting: WITHIN competition, by construction

The registered spec already says "≥10 prior settled matches in the same
competition" and "a name that appears in two competitions treated as two
entities until proven otherwise". Both are implemented as **one decision**:
player identity is the pair `(competition, token)`, not the token.

So a token in two competitions is two players automatically — there is no code
path in which the two definitions can disagree. What still needs surfacing is
that it **happened**, because the two definitions are indistinguishable on
today's data (0 of 180 tokens cross competitions) and will diverge silently the
first time one does. `cross_competition_tokens()` returns them and the runner
prints them loudly; a test pins the detection.

It is a NOTICE, not a crash. Crashing would stop a run that the registered
spec says how to handle.

## 3. Match ordering: the venue's start time, not the slug's date

The slug carries a date and nothing finer, and 94% of the settled set falls on
one day. Day-granularity ordering would therefore force a choice between
excluding same-day matches from the prior (conservative, and it costs a whole
day of accrual) and including them (which leaks: a match cannot inform its own
prediction).

Neither is necessary. `market_snapshots.game_start_time` gives each match a
start instant, so "strictly before" is exact at second resolution and same-day
matches order correctly. **The harness orders on `game_start_time` and refuses
a match that has none** — counted, not dropped silently.

This corrects an optimism in the accrual projection I published in
`tabletennis-player-identity.md` §3. That projection compared each token's
cumulative match count against the threshold, which is right only if
same-day matches count toward same-day predictions. With exact ordering they
do, so the published curve stands — but had the answer been day-granularity,
every figure would have shifted one day later (50% between +2 and +3 rather
than +1 and +2). The curve depends on the ordering rule, and the ordering rule
was not specified until now.

## 4. Estimator: the registered interval AND the one I think is right

The pre-registration says "game-clustered interval". A match is a **dyad** —
two players, two clusters — and players recur across matches, so a
match-clustered SE treats repeated players as independent and is optimistic.
Per `dyadic-power-saturates`, n_eff → P/(2ρ).

**Both are computed and both are reported, with the estimator named on every
number.** The registered game-clustered interval is the one the
pre-registration's verdict is read from; the two-way player-clustered interval
is reported beside it. If they disagree materially, that disagreement is the
finding and the registered one is not quietly replaced.

`G_eff` is reported for both.

**CORRECTED before it was used, by running it on the positive control.** I
first wrote here that "a large Elo coefficient with a small design effect is a
defect signature". On the positive control the coefficient is **+1.09** and
deff is **1.17** — and there the effect is real by construction, so the
heuristic flags its own control. What deff tracks is the **imbalance of
appearances**: with balanced pairing the player clusters do not concentrate
the residuals and deff sits near 1 whether or not the effect is real. The
settled set is fairly balanced too (180 tokens, 712 appearances, max 9), so it
would likely have flagged a genuine result.

So deff is **reported next to the appearance distribution and is not a verdict
input**. The defect signature is narrower than I wrote: a large coefficient
with deff ~1 *on an UNBALANCED panel*, where a few players carry most
appearances and their clusters therefore should concentrate the residuals.
`test_a_small_design_effect_is_not_by_itself_a_defect_signature` pins the
correction.

## 5. The decision rule, pre-committed

Per competition, never pooled. All four thresholds are from the registered
spec except where noted.

| condition | value | source |
|---|---|---|
| predicted matches | ≥ 200 | registered |
| distinct players | ≥ 25 | registered |
| both players' prior matches | ≥ 10, same competition | registered |
| Elo coefficient interval | must exclude 0 | registered |
| interval used for the verdict | game-clustered | registered |
| **money arm: net P&L per contract** | **interval must exclude 0, null at ZERO net** | **registered 09-15** |
| money arm: entry | **last pregame quote, executable side** | registered 09-15 |
| money arm: minimum matches | **n = (1.96·49.1/X)², X = the REALISED cost of the bets placed** (see §7) | registered 09-15, X amended 09-21 |

**PASS** — ≥200 predicted matches, ≥25 distinct players, and the Elo
coefficient's game-clustered 95% interval excludes zero.
**FAIL** — the floors are met and the interval includes zero.
**NOT YET** — a floor is unmet. Report the counts and stop; this is not a fail.

**MONEY PASS / FAIL / NOT YET** — a second verdict, reported beside the first
and never collapsed into it. `core/tt/money.py`, `rule.money_verdict`.

The registered wording said the P&L secondary runs *only on PASS*. It now runs
ALWAYS, which is a strengthening and the reason is not stylistic: conditioning
the P&L on a favourable coefficient draw selects on the same outcomes the P&L
then measures, so a conditional secondary is biased upward by construction.

Its wording also sized the entry filter as "disagrees with the price by more
than the half-spread plus fee", written against a mid. Entry at the executable
price (buy YES at the ask, NO at one minus the bid) already pays the
half-spread, so the implemented filter is positive expected value at the price
actually paid. Adding the half-spread on top would be the same charge twice,
which is `anchor-is-bookkeeping`. For the same reason the null is **zero net,
not −cost**: every bet's own fee is already inside its P&L.

**Why a coefficient PASS is not a money answer.** The primary asks whether
ratings carry information beyond price. A model with a real 0.5pp edge passes
it and loses to the cost bar. PASS as a word implies the second question and
delivers the first, and the moment it fires that is how it will be read.

## 6. The achievable image of that rule, checked before it runs

Per `check-a-decision-rule-against-its-achievable-image`: project what this
design can produce onto the rule's branches.

| competition | settled (3d) | distinct players | can it ever reach the floors? |
|---|---|---|---|
| setkameua | 256 | 113 | yes — players already clear 25 |
| setkamecz | 48 | 32 | yes |
| setkamemd | 39 | 29 | yes |
| **setkawoua** | 14 | **6** | **NO — 6 players against a ≥25 floor** |

**One of the four competitions can never return PASS or FAIL.** With ~5
matches a day among 6 players, setkawoua cannot reach 25 distinct players
unless its pool grows, so its only reachable branch is NOT YET, permanently.
That is stated now rather than discovered as a mysterious silence later, and
it is a reason to report it separately rather than let it sit in a table of
four looking like a pending result.

For the other three the rule has both branches reachable: an Elo coefficient
is a continuous quantity whose interval can fall either side of zero at the
sample sizes these competitions reach, so neither PASS nor FAIL is
predetermined.

**Today every competition returns NOT YET**, because zero matches are
eligible — the busiest player has 9 priors against a floor of 10. A harness
that cannot run today is a harness debugged on the day it matters, so the
replay is required to produce zero eligible matches and exit cleanly, and
there is a test for exactly that.

## 7. The money arm's achievable image, and what it costs to cross

**The cost bar, measured 09-15 on prod (read-only), `market_slug LIKE
'aec-setka%'`, September partitions.** Three axes have to be named at once:

| population | n | median spread | mean fee at ask |
|---|---|---|---|
| all pregame quotes, mid .2–.8 | 42,485 | 17.00c | 1.266c |
| **LAST pregame quote, mid .2–.8** | **724** | **2.00c** | **1.388c** |

The book tightens into the start — the median last quote is **8.2 minutes**
before it and most are one cent wide. Both rows are correct computations of
different populations, and the 17c row describes listings nobody trades.
Pooling them would have closed the last live path in the programme on a number
about listings. The 724 and the 2.00c reproduce §0bc exactly.

**The fee term does not, and neither does my own first correction of it.**
§0bc gave 1.22c as the "median taker fee 0.06·p·(1−p) at that mid" over the
724, and no statistic of that population produces it — mean 1.411c at the mid
and 1.388c at the ask, median 1.462c and 1.451c, against a median mid of 0.500
where the formula must give ~1.5c. Its actual origin, from its author: the
median of the SUM (2.248c) with the median half-spread subtracted out.
**Medians do not add, so 1.22c never existed as a quantity.**

I then published **2.39c = median half-spread 1.000 + mean fee 1.388**, which
is the same error in a new costume. The coherent statistics are the two TOTAL
columns, and nothing else in this table may be added across:

| over the 724, at the ask | median | mean |
|---|---|---|
| half-spread | 1.000c | **2.339c** |
| fee | 1.451c | 1.388c |
| **TOTAL** | **2.260c** | **3.728c** |

*(p25 1.962c, p90 4.923c.)* **The mean half-spread is 2.34× the median**: there
is a long right tail of wide-quoted matches and that tail is the entire
difference between the two totals. Three revisions of one number by two people,
every version a different mixture of the same 724 rows, so per
`three-revisions-is-the-signal` what is registered is the **range 2.26c to
3.73c** rather than a fourth point.

**Where a strategy sits inside that range is a property of its selection, which
does not exist yet.** Bet every match and you pay the mean; bet typical ones and
you pay near the median; a model bets where it disagrees with the price, which
is neither. So the realised cost of the matches actually bet is a first-class
output of the arm (`MoneyResult.cost_mean`), not a footnote — and if the model
preferentially bets wide quotes it pays the tail, which makes even 3.73c
optimistic. There is a test for exactly that selection.

**AMENDED 2026-09-21 — the bar moved twice more, so the code carries none.**
Re-measured on the venue's own coefficient (`market_snapshots.fee_coefficient`
= 0.069500, zero variation on 12,713 table-tennis rows in twelve hours; the
0.06 above and in every figure before 09-21 was never checked against that
field):

| window | n | med half | mean half | MED total | MEAN total |
|---|---|---|---|---|---|
| 09-13..09-15 (fee 0.06) | 724 | 1.000c | 2.339c | 2.260c | 3.728c |
| **09-18..09-21 (fee 0.0695)** | **1,339** | **0.500c** | **4.499c** | **2.238c** | **6.065c** |

The median total barely moved; **the mean grew 63%**, because the board nearly
doubled and its tail of wide-quoted matches grew with it — the mean half-spread
is now **9× its median**. Two independent reasons for one number to move in
three days, on top of two constants already retracted for crossing statistics
(2.22c, 2.39c).

**So the fourth revision is not a fifth number: `core/tt/money.py` carries no
cost-bar constant at all.** `required_n` takes `resolution` with no default and
the runner passes what the arm ACTUALLY PAID — `MoneyResult.cost_median` as the
strict gate, `cost_mean` as the loose one. That cannot go stale, it is measured
on the same rows as the P&L it gates, and it answers the only question the gate
is for: can this sample resolve an effect the size of our own costs. A test
drives two selections with identical P&L and different books and pins that they
get different targets.

At today's costs that is **~1,850 matches** to resolve the median and **~252**
to resolve the mean — against the 1,814 and 667 registered on 09-15. The mean
end moved from "eight days of accrual" to "three", which is the practical
content of the tail growing: a strategy that pays the tail needs less data to
prove it loses.

**The power, stated before any fit.** Per-contract P&L noise is the binary
outcome's and therefore irreducible. Measured two ways, one decimal apart: the
357 settled matches in `tabletennis-player-identity.md` give a per-match SE of
0.026, so sd = 0.026·√357 = **0.491**; √(p(1−p)) at the observed mean price
0.5226 is 0.4995.

| n | SE | 95% half-width | MDE at 80% power | what this n is |
|---|---|---|---|---|
| 200 | 3.47c | ±6.80c | 9.73c | the signal floor |
| 667 | 1.90c | ±3.73c | 5.33c | resolves the MEAN bar |
| 724 | 1.82c | ±3.58c | 5.11c | today's whole last-quote population |
| 1,814 | 1.15c | ±2.26c | 3.23c | resolves the MEDIAN bar |
| 9,261 | 0.51c | ±1.00c | 1.43c | resolves 1c |

**At the registered 200-match floor the money arm has exactly ONE reachable
verdict.** Its interval is ±6.80c against a bar of 2.26c–3.73c — wider than
the bar by 1.8× even at the bar's generous end — so every achievable mean,
−50c through +50c, returns NOT YET. That is the same dead-branch
finding §6 records for setkawoua, one arm over, and there is a test that fails
if any mean at n=200 returns anything else.

**The registered money floor is a FORMULA, not a count**:

    n = (1.96 · 49.1 / X)²      X named, in cents

| X | n | what X is |
|---|---|---|
| 2.260c | **1,814** | median total cost |
| 3.728c | **667** | mean total cost |

A factor of 2.7 from one unstated word, which is why `money.required_n` has no
default for it and raises a `TypeError` instead. A bare "1,618 matches" — my
own first version — reads as a property of the data and is a choice of target;
that is the shape which survives review.

The sd's own precision is the smaller worry and worth stating so it is not
chased: 0.026 is published to two significant figures, so 0.49 / 0.491 / 0.4913
move the floor by 3 and then 1 match, against the 1,147 that choosing X moves
it. Quote ~1,810, never 1,814. All of these ignore clustering and are **lower
bounds** — players recur, so n_eff < n (`dyadic-power-saturates`).

At setkameua's ~85 settled matches a day (§6: 256 in three days) that is about
**21 days** against the median bar and **8** against the mean, and it is the
only competition with the volume to get there either way.

**The most likely outcome is SIGNAL yes / MONEY not yet, and that is a
finding.** On the reference numbers it is also the honest expectation that
MONEY, once powered, comes back negative: the measured pooled price-vs-realised
gap is −4.36pp at |t| ≈ 1.7, so if half of it were systematic and capturable
that is ~2pp against a bar of 2.26c–3.73c — **below both coherent statistics,
so negative rather than marginal**. §0bc's "marginal, not hopeless" rested on
2.22c, a number that never existed. But the sign turned on less than one tick
across three revisions, which argues for measuring the arm rather than
believing any of the words — mine included.
