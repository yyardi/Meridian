# Research update, 2026-09-07 — the plan is executed; here is what it found, what it refuted, and what I need from you

Written for the researcher who authored the E1–E8 plan. Every number below is
game-clustered with G stated, estimator named, and reproducible from a committed
script on `quant-b/cfb-touch-making`. The short version: **the plan was run in
full on the data that exists; no route produced measurable edge; three of the
plan's own hypotheses are refuted by measurement; one small regularity survived
and its decisive test is pre-registered and waiting on data.** The rest of this
document is the evidence, then the questions I cannot answer without you.

---

## 1. Results, in the plan's order

| item | population | result | verdict |
|---|---|---|---|
| **E2** audit of the 11 losses | 53 CFB games vs ESPN WP | OT, garbage time, data errors do **not** separate losers (60/56%, 60/53%, 10/12%). The single separating variable is *favourite won*: 49 games −0.0320 [−0.0435, −0.0204]; 4 upsets +0.2088; pooled **spans zero**. Our WP model is a leveraged bet on the pregame line; ESPN's WP is nearly line-blind. | your hypothesis refuted; the ESPN gate retired |
| **E1** touch-joined making, model as shield | 70 CFB games pooled, 36 markets with fills | A −1.94¢ [−4.83, +0.96]; B −2.93¢ [−9.03, +3.17]; B−A −0.99¢. G_eff 15. Withdrawn fills +2.25¢ on G_eff 7.8. | could-not-measure; shield not shown to help |
| **E3** cover model | CFBD 813 held-out; 55 recorded 2026 | beats in-game normal −0.0014 [−0.0021, −0.0008] and −0.0076 [−0.0107, −0.0046]; **loses to ESPN `spreadCoverProbHome` at the line +0.0300 [+0.0155, +0.0445]**; monotone 0/138k; one pre-stated retrain (near-line K) refuted | ESPN leg of the gate fails |
| **E3, NFL** | nflverse 2022–24, 163 held-out | beats normal **−0.0052 [−0.0074, −0.0030], +4.9%** — 3× CFB's skill on 1/5 the games | passes what can be evaluated pre-tape |
| **E4** totals | NFL 163 / CFB 261 held-out; 55 recorded | XGBoost **even with the in-game normal** (σ measured 13.07 / 16.15) in both leagues; **ESPN `totalOverProb` even with it too** (−0.0081 [−0.0185, +0.0022]). 78% of gain on `projected − T`, the normal's mean. | the normal *is* the model |
| **E5** ladder relative value | 73 CFB games, 347 positions | net −2.41¢ [−8.46, +3.63]; mid-to-mid +1.92¢ spans zero; **296,094 stale pair-instants vs 11,936 tradeable (96%)** | could-not-measure; the tape cannot price a pair |
| **E6** one dead-window stratum | 70 games, 32 with fills | A **+0.50¢** [−1.95, +2.94], G_eff 11.2; adverse-by-markout **47% → 30%** vs at-plays, stable in every run | could-not-measure; composition moved, P&L did not |
| **E7** live probe | — | E1 never justified it | not armed |
| **E8** NFL heads | nflverse | WP head reproduces nflfastR's `vegas_wp`: +0.0007 [−0.0044, +0.0059], G=163. Cover head above. Map 16/16, harnesses league-aware, ESPN benchmark URL fixed | ready; needs tape |

**Beyond the plan, because the plan's §5 named them as the only speed-independent edge:**

| test | population | result |
|---|---|---|
| between-play drift, our venue | 73 CFB games, 130k snapshots | **87% of the post-play move is realised by +30s** (n=145, ±0.08); residual spans zero; **4,542 of ~6,000 windows end before 30s because the next play arrives** — at our lag there is no between-play window |
| pregame softness vs DraftKings | Polymarket + Kalshi wk-1 snapshot (16); Kalshi NFL preseason **49 settled**; Kalshi CFB **137 settled** | favourites: +0.26¢ / +0.20¢ / −0.12¢ / **−1.3¢ at the ask with Kalshi ask 0.950 vs realized 0.949 vs DK 0.963** — Kalshi had them right. Brier diffs span zero in every set. Underdog side: no lottery premium; two team markets sum to $1 at the mid. **Not soft, either side, either venue, any population.** |
| in-game overshoot, Kalshi | NFL pre 49 / CFB 132 games | after a ≥1¢ one-minute move, **~6% (NFL) / ~2.5% (CFB) of the shock reverts within 2 min**; NFL strata −5.0/−6.3/−4.9% with ≥2¢ excluding zero; CFB β<0 excludes zero at h=1/2/5, marginal in cents, vanishes on a 30-game traded-minutes check | small, real, direction replicates; under Kalshi fees |

---

## 2. What this refutes in the report, specifically

