# Table tennis (Setka Cup) — pre-registration, written before any tape

2026-09-13. Registered **before** outcomes accrue, which is the whole point:
this is the one family on the board where the design can be fixed in advance
and the answer arrives inside weeks rather than a season.

Everything below marked MEASURED comes from the venue's own slugs pulled from
`market_snapshots` tonight. Everything marked ASSUMED is a parameter that must
be estimated from the first tape before any verdict.

---

## 0. The headline answer

> **The premise "the equivalent power exists by Tuesday" does not survive the
> arithmetic.** By Tuesday (~300 matches) the smallest detectable effect is
> **6.5¢**, against a round-trip hurdle of ~2.0–2.5¢. Table tennis can **rule
> out large edges very fast** — that is genuinely valuable and no other family
> offers it — but it **cannot establish a hurdle-sized edge quickly**, and
> under plausible clustering it may never.

## 1. MEASURED structure

| competition | matches | players P | mean appearances | max |
|---|---:|---:|---:|---:|
| setkameua | 54 | 49 | 2.2 | 5 |
| setkamecz | 48 | 32 | 3.0 | 3 |
| setkamemd | 39 | 28 | 2.8 | 4 |
| setkawoua | 15 | 6 | 5.0 | 5 |
| **all** | **156** | **115** | **2.7** | **5** |

One market per match (`table_tennis_match_winner`), one line, no ladder.
**Zero players appear in more than one competition** — the four pools are
disjoint.

## 2. (d) FIRST: the clustering. A match is a DYAD, not a member of a cluster

**The structure is a network, not a partition.** Each match has two players, so
it belongs to *two* player clusters. "Cluster on player" is not a well-defined
one-way clustering and the usual sandwich does not apply. The correct estimator
is two-way / dyadic-robust (Cameron–Gelbach–Miller):

> **V = V_playerA + V_playerB − V_match**

**Register that estimator now**, because it cannot be retrofitted onto a
published interval.

### How bad is it? Less than feared *within* a day — much worse *across* days

With mean appearances m̄ and intra-player correlation ρ:
`deff = 1 + (m̄ − 1)ρ`, `n_eff = n / deff`.

**MEASURED m̄ = 2.7 per day**, so within one day `deff = 1 + 1.7ρ` ≈ **1.3** at
ρ = 0.3. **I expected far worse and the data says otherwise; the within-day
penalty is mild.**

The danger is cumulative. If the same pool recurs, m̄ grows with days and

> **n_eff → P / (2ρ)** — a constant. More matches from the same pool buy nothing.

| ρ | n_eff cap (P = 115) | best detectable effect, ever |
|---:|---:|---:|
| 0.05 | 1150 | 3.30¢ |
| 0.15 | 383 | 5.72¢ |
| 0.30 | 192 | 8.09¢ |

**Whether the pool recurs across days is the single measurement that decides
whether this family can ever answer anything, and I cannot make it yet** — the
tape spans about one day of schedule. **First registered measurement: player
recurrence across 7 days, and ρ estimated from it.**

### The self-limiting property — the part that matters most

**The edge and the clustering come from the same source.** A favourite-longshot
edge on the winner price exists only if the market systematically misprices
particular players. If it does, ρ is large and `n_eff` saturates early. If ρ ≈ 0
there is no player-linked mispricing to find.

> **You cannot have a large player-linked edge and a small design effect.**
> Any result showing both is evidence of a defect, not of alpha.

Hypotheses that are **not** player-linked escape this entirely, because their
cluster is time or competition rather than player. That is the argument for
ranking the staleness cut above the favourite cut.

## 3. (a) Power

Per-bet SD of a binary held to settlement is **√(p(1−p)) — the outcome's SD, not
the price's**: 50¢ at p = 0.5, 47.7¢ at 0.65, 40¢ at 0.8. That is what governs,
and it is large.

**Hurdle, held to settlement: half-spread + ONE fee.**

| spread | p | hurdle |
|---:|---:|---:|
| 1¢ | 0.50 | 2.00¢ |
| 2¢ | 0.50 | 2.50¢ |
| **2.59¢ MEASURED** | **0.6152 MEASURED** | **2.72¢** |
| 2.59¢ measured | 0.50 | 2.80¢ |

> **Measured on the 27 started matches: mean spread 2.59¢, median 3.00¢** — not
> the 1–2¢ the brief assumed, so **the hurdle is 2.7–2.8¢, not 2.0–2.5¢.**
> Every "days to detect" figure below is correspondingly optimistic.

