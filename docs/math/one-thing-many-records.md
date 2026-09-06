# One thing, many records — `game_start_time` and the general rule

**Written 2026-09-06 by Quant D**, in response to a postponed CFB game whose
moneyline moved its `game_start_time` while its 13 sibling spread markets did
not, so `board.py:market_state()` read FINISHED for the spreads and IN_PLAY for
the moneyline **in the same snapshot cycle**.

---

## 1. Counted first, and the count says something uncomfortable

Across the 61-game pin: **2,311 market-level records, median 29 markets per
game, and sibling start times agree in every single game.** Zero disagreements.

That is not reassurance. **The postponed game has 0 markets and 0 fills in the
pin** — it was postponed, so it produced none. So:

> **The defect occurs in games that do not produce fills, and every fill-based
> analysis in this programme is structurally blind to it.**

The measurement bounds the frequency among fill-producing games and says
nothing about the population where the defect actually lives. Reporting "0 of
61" as evidence of rarity would be an instrument reporting its own blind spot.

## 2. ★ The invariant is per-cycle AGREEMENT, not constancy over time

The manager's constraint is the design's hinge: a postponement is a **legitimate**
reason for a start time to change, and a rule that cannot tell it from partial
propagation will be wrong in the other direction.

The two are cleanly separable, and not by looking at change:

    legitimate postponement  — ALL siblings move together
    partial propagation      — SOME siblings move

**So the invariant is not "the start time does not change". It is "within one
cycle, all markets of one event agree."** A postponement satisfies it before
and after; a propagation bug violates it.

**With one allowance:** propagation is not atomic, so a brief disagreement
during an update is expected. Transient disagreement is a note; disagreement
that **persists across cycles** is the fault. That distinction is what stops
the guard crying wolf on every legitimate reschedule.

## 3. ★ Do not reconcile. A reconciliation rule is a silent-failure generator

Max, latest-write, majority — all of them share the disqualifying property:
**they always produce an answer.** Taking the max would have "fixed" this case
and hidden the next one, exactly as the manager said. A rule that cannot fail
cannot report.

Two acceptable designs, in order of preference:

**(a) Store it once, at the event level.** `game_start_time` is a **per-event
fact stored per market**. The fix is not a better reconciliation — it is to
represent the thing at its own granularity, so disagreement becomes
*unrepresentable*. Markets reference the event's value; there is nothing to
reconcile.

**(b) If it must stay per-market** because the venue supplies it per market and
we mirror the venue: keep the per-market value verbatim for provenance, and
define the event-level value as **defined only when all siblings agree.** When
they disagree past the transient window, `market_state()` **refuses to
classify** rather than classifying wrongly.

Fail-closed matches this programme's existing discipline — the quote engine
already refuses to start without `GIT_COMMIT`. The cost is that markets are
briefly unclassifiable during a reschedule, which is correct: we should not
quote a market whose state we cannot determine.

## 4. What it can and cannot catch

**Catches:** partial propagation — the actual defect, in the population where
it occurs, regardless of whether fills exist.

**Cannot catch — coherent and wrong.** All siblings agreeing on a start time
that is simply incorrect. Agreement among our own records is an **integrity**
check: it reconciles our copies with each other. Only a **second independent
source** — ESPN's schedule against the venue's — makes it a validity check.
That is the same distinction as the deploy log against per-fill stamps.

**Cannot catch — right but stale.** The game is postponed and the venue has not
yet updated *any* market. Every sibling agrees, on the old time. Again only a
second source sees it.

## 5. ★ Is this the third instance of one pattern? Partly — and the shared part is not what it looks like

    engine_commit      a REPO fact standing in for a DECISION fact
    game_start_time    a MARKET fact standing in for an EVENT fact

Both fragment something that should be one, and in both the remedy is to
represent the thing at its own granularity rather than to reconcile copies.
That much generalises.

**What does not generalise is the mechanism.** `decision_hash`'s
named-list-plus-drift-guard answers a **boundary** question — which files and
env vars count. There is no boundary question here; there is a **granularity**
question, and the drift guard has nothing to guard. Calling them the same
pattern would flatter the analogy.

The rule that does cover all of it:

> **When one thing has many records, do not reconcile them. Either store it
> once, or make disagreement an error state.** A reconciliation rule always
> produces an answer, which is precisely why it cannot report a fault.

And its companion, which is the same integrity-versus-validity line drawn a
third time:

> **Agreement among our own copies is never validity.** It shows the copies
> reconcile, which they will do just as happily when all of them are wrong.
> Validity needs a source that could disagree.

---

No in-sample result justifies capital. The forward test is the evidence.
