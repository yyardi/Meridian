# Passive market-making: the close

**VERDICT (name the line, always).** Against the break-even floor — benign fills
must be **≥ 57.8%** of fills received (H and |A| on the same guarded real fills:
H = 1.193¢, |A| = 1.634¢; see §1) — the measured benign ceiling of **23.7%** (upper
bound **≈31.4%**) cannot clear it, **26.4 points clear**. So against the 57.8%
floor, passive joining **cannot break even**. Against c7's independently-registered
**10% kill line**, the same 23.7% does **not** kill. The verdict flips on which
line, so the line is named at every claim below. **Even at the full quoted spread**
(r\* = 40.6%) the floor clears the 31.4% ceiling, so no passive-maker earnings
assumption reopens it (§4).

Substrates: the floor is from the shadow **fills** (settlement P&L); the ceiling
is from c7's **book tape** (depth transitions). Different substrates — not one
statistic read twice — and each is blind to a benign FILL in its own way: the
shadow fills bury benign fills in the ask>B "phantom" bucket (the fill rule never
sees the trade), while c7's book tape is raw venue depth the fill rule never
touches and carries its own blindness — trade-vs-cancel and no queue position.
Neither sees a benign fill directly (see "What only the probe can see"). All
figures on the pinned export
`quote_fills_classified_20260906T024500Z.csv` (WNBA + CFB) and c7's WNBA book
tape 2026-07-31..08-20.

---

## 1. The floor — r* = |A| / (H + |A|)

r* is the benign-fill share needed to break even: adverse fills earn A (negative),
benign fills earn H (positive), and the population mean is zero when benign is r*.

**Adverse anchor A, rebate-free (real fills, one-sided-guarded
[`onesided<0.65 OR n<4`, `scripts/sandbox.py`], fills-weighted; cluster-robust CI):**

| population | A (¢/fill) | game-clustered CI | G_eff / G |
|---|---:|---|---:|
| **pooled** | **−1.634** | **[−2.694, −0.573]** | 29.5 / 48 |
| CFB | −1.357 | [−2.754, +0.041] (spans 0) | 19.9 / 35 |
| WNBA | −2.462 | [−3.551, −1.372] | 11.2 / 13 |

> **CORRECTION, AT THE TABLE — there is NO maker rebate.** Figures published
> earlier this day added +0.283¢/fill for a maker rebate that does not exist
> (θ_maker = 0; the advertised rebate is a 50%-of-own-taker-fees promo that ran
> 2026-03-29 → 05-10 and ENDED, never credited since — `docs/findings.md` C7,
> resolved 2026-08-25). The rebate-inclusive anchor **−1.349¢ is SUPERSEDED** by
> the −1.634¢ above; every rebate-inclusive figure was ~0.28¢ too generous. Do
> not quote the rebate-inclusive numbers.

