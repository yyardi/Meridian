# Loss-cap counterfactual surface — Quant B, 2026-09-02 (operator's O3)

**Artifact:** `analysis/loss_cap_surface.py` (mutation-tested both ways:
grind-down tape → cap wins +0.65/$ paired, CI off zero; mean-reverting
null → zero caps invented). **Pins:** `20260901T195202Z` (A's ledger +
the 200ms tick pin). **Grid:** 5×5 (k ∈ {3,5,10,15,20}¢ × m ∈
{0.5,1,2,5,10} min), declared pre-compute; **50 clustered intervals, ~2
expected spurious.** Paired per entry against the realized outcome
(trap 1), taker-priced at the real touch + 0.06·p(1−p) (real spreads,
not a stylized toll), game-clustered, both fill arms.

**No in-sample result justifies capital. The forward test is the evidence.**

## The answer: no (k, m) cell survives, in either arm

* **Against the optimistic tape**: the cap is NEGATIVE across
  essentially the whole surface — Δ per-$ −4 to −13¢, **12 of 25 cells
  with the CI fully below zero, zero cells above.** Tight, fast caps are
  the worst (3¢/30s: −12.1 [−17.7, −6.6] on 663 fires): they fire on
  oscillations the roll would have harvested and systematically sell the
  local extreme — the reversion-is-priced lesson (#18) arriving through
  the exit door.
* **Against the pessimistic tape**: every cell ≈ 0 (means −3 to +3¢/$,
  all CIs straddling). Under realistic fills the trips were already
  losing; capping a loser earlier at taker cost is worth about what
  holding it was worth. **A loss-cap does not rescue this book — it
  cannot, because the losses are adverse selection at entry, not
  discipline failure at exit.** Same verdict as the withdrawal autopsy,
  from the opposite side: neither more patience nor faster loss-cutting
  fixes a book whose entries are picked off.
* **`unexec = 0` in every cell** — a finding: the cap always found a
  two-sided book, because ≥k¢-for-≥m-min conditions are met EARLY in a
  decline, long before books die. Booklessness constrains the *last*
  exit of a dying position (the ride autopsy), not this one.

The operator's instinct, honestly tested: the monotone
losers-held-longer-lose-more fact was the confound wearing a policy's
clothes — holding time is what happens when the exit doesn't fill, and
cutting at (k, m) reliably locks in the toll plus the bottom tick.

## One thing worth carrying forward (post-hoc, labeled)

Under the pessimistic arm the cap is EV-≈0 while mechanically truncating
the −80¢/$ ride tail. **An EV-neutral tail truncation can still raise
log-growth** — that is a variance effect, and it belongs to the
variance-aware Kelly machinery, not to this surface: the existing scorer
(`analysis/variance_kelly_scorer.py`) already scores paired per-game
log-growth and could take "incumbent + cap" as an arm. Registering that
would REQUIRE the exit-policy cohort split (the registration's own
condition — a cap IS an exit-policy change) and a re-net of the
engine-mediated compensation. Handed to c7 as a candidate, not a
recommendation; it was noticed by staring at this surface, so it is
in-sample twice over.

Trap 3, restated: nothing here may be inherited by the flat-quintile
analyses — a loss-cap changes the payoff structure, and the ride-risk
netting must be recomputed under any exit-policy change.

**No in-sample result justifies capital. The forward test is the evidence.**
