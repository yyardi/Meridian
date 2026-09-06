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

---

# Re-costed: money on FILLED orders, against the MAKER bar

**MY VERSION, pending reconciliation with d5. Not for broadcast.**

Anchor: filled orders only, side-signed P&L on the YES scale at the quoted
`limit_price`, game-clustered.

    n 1,944 filled   G 34   fill rate 65.4%   57.2 filled bets/game
    P&L/contract  +4.761pp  [-1.455, +10.978]   half-width 6.216pp

## The maker bar is not the taker bar

PULSE joins the touch, so it pays neither the half-spread nor the 0.06·p(1−p)
taker fee, and d5 verified a maker **rebate** of −0.0125·p(1−p) — a credit.

    p       taker threshold      maker break-even
    0.50        2.69 pp             -0.31 pp  (rebate)
    0.30        2.45 pp             -0.26 pp
    0.20        2.15 pp             -0.20 pp

**The bar PULSE must clear is approximately zero, not 2.69pp.**

## Games required, G = 34 × (6.216 / target)²

    effect to resolve          games   weeks CFB@54   date
    current point +4.76pp         58        1.1 w     2026-09-13
    taker bar      2.69pp        182        3.4 w     2026-09-29
                   2.00pp        328        6.1 w     2026-10-18
                   1.00pp      1,314       24.3 w     2027-02-23
    maker break-even 0.31pp    13,672      253   w     2031

## ★ THE DECISION NUMBER IS 58

**Whether PULSE's passive fills make money is resolvable in about 58 games —
one to two CFB Saturdays**, not a season. That is the question the operator can
act on this week.

Two things it does **not** say:

* 58 games resolves *the current point estimate* from zero. If the true effect
  is smaller than +4.76pp the ladder above applies, and at 1pp it is a season.
* It does **not** establish the effect clears any particular bar — only that it
  is distinguishable from zero. Since the maker break-even is ~zero, those
  happen to coincide here, which is why the maker framing matters.

The 54/week CFB rate is the 94% WNBA capture applied to football and is an
**upper** estimate. The 09-12 slate tests it, and that test is upstream of this
table.

---

# ★ CONVENTION SENSITIVITY: the 58 is not robust

ce asked whether the money half-width is convention-sensitive the way lambda*
was (0.219 -> 0.364, with the bar between). **It is worse.**

    convention                      n      point       95% CI          hw    G@point
    all filled rows (mine)      1,944   +4.761pp  [-1.46,+10.98]   6.216pp        58
    earliest per market           399   +2.516pp  [-4.27, +9.30]   6.786pp       247
    latest per market             399   +0.449pp  [-5.32, +6.22]   5.769pp     5,622
    earliest per (market, side)   551   +3.156pp  [-0.18, +6.49]   3.335pp        38
    latest per (market, side)     551   +3.040pp  [+0.35, +5.74]   2.695pp        27
    earliest per game              34   -3.294pp  [-17.2,+10.61]  13.905pp       606

    point estimate  -3.294 to +4.761 pp   (spread 8.055pp, AND IT CHANGES SIGN)
    half-width       2.695 to 13.905 pp
    games at point      27 to 5,622       (a 208x range)

**One convention excludes zero** — `latest per (market, side)`, +3.040pp
[+0.345, +5.735]. **It is also the convention with a look-ahead problem**: the
last decision in a market is taken when the game has moved toward its outcome,
which is the defect diagnosed on the horizon ladder. Its significance should
not be trusted, and it is the only significant cell of six.

## ★ BUT UNLIKE lambda*, THERE IS A PRINCIPLED TIEBREAK

For a **forecast** comparison, deduping is right: many rows share one outcome,
so counting them all double-counts the evidence. That is why the Brier work
deduped.

**For a MONEY statistic the question does not arise the same way. Every fill is
a separate real trade with real P&L.** Deduping discards realised money. If we
filled 57 times in a game we earned or lost on all 57, not on one.

So **all filled rows is the correct population for the point estimate** — it is
the money actually made — and the shared-outcome dependence is handled where it
belongs, in the game-clustered interval rather than by throwing away trades.

