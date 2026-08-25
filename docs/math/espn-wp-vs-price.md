# ESPN win probability vs the live price — registration

**Status: REGISTERED 2026-08-25, NOTHING COMPUTED.** This document is written
before the test is run. Nothing above the results line may be edited after data
accrues — append below it instead.

Registered by the research agent, who runs the test. This page is the exam, not
the answer; Builder D landed it and computed nothing.

## The registered text, verbatim

Recorded exactly as written, including the disclosure. It is reproduced rather
than paraphrased because a registration that has been tidied is no longer the
thing that was registered.

> ESPN-WP vs the live price. At every recorded ESPN win-probability play in
> signal-covered games, pair home_win_pct (slug-first frame via V20 +
> ESPN-resolved home/away) with the winner-market two-sided mid within <=10s.
> Primary: logistic outcome ~ logit(mid) + k*logit(espn_wp); k's 95% CI
> clustered by game; floor >=15 signal-covered joined games. PASS = CI excludes
> zero (either sign). Second clause computed ONLY on PASS, declared now:
> money-at-price at the 4.70c in-game concession; rule = trade the side ESPN
> favors when |espn_wp - mid| >= 5c, hold to settlement, unit stake,
> game-clustered ROI. Disclosure: motivated by the seen v3a diagnostic (ESPN WP
> beat both arms on matched late winner ticks at n=11); the archive's prices
> were seen in prior studies; this joint quantity has never been computed.
> Harness will be mutation-tested (calibrated synthetic must read k~0) before
> the real data run.

## What is fixed by the text above

Restated for a reader who does not want to parse the paragraph — this section
adds nothing and constrains nothing beyond the verbatim text, and where the two
appear to differ the verbatim text wins.

* **Pairing rule** — every recorded ESPN win-probability play in a
  signal-covered game, matched to a winner-market two-sided mid **within 10
  seconds**. `home_win_pct` in the slug-first frame (V20 plus ESPN-resolved
  home/away), which is the frame that has silently inverted results before.
* **Primary statistic** — `outcome ~ logit(mid) + k·logit(espn_wp)`, with **k**
  the quantity of interest: does ESPN's number carry information the price does
  not already hold? 95% CI **clustered by game** (C4).
* **Floor** — **≥ 15 signal-covered joined games.** Below it there is no
  verdict, only counts.
* **PASS** — the CI on k excludes zero, **either sign**. A negative k is a
  finding, not a failure.
* **Second clause, computed only on PASS and declared now** — money-at-price at
  the **4.70¢** in-game concession; trade the side ESPN favours when
  |espn_wp − mid| ≥ 5¢, hold to settlement, unit stake, game-clustered ROI.
  Declaring it now is what stops it from becoming a second attempt if the first
  clause disappoints.
* **Harness mutation-tested first** — a calibrated synthetic must read k ≈ 0
  *before* the real data run. A harness that cannot produce a null on data with
  no signal cannot be trusted to report one on data that has some.

## Why the disclosure paragraph stays

The disclosure says the test was **motivated by a diagnostic that was already
seen** (ESPN WP beating both arms on matched late winner ticks, n = 11), and
that the archive's prices have been seen in prior studies.

That is not a caveat to be tidied away in a later edit. It is the honest
position, and it is the one thing a future reader most needs in order to weigh
the result: this is not a hypothesis that arrived from nowhere, it is one
prompted by an observation, and the defence is narrower than "we had no idea" —
it is that **this joint quantity has never been computed**. A reader can accept
or reject that defence, but only if it is visible.

Recording it verbatim also means nobody has to trust a summariser's judgement
about which hedges mattered.

## Relation to the ledger and to #18

Ledger row **#19** carries the same registration in the hypotheses table. The
neighbouring result is #18, which asked a structurally similar question about a
different signal — whether boundary deviation carries information beyond the
live price — and returned **FAIL because the effect was real and already
priced**, logit 0.881 on the live mid.

#18 is the reason k is the right statistic here rather than a raw correlation:
a signal can be genuinely predictive and still add nothing once the price is in
the regression. That is the outcome this design is built to detect, and the
second clause exists precisely so that a PASS is not automatically read as
tradability.

---

*Registered 2026-08-25. Results append below this line, never above it.*


## RESULT — PASS on stated terms, NOT TRADABLE, 2026-08-25

Run by the research agent. **5,847 pairs across 17 settled joined games**, floor
(15) met. Harness mutation-tested before the real run, as registered.

| | |
|---|---|
| **k** (coefficient on `logit(espn_wp)`) | **+2.54, 95% CI [+0.41, +4.66]** — excludes zero |
| registered verdict | **PASS** |
| r between the two regressors | **0.973** |
| mid's joint coefficient | **spans zero** |
| pre-declared money clause | **−14.3%, CI [−57, +28]** |

### The PASS is real and it is not what it sounds like

k's interval excludes zero, so the registration passes on its own terms and is
recorded that way. But the two regressors correlate at **0.973**, and at that
collinearity the fit cannot cleanly attribute information to either source —
which is why **the mid's own coefficient spans zero in the same regression.**
Neither variable is separately identified. The honest reading is not "ESPN beats
the price"; it is **two near-duplicate readings of the same quantity**, one of
which happened to take the coefficient.

That is also why k's interval is so wide (+0.41 to +4.66): the design has little
discriminating power left at r = 0.973. A PASS obtained in that regime is a
weaker claim than a PASS obtained with independent regressors, and it should be
read as one.

### The money clause is why this was declared in advance

Computed only on PASS, exactly as declared before the data run:
**−14.3%, CI [−57, +28]**, and **disagreements of ≥5¢ favour the market, not
ESPN**. When the two sources diverge, the price is the one that turns out to be
right.

Had the trading test been designed after seeing k = +2.54, there would have been
every temptation to pick a threshold that flattered it. It was fixed first, so
the −14.3% is a result rather than an argument.

### Why k, and not a correlation — now with the number

The registration section above argued that a coefficient on top of `logit(mid)`
is the right statistic because #18 showed a signal can be real and still add
nothing once the price is in the regression. **This result puts a number on that
argument.**

ESPN's WP and the live mid correlate at **r = 0.973**. A raw correlation of ESPN
WP against the outcome would have screamed signal. The joint fit says the two are
near-duplicate readings of the same quantity. Run as a correlation, this study
would have produced a confident, tradable-looking, wrong answer — and the money
clause below is what catches it either way.

### Same family as #16

#16 also passed its stated terms and was not tradable — it inverted once
anchored on a team-aware baseline. #19 passes and is not tradable because the
signal duplicates the price. Different mechanisms, same lesson: **the gate
answers the question it was written to answer, and that question is not "should
we trade this".**

---

*Result appended 2026-08-25. Nothing above the results line was edited.*
