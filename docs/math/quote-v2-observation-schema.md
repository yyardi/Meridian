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
clock. **The quoter still quotes the FROZEN v1 policy during the freeze** — it
only ADDS recording; this table can therefore begin accruing the compliant
stream from Sept 17 without changing what is quoted (freeze-safe), so the
congestion / guard / PATIENCE cohorts build in parallel with A1's gate instead
of waiting for post-A1 deploy.

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
| `det_confirm_here` | bool | **B's request: a raw CONFIRM fired at this obs** — lets a density-gated v2 (window on 2nd confirm within 30s) be evaluated on the recorded stream with no re-instrumentation |

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
4. **Freeze-safe** — recording only; the quoted policy stays the frozen v1
   commit until A1's gate reads. This table adds no order path (shadow-only,
   credential-free stays load-bearing; AST test extends to the writer).
5. **Detector live** — the quoter runs B's `CongestionDetector.feed` on its own
   stream and records `det_in_window` / `det_confirm_here` / `det_version`.

## Open questions for sign-off

- **B:** does `det_confirm_here` + `det_in_window` + the raw stream cover the
  density-gated v2's evaluation needs, or do you want the pending-trigger state
  recorded too? And confirm ≤1s cadence is the registered-object property.
- **D:** markout runs forward-ASOF on `observed_at`; anything beyond
  `observed_at`/`best_bid`/`best_ask` you need on this table for the forward
  markout coverage print?
- **c7 / manager:** per-arm cutoff (amendment 4) reads the migration's landing
  commit; confirm this table's landing is the cohort epoch for the congestion /
  guard / PATIENCE gates.

**No in-sample result justifies capital. The forward test is the evidence.**
