# Dynamic-exit repricing — the shadow arm (builder's note)

Companion to the registration `docs/math/dynamic-exit-repricing.md`. That doc
governs; this records what was built against it (rule 11) and how to read the
pair. **The arm is an instrument. No forward result is computed here** — the
registration is forward-only and results append below its own line.

## What ships

- `core/pulse/reprice.py` — the pure arm state machine (no DB, unit-tested).
- `core/pulse/live.py` — wiring: an arm is born when an entry fills, advanced
  every cycle, and written to `pulse_reprice_exits` on fill or ride. **The
  incumbent's behaviour is untouched** (design constraint 2); this only
  records a second, would-be exit.
- `pulse_reprice_exits` table (migration `c9e4f1a37b62`) — one row per filled
  entry, `entry_decision_id` unique.
- `tests/test_pulse_reprice.py` — the mutation tests below.

Deploy needs `alembic upgrade head` (new table only). Shadow by construction:
the AST no-order test (`test_pulse_live.py`) now covers `reprice.py` too.

## The pinned rule (rule 12 — the code is the pin)

YES frame, recomputed each cycle:

    static_target  = entry ± profit_target
    dynamic_target = static_target + (fv_now − fv_open)

`fv_open` = fair value at the cycle the position opened (anchored on the first
usable FV). Flat FV reproduces the static target exactly ⇒ **zero divergence
when nothing moves**. Everything else — the ev/adverse stop, the endpoint fill
rule, the YES/NO frame — mirrors the incumbent, so **the only changed variable
is the profit-target limit**. The arm keeps the incumbent's ev stop, so below
entry both arms behave alike and the comparison isolates the profit-taking
side.

**Staleness bound (v3a pattern):** fresh FV reprices; FV missing but the last
good value is within `REPRICE_STALENESS_SECONDS` (60s, mirroring
`VENUE_CLOCK_STALENESS_SECONDS`) HOLDS at that value; beyond the bound it FALLS
BACK to the static target. `staleness_holds` / `staleness_fallbacks` make the
bound observable — and the tests prove it fires.

## Reading the pair (no reconstruction)

The dynamic arm is `pulse_reprice_exits`; the **static incumbent** is the same
entry's outcome in `pulse_decisions` / A's round-trip ledger. One-key join on
`entry_decision_id` (unique on both sides):

- dynamic per-entry P&L, ledger policy (round-trip, YES frame, maker, $0 fee):
  - `dynamic_outcome='exit_fill'`: `sign·(dynamic_exit_price − entry_price)`,
    sign +1 YES / −1 NO.
  - `dynamic_outcome='settlement'`: `sign·(settlement − entry_price)`, with
    `settlement` joined from the entry's `pulse_decisions` row (this table
    stores none, exactly as A's ledger reads it).
- static per-entry P&L: A's ledger's value for that `entry_decision_id`.
- **a diverging exit** (the floor unit): the dynamic realized exit differs from
  the static one (different fill price, or one filled and the other rode).
  `target_diverged` is the cheap in-engine pre-filter (the repriced target
  differed from static on some cycle); a flat-FV game has it false and cannot
  produce a diverging exit.
- gate (registration): paired per-$ CI, **game-clustered**, floors ≥15 games
  with ≥1 diverging exit and ≥100 diverging exits; closure at 2× floors.
- **re-netting clause:** the compensation structure moves with the exit rule,
  so re-net D's premium/quintile table under this exit policy before citing
  any incumbent-era number in the gate.

## Mutation tests (required, all passing)

- FV moves ⇒ the target diverges and the arm holds out for (or cuts to) a
  different exit; FV flat ⇒ zero divergence, fills exactly where the incumbent
  would (`test_a_moving_game_diverges_a_flat_one_does_not_count`,
  `test_flat_fv_never_diverges...`, `test_rising_fv...`, `test_falling_fv...`).
- staleness bound provably fires: held within 60s of the last good FV, reverts
  to static beyond it (`test_staleness_holds_within_bound_then_falls_back...`).
- stop mirrors the incumbent; born-tick never fills; NO-side symmetric.
- DB wiring: an entry fill creates an arm that rides to a `settlement` row, and
  a moving game writes a diverging `exit_fill` row — paired by
  `entry_decision_id` with no reconstruction.

## Limitations, stated

- **F8 caveat (registration):** repricing fixes staleness of the TARGET, not
  adverse selection of the RESTING order — a repriced exit still rests against
  flow ~37s ahead, and repricing a real resting limit is a cancel+replace that
  surrenders queue position. Neither is modelled; the arm is optimistic by
  construction, an instrument and never evidence.
- **In-memory, like the incumbent position.** An arm lives from entry fill to
  fill/settlement in process memory; a mid-game restart abandons in-flight arms
  exactly as it abandons in-flight incumbent positions. Continuous per-game
  operation is the assumption for both.

*No in-sample result justifies capital. The forward test is the evidence.*