> **PROVENANCE, AT THE TABLE — name the guard and the aggregation (c7/ce audit).**
> A is **guarded settlement P&L, fills-weighted** (`pnl = s·(settlement − qp)`, an
> identity to zero residual on all 73,964 rows — full horizon, not a markout). The
> guard is the **one-sided guard** (`scripts/sandbox.py`, strategy `quote-guarded`),
> **not** a "circuit-breaker" (no such predicate exists — c7 and I both searched and
> missed it, which is what makes it a citation defect): per `(game_id,
> market_slug)` over real fills, `onesided = max(#bid,#ask)/n`, **keep if
> `onesided < 0.65 OR n < 4`**, withdrawing one-sided well-populated markets (3,270
> of 25,332 fills). It **reproduces exactly** from the pinned export — kept 22,062,
> fills-weighted `pnl×100` = **−1.634¢** pooled (CFB −1.357, WNBA −2.462). The
> **unguarded** anchor is −2.400¢: same column, same settlement horizon, different
> subset — the *unguarded maker* (floor 60.5%), a strategy choice, **not** a more
> "consistent" anchor. Two citation defects this fixes: the guard was mis-named
> "circuit-breaker" (→ `onesided`), and `sandbox.py`'s own emitted statistic is
> **game-clustered −2.626¢** (avg of per-game means), not the published
> **fills-weighted −1.634¢** — fills-weighted is the correct one here because
> `r* = |A|/(H+|A|)` is per-fill on both sides (`H = s_q/2` is per-fill). **Published
> floor 57.8% stands** (H and |A| both on these guarded real fills — §1 below; the
> H that matches |A|'s population is 1.193¢, not the all-fills 1.569¢).

**H (benign-fill earnings) — population-matched to |A|.** A benign fill is a seller
crossing to our resting bid at `qp`; against our quote mid `m_q` we earn
`m_q − qp = s_q/2`, our quoted half-spread (`qp = m_q − s_q/2`, zero residual on
every bid fill). Measured on the **same 22,062 guarded real fills that produce |A|**,
H = **mean(s_q/2) = 1.193¢** — the half-spread we quoted on the very fills that
entered the anchor (verified: reproduces to the digit).

> **CORRECTION, AT THE TABLE — the floor is 57.8%; 51.0% is WITHDRAWN as a
> population mismatch.** This number moved **57.8 → 51.0 → 57.8** today. 51.0% paired
> the guarded-real |A| (1.634¢) with an **all-fills** H (`s_q/2` over all 73,964
> fills = 1.569¢) — a population mismatch: real/adverse fills happen in tighter, more
> active markets, so their quoted half-spread (1.193¢) sits below the all-fills mean
> (1.569¢). The population-matched pair — **both H and |A| on the 22,062 guarded real
> fills** — is **H = 1.193¢, |A| = 1.634¢, r\* = 57.8%**. And 1.193¢ is **not**
> unsourceable (an earlier reading called it so, and I wrongly "superseded" it with
> 1.569¢): it is `mean(s_q)/2` over the guarded real fills, reproduced exactly — what
> was missing was its population and aggregation, now stated.

**Floor, population-matched: r\* = |A|/(H+|A|) = 1.634/(1.193+1.634) = 57.8%** —
26.4 points above the ≈31.4% ceiling.

> **H = s_q/2 is a CEILING on benign earnings, so 57.8% is if anything an
> understatement (c7).** "Benign" is classified by book geometry (ask held vs moved),
> not by whether the counterparty was informed; an informed seller can cross with the
> ask held and drift against us afterward. So the realized benign earning is ≤ s_q/2
> ⟹ true r\* ≥ 57.8%. The caveat widens the close.

---

## 2. The ceiling — the benign share that actually exists

**Benign share of touch-level bid events = 23.7% (28/118).** Three concordant
interval routes: naive binomial **[16.1, 31.4]**, cluster-robust sandwich
**[15.9, 31.6]**, cluster bootstrap over games **[15.4, 30.7]**. **The upper bound
the floor must clear is ≈31.4–31.6%.** Instrument: c7, book-tape depth transitions
(200ms tape, gap ≤ 2s), benign = "ask stays put" (ask-held). Pre-declaration +
cross-tab in `docs/math/benign-fill-predeclaration.md`.

> **CORRECTION, AT THE TABLE — the old [11.6, 35.8] is WITHDRAWN.** It assumed
> G≈20, ρ≈0.3, design effect ≈2.5; the clustering **measured** on the same 118
> events is **G=35, ρ≈0, design effect 1.05**, so the honest upper bound is
> ≈31.4–31.6%, not 35.8% (verified here: the naive CI and the design-effect
> mechanism reproduce exactly; the ρ≈0 measurement is c7's, three concordant
> routes; ce corrected STATUS). The 35.8% made the ceiling look *higher* — it
> flattered the close, the **opposite direction** to the 1.193¢ H error, which
> flattered the floor. Net across both, the close is unchanged and better-sourced.

> **CAVEATS, AT THE TABLE (the number does not travel without them):** n = 118;
> only **1.6%** of transitions carry any touch event; the estimate **RISES with
> sampling gap** (15.6% @1s → 25.0% @10s → 24.3% @30s) because longer gaps admit
> moved-and-reverted books — so **wide-n rows are dirtier, not cleaner; do not
> quote the 30s row** for its narrow interval. WNBA, not CFB. And — the reason
> 23.7% is a BOUND not an estimate — **cancels sit in the numerator** (a maker
> pulling looks identical to a seller hitting), so it overstates the true
> benign-*trade* share (developed in §3).

---

## 3. Commensurability — 23.7% is an UPPER bound on r

r's denominator is fills **our resting order receives**; the ceiling's is **all
touch-level book events**. Not equal, but 23.7% bounds r from above:

- **Cancels** sit in the ceiling's numerator (a maker pulling looks identical to
  a seller hitting), inflating it above the true benign-trade share.
- **Queue selects us into the adverse tail.** A benign cross fills the front of
  the queue (median **15 contracts ahead of us**, p90 850 — c7's book tape; this
  is queue depth *ahead of our order*, a different quantity from the median touch
  depth of 272 in §6, and does not reconcile against it); an adverse sweep clears the
  whole level, us included. So benign flow lives in the small partial crosses
  that fill the front (bid-held-size-down row, 56% benign), while behind the
  queue we catch the large full consumptions (bid-fell row, ~12% benign).
  Realized r sits **below** the event share, not above.

