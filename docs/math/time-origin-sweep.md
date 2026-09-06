# Time-origin sweep of `core/gridiron/` — 2026-09-06

Three defects of one family appeared in this module in a single session, all
making a **mid-game row look like a kickoff row**, and none raising an error:

| liar | found by |
|---|---|
| `display_clock` holds `15:00` in period 1 at 21-0 | Quant B |
| `reg_left` jumps backwards, once by a full 900 s | me |
| "first row seen in state `in`" is the **recorder's start** | me, after ce asked |

So this is an audit of every construct in the module that establishes a **time
origin** or a **pregame population**. Written because the fourth instance found
on Saturday costs the slate, and because two of the three above were found only
when somebody asked a question, never by a test.

## Findings

**1. `fit.true_kickoff` — was broken, fixed this session.**
`state[state=="in"].first_seen_at.min()` returned **22:08–22:09Z for all 14
cohort games — the same minute**, because that is when the recorder started.
Every game was already in progress; **zero of 14 was observed at 0-0**. Now
gated on period 1 AND 0-0, returning nothing for a game never seen at 0-0.

**2. `fit.outcome_cohort`'s clock branch — the FOURTH instance, and load
bearing.** `(period == 4) & (display_clock == "0:00") & (margin != 0)` supplies
**14 of 42** cohort games, where the recorder stopped before ESPN flipped to
`post`. Those are real finals (66-21, 50-0, 34-18), so the branch stays.

But **`P4 0:00` does not mean the game is over.** Seven games carry such a row
followed by more live action, and on game **401858428 the margin went −5 to +1
across it — a sign flip.** Recording that row as the outcome names the wrong
winner.

Nothing goes wrong today only because the rule reads `tail(1)` and those seven
games end in a `post` row. **The safety came from the row selector, not the
predicate** — the same undocumented rescue that let the broken kickoff selector
ship. Guard now explicit: no later live row, and no period beyond 4. Cohort
unchanged at 42, which is the point: it was correct by luck and is now correct
by construction.

**3. `fit.spread_anchor(prices, game_map, kickoff)` — hazard is the caller.**
It takes `kickoff` as a parameter and cannot check it. Any caller passing
anything other than `true_kickoff(state)` reintroduces defect 1 silently. Not
fixable inside the function; recorded here.

**4. `fit.espn_spread_anchor` — `.first()` is the recorder's first sight, not
kickoff.** Low consequence *only* because `live_spread` moves in **4 of 50
games**, all ≤1 point inside Q1, so nearly any row returns the same number.
**That is a property of the data, not of the selector.** The "pregame line"
claim rests on staticness, not on selection being right.

**5. `features.build`'s `merge_asof` on `first_seen_at` — CHECKED AND SOUND.**
The worry was that state rows are backfilled, which would cluster
`first_seen_at` at the recorder start and pair every state row with one price.
Measured: **median inter-row gap 26 s, median span 190 minutes over 426 rows,
and zero rows sharing a timestamp within a game.** Genuinely polled. This is a
different answer from "not checked".

**6. `features.clock_seconds` / `regulation_left` — the gate cannot apply.**
These consume `display_clock` per row as a **feature**, not to select a
population, and nothing downstream assumes monotonicity. A lying clock here is
a wrong feature value, not a wrong cohort. Stated rather than left silent: the
P1-and-0-0 gate is a population test and has no meaning on a single row.

**7. `core/gridiron/scale.py` — no time origin at all.** It takes ladders as
given and fits a cross-section. Correct by construction; the hazard is entirely
in whoever selects the rows, which is finding 1.

## The pattern worth keeping

All four defects produce **plausible, non-null output**, and three of them were
right on this tape for reasons unrelated to the code being right — a frozen
board, a static line, a `tail(1)` that happened to land well. **A rescue you did
not design is indistinguishable from correctness until the rescuing condition
goes away**, and on Saturday all three go away at once: the board quotes, the
line moves, and the recorder runs from kickoff.

---

*Swept 2026-09-06 against `espn_cfb_game_state_20260906T174104Z` and
`cfb_prices_20260906T194301Z`. 83 tests pass.*
