# QUOTE v2 — the forward observation-stream schema (FIELD SET FOR SIGN-OFF)

**Status: SPEC for sign-off, not yet built. The program's single
highest-leverage build item (manager, 2026-09-02): guards, the congestion
gate, and PATIENCE's stream-read gate ALL converge on one artifact — the v2
quoter recording its OWN observation stream. This is impossible to backfill,
so the field set is circulated for consumer sign-off (B, D, c7, manager)
BEFORE the model + migration land.**

## Why a new table, not `market_snapshots` or `shadow_quote_fills`

- `market_snapshots` is the RECORDER's stream (recorder stamps, ~200ms). B's
  congestion detector registration forbids a cross-process recorder-timestamp
  join and requires the QUOTER'S OWN stamps at a compliant cadence
  (observation cadence ≪ LONG_S=5s; rule of thumb ≤1s). Feeding the recorder
  tape over-fires the detector to 90.6% of fills / 75% of game time — a
  substrate artifact, not congestion (in-sample finding, 2026-09-02).
- `shadow_quote_fills` records only FILLS. PATIENCE needs the FULL quote stream
  including unfilled requotes (v1 persisted none — the honest-bound reason M4
  had to extrapolate from births). Guards need the quote-time state snapshot,
  absent on that table.

So: a new `quote_v2_observations` table, written by the v2 quoter on its own
clock. The quoter still quotes the FROZEN v1 policy — it only ADDS recording.

**Two gates, not one (manager, 2026-09-02) — do not conflate them:**
- **LANDING** this model + migration on main is repo code, off-path, no deploy
  implied — safe once D's field sign-off arrives.
- **STARTING the recording** — deploying the v2 quoter binary — is
  AMENDMENT-GATED even though it is recording-only, because the freeze's LETTER
  pins the running COMMIT (7a3a217), and a new binary replaces it. It requires
  a research DATED AMENDMENT first: (a) deploy BEFORE the first Sept 17 tip so
  A1's entire cohort accrues under ONE commit (no mid-accrual change — this
  serves the sequencing clause's purpose better than its letter); (b) the
  amendment names the new pinned freeze commit; (c) a policy-equivalence
  obligation rides with it — replay proof that the v2 quoter's quoting code
  paths produce IDENTICAL outputs to v1 on identical inputs, plus the shadow
  AST test extended to the writer.

**Hard consequence:** if the amendment + build + deploy cannot all complete
before the first Sept 17 tip, the recording does NOT deploy mid-accrual — it
waits for A1, and congestion / guards / PATIENCE lose their parallel accrual.
Ship once, complete, before the 17th. Only WITH the amendment landed does the
compliant stream accrue in parallel with A1's gate.

## Field set (one row per quoter observation of one market, ≤1s cadence)

| field | type | consumer & why |
|---|---|---|
| `id`, `created_at` | bigint, ts | identity / server default |
| `market_slug`, `game_id`, `event_slug` | str | join keys |
| `sports_market_type` | str | congestion detector ladder=kind, rung=slug |
| `observed_at` | ts (tz) | **the QUOTER'S OWN stamp** — the compliant clock; detector + markout run on this, never recorder stamps |
| `best_bid`, `best_ask` | Price | book; mid/spread derived |
| `is_live` | bool | pregame/in-play regime seam |
| `event_period` | str | LATENESS arm, guards |
| `event_score` | str | guard-1 (score-vs-elapsed), state |
| `margin` | int | state, guard context |
| `total_so_far` | int | guard-1, totals state |
| `minutes_left` | Numeric | LATENESS arm, guards |
| `minutes_left_is_estimate` | bool | **guard trigger — clock quality** |
| `fair_value` | Price null | **guard-2 trigger (needs fv); state** |
| `game_start_time` | ts null | **D1 pregame hours-to-tip fold** |
| `quote_bid`, `quote_ask` | Price null | **PATIENCE — the resting quote at this obs, incl. unfilled requotes (the full stream)** |
| `quote_event` | str | quote lifecycle: rested / requoted / withdrawn / held / filled_bid / filled_ask / none — PATIENCE requote behaviour |
| `det_version` | str | **B's pin discipline: detector code version (commit) that produced the fields below** |
| `det_in_window` | bool | live congestion detector: is this obs inside a confirmed window (opens t0+5s) |
| `det_confirm_t0` | ts null | **B sign-off: the confirmed trigger's t0 AS A VALUE, not a boolean.** The true confirm instant is t0+5s, which falls BETWEEN observations; a boolean flag is quantized to obs times while offline replay computes exact instants, so they could never byte-match. Recording t0 pins the confirm identity exactly and gives the density-gated v2 its confirm times for free. NULL when no confirm is tied to this obs |

**Deliberately NOT stored — recomputed offline from the raw stream, to avoid
freezing a version into the table:**
- `character` (A1 vol classifier): recompute via the frozen a1 classifier on
  the recorded `(observed_at, mid)` series. Storing it would bake a classifier
  version in; the raw stream + the pinned classifier is the reproducible pair.
- alternate congestion-detector versions: `sports_market_type`, `observed_at`,
  `best_bid/ask` are the raw detector INPUT, so any detector version (incl. the
  density-gated v2) recomputes offline; `det_*` fields above are the LIVE
  detector's output for the online arm, pinned by `det_version`.

## Recording requirements (the quoter's obligations)

