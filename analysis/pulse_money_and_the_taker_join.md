# PULSE money, and why the taker threshold is the wrong bar

## ★ 1. PULSE IS 100% PASSIVE. IT NEVER CROSSES.

    side=yes  limit_price == market_bid  on 100.0% of 1,342 entries
    side=no   limit_price == market_ask  on 100.0% of 1,632 entries

`limit_price` is on the **YES scale for both sides** — corr with the YES mid is
+0.995 on each arm, and +0.91/+0.95 with `fair_value`, which is a YES
probability. So `side` is buy-YES versus sell-YES on one price scale, and both
arms **join the touch rather than cross it.**

**A taker threshold that charges the half-spread is not this engine's
threshold.** d5's `e_min(p) = s + 0.06·a(1−a)` prices crossing. PULSE does not
cross. Its economics are **maker** economics — the s/2 revenue against adverse
selection that the QUOTE programme measured and closed at 23.7% benign against
48% needed.

That is not a softer conclusion than "λ* = 0.15 does not clear 2.69pp". It may
be a harder one: the passive route was closed this afternoon on its own
evidence.

## ★ 2. MY +6.88pp MONEY FIGURE WAS CONTAMINATED BY ORDERS THAT NEVER TRADED

    ALL entries         n 2,974  G 34   +6.880pp [ +2.774, +10.985]  excludes 0
    FILLED only         n 1,944  G 34   +4.761pp [ -1.455, +10.978]  SPANS ZERO
    WITHDRAWN, unfilled n 1,019  G 33  +10.857pp [ +7.554, +14.160]  excludes 0

**34.3% of entries never traded.** Scoring them counts P&L on orders that do
not exist. On the fills we actually got, the money statistic is **+4.761pp and
does not clear zero.**

**And the withdrawn orders are where the money is.** +10.86pp on orders that
never traded against +4.76pp on those that did — the adverse-selection
signature in its plainest form: *the bets we wanted are the ones nobody would
take.* This is the same finding as the withdrawal autopsy, now visible in P&L
rather than in fill rates.

## 3. What the numbers mean for the join

The point estimate on filled entries, +4.76pp, sits **above** d5's 2.69pp taker
threshold — but the interval spans zero, so it resolves nothing, and the
threshold is the wrong bar for a passive engine in any case.

**The joinable question is not "does λ* clear the taker threshold" but "does the
passive fill population pay after adverse selection".** That is answerable on
this data and it is what §2 measures: not yet, at G=34.

## 4. A convention check of mine that gave the wrong verdict

Deciding whether `limit_price` was the YES price or the price of the side
bought, my first test compared mean distances: |lp − mid| = 0.0323 against
|lp − (1−mid)| = 0.0304. **Nearly tied, and it picked the wrong one.** The
correlation was decisive in the opposite direction (+0.995 with the YES mid,
−0.995 with 1−mid), and the exact bid/ask equality settled it outright.

**A test that is nearly tied is not a test.** I nearly inverted the sign on
1,632 rows on a 0.002 margin.