1. **"The 11 catastrophic games share a structural cause (OT + garbage + data)."** No. They are the four upsets. The model's Brier advantage over ESPN's WP is line knowledge the market already has.
2. **"A better model should fix making, if used to skew and withdraw at the touch."** The shield, built exactly as prescribed, made the naive maker worse in point estimate in both strata (−0.99¢, −1.03¢) and could not be distinguished from zero. Withdrawn fills lean *positive*: the model's disagreements with the market lean the wrong way, which is what E2 predicts of a line-anchored model. I am not claiming the shield hurts — G_eff 15 — I am claiming it has not been shown to help, twice.
3. **"Realistic edge lives in between-play dead time exercised by a better map."** Measured: the move is 87% priced before we see it, and the dead window that E6 finds in 66% of game *time* does not exist as *usable windows* at a 30s lag.
4. **"Bartlett–O'Hara's retail cross-subsidy (~0.8¢) is the edge source."** Not visible in football winner markets: favourites are not underpriced, longshots are not overpriced, the two-market sum is $1, on 186 settled games across two sports plus two live snapshots. Whatever earns 0.8¢ on Kalshi broad-based markets, it is not sitting in NFL/CFB winner pregame prices.
5. **The 23.7% benign ceiling** is relabelled unknown, as you asked. E6 measured adverse-by-markout at **30%** in dead windows vs **47%** at plays — that is the composition shift you predicted, and it is the one mechanism that behaved as theory said.

## 3. What survived

- **NFL margin has structure past line+score+clock; total does not.** The cover model earns +4.9% over the normal on NFL, ESPN's cover prob beats the normal too; totals reduce to the normal for everyone. This is the strongest empirical fact of the programme.
- **Dead windows cut adverse fills by a third.** Stable across every run. Not yet P&L.
- **The overshoot.** Small, scales with the shock on NFL, direction replicates on CFB. The venue where it could clear costs is Polymarket US (maker fee 0, 0.5¢ spread). Pre-registered with its gate (`docs/math/e8-nfl-preregistration.md`, H1; `cfb/run_overshoot.py`).

## 4. Data constraints you should design against

- **30-second feed lag**, structural. Plays are ~40s apart.
- **Ladder tape is 96% stale at pair-instants** — the recorder samples deep rungs on a slow tier. E5 as designed cannot run on it.
- **17 of 73 recorded CFB games have no venue prices during play** (recorder outages, now quantified). Every making number comes from the 39 covered.
- **Book depth exists on 3% of snapshots, 60% of those pregame.** Queue position is modelled optimistically on 99% of quotes; a loss under that assumption is real, a profit is not evidence.
- **CFB winner markets are 1.8% of the board and barely print** — 17 Friday markets produced 6 trades between them.
- **Power.** Effect sizes here are 0.5–2¢; per-game sd of fill P&L is 5–10¢. That is G ≈ 100–400 games per arm. One CFB Saturday is ~20 covered games.

## 5. Questions I need you for — these are the ideas

**Q1. What is the overshoot, mechanically?** ~6% of a one-minute move reverts within two minutes, scaling with the shock. Candidates: (a) a taker sweeps the touch and the book refills at the old level — then the fade should be conditioned on sweep size vs resting depth, and it is a *liquidity-provision* return; (b) bid-ask bounce — but it survives on trade prices for NFL and scales, which bounce does not. If (a), what is the right sizing rule for a zero-maker-fee venue, and what should the Polymarket test add beyond "reversal > half-spread"?

**Q2. What is the margin structure the cover model finds?** +4.9% over the normal on NFL is real. Field position and possession carry <1.5% of gain in the trees, yet ESPN's cover prob beats ours at the line by 0.03 — it has something we don't. Is it EP-based? Key-number multipliers? If we can *name* the structure we can test whether the venue's spread ladder prices it (E5-NFL) — and target only rungs where it doesn't.

**Q3. E5 on a sparse ladder — quote provision, not fill-on-quotes.** Your §4(i): "be the first to quote a tail rung." Our tape says 96% of rungs are unquoted when we'd want a pair. Is that the opportunity (we *are* the market) or the trap (no flow)? A backtest needs a flow model for rungs with no counterparty tape. What is the minimum honest version — e.g., condition on the rung being quoted within N minutes *after* we would have posted, as a proxy for arriving flow?

**Q4. Variance reduction instead of more games.** At G ≈ 100–400 per arm, waiting is a season. Control variates could cut that 3–5×: score each fill against the contemporaneous DraftKings/ESPN probability rather than the raw outcome, so the outcome's binomial noise is removed and only the venue-vs-model residual is estimated. Would you specify that estimator? I'd rather implement your version than mine.

**Q5. Is in-game closed for us?** The lag is structural; 87% of moves are priced before we see them; no between-play window exists. Unless there is a legitimate faster public source, should in-game be restricted to *structural* positions (relative value across rungs, held to settlement) where speed is irrelevant?

**Q6. Totals.** The normal is the model for us and for ESPN. Is there known structure — pace, weather, tempo regimes — worth one feature, or is a total a "make it, don't predict it" instrument?

**Q7. The question under all of them.** Six routes measured negative on powered, settled data. What would you need to see to conclude that this venue is efficient for a participant at our information level — and what is the cheapest experiment that could still change your mind?

---

Scripts: `cfb/run_audit_losers.py`, `run_making_touch.py` (`LEAGUE`, `DEAD_WINDOW`), `run_cover_fit.py`, `run_total_fit.py`, `run_ladder_rv.py`, `run_drift.py`, `run_overshoot.py`, `run_nfl_wp_fit.py`; `analysis/pregame_softness/`, `analysis/kalshi_preseason/`, `analysis/kalshi_settled/`. Docs: `docs/math/e3-*`, `e4-*`, `e5-*`, `e6-*`, `e8-*`, `between-play-drift.md`.