> **Correction:** the venue fee `0.06·p(1−p)` is charged **once** on a position
> held to settlement, not on entry *and* exit — verified against `bet_pnl` in
> `cfb/run_paper_book.py`. Two fees apply only to a round trip. The hurdle is
> half what the brief assumed.

**Smallest detectable effect (Bonferroni m = 2, z = 2.241):**

| matches | days | deff 1.0 | deff 1.3 | deff 2.0 | deff 4.0 |
|---:|---:|---:|---:|---:|---:|
| 300 | 1.9 | 6.47¢ | 7.38¢ | 9.15¢ | 12.94¢ |
| 1000 | 6.4 | 3.54¢ | 4.04¢ | 5.01¢ | 7.09¢ |
| 3000 | 19.2 | 2.05¢ | 2.33¢ | 2.89¢ | 4.09¢ |
| 10000 | 64.1 | 1.12¢ | 1.28¢ | 1.58¢ | 2.24¢ |

**To detect an edge that merely clears the hurdle (2.5¢): n ≈ 2,000–2,600, i.e.
13–17 days** at the measured 156/day — and **unreachable** if ρ ≥ 0.15 and the
pool recurs.

## 4. (b) The family, and what the small penalty buys

One market per match means far fewer cells than a ladder. The two registered
lines — `tt_home_fav_yes_60` (mid ≥ 0.60) and `tt_home_dog_yes_40` (mid ≤ 0.40)
— select **disjoint** row sets, so **m = 2 genuinely**.

**Bonferroni z = 2.241 at m = 2 versus 3.078 at the CFB registry's m = 24.**
Required effect scales with z, so n scales with z²:

> **(2.241/3.078)² = 0.53 — the same conclusion costs about HALF the data.**
> That is the concrete value of a one-market-per-match family, and it is the
> strongest argument for this venue.

**It evaporates the moment anyone sweeps buckets to find the shape.** Ten price
buckets print 20 cells and compute 10 (YES and NO on one market are exact
complements), taking z back to 2.81. **Register the buckets before looking, or
lose the entire advantage.**

## 5. (c) Askable hypotheses

Given no model, no ESPN feed, and venue-only settlement:

1. **Calibration curve** — does a contract priced p settle YES at rate p?
   Cheapest, needs no edge claim, and doubles as the frame gate (§6). **Run
   first.**
2. **Staleness / first-to-move.** Clustered on time, not player, so it escapes
   the saturation in §2. **Rank above the favourite cut for that reason alone.**
3. **Favourite–longshot on the winner price.** Player-clustered, self-limiting.
4. **Slug-order (home/away) asymmetry** — YES is the *first-named* player for
   table tennis, the opposite of the US team sports.
5. **Within-day sequence effects** — a player's 3rd match of the day against
   their 1st. Uniquely available here, and note the symmetry: the repetition
   that damages the clustering is what makes this hypothesis askable.
6. **Cross-competition replication.** Four disjoint pools, so register in one
   and confirm in another at no cost. **This is the best feature of the family**
   and no other league on the board offers it.

**Not askable:** anything needing an independent state feed — live win
probability, score-path, in-game models. There is no ESPN for Setka Cup.

## 6. Trap list

**TRAP 1 — there is no independent settlement source, and this outranks the
clustering.** The CFB audit's decisive check was ESPN agreeing with the venue
65/65 on the frame. Here there is no second source, so **a systematic frame
error is unfalsifiable from inside** and would present as a large, stable,
beautiful edge. That is exactly how a 20¢ phantom Kalshi edge was once
produced.
**Mitigation, registered as a GATE before any edge claim:** the calibration
invariant of §5.1. A correctly-framed binary has realized YES rate ≈ mean YES
price, and favourites win more than half. **A flipped frame shows favourites
winning less than half.** If realized YES rate and mean YES price disagree,
halt and re-derive the frame — do not report an edge.

**TRAP 2 — player codes are 6-char truncations.** `turrom` / `turmax` share
`tur`; **9 of 115 codes share a 3-character prefix.** A collision silently
merges two players, which **understates ρ and therefore understates the
interval** — the dangerous direction. Validate codes against the venue's full
player names before trusting any clustered interval.

**TRAP 3 — 301 listed versus 156 recorded.** The brief counts 301 events in
~18h from the venue listing; deduplicating recorded slugs gives **156 distinct
matches** over a ~24.5h kickoff window. If the recorder captures about half of
what is listed, **every day-count in §3 doubles.** Resolve before planning.

