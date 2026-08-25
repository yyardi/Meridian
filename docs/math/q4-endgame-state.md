# Q4 endgame-state FV calibration — registration

**Status: REGISTERED 2026-08-25, NOTHING COMPUTED.** This document is written
before the test is run. Nothing above the results line may be edited after data
accrues — append below it instead.

Registered by the research agent, who runs the test. This page is the exam, not
the answer; Builder D landed it and computed nothing.

## The registered text, verbatim

Recorded exactly as written, including the disclosure. It is reproduced rather
than paraphrased because a registration that has been tidied is no longer the
thing that was registered.

> **PURPOSE.** Does adding endgame state — possession, bonus, timeouts — to the
> pregame-anchored win-curve FV improve Q4 win-probability calibration? Serves
> exit quality (the EV stop), not entries. A STATE test on the surviving side of
> the F8 bound; the possession leg is specifically at risk from that bound and
> this registration says so before any number exists.
>
> **ARMS.**
>
> - base: pregame-price-anchored Gaussian win curve, sigma 2.628*sqrt(minutes),
>   venue (exact) clock. Exact formula pinned in the eval script.
> - state-deployable (PRIMARY, the only gate-eligible arm): base plus three
>   state variables valued at each tick's KNOWLEDGE time (first_seen_at — stale
>   possession included): possession (last known, from play sequence), bonus
>   differential (team fouls this period, >=5 puts opponent in bonus),
>   timeouts-remaining differential (from typed timeout plays). Exactly three
>   coefficients, zero interactions. Fitted leave-one-game-out; scored only on
>   held-out games.
> - state-ceiling (DIAGNOSTIC, never gate-eligible): identical variables valued
>   at wallclock time — the physics upper bound, priced only to quantify what
>   the 36s feed lag costs.
>
> **COHORT.** Settled signal-covered games; Q4, <=5:00 on the venue clock; OT
> excluded (no registered OT model); one decision tick per 10s per game (dedupe
> of the 200ms stream); both arms priceable at the tick.
>
> **METRIC AND GATE.** Primary: paired Brier difference (base minus
> state-deployable) on held-out ticks, game-clustered 95% CI (C4). Floors: >=15
> settled signal-covered games AND >=1,000 held-out cohort ticks. PASS: CI
> excludes zero in the state arm's favor at floor. FAIL: floor met, CI at or
> below zero. Anything else NO DATA.
>
> **NAMED-CASUALTY CLAUSE:** if the ceiling arm's paired-diff CI excludes zero
> in its favor while the deployable arm's does not, the verdict SHALL state
> "the possession leg is an F8 casualty" in exactly those words — not "further
> work needed."
>
> **CONTEXT LINES, never gate-eligible:** incremental information of the
> deployable states beyond the live mid (y ~ logit(mid) + states) — expected
> priced, per F7/F9; per-leg coefficients; ceiling-vs-deployable decomposition
> by variable.
>
> **DISCIPLINE.** Harness mutation-tested before real data: a synthetic tape
> with an injected possession effect must recover it; a null tape must read
> zero. Motivated by the operator's Q4 focus and the F8 bound design; the
> archive's prices have been seen in F7/F9; this joint quantity has never been
> computed.

*(Transcription note: the text arrived with `>=` and `<=` HTML-escaped by the
message transport. They are restored to the characters the registration was
written with. Nothing else was touched.)*

## What is fixed by the text above

Restated for a reader who does not want to parse the paragraph — this section
adds nothing and constrains nothing beyond the verbatim text, and where the two
appear to differ the verbatim text wins.

* **Question** — does endgame state improve **Q4 calibration** on top of the
  pregame-anchored win curve? It serves the **EV stop**, i.e. exit quality. It
  is not an entry signal and a PASS does not make it one.
* **Three arms, only one gate-eligible.** `base` is the pinned win curve.
  `state-deployable` is the **primary and only** arm the gate can read.
  `state-ceiling` is a **diagnostic that can never pass anything.**
* **The three state variables** — possession (last known, from the play
  sequence), bonus differential (team fouls this period, ≥5 puts the opponent
  in the bonus), and timeouts-remaining differential (from typed timeout
  plays). **Exactly three coefficients, zero interactions**, fixed now.
