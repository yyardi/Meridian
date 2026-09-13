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
| 1¢ | 0.65 | 1.86¢ |
| 2¢ | 0.50 | 2.50¢ |
| 2¢ | 0.65 | 2.36¢ |

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
