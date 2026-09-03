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

---

# FIFTH ARM + THE BRANCH TREE (2026-09-03, dated BEFORE the first slate)

**Added because the operator pushed: "make sure u are innovating on the
losses, be prepared for the downside case if it doesnt work or gets worse
too cuz otherwise ur just gonna be doing some stupid shit and not fixing a
broken algo approach."** They were right on both counts, and fixing it
exposed a false claim of the manager's, corrected below.

## ★ FLATTEN(k=1¢) — the fifth arm, and the manager was wrong to defer it ★

The manager wrote that flattening "needs an exit mechanism the engine
lacks." **It does not.** The engine already quotes both sides every cycle,
and flattening is **inventory-conditional quote PLACEMENT**: when net long
in a market, lean the ask 1¢ toward the mid; when short, lean the bid. Same
class of change as PATIENCE — both modify quoting as a function of the
engine's own recent history — not an architectural addition. The engine
writes its own fills, so its position is derivable in-process.

**And it is the best-motivated arm we own.** Round trips were available at
up to 27–42% within 30s; +1.44¢ on the flattened subset; +$76 whole-book at
k=1¢, direction consistent, decaying with k, negative by 5¢, CI spanning
zero only for lack of power. **k=1¢ is pre-declared from that curve and may
not be tuned.**

**Why it matters for the design: without it, ALL arms are "quote less" and
the program's headline finding — that v1 never closes a round trip — goes
untested on the first real slate.** With it, four arms are "quote less" and
one is "quote DIFFERENTLY," which is the family balance the criticism asked
for.

## The branch tree — every outcome names what gets built next

**(a) ALL ARMS ≈ BASE.** The basketball levers do not transfer; adverse
selection in football is not concentrated where basketball's was.
**Next: flattening becomes the whole program** — "quote less" was the wrong
family and "close the round trip" is the untested one.

**(b) ALL ARMS WORSE than BASE on per-fill capture** (total P&L is covered
by the instrument-bias clause and cannot trigger this). Our model of where
the loss lives is wrong, not mistuned. **Next: stop adding levers and
re-derive from the fills. A wrong map is not fixed by walking faster.**

**(c) BEST ARM STILL DEEPLY NEGATIVE (worse than −1¢).** The levers work,
the level does not — pointing at the structural story: **we are always
behind the queue with no speed or priority advantage, so we systematically
receive the informed side of the flow the spread exists to compensate.**
*ITS DISCRIMINATOR, registered so this is a diagnosis and not a story told
when things go badly:* the claim predicts that **fill events cluster with
subsequent adverse price movement, and more so for fills arriving after
larger queue clearance.** Measurable on the variants' own fills and on the
operator's probe log. Confirmed or refuted, never asserted.

**(d) THE CROSS-VENUE PIVOT — SUBSTRATE CORRECTED, AND ITS PRIOR DEATH
CITED.** *The manager claimed "we record BOTH Kalshi and Polymarket on the
same NFL games, starting now." **That is false.** Verified at prod:
`kalshi_contracts` is 771 KXWNBASP + 684 KXWNBATO + 152 KXWNBAGA —
**WNBA only, zero NFL**, across 530,061 snapshots.* Cross-venue NFL would
require extending the Kalshi recorder to NFL series: a build with a Sept 9
deadline, not a free query.
**AND THE THESIS ALREADY FAILED ONCE:** venue-gap was this project's
FOUNDING thesis and was killed — **V23, pregame resolution, 36 games,
median gap 0.0000.** Reviving it unnamed is how a dead idea returns wearing
new clothes, which a branch tree exists to prevent.
**SALVAGED FORM, better than proposed and free:** we hold 530k Kalshi WNBA
snapshots beside Polymarket WNBA ticks, so **cross-venue IN-PLAY gap is
measurable on the historical tape today.** That differs from V23 in the one
dimension that could matter — V23 tested PREGAME, where prices have hours
to converge; in-play they may not. **Scored NET OF BOTH VENUES' SPREADS AND
FEES** (Kalshi ~1¢ + Polymarket 5–6¢ ⇒ a tradeable gap must exceed ~6–7¢
against a pregame median of 0.0000), with a pre-declared bar and a null
clause. If it survives on WNBA, extending Kalshi to NFL becomes justified
rather than speculative.

**(e) ONE OR MORE ARMS BEATS BASE on per-fill capture, CI excluding zero.**
The lever transfers. **It does NOT authorise capital and does NOT end the
experiment** — it authorises the pre-declared composition arms (pairs,
single-lever-additive) and continued accrual to the 3-slate gate. **A
winning arm on one slate is a regime observation, not a result.**

**(f) MIXED — some better, some worse. The most likely actual outcome.**
Rule, fixed now: **each arm reads independently against BASE; no composite
verdict.** A family-level conclusion ("quote-less levers transfer") requires
consistency across all three; its absence means the mechanism is
arm-specific rather than familial.

**And the framing that makes a null a diagnosis rather than a shrug:**
market making has three failure modes — adverse selection, inventory risk,
and never being filled. **Our quote-less levers address only the first.** A
null would be evidence the loss lives in the other two, and both are already
measured: inventory shows an 18× variance fan-out across peak position, and
queue depth runs ~1,000 contracts ahead of us at our own price.