* **Knowledge time vs wallclock is the whole design.** The deployable arm values
  every state at `first_seen_at` — **stale possession included**. The ceiling
  arm values the identical variables at wallclock. One measures what we could
  trade; the other measures what the information is worth to a system with no
  feed lag.
* **Cohort** — settled signal-covered games, Q4 at **≤5:00 on the venue clock**,
  **OT excluded** (no registered OT model), **one decision tick per 10s** per
  game, both arms priceable at the tick.
* **Metric** — paired **Brier difference** (base minus state-deployable) on
  **held-out** ticks, game-clustered 95% CI (C4). Fitting is
  leave-one-game-out and scoring is on held-out games only.
* **Dual floor** — **≥15 settled signal-covered games AND ≥1,000 held-out
  cohort ticks.** Both, not either.
* **PASS** — CI excludes zero **in the state arm's favour** at floor. **FAIL** —
  floor met, CI at or below zero. **Anything else is NO DATA**, including a
  floor met on one clause and missed on the other.
* **Context lines are never gate-eligible** — the incremental-information
  regression against the live mid, the per-leg coefficients, and the
  ceiling-vs-deployable decomposition are all reporting, not verdicts.
* **Mutation test runs in both directions** before the real data: a synthetic
  tape with an injected possession effect **must recover it**, and a null tape
  **must read zero**.

## The named-casualty clause, and why it is the precedent here

> if the ceiling arm's paired-diff CI excludes zero in its favor while the
> deployable arm's does not, the verdict SHALL state "the possession leg is an
> F8 casualty" in exactly those words — not "further work needed."

That outcome — the information is real, and the feed cannot deliver it in time —
is the one most likely to be written up softly. "Further work needed" is true,
costs nothing to say, and leaves the hypothesis alive in everyone's mental
backlog. It is how a closed question stays open for months.

**This registration pre-commits the words it will use to describe its own worst
outcome.** That is a stronger device than a gate. A gate constrains which number
counts; this constrains what we are allowed to *call* the number once we have
it, and it does so while nobody yet knows whether it will fire.

It also names the mechanism rather than the row, which is what makes it
reusable: an F8 casualty is any signal whose ceiling arm beats its deployable
arm because the feed arrives after the information is worth having. Future
registrations of that shape should carry the same clause.

## Why the disclosure paragraph stays

The disclosure records that the test is **motivated by the operator's Q4 focus
and the F8 bound design**, and that **the archive's prices have been seen in
F7/F9**. The defence is narrow and stated plainly: **this joint quantity has
never been computed.**

As with [espn-wp-vs-price.md](espn-wp-vs-price.md), that is not a caveat to be
tidied away later. A reader can accept or reject the defence, but only if it is
visible, and recording it verbatim means nobody has to trust a summariser's
judgement about which hedges mattered.

## Relation to the ledger, to F8, and to #19

Ledger row **#20** carries this registration in the hypotheses table.

**On F8.** The F8 bound (feed lag p50 36.4s, price move complete by feed time)
kills hypotheses that need to *react* to an event inside the lag window. This is
a **state** test — Q4 possession, bonus and timeouts are conditions that persist
rather than events to be raced — which is why it sits on the surviving side of
the bound. The registration nonetheless flags the possession leg as **at risk**
before any number exists, because possession turns over on a timescale
comparable to the lag. Naming that exposure in advance is what makes the
named-casualty clause enforceable rather than decorative.

**On #19.** Two of this design's constraints read as direct answers to how #19
turned out. #19 passed its gate at k = +2.54 and was unreadable as a trading
claim because its two regressors correlated at r = 0.973. Here the coefficient
count is **pinned at three with zero interactions** before any fit, the scoring
is on **held-out** games rather than in-sample, and the incremental-information
check against the live mid is declared **in advance as a context line that
cannot gate anything** — the registration expects those states to be priced,
per F7/F9, and says so rather than discovering it afterwards.

The mutation test is also stronger than #19's. #19 required a calibrated
synthetic to read k ≈ 0 — a null check only. This one additionally requires an
**injected effect to be recovered**, which catches the opposite failure: a
harness that reports null on everything would have passed #19's check and would
fail this one.

---

*Registered 2026-08-25. Results append below this line, never above it.*
