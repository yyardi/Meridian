# Passive market-making: the close

**VERDICT (name the line, always).** Against the break-even floor — benign fills
must be **≥ 57.8%** of fills received — the measured benign ceiling of **23.7%**
(an upper bound) cannot clear it, and inverting the formula shows **no
passive-maker earnings assumption reopens it**. So against A's 48%/57.8% floor,
passive joining **cannot break even**. Against c7's independently-registered **10%
kill line**, the same 23.7% does **not** kill. The verdict flips on which line, so
the line is named at every claim below.

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

**Adverse anchor A, rebate-free (real fills, circuit-breaker guarded,
fills-weighted cluster-robust sandwich):**

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

**H (benign-fill earnings) is the maker's structural edge.** A passive order
resting at the touch captures at most the spread it quotes: the measured
**half-spread is 1.193¢** (the structural value), the **full spread 2.386¢** the
optimistic ceiling (all edge, zero post-fill drift).

**Floor at the half-spread: r\* = 57.8%.** With the phantom rebate it was 48%;
removing the rebate moved A from −1.349 to −1.634, which raised the floor **48% →
57.8%**.

---

## 2. The ceiling — the benign share that actually exists

**Benign share of touch-level bid events = 23.7% (28/118).** Naive binomial CI
[15.9, 31.4], but that ignores clustering; the **clustering-widened CI is
[11.6, 35.8]** (G≈20, ρ≈0.3, design effect ≈2.5). **The upper bound the floor
must clear is 35.8%, not 31.4%** — the wider, more honest number, quoted here
precisely because the conclusion survives it. Instrument: c7, book-tape depth
transitions (200ms tape, gap ≤ 2s), benign = "ask stays put" (ask-held).
Pre-declaration + cross-tab in `docs/math/benign-fill-predeclaration.md`.

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
benign-rich markets); the current design quotes the whole board, so it is unbuilt.
(The probe-size counterfactual is NOT an upward force on the event share: benign
is ask-defined, our bid depth moves events between bid rows within an ask column,
leaving 23.7% invariant.)

**League-mix caveat (populations differ, examined only in direction).** The floor
is the pinned export (**WNBA + CFB**); the ceiling is the book tape (**WNBA
only**). The cross-league comparison is not reconciled in magnitude. Direction is
reassuring, not alarming: WNBA's adverse anchor (−2.462¢, §1) is more negative
than pooled (−1.634¢), so a like-for-like WNBA-only floor would be **higher** than
57.8%, *widening* the gap the ceiling must clear — the exact same-league floor
needs the WNBA-specific half-spread, not computed here. Flagged because "probably
harmless" is not "examined."

---

## 4. The H inversion — the close that needs no earnings assumption

Invert r* = |A|/(H+|A|): the H that would let the ceiling break even is
`H = |A|·(1−r)/r`.

| for r = | H required | vs half-spread (1.193¢) | vs full spread (2.386¢) |
|---|---:|---:|---:|
| 23.7% (ceiling point) | 5.26¢ | 4.4× | 2.2× |
| 31.4% (naive CI upper) | 3.57¢ | 3.0× | 1.5× |
| **35.8% (clustering-widened upper bound)** | **2.93¢** | **2.5×** | **1.23×** |

Curve r*(H): 0.6→73% · **1.193 (half)→57.8%** · **2.386 (full)→40.6%** · 3→35% ·
4→29% · 5→24.6% · the widened 35.8% bound at H = 2.93¢ · reaches the 23.7% point
only near H = 5.26¢.

**Even at the FULL spread** (H = 2.386¢ — capturing the entire quoted spread with
zero adverse post-fill drift, already optimistic), **r\* = 40.6%**, above the 23.7%
point AND above the **clustering-widened 35.8% ceiling upper bound** (not just the
naive 31.4%). So no H a passive maker can reach clears the
ceiling. **Lead with the honest bound:** even granting the maker the
clustering-widened **35.8%** ceiling (the most generous defensible share),
breaking even needs **H = 2.93¢ = 1.23× the full spread**; at the 23.7% point it
is 5.26¢ = 2.2×. Either figure exceeds the full spread — the ceiling on what
passive joining can earn — so it is directional alpha, not making. **The close
does not rest on the half-spread assumption** — it is: *even at the most generous
honest ceiling, the rate is too low unless a passive fill earns more than the
entire quoted spread, which a passive maker structurally cannot do.*

---

## 5. What only the probe can see

The simulator measures the **adverse** side cleanly (ask≤B fills = A) but
**cannot see the benign side at all**: benign fills (a real trade at our bid,
ask stayed up) sit inside the ask>B "phantom" bucket, **indistinguishable** from
true phantoms (mid crossed, no trade). So **both H and r are unmeasurable from
the shadow fills.** No export pairs trade prints with contemporaneous book depth
at a cadence fine enough to attribute a transition (an exact `snapshot_id` join
exists, but the joined file samples at 265.85s median — too sparse; n=13).

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

**Against our own 57.8% break-even floor, benign fills are at most 23.7% of the
flow (35.8% at the clustering-widened upper bound), and no passive-maker earnings
can bridge the gap — even at the full spread the floor is 40.6%, above that
widened ceiling; passive market-making cannot break even on this venue. Against the registered 10% kill line it survives
— so the verdict is stated against the 57.8% floor, and the line is named.** The
probe is the only instrument that can ever separate a real benign fill from a
phantom — a permanent measurement gap — but at this margin it is not worth arming:
it would confirm the negative, not test an open one (a1, `e6e6bef`).
