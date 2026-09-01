# Edge-hunt wave — 2026-09-01

The operator's mandate: find whether an edge exists, before NBA season. Four
agents work in parallel off **pinned artifacts**, never off a live database —
the operator stops and starts Docker on their laptop for coursework, and a
research run must not depend on their machine being up.

## Pinned datasets

| file | rows | what |
|---|---|---|
| `backups/exports/pulse_decisions_full_20260901T195202Z.csv` | 19,333 | every PULSE decision, 34 games, 2026-08-18 → 08-31 |
| `backups/exports/resolved_outcomes_20260901T195202Z.csv` | 2,778 | settlement ground truth |
| `backups/exports/live_ticks_pulse_games_20260901T195202Z.csv.gz` | 65 MB | live ticks for the same 34 games |

Decisions break down as **2,974 `enter` · 2,679 `exit` · 13,680 `hold`**, with
full state at decision time (`score, margin, period, minutes_left,
total_so_far, projected_total, total_sigma, market_bid/ask, fair_value,
edge_net`) and outcome after (`filled_at, mid_at_fill, withdrawn_at,
settlement, settled_at`). `entry_id` carries round-trip lineage.

## The four tracks

- **A — round-trip ledger.** One row per entry joined to its outcome, P&L net
  of fees. The foundational artifact; B, C and D consume it.
- **B — conditional performance.** Where the money goes, sliced by state.
- **C — calibration.** Is `fair_value` calibrated, and is the failure one of
  calibration or of resolution? Different failures, opposite remedies.
- **D — execution.** How much of the loss is spread, fees, adverse selection
  and unavailable exits, rather than prediction error.

## The standing rule for this wave

**Everything produced here is IN-SAMPLE and hypothesis-GENERATING.** The output
is a ranked list of candidates, each with the forward test that would confirm
it — never a strategy, and never a basis for deploying capital. Anything that
survives gets a registration written *before* it is tested forward, per the
house rule that has already killed several hopeful results.

Known priors that bound optimism, all measured: model Brier is worse than the
market's on every slice with real n; the in-game reversion the FV shrinks
toward is already priced (#18); the venue-gap thesis failed at pregame
resolution (V23); 9 of 22 endgames carried no two-sided winner book at all.

**A wave that returns "we lose money in X, Y and Z, and here is the mechanism"
is a success.** It tells the operator where not to put money.