**That is a principled reason to prefer one convention, and no such reason
existed for lambda*.** The sensitivity is real and must travel with the number,
but it is not the same situation as a statistic with no canonical form.

## What this does to the ladder

The **58 stands as the estimate under the defensible convention**, and the
ladder should be quoted with the range attached: *the same question costs
27–5,622 games depending on how fills are counted, and the count that
corresponds to money earned gives 58.*

Anyone quoting 58 without that range will budget wrong, and anyone quoting the
+3.040pp significant cell is quoting the one convention with look-ahead in it.

---

# JOINT VERSION — B and d5 reconciled

## The number

**58 games** (d5 independently: 56; the gap is sandwich implementation only).
Point estimates match to three decimals.

    filled n=1,944   G=34   fill rate 65.4%   57.2 bets/game
    row-weighted     +4.761pp  [-1.455, +10.978]   hw 6.216pp   ->  58 games
    game-weighted    +2.451pp  [ -4.33,  +9.24]    hw 6.784pp   -> 260 games

**The estimand must be named with the number: 4.5x sits between them.**
Row-weighted is right for a money question — you earn per bet, and a 146-bet
game genuinely contributes more money than a 1-bet game — but game-weighted is
defensible and gives 260, the difference between "one to two Saturdays" and
"most of a season".

## ★ CORRECTION: THE MAKER REBATE DOES NOT EXIST, AND I CITED IT AS d5's

I wrote "d5's verified maker rebate of −0.0125·p(1−p)" and built a ladder row
on it. **Two errors.** It is C7, it was **RESOLVED 2026-08-25 as unobserved**,
and **d5 helped land the retraction** — so I attached a peer's name to a claim
they had personally refuted.

The repo is unambiguous and I checked it rather than argue:

* C7: *"the advertised maker rebate remains unobserved in this account across
  its entire history; the zero default was right. **θ_maker = 0 stays correct
  everywhere**"*
* V24: the observed credits were a **50%-of-own-taker-fees promo**, window
  2026-03-29 → 05-10, **ended**
* V9: *"**No corresponding maker field exists**"*
* Code: `theta_maker = 0` default in `fills.py` and `wallet.py`

**Break-even is exactly 0.00pp, not a −0.31pp credit.** The ladder's bottom row
(13,672 games at 0.31pp) was chasing a target derived from a credit that does
not exist. **The headline 58 is unaffected** — it resolves the point estimate
from zero either way, and zero is now the bar for a cleaner reason.

I propagated this from a manager's message without checking it against
`findings.md`, which had the resolved entry the whole time.

## ★ THE FRAGILITY, AND A MEASURE THAT DISAGREED

d5's finding reproduces:

    games <=20 bets   10 games   mean P&L  -9.84pp   (d5: -10.97)
    games >=80 bets   13 games   mean P&L  +2.52pp   (d5: +2.67)
    corr(game size, game mean P&L) = +0.166          (d5: +0.166, exact)

**Where the engine bet little, it lost heavily per bet**, and row-weighting
down-weights exactly those games. Money-correct, and it makes the 58 conditional
on that bet-allocation pattern holding.

**One measure disagreed: "top 3 games as a share of net total" — d5 −9%, me
+65.7%.** Neither is wrong; **the measure is unstable.** Net P&L is a small
difference of large offsetting sums (+173.3 positive against −80.8 negative,
net +92.6), so any subset's "share of net" can exceed 100% or flip sign on an
ordering choice.

**The stable version is leave-one-game-out**, and it supports d5's conclusion:

    full sample                     +4.761pp
    LOGO range              +3.259 to +6.152pp
    largest single-game influence      1.503pp  (32% of the estimate)
    sign flips on dropping any one game:     0

**No single game carries the result and the sign survives dropping any one of
the 34** — d5's conclusion, on a measure that does not move when you look at it
differently.

## What the operator can act on

**The directional question is answerable in one to two CFB Saturdays if the
effect is near the measured point, and in most of a season if it is near 1pp.**
The ladder is the object, not the 58:

    +4.76pp (measured point)      58 games        2.69pp    182
     2.00pp                      328              1.00pp  1,314

And **09-12 gates all of it** — every date assumes a 94% capture rate measured
on WNBA and applied to football, which Saturday tests.