The only unquantified force that runs **upward** is market **SELECTION** (quoting
benign-rich markets); the current design quotes the whole **quotable band** (mid ∈
[0.20, 0.80], spread ≤ 15¢) but does **not** select for benign-richness within it,
so that force is unbuilt. (The probe-size counterfactual is NOT an upward force on
the event share: benign is ask-defined, our bid depth moves events between bid rows
within an ask column, leaving 23.7% invariant.) Note `pop` is mechanically
confounded with spread — `real` is *defined* by ask ≤ B, a narrow-spread
condition, and benign fills live in the ask>B bucket — but that confound bears on
the benign **rate** (the probe's domain, this section), **not** on H, which is the
observable quoted half-spread of §1.

**League-mix caveat (populations differ, examined only in direction).** The floor
is the pinned export (**WNBA + CFB**); the ceiling is the book tape (**WNBA
only**). The cross-league comparison is not reconciled in magnitude. Direction is
reassuring, not alarming: WNBA's adverse anchor (−2.462¢, §1) is more negative
than pooled (−1.634¢), so a like-for-like WNBA-only floor would be **higher** than
57.8%, *widening* the gap the ceiling must clear — the exact same-league floor
needs the WNBA-specific quoted half-spread, not computed here. Flagged because
"probably harmless" is not "examined."

---

## 4. The H inversion — no passive-maker earnings assumption reopens it

Invert r* = |A|/(H+|A|): the H that would let the ceiling break even is
`H = |A|·(1−r)/r`. Compared against **our quoted half-spread, 1.193¢** (H
population-matched to |A|, §1):

| for r = | H required (¢) | × our quoted half-spread (1.193¢) |
|---|---:|---:|
| 23.7% (ceiling point) | 5.26 | 4.41× |
| **31.4% (measured upper bound)** | **3.57** | **2.99×** |

Curve r*(H): 0.6→73% · **1.193 (our quoted half)→57.8%** ·
**2.386 (full spread)→40.6%** · 3→35% · 5.26 (required at the 23.7% point).

**Even at the FULL spread the close holds.** A maker that rests to settlement earns
only the *entry* price improvement, the quoted half-spread (1.193¢), because a
settled binary has **no exit leg** (the same reason the taker threshold carries one
fee) — floor **57.8%**. The optimistic bound is the **full** quoted spread
(2 × 1.193 = 2.386¢, a benign round-trip capturing both legs with zero drift), and
even there **r\* = 40.6%**, above the 31.4% ceiling by ~9 points. So **no
passive-maker earnings assumption reopens the close** — half-spread (57.8%) or full
spread (40.6%), both clear the ceiling. (A round-tripper is a different strategy from
resting-to-settlement, parallel to a taker with edge, and it does not even need to be
invoked — it clears too.)

---

## 5. What only the probe can see

The simulator measures the **adverse** side cleanly (ask≤B fills = A), and **H is
observable per fill** (s_q/2, §1). What it **cannot see is the benign RATE r**:
benign fills (a real trade at our bid, ask stayed up) sit inside the ask>B
"phantom" bucket, **indistinguishable** from true phantoms (mid crossed, no
trade). So **r — not H — is unmeasurable from the shadow fills.** No export pairs
trade prints with contemporaneous book depth at a cadence fine enough to attribute
a transition (an exact `snapshot_id` join exists, but the joined file samples at
265.85s median — too sparse; n=13).

A **probe** — a real resting order that fills — resolves benign-vs-phantom by
construction, so it is the **only** instrument that can ever separate a true
phantom from a real benign fill: a *permanent* measurement gap, not one this tape
can close. **But being the only instrument is not being worth arming.** Given the
floor/ceiling gap already established, the standing recommendation is **not** to
spend the $278 (a1, `e6e6bef`): the probe would confirm a negative already shown,
not open a live question. Both hold — a permanent gap, and not worth the spend at
this margin.

---

## 6. Probe sizing — a spending correction

$278 = **556 contracts @50¢ = 204% of median touch depth** (511% @20¢), so the
probe as sized would be the **dominant order at the touch** — "be the level," not
"join the queue." It lands on the dominate side of **53–79%** of touch
observations depending on price:

| price | probe qty | we dominate | we are buried |
|---|---:|---:|---:|
| 0.20 | 1390 | 78.8% | 21.2% |
| 0.50 | 556 | 58.4% | 41.6% |
| 0.80 | 348 | 53.2% | 46.8% |

To test **passive joining**, size against **p25–p50 depth (36–272 contracts)**,
not a round dollar. At 36c we are buried in 75% of observations (a real
passive-joining test); at 272c it is 50/50; $278 buys mostly the opposite
experiment. This changes what the money buys.

---

## 7. Market selection is closed too — arithmetically

Selection-based making (quote only benign-rich markets) is closed on this tape as
well: B's split needs **31+ benign events where only 28 exist** (of 118). There
is not enough benign flow to select toward, independent of the rate argument.

---

## The one-line close

**Against our 57.8% break-even floor (H and |A| on the same guarded real fills:
H = 1.193¢, |A| = 1.634¢), benign fills are at most 23.7% of the flow (upper bound
≈31.4%), so passive market-making cannot break even on this venue — 26.4 points
clear, for a maker that rests to settlement. Even at the full quoted spread
(r\* = 40.6%) the floor still clears the ceiling by ~9 points, so no passive-maker
earnings assumption reopens it. Against the registered 10% kill line it survives —
so the verdict is stated against the 57.8% floor, and the line is named.** The probe is the only instrument that can ever separate a real
benign fill from a phantom — a permanent measurement gap on the RATE r, not on H —
but at this margin it is not worth arming: it would confirm the negative, not test
an open one (a1, `e6e6bef`).
