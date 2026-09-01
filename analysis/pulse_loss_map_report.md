# PULSE loss map — Quant B, 2026-09-01 wave

**Question assigned:** where does this model actually lose money, and is there
any region where it doesn't.

**Artifact:** `analysis/pulse_loss_map.py`. Reproduce:
`.venv/bin/python analysis/pulse_loss_map.py` (mutation self-test:
`--selftest` — null reads ~zero, injected +3¢ capture recovered).
**Pins:** decision tape and substrate ledger at export instant
`20260901T195202Z`; substrate is Quant A's
`backups/exports/roundtrip_ledger_20260901T195202Z.csv`, reconciled against
an independent tape reconstruction: 1,944 scored rows both sides, per-$
identical to 6 decimals on every same-leg row, 17 known leg differences (A's
re-linked orphan exits, carried). **Policy:** A's per-$ P&L, maker Θ=0
(gross = net); pessimistic arm = measured in-game concession 4.70¢ per
filled leg (QUOTE-study regime — mismatch with PULSE's resting limits
stated, not hidden). **Population:** full-intent tape (96.5% of entries are
cap-annotated intents; live-faithful subset shown unsliced — 60 fills / 13
games, far under the registered floors). **n:** 1,944 filled entries
(1,807 trips, 137 rides), 34 games, 2026-08-18 → 08-31. All intervals
game-clustered (`clustered_mean`, C4). **Comparisons computed: 197** — at
95%, ~10 cells are expected 'significant' by chance; ranking below is
mechanism + effect size + robustness, never p-value.

**No in-sample result justifies capital. The forward test is the evidence.**

---

## The map

Money is not lost evenly across states. It is lost in one specific place,
twice over:

1. **The ride tail.** 137 of 1,944 fills (7%) never got an exit fill and
   rode to settlement. They lost **−55¢ to −100¢ per $ in every version ×
   market type** (all CIs below zero where computable). Everything else the
   engine does — 1,807 trips at +6¢ to +10¢/$ (upper bounds, doubly
   optimistic) — exists to pay for this tail. Under optimistic fills the two
   roughly cancel: the whole book is **+1.6¢/$ [−1.4, +4.7]**, 34 games.
   Even the double-upper-bound straddles zero.
2. **Everywhere, under honest fills.** The pessimistic arm puts every big
   cell at **−17¢ to −35¢/$, CI below zero in 7 of 9 cells**. Truth lies
   between the arms; nothing in this tape distinguishes where.

Where the losses sit in state space (composition, then outcome):

* Rides concentrate exactly where the bookless-endgame doc says exits die:
  ride share **16.6% in Q4** and **18.1% at 5–10 min left** vs ~4–7%
  mid-game; **10.8% at |margin| ≥ 10** vs ~6% in close games. The ride tail
  is substantially the *no-exit-at-any-price* mechanism, measured in P&L.
* Per-$ outcome declines with game progress in both current estimators —
  v3 spread: +7.7 → +6.3 → +1.6 → −4.4 → −9.1¢/$ across minutes-left
  buckets; v4 total: +3.8 → +1.2 → −4.2 → −13.7 (◄) → −1.1. Q4-adjacent:
  flagged for #20, which should resolve first and may own this answer.
* **v3 winner is the one whole cell negative even under optimism**:
  −5.3¢/$ [−10.0, −0.5], 88 fills / 15 games. Its trips are flat (−0.7)
  and its four rides all settled at −100%.
* The depth question (wave priority): **PULSE does not hide in the depth
  desert.** 50% of fills land in the 35–65¢ band (~$118 at the touch),
  16% above 65¢, only 12% below 20¢. Unlike V1–V3's old model, the edge
  claimed here is claimed where size exists — and realizes **+1.4¢/$
  [−1.1, +4.0]** there. Flat, not negative: the model trades where it
  could trade and makes approximately nothing.

## Candidates (hypotheses, ranked; each needs its forward test)

1. **The roll captures something under honest fills.** *Falsifiable:*
   round-trip capture on the live-faithful forward cohort is > 0 at the
   registered floors (100 fills / 10 games, clustered). *Confound:* the
   entire +6–10¢/$ trip signal is doubly fill-rule-optimistic; the
   pessimistic arm inverts it, so the candidate is exactly the gap between
   fill models. *Forward test:* **already registered and accruing**
   (docs/math/pulse-live.md; live-faithful series at 60/100 fills, reading
   +1.2¢/$ [−11.0, +13.5]) — no new registration needed; wait.