**TRAP 4 — integrity risk is a statistical hazard here, not a moral aside.**
This match format carries a known integrity-risk profile. If some fraction of
matches are compromised, outcomes are non-random *in ways correlated with the
price and with who is resting size*. **Any edge concentrated in a few players
or a narrow price band is adverse selection until shown otherwise.**

**TRAP 5 — resting size is not executable size.** "Median 27k shares" needs its
units checked and its position in the book — at the touch or spread across it.
In a market settling in 20 minutes, a maker who is there is choosing to be.

**TRAP 6 — silent settlement drops.** With ~156 matches a day settling
continuously, an unsettled market vanishes from a cell unnoticed. **Print the
unsettled count per cell from day one** — the defect just fixed in
`cfb/run_longshot_decomp.py`.

**TRAP 8 — "the last quote before kickoff" is a trap on a forward-listed board,
and it nearly produced a fabricated headline here.** At any moment ~92% of
listed Setka markets have not started (measured: **325 of 352**). For those, the
last quote *before* kickoff is simply **the most recent sweep**, hours ahead of
a kickoff that has not happened. Selecting without a `kickoff < now` filter
gave a **median staleness of 11 hours and a median spread of 50¢** — both pure
artefacts of unstarted markets carrying placeholder books. Filtered to started
matches the same data gives **8.2 minutes and 3.0¢**. **Every pregame-close
query on this family must filter `ko < now()`**, and any figure that looks
catastrophic should be checked against that filter before it is reported.

**TRAP 7 — the complement identity.** YES and NO on one match sum to
`−(spread + both fees)`. Any grid reporting both sides prints double what it
computes, and "YES beat NO" is then arithmetic, not a finding.

## 7. Registered decision rule

1. **Gate:** calibration invariant passes (TRAP 1). Otherwise halt.
2. **Estimator:** two-way dyadic-robust interval, per-contract cents, with
   `deff` and `n_eff` **printed beside every cell**.
3. **Threshold:** Bonferroni at the pre-registered family size, currently m = 2.
4. **Replication:** an effect found in one competition must hold in a second,
   disjoint-pool competition before it is called real.
5. **No verdict before** the 7-day recurrence measurement returns ρ, because
   until then `n_eff` is unknown and every interval is provisional.

## 8. The frame gate: the registered n, and which arm to watch

Added after the gate was first run on 17 matches (mean YES price 0.5588,
realized YES rate 0.5294, favourites 6 of 11). **That was correctly recorded as
NO POWER YET, not as a pass** — P(≥6 of 11 | true rate 0.50) = 0.5000 exactly,
so the test could not have failed and a "pass" would have been an artefact of
running it.

### It is a discrimination, not a significance test

The two hypotheses are **exact mirror images about 0.5**: correct frame puts the
favourite's win rate at p̄_fav, a flipped frame at 1 − p̄_fav. With equal priors
the rule is "decide at the midpoint, 0.5" and the error is symmetric.

> **n ≥ z²·E[p_f(1−p_f)] / (p̄_fav − 0.5)² × deff**
> z = 1.645 for a 5% wrong-call rate, 2.326 for 1%; deff = 1.3 (§2).

| p̄_fav | n (5%) | n (1%) | hours at 156/day |
|---:|---:|---:|---:|
| 0.55 | 348 | 696 | 54 |
| 0.60 | 84 | 169 | 13 |
| 0.65 | 36 | 71 | 5.5 |
| 0.70 | 18 | 37 | 2.8 |
| 0.75 | 11 | 21 | 1.6 |

### MEASURED, on the 27 matches that have actually started

> **p̄_fav = 0.6152** (sd 0.078), E[p_f(1−p_f)] = 0.2367, mean YES mid 0.5541.
>
> **n = 61 matches for a 5% wrong-call rate (9.4h at 156/day); 122 for 1%
> (18.8h).** The 17 already run carry a **19.3%** wrong-call probability.

So the gate is **decisive by tomorrow, not in "a few hundred"** — but it is not
decisive yet, and 19.3% is the number that says so.

### Which arm — and why the obvious one is wrong

| arm | statistic | distance to boundary |
|---|---|---|
| A | favourite win-rate vs 0.5 | p̄_fav − 0.5 |
| **B** | **oriented gap `mean(y_f − p_f)`** | **p̄_fav − 0.5**, lower variance than A |
| C | unoriented `mean(y) − mean(p)` | p̄_YES − 0.5 |

**B dominates A for free**: subtracting p_f removes Var(p_f) from the variance
while leaving the signal untouched.

