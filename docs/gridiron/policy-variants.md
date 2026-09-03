# GRIDIRON — parallel policy variants (REGISTRATION)

**Research agent, 2026-09-03. Landed by the manager; this commit is the
cutoff, read from git `%ct`. Written because the operator asked what had
changed from the failing quoter and the honest answer was NOTHING.**

## Why this is not another data collector

**Every prior deployment measured the MARKET. This measures our own POLICIES
against each other.** Four engines, same games, same second, same book,
different rules — the first experiment in this program whose output is
*"which rule is better"* rather than *"what does the venue do."* Shadow
costs nothing and nothing can trade, so the only price is CPU.

## Cohort

GRIDIRON, league-filtered at the observation query, every row stamped with
engine identity — four engines share tables, so identity is what makes the
cohort legible. **Touches neither A1's cohort nor the basketball freeze**;
authorised by amendment 12, which places GRIDIRON's binaries outside the
freeze by construction.

## Arms — one lever off a common base, each difference pre-declared

- **BASE** — frozen v1 policy, byte-identical. The control; every other arm
  is interpretable only against it.
- **PATIENCE(N=30s)** — after a fill, do not requote to the touch for N
  seconds. *Basis: v1 requoted into the dip 82.2% of the time at 0.0s median
  gap; dips revert +0.76→+0.90¢.*
- **LATE-SUPPRESS** — no quoting in the final period. *Basis: Q4 collected
  the fattest half-spreads (2.2–2.3¢) and posted the worst nets (−2.6 to
  −3.3¢).*
- **WIDTH-FLOOR** — **self-calibrating, no imported constant:** quote only
  when the current spread is at or above the **60th percentile of that same
  market's own spread over the trailing 30 minutes.** A literal >10¢ floor
  quotes nothing on 5–6¢ NFL cells; a percentile rule adapts to whatever the
  board turns out to be and is fixed before any NFL data exists. **Percentile
  and window are pinned here and may not be tuned after a read.**

## ★ THE INSTRUMENT-BIAS CLAUSE — the one that must not be dropped ★

**All four arms use the mid-cross fill rule, which is optimistic in a way
that scales with QUOTING FREQUENCY:** it books ~1.5¢/leg and the mid then
reverts ~1.8¢ favourably, so **the model pays a bonus for every additional
quote.** PATIENCE, LATE-SUPPRESS and WIDTH-FLOOR all quote LESS than BASE
by construction.

**Therefore the instrument systematically handicaps exactly the levers under
test, and a slate in which every variant loses to BASE on TOTAL P&L is the
EXPECTED OUTPUT OF THE BIAS, not evidence against the levers.**

Registered consequences:
- **PRIMARY METRIC IS PER-FILL CAPTURE, not total P&L.**
- **Fill COUNT per arm is reported beside every number**, so the volume
  difference is visible rather than buried.
- Total P&L is secondary and read only with the bias named in the same
  sentence.
- **A variant that beats BASE on per-fill capture is STRONGER evidence than
  its number suggests, because it did so carrying the handicap.**

## Scoring

Both fill arms (optimistic and measured-concession), game-clustered CIs,
per-arm fill counts, per-arm inventory path. **Rule 16 before any read:
BASE must reproduce v1's policy byte-identically on the pinned replay — if
the control is not the control, nothing downstream means anything.**

## Contention clause (amendment 12's residual channel, now +4 processes)

Per-engine cycle-time telemetry printed every slate, and a pre-declared
equivalence check: **if arms' median cycle times differ materially, the
comparison is confounded by TIMING rather than policy and the slate reads
NO DATA.** Four engines contending on one m7i.large is a real mechanism for
exactly that.

## Schedule — dress rehearsal, then cohort

- **Sept 9–10, single game: HARNESS VERIFICATION ONLY, never a read.** All
  four engines running, identity stamps landing, cycle times equivalent,
  BASE reproducing v1. The unrepeatable-night discipline: prove the
  instrument on the cheap game.
- **Sept 13, ~12 games: first real cohort.** One slate gives an INDICATIVE
  read at G≈12 clustering. No gate.
- **GATE at 3 slates (~Sept 27) or ≥2,000 fills per arm across ≥24 games,
  whichever is later.** Below that: NO DATA, accrue.

## Pre-declared expectations — magnitudes, so the read can surprise us

- **PATIENCE:** improves per-fill capture on the affected subset by some
  fraction of the measured 0.8¢ dip; diluted across all fills, expect
  **+0.2 to +0.5¢/fill.** Below +0.1¢: the dip does not transfer to football.
- **LATE-SUPPRESS:** removes fills averaging ~1¢/fill worse than the book;
  at ~25% late share expect **≈+0.25¢/fill**, partly offset by forgoing the
  fattest half-spreads. **A NEGATIVE result here is informative** — it would
  mean football's late-game structure differs from basketball's, which is a
  real finding about the sport.
- **WIDTH-FLOOR:** **no prior on NFL. Genuinely open**, and the only arm
  with no expected magnitude — stated as such rather than dressed with one.
- **OVERALL: we do NOT expect positive capture on the first slate. We expect
  the levers to move −1.60¢ toward zero and to tell us which ones transfer
  from basketball to football.** Anything better is a surprise, and
  surprises that arrive unpredicted are worth more than promises that arrive
  on schedule.

## Capital

Shadow-only, credential-free, nothing trades. **No in-sample or first-slate
result justifies capital; the gate is the evidence.**