2. **Avoiding the ride-tail states improves the book.** *Falsifiable:*
   entries decided outside (Q4 ∪ |margin| ≥ 10) outperform entries inside
   on per-$ outcome, forward cohort, clustered. In-sample effect (post-hoc
   filter, chosen after seeing the composition): kept 1,235 fills / 31
   games at +2.4¢/$ [+0.5, +4.3] vs dropped +0.2¢/$ [−5.8, +6.3] — an
   upper-bound number among 197 comparisons. *Confound:* shares its
   mechanism with bookless endgames (selection: books die in decided
   games), so it may be venue structure, not model skill; **Q4-adjacent —
   inherits #20's answer if #20 resolves it.** *Forward test:* pre-declare
   the state filter, score both arms on forward games only.
3. **Totals in the 35–65¢ depth band are the one deployment-relevant
   region that is not negative.** *Falsifiable:* v4-total entries at
   35–65¢ cost have per-$ ≥ 0 on the forward cohort. In-sample: v4
   +1.9¢/$ [−1.6, +5.5] (384/17), v1 +4.7 [+0.1, +9.3] (160/13 — one of
   the ~10 expected spurious ▷s; the v1 era split leaves both v1 cells
   straddling zero). *Confound:* stated — weak, and chosen partly because
   it is where size exists, not because the signal is strong. *Forward
   test:* band-conditioned forward accrual under the existing full-intent
   registration.

No anchoring check is owed under rule 3: none of these compare a market
price to a historical base rate — every number is realized P&L against the
venue's own prices.

## Negatives (mechanism named)

1. **The exit that isn't there.** A position whose exit never fills loses
   nearly everything (−55 to −100¢/$, every cell), and such positions
   cluster in late/decided games where the venue stops quoting
   (docs/math/bookless-endgames.md — measured, three ways). The fallback
   leg is not a neutral tail; it is the adverse-selection tail plus a
   structural no-exit venue fact. **Any in-game strategy on this venue must
   price Q4/decided-game entries as potentially unexitable at any price.**
2. **Winner markets.** v3 winner: −5.3¢/$ [−10.0, −0.5], trips flat even
   doubly-optimistic, rides all −100%. Mechanism: the winner book dies
   first and most completely in endgames (the within-game control:
   winner 5 two-sided rows vs spread's 3,430 in the same window), and the
   win-curve at the rung has no captureable disagreement with the market
   the rest of the time. Q4-adjacent; #20 flag.
3. **Late-game entries under current estimators.** The minutes-left
   gradient is negative-going in both v3 spread and v4 total (two
   independent estimator cells, same shape); v4 total at 5–10 min is
   −13.7¢/$ [−27.0, −0.4] ◄. Mechanism candidates: ride share triples
   (mechanism 1), and resolved-variance leaves less mispricing to harvest
   while the model's tempo/sigma anchors are at their stalest. #20 flag.

Also real but mechanical: the pre-08-24 `fv_adverse` stop realized −21 to
−32¢/$ per stop (exit-reason cells describe outcome composition, not
entry-time structure — a stop locks a loss by construction). The ev_stop
replacement already shipped; its trips read flat-to-slightly-negative.

## Boring list (checked, flat — do not re-mine)

* **Spread at entry** (V4 worry): no consistent effect in any cell across
  four buckets ≤15¢.
* **Side (yes/no)**: signs disagree across cells; noise.
* **Claimed edge (`edge_net`) does not order outcomes** — no monotone
  relationship in any big cell; in 2 of 4 the lowest-edge bucket outruns
  the highest. This is C's lane (calibration); flagged to them, not
  pursued here.
* **Cheap contracts (<20¢)**: signs disagree (v3 spread +18.6 wide, v4
  total −20.0 wide); untradeable at size regardless (~$5 at the touch).
* **Mid-game margin buckets (3–9)**: nothing consistent.
* **The if-ridden counterfactual**: CIs of ±40–120¢/$ — uninformative at
  this n except as the reminder that settlement variance dwarfs trip
  variance (the v4-spread +134¢ ▷ cell is 20 fills and noise).
* **v1-only positive cells** (v1 spread >65¢, v1 total 35–65¢): the era
  split (pre-v3-deploy model vs post-deploy stale-clock fallback rows)
  leaves every v1 cell straddling zero; likely members of the expected
  ~10 spurious.

---

**Comparisons: 197 clustered intervals across ~10 cut families**
(version × type map, depth bands, trip/ride, pessimistic arm, portfolio
counterfactual, era split, and per-cell state cuts in 4 big cells).
Bucket edges and cell-eligibility floors were fixed in the script before
results were read; the one post-hoc construction (candidate 2's filter) is
labelled as such.

**No in-sample result justifies capital. The forward test is the evidence.**