**C's entire signal is an accident of slug ordering.** If the venue assigned YES
without regard to strength, p̄_YES → 0.500 and **C has no power at any n** — 196
matches at p̄_YES = 0.5588, 1,691 at 0.52, 27,055 at 0.505. A and B *construct*
their signal by orienting on the favourite, which guarantees a positive
distance. At p̄_fav = 0.65, C needs **7× the matches B does.**

> **Registered: the gate is arm B. C is secondary and never counts as the gate.**

## 9. What the sweep interval does to the estimator

Sweeps ~8 min apart; matches last ~20 min.

**MEASURED, on started matches: it does neither. Capture is good and staleness
costs nothing detectable.**

| `mins_before` | p10 | p50 | p90 | max |
|---|---:|---:|---:|---:|
| started matches (n=27) | 2.9 | **8.2** | 22.9 | <120 |

The median close is **8.2 minutes** before start — exactly one sweep interval,
as designed — with **no mass beyond 120 minutes.** Capture ≈ 1; no match is
being dropped.

The registered diagnostic was run: **|p − 0.5| regressed on `mins_before` gives
slope +0.00007/min, r = +0.006** — no detectable attenuation over the observed
0–23 minute range. **Staleness at this sweep rate is free.**

> **Honest limit: n = 27 bounds |r| only below about 0.39** (Fisher-z 95%).
> This is "no detectable attenuation", not "no attenuation". **Re-run the same
> regression at n ≈ 200 before treating it as settled.**

**And the gate would survive it even if it were there.** Attenuation shrinks
toward the null and cannot pass it, so **a flipped frame still shows favourites
winning under half.**

**Price-bucket hypotheses do not survive it.** A stale price misassigns matches
to buckets, and selecting on a noisy variable is regression to the mean.
**Do not run bucketed favourite–longshot on hand-swept tape.**

**A real selection channel, second-order, with the mechanism inverted from the
obvious guess:** a long match does not over-represent *itself* — it delays the
**next** match on that table, lengthening that one's window and making it *more*
likely captured. With players at ~2.7 matches/day back-to-back, the surviving
sample tilts toward **matches following a long match**, i.e. a possibly-fatigued
player. **That shares a cause with registered hypothesis #5 (within-day sequence
effects), so #5 cannot be read on hand-swept tape at all.**

**Registered diagnostics, one column each:**
1. `mins_before` per captured close. Under capture ≈ 1 it lies in (0, S]; **mass
   beyond S means the market stopped being swept — a genuine drop.**
2. **`mins_before` distribution for matches settling YES vs NO.** If capture is
   outcome-independent they coincide. This is the direct falsification of the
   selection worry and costs one query.

## 10. If the gate fails: the re-derivation procedure, written before the answer

Written 2026-09-14 with the gate **trending against the frame and undecided**
(21 settled: favourite win rate 47.6% against a priced 0.6145). Written now
precisely because writing it afterwards is how people talk themselves into the
frame they wanted.

### First, a correction to §6 and §8 — the gate was the wrong instrument

**A "frame error" is not a mislabelling of which player is YES.** If price and
settlement both come from the venue in the same frame, our interpretation of who
YES refers to **does not affect any statistic**: the venue says "YES priced
0.62, YES settled 1" and that is internally consistent whoever YES is.

> **A frame error can only bite as a MISMATCH between the PRICE field and the
> SETTLEMENT field** — for example reading `outcomes[]` order, which is
> documented as unreliable, instead of `marketSides[1].price`.

That is a **code-level field-mapping bug**. It is global, it is symmetric across
YES/NO, and — decisively — **it is a lookup question, not an inference
question.** §6 registered a 61-match statistical gate for it. That was the wrong
instrument, and cheaper ground truth was available all along.

### Step 1 — one hand-verified match beats sixty-one statistical ones

Take a single settled match. Read the venue's recorded price and its settlement.
Check who actually won from the competition's own published result. **n = 1 of
ground truth settles a binary frame question that n = 61 settles only
probabilistically.** The "no independent settlement source" constraint in §6 is
about *routine settlement at scale*; it never meant ground truth was
unobtainable for a handful of matches. **Do this first.**

### Step 2 — audit the mapping in code, not in statistics

Confirm which field is the YES book (`marketSides[1].price`, **not** `outcomes[]`
ordering) and what `settlement` 0/1 refers to. Steps 1 and 2 together either
find the bug or exonerate the mapping; everything below is a fallback for when
they cannot be completed.

### Step 3 — the calibration slope, which separates what the gate conflates