1. **Cadence ≤1s** (B: observation cadence ≪ LONG_S=5s or the detector
   degenerates). The v2 quoter observes at ≤1s even though v1 was 5s.
2. **Own stamps** — `observed_at` is the quoter's receive time, never a
   recorder timestamp.
3. **Full quote stream** — a row on every observation, carrying the current
   resting quote (or its absence), so unfilled requotes are visible to
   PATIENCE, not just fills.
4. **Recording only, but deploy is amendment-gated** — the quoted policy stays
   the frozen v1 commit, and this table adds no order path (shadow-only,
   credential-free stays load-bearing; AST test extends to the writer). But
   deploying the recording binary replaces the pinned freeze commit, so it
   ships only under the research amendment above (new pinned commit +
   policy-equivalence replay proof + before the first Sept 17 tip, else it
   waits for A1). Landing the model/migration is separate and off-path.
5. **Detector live** — the quoter runs B's `CongestionDetector.feed` on its own
   stream and records `det_in_window` / `det_confirm_t0` / `det_version`.

## Read embargo (amendment 10, 256c038)

**The forward observation table is EMBARGOED from ANALYTICAL reads until a
consuming gate registers.** The sole pre-registered exempt reader is B's blind
saturation diagnostic (coverage only). The standing checks below are
RECORDING-INTEGRITY checks (provenance + cadence of the recording itself), NOT
analytics — they read no outcome and score no arm, so they do not breach the
embargo. Framed here so the embargo and the checks are never seen in tension.

## Standing checks (B sign-off — recording-integrity, not analytics)

1. **Replay reconciliation.** The scorer recomputes the detector outputs
   OFFLINE from the recorded raw stream (`observed_at`, `best_bid/ask`,
   `sports_market_type`) and ASSERTS they match the recorded `det_in_window` /
   `det_confirm_t0`, per game, printed. This is what makes recorded `det_*`
   VERIFIED provenance rather than unverifiable trust, and it makes the
   pending-trigger state fully derivable (so it is deliberately NOT a column);
   any live/replay divergence (state corruption, a missed observation) is
   caught by it. `det_confirm_t0` as a value (not a quantized boolean) is what
   lets this reconciliation be exact.
2. **Cadence self-measurement.** The scorer prints the median and p99
   inter-observation gap per game FROM THE RAW STREAM — no trust, just
   arithmetic — so ≤1s compliance is measured, never assumed.

## Deploy proofs (amendment 10, 256c038 — attach to the recording deploy; the freeze re-binds only at the instant they land)

The v2 quoter binary deploys only WITH these three proofs; c7's #214 sign-off
rides on them being spec requirements. They are the v2 quoter build's finish
line (built with the recording path, not this schema PR):

1. **Replay equivalence** — the new binary, replayed on the pinned Aug tape,
   produces BYTE-IDENTICAL quoting decisions to the frozen commit 7a3a217.
   Built as a SELFTEST (not a one-off run), because the freeze re-binds only at
   the instant the proofs land — a standing check, re-runnable.
2. **AST extension** — the credential / venue-order-client import ban, verified
   on the WRITER path, registration-grade (extends the shadow-only AST test the
   quote + pulse engines already carry).
3. **Off-decision-path** — the observation writer is ASYNC off the quote loop,
   with quoter loop-time telemetry printed pre/post on the first slate night. A
   recording-only change that slowed the loop would be a policy change wearing a
   recording costume (c7); the telemetry proves it did not.

## Arm-pin decisions this schema forces (pinned before first read, not at read time)

- **Stall-degeneracy (B):** an observation STALL > ~2s inside a pending
  trigger's life partially FORCES its confirm, the same way a 5s cadence would
  (a sibling response can't arrive within LONG_S if no observation arrives).
  No extra column is needed (stalls are derivable from the raw inter-obs gaps),
  but the CONGESTION arm's registration MUST state, before its first read,
  whether stall-affected confirms are excluded or included in the cohort.
  Flagged here so it is an explicit pin, decidable now, never a read-time
  choice.

## Open questions for sign-off

- **B: SIGNED OFF 2026-09-02** — no pending-state column (derivable, guarded by
  the replay-reconciliation check above); `det_confirm_here` → `det_confirm_t0`
  (timestamp value); ≤1s confirmed as the registered-object property; cadence
  self-measured and the stall-degeneracy arm-pin flagged. All folded above.
- **D: SIGNED OFF 2026-09-02** — markout core needs only
  `observed_at`/`best_bid`/`best_ask` (present). The three forward-post-mortem
  fields D flagged (`event_period`, `event_score`, `is_live`) are ALREADY on
  the row point-in-time at observation, plus `margin`/`total_so_far` for the
  guard cut — so the state cuts avoid a cross-stream stamp join. Confirmed
  present; no raw-JSONB fallback needed.
- **MANAGER: SIGNED OFF 2026-09-02** on the field set + design, with the
  deploy condition folded above (landing is off-path; STARTING recording is
  amendment-gated: new pinned freeze commit, policy-equivalence replay proof,
  before the first Sept 17 tip or it waits for A1).
- **c7:** per-arm cohort-epoch framing (amendment 4) routed to research —
  manager's framing: substrate epoch = migration landing, gates carry their own
  instants and invoke amendment 4's disclose-and-justify for the gap (the
  stream is written by a frozen recorder the gate authors don't shape).
  Research's ruling, not settled here.

**No in-sample result justifies capital. The forward test is the evidence.**
