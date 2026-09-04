# What PULSE must record to be auditable — a specification

**Status: specification, 2026-09-04. League-agnostic by construction.** Written
because scoring PULSE (`analysis/pulse_settlement.py`) found that several of its
most decision-relevant questions have **no observable answer on the current
tape, and no reprocessing can produce one.** Those are recording defects, not
analysis defects, and they are the half of a port worth doing regardless of
which league comes next — three ports multiply them.

## The one principle, and it is being proven live right now

> **RECORD OBSERVABLES. DERIVE VERDICTS.**

Never store a classification, a label, or a boolean that encodes a rule. Store
the inputs the rule consumed, so any rule — including the one nobody has written
yet — can be applied retrospectively.

The live proof: PULSE's fills were classified real/phantom for the first time
today using `real ⟺ ask ≤ B`, giving 81.4% phantom. **That criterion is now
itself under question** (meridian-70: a resting bid is filled when a seller hits
it, and the ask never has to move, so `ask ≤ B` selects the maximally adverse
subset). Because the classification was DERIVED from a recorded book rather than
stored as a column, a change in the criterion costs one re-run. **Had PULSE
stored `population='phantom'` at fill time, every historical row would now be
wrong and unfixable.** That is the whole argument, and it happened this week.

The corollary that follows: also record **the rule's own parameters in force at
the time** — thresholds, caps, model version. A number without the rule that
produced it is a number whose description cannot be tested, and a description
has no test.

## The six questions that are currently unanswerable

| # | question | why it cannot be answered today |
|---|---|---|
| 1 | Is the 3¢ entry threshold in the right place? | **Declines are not recorded at all.** 19,333 rows contain zero with `edge_net` below the threshold; every `hold` is `reason=position_open` with no edge. The rule's recorded image is a single branch — we see every firing and never a decline. |
| 2 | What did we pass on, and what would it have been worth? | Same: the excluded population is invisible, so the threshold's opportunity cost is structurally unmeasurable. |
| 3 | Do the state guards fire, and on what? | `pulse_abstentions` has never had the opportunity to record anything — guards landed 2026-09-02, the engine's last decision was 2026-08-31. An **unproven instrument**, not evidence of absence. |
| 4 | How many independent opinions does the tape hold? | 749 distinct (market × side) sit behind 2,974 entries, one re-entered 30×, and nothing marks a re-entry as a re-entry. Rows are not bets and the tape does not say which are which. |
| 5 | What would the engine have done unconstrained? | 93% of entries were size-capped by `max_open_per_event`. The cap is recorded as the *binding constraint* but the **desired** size is not, so per-dollar aggregates are policy artifacts that cannot be undone. |
| 6 | What is the round-trip P&L of an entry? | `entry_id` is NULL on every row of the pinned export, so exits cannot be matched to entries and only held-to-settlement is computable. |

Questions 1–3 are the expensive ones: they are not merely unmeasured, they are
**unmeasurable from any amount of existing data.**

## The events to record

PULSE today logs **chosen actions** (`enter` / `hold` / `exit`) — its own schema
says so. The fix is to log **evaluations**, of which actions are a subset.

### E1. `EVALUATION` — the missing event, and the important one

One row per market the engine *considered*, whatever it decided.

| field | why |
|---|---|
| `decided_at`, `event_slug`, `market_slug`, `game_id` | join keys, as today |
| `decision` | `enter` \| `decline` \| `abstain` \| `hold_open` \| `exit` — **`decline` and `abstain` are the new values and the whole point** |
| `decline_reason` | `below_threshold` \| `no_book` \| `position_cap` \| `bankroll` \| `min_qty` \| `guard_<name>` — one enum, never free text |
| `fair_value`, `market_bid`, `market_ask` | the belief and the book, on **every** evaluation including declines — answers Q1/Q2 |
| `edge_net` | **recorded even when negative or below threshold**; today it exists only where it already passed |
| `threshold_in_force` | the parameter the decision was taken against, so a threshold change does not silently invalidate history — answers Q1 retrospectively |
| `estimates_version`, `model_config_id` | which model produced the fair value |
| state block (`score`, `period`, `minutes_left`, `clock_is_estimate`, …) | as today, at decision time |