Regress settled `y` on YES mid across **all** markets, not the favourite-oriented
subset.

| slope | reading |
|---|---|
| ≈ **+1** | frame correct; any shortfall is **mispricing** |
| ≈ **−1** | **frame inverted** |
| ≈ **0** | prices carry no information — a third state the gate cannot express |

**This is the answer to a defect in arm B: "frame inverted" and "favourites
systematically overpriced" make the SAME prediction — favourites winning below
their price — so arm B cannot distinguish them, and a gate failure would not
establish a frame error.** The slope can: mispricing shifts the intercept and
leaves the slope positive; inversion flips the sign.

Power, y on price: at sd(price) = 0.12, **n = 61 gives a 2.8% wrong-call rate;
n = 150 gives 0.13%** — better than arm B at equal n *and* it separates the two
hypotheses.

### Step 4 — settlement-order selection

Only ~21 of ~156 daily matches have settled with a pregame close: **the
fastest-settling ~13%.** If settlement speed correlates with outcome
(retirements, disputes, five-setters posting late) the sample is biased, and
nothing makes that bias symmetric. **Compare win rate and p̄_fav across
settlement-lag quantiles; flat means no selection.** This is TRAP 6 and it is
live right now.

### Step 5 — pre-committed decisions

- **slope significantly < 0** → frame inverted. **Halt all table-tennis work**,
  fix the field mapping, re-run every number from scratch.
- **slope ≈ +1 and the shortfall persists** → a **mispricing** result, subject to
  the full multiplicity and power discipline of §3–§4. **Not an edge** until it
  clears them.
- **slope ≈ 0** → prices are uninformative; there is nothing here to trade.
- **To conclude the frame is FINE requires both**: slope > 0 with an interval
  excluding 0, **and** at least one hand-verified match agreeing.

> **Anti-rationalisation clause.** The four readings above are exhaustive as of
> this writing. If, after seeing the resolved data, anyone argues for a fifth,
> that argument must be written down and dated **before** it is acted on.

### What the current 21 matches actually say

**Likelihood ratio for inverted over correct: 1.59 to 1.** A Bayes factor of 3
is "substantial" and 10 is "strong". **1.6 is not evidence**, and "trending, not
decided" is the correct record.

Two candidate explanations sized rather than asserted:
- **max() bias.** Defining the favourite as `max(mid, 1−mid)` on a noisy mid
  overstates p̄_fav by Jensen. Real and correctly signed, but at a 3¢ spread it
  is **~0.03¢ against a 13.8¢ miss — under 0.3%.** Negligible.
- **Settlement-order selection** (Step 4) — unsized, untested, and the largest
  unexamined term.

## 11. Step 2 executed — and a retraction placed where it belongs

### The audit: our code is clean

- `core/recorder.py:212` writes `best_bid`/`best_ask` from `market.best_bid` →
  `schemas.py:96` → **`bestBidQuote.value`**, a venue **market-level** field.
  **No index selection, no `outcomes[]` read, no `marketSides[i]` pick.**
- `core/polymarket/client.py:163` `get_settlement` →
  `/v1/markets/{slug}/settlement`, **the same slug, also market-level.**
  `core/settlements.py` adds only the 0.5 draw label.
- **No per-league or per-sport branching on this path.**

> **Our code cannot introduce a price/settlement mismatch.**

### But that does not close it

**"Consistent by construction" does not follow.** The audit **relocates** the
question from our code to **the venue's** convention: does `bestBidQuote` refer
to the same side that `/settlement` reports? **A code audit cannot answer that.**
If the venue is internally inconsistent for this family, a faithful reading of
both fields reproduces the inconsistency exactly. Our cleanliness is **necessary,
not sufficient.**

### RETRACTED, before it was published: the "±12¢ therefore not inverted" argument

I drafted, and did not send, this: *"the four measured CFB cells sit within
±12¢, and an inversion would show ±50–90¢, therefore the venue's fields agree in
side."*

**It is wrong. All four cells sit at p ≈ 0.5, where the two hypotheses differ by
only ~10¢ against ~20¢ intervals.**

| cell | m | correct | inverted | measured | separation |
|---|---:|---:|---:|---:|---:|
| away @0.55 | 0.55 | −3.0¢ | −13.0¢ | −11.6¢ | **10¢** |
| home @0.45 | 0.45 | −3.0¢ | −13.0¢ | +7.5¢ | **10¢** |

**That is reading a test at the price where its two hypotheses coincide** — the
same defect retired in §2's twin clause. **The discriminating information lives
in the price TAILS**, where inversion moves E[pnl] by 40–90¢.

**The genuine CFB evidence is the ESPN check**, for a different reason: 65/65
compares venue settlement to **real-world outcomes directly, independent of
price.** That establishes settlement↔reality **for CFB**. It says nothing about
table tennis.

### MEASURED correction: the price sd, and what it buys

**sd(YES mid) = 0.1355** on started markets, range **0.200 – 0.775**. §8 had been
quoting 0.078, which is the sd of **p_fav**, not of the price. **8 of 35 markets
sit at |p − 0.5| ≥ 0.20**, where inversion moves E[pnl] by ≥40¢ — and the slope
weights that tail automatically.

| n | calibration slope, wrong-call | arm B, wrong-call |
|---:|---:|---:|
| **21 (already settled)** | **10.0%** | 17.1% |
| 35 | 4.9% | 11.0% |
| 61 | 1.5% | 5.2% |
| 150 | 0.0% | 0.5% |

> **On the same 21 matches the slope is about twice as informative as arm B, and
> it separates inversion from overpricing, which arm B cannot. It needs no new
> tape. Run it before waiting for n = 61.**

### Registered amendment to Step 1

**Verify two or three matches, not one, and choose them at |p − 0.5| ≥ 0.20.**
A single match at p ≈ 0.55 is consistent with both hypotheses; one at p = 0.775
going the wrong way is already strong evidence. **The information is in the
tails, so choose the lookups there** — the same principle as the slope.

## 12. TRAP 1 CLOSED — the frame is sound, and the shortfall was noise

### The chain, verified end to end by two independent routes

    bestBidQuote == marketSides[0]  [10/10 exact]  →  /settlement  [30/30 agree]

**Route 1, field identity.** `bestBidQuote.value == marketSides[0].price` and
`bestAskQuote.value == marketSides[1].price`, **exactly, on every market
checked.** And `marketSides[0].long = true` on **all 6,560** recorded rows.

> **`marketSides[]` is NOT two contracts. It is the BID and the ASK of one book
> — the YES book.** side0 is the YES bid, side1 the YES ask. The array's naming
> (each entry carries a team/player description) invites reading it as two
> opposing sides, which is the venue's presentation defect. Anything that treats
> side0 and side1 as complementary outcomes is wrong.

**Route 2, the calibration slope.** n=35, slope **+0.8990 (se 0.5813)**:

| hypothesis | z | p | |
|---|---:|---:|---|
| **inverted frame (slope = −1)** | +3.267 | **0.0011** | **REJECTED** |
| prices uninformative (slope = 0) | +1.547 | 0.122 | not rejected |
| perfect calibration (slope = +1) | −0.174 | 0.862 | not rejected |

**The slope rejects inversion on its own, with no shared code with Route 1.**
Two genuinely independent instruments, same answer. **TRAP 1 is closed.**

### The "favourites underperform by 13.8¢" reading is retired — it was noise

The YES-frame calibration gap was **−2.9¢ at n=21** and **+3.2¢ at n=35**. The
21 are a subset of the 35, so **the 14 new matches averaged +12.35¢** — two
adjacent subsamples of one process differing by **15.3¢**.

**The SE of a mean gap is 10.9¢ at n=21 and 8.5¢ at n=35 — both larger than
either observed gap. Neither reading was ever readable.** It was not a trend
that reversed; it was the first draw from a wide distribution, and recording it
as "trending" gave it more standing than the arithmetic supported.

> **Registered correction: do not carry a direction forward from a sample whose
> SE exceeds the effect. "Trending" is a claim about a sequence, and one draw is
> not a sequence.**

### What is actually open

Not the frame. **Whether these prices carry any information at all** — slope
+0.899 cannot be distinguished from 0 (p=0.12) or from 1 (p=0.86).

> **Next milestone: n = 56 puts the slope CI off zero — about 8.6 hours at
> 156/day.** Until then no TT number is readable in either direction.

### A method note worth keeping

My own test of Route 1 was **built on a wrong model of the field** — I compared
the mid against side0 and side1 as if they were complementary outcomes, so
`mid = (side0+side1)/2` was **equidistant from both by construction** and the
statistic could never discriminate. **48% of rows came back as exact ties**,
which was the answer in disguise. And `avg(side0+side1) ≈ 1.0091` looked like
confirmation of the wrong model, because averaging a symmetric high/low mix
destroys the shape. **Check what your statistic can produce under the model you
are testing before you run it.**