### E2. `INTENT` — what the engine wanted, before policy trimmed it

| field | why |
|---|---|
| `desired_qty`, `desired_stake` | **the unconstrained size** — answers Q5; today only the capped result survives |
| `final_qty`, `final_stake`, `binding_constraint` | as today |
| `opinion_id` | stable per (market, side, direction-of-view); **increments only when the view changes, not when it is re-asserted** — answers Q4 |
| `is_reentry`, `reentry_index` | derived at write time from `opinion_id`, so a reader need not reconstruct it |

### E3. `FILL` — with the book that made it possible

| field | why |
|---|---|
| `filled_at`, `fill_price`, `qty` | as today |
| `best_bid_at_fill`, `best_ask_at_fill`, `book_captured_at` | **the observables the classifier needs.** Store the book, never the classification (the principle above). Today this must be recovered by an external as-of join against the tick tape; recording it inline makes every future criterion applicable and makes the join's age assertable at write time |
| `book_age_s` | asserted **non-negative** at write, not merely capped — a one-sided cap on an age whose join points the other way is vacuous |
| `entry_id` | populated, so exits match entries — answers Q6 |

### E4. `EXIT` — unchanged except for lineage

`entry_id` populated; `exit_reason` as today. Nothing else needed.

## The volume problem, which is why the naive version never gets built

A 1s loop over ~14 markets per game for ~2.5 hours is ~126,000 evaluations per
game, ~4.3M over a 34-game window. **Logging every evaluation in full is not
viable and a spec that ignores this gets ignored.** Three tiers, cheapest first:

1. **Per-cycle aggregate (always).** One row per cycle per game: counts by
   `decision`, plus a fixed-bin **histogram of `edge_net` across evaluated
   markets**. This alone answers Q1 and Q2 — "what was the distribution of edge
   we declined" — at a few hundred bytes per cycle rather than 14 full rows.
2. **Full rows near the boundary (always).** Any evaluation with
   `|edge_net − threshold| ≤ 2¢`, both sides. These are the decision-relevant
   ones; a decline at 0.1¢ of edge is noise, a decline at 2.9¢ is the question.
3. **Full rows on decision change (always).** When a market's `decision` differs
   from its previous cycle. Steady states cost one row, not 9,000.

Everything in E2–E4 is per-action and already low-volume; only E1 needs tiering.

## What must NOT be recorded

- **No stored classifications** (`population`, `is_phantom`, `is_real`) — the
  criterion is under revision this week; a stored verdict would already be wrong.
- **No stored "would have been profitable"** or any outcome-conditioned field: it
  bakes hindsight into the tape and cannot be un-baked.
- **No free-text reasons.** An enum can be counted; prose cannot, and it drifts.

## The acceptance test — how to know the fix worked

Not "the columns exist". Each question must become **computable**:

1. On one recorded game, the edge histogram over `decline` rows is non-empty and
   spans below the threshold. *(Q1/Q2 — the decline branch is now observable.)*
2. `decision='abstain'` appears at a non-zero rate, or, if zero, the count
   carries provenance saying the instrument has never fired rather than printing
   a bare zero. *(Q3 — rule 22.)*
3. `opinion_id` count is materially below the entry-row count on a game with
   re-entries. *(Q4 — opinions distinguishable from rows.)*
4. `desired_stake > final_stake` on the capped rows, and the ratio is
   recoverable. *(Q5.)*
5. Every settled exit joins to exactly one entry via `entry_id`. *(Q6.)*
6. Real/phantom classification runs **from the recorded fill book alone**, with
   no external tick join — and reproduces the external-join answer on an
   overlapping window. *(The principle, tested rather than asserted.)*

## Cost, honestly

E2–E4 are field additions to existing writes: small. E1 is a new event with a
tiering design: the real work, and the tiering is what makes it affordable.
**None of it requires a model change, and none of it is league-specific** —
which is the argument for doing it before the port rather than after, since
every defect above otherwise reappears in NBA, CFB and NFL simultaneously.

**No in-sample result justifies capital. The forward test is the evidence** —
and this specification is about making the forward test *legible* when it comes.
