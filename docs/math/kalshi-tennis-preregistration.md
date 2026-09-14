# Kalshi tennis — pre-registration, written before the recorder's first tape

2026-09-14. Registers the frame check, the hurdle and the power arithmetic for
ITF / ATP-Challenger / WTA match-winner markets **before any tape accrues**.

Everything marked MEASURED comes from the catalogue survey's saved payloads.
Everything marked UNVERIFIED is flagged as such and may not be used in a number.

---

## 0. The structural fact everything else follows from

**Kalshi lists TWO markets per match, one per player.**

    event  KXWTAMATCH-26SEP14SONSHY
      market -SON   title "Zeynep Sonmez wins"      yes_sub_title "Zeynep Sonmez"
      market -SHY   title "Iryna Shymanovich wins"  yes_sub_title "Iryna Shymanovich"

Two consequences, in opposite directions.

**Good: there is no frame ambiguity.** `yes_sub_title` names the player
explicitly. Nothing has to be inferred from ticker ordering — unlike the
Polymarket convention, where "YES = away team" had to be established and then
verified 65/65 before any number could be read.

**Bad: four tradeable positions per match collapse to ONE statistic.**
`YES(SON) ≡ NO(SHY)` and `NO(SON) ≡ YES(SHY)` are the same economic bet, and
YES/NO on one market are complements summing to `−(spread + fees)`.

> **REGISTERED: `m_eff = m/4` for these families, not m/2 and not m.**
> Bonferroni at m=500 is |z| 3.891; at m=125 it is 3.540. **That hands back
> 0.351σ**, free, for counting correctly.

**This is the fourth appearance of the complement property in two days** — five
pairs in the paper-book registry, ten-of-twenty printed decomposition cells, the
scan's side axis, and now the venue's own market structure. **It is a property
of two-sided prediction markets, and the market count is the first thing to
check on any new venue.** In particular **107,599 "open markets" overstates
distinct binaries by ~2× for two-market families**, and a claim of "833 settled
matches/week" must be confirmed to count *matches* and not *markets*.

---

## 1. The dyadic problem — measured, not carried over from Setka

MEASURED, from one snapshot of 151 singles match-winner events:

| | Setka Cup | Kalshi tennis |
|---|---:|---:|
| distinct players | 115 | **298** |
| matches in view | 156 (one day) | 151 (snapshot) |
| appearances per player | 2.7/day | 294 of 298 appear **once** |
| players crossing competitions | **0** | 3 apparent — **all name collisions** |

**A snapshot bounds pool BREADTH at an instant. It cannot measure recurrence or
ρ**, which need a time series — the same limit that stopped the Setka analysis,
and it must not be papered over by projecting.

### Whether the cap stops binding

`n_eff → P/(2ρ)`. A conclusive negative at the 2.25¢ taker hurdle needs
**G ≈ 3,900**:

| pool P | ρ=0.30 | ρ=0.15 | ρ=0.05 |
|---:|---:|---:|---:|
| 298 | 497 | 993 | 2,980 |
| 600 | 1,000 | 2,000 | **6,000 ✓** |
| 1,200 | 2,000 | **4,000 ✓** | **12,000 ✓** |
| 2,400 | **4,000 ✓** | ✓ | ✓ |

**So the cap plausibly stops binding — but it is NOT established, and the
snapshot cannot establish it.**

### The structural difference, and the one diagnostic that settles it

**In Setka the pool is closed: the same ~115 players play daily, so P is fixed
and the cap bites. In professional tennis the draw turns over weekly, so P GROWS
with the observation window.** That is the whole difference, and it is directly
measurable.

> **REGISTERED, first diagnostic once tape exists: plot cumulative distinct
> players against cumulative matches. Growth that stays near-linear means the
> cap never binds. A plateau means it does, and `P_plateau/(2ρ)` is then the
> ceiling on everything.** No power claim may be published before this is read.

### ⚠ Player identity cannot be resolved from titles

MEASURED name formats across 302 title slots: **261 surname-only** ("Sonmez",
"Frech"), 37 two-token, 4 three-token. The three apparent cross-series players
are collisions — **"Liu" spans an ATP series and a WTA series** and is certainly
two people.

**A collision merges two players, which understates ρ and therefore SHRINKS the
interval — the dangerous direction.** Use ticker player codes or an external
player ID; **never parse identity from `title`.**

---

## 2. The hurdle — re-derived, and one premise corrected

### `fee_type` is a venue-declared field, and it is not uniform

MEASURED across all 14,018 series: **`quadratic` 13,855 (98.8%)**,
**`quadratic_with_maker_fees` 160 (1.1%)**, `quadratic_with_combo_maker_fees` 3.

| series | fee_type | |
|---|---|---|
| KXATPCHALLENGERMATCH | quadratic | no maker fee |
| KXITFMATCH | quadratic | no maker fee |
| KXITFWMATCH | quadratic | no maker fee |
| KXWTACHALLENGERMATCH | quadratic | no maker fee |
| **KXWTAMATCH** | **quadratic_with_maker_fees** | **HAS maker fees** |

> **Correction: "these series carry no maker fee at all" is true of four of the
> five. KXWTAMATCH — the WTA main tour — carries maker fees.** Any making
> registration must be per-series.

**This partially resolves an older note.** Kalshi fee facts were recorded as
"unverifiable from the venue". **The fee TYPE and MULTIPLIER are venue-declared
and verifiable.** The taker RATE is not — I could not extract a rate from the
CFTC filing with available tooling, so **`0.07·p(1−p)` remains UNVERIFIED and is
used below only as a stated assumption.**

### ⚠ fee_type CHANGES ARE SCHEDULED

`series_fee_changes.json` carries dated future changes, including series moving
*into* `quadratic_with_maker_fees`.

> **REGISTERED: poll series fee_type before every read. A maker-fee-free series
> can acquire maker fees under a live strategy on a scheduled date, and the
> strategy would keep reporting as though free.**

### The "rebate accumulator" is a rounding refund, not a maker rebate

Kalshi's own doc: **Net fee = trade fee + rounding fee − rebate, always ≥ $0.00.**
The accumulator amortises round-up across the fills of one order so the total
converges to a single equivalent fill. **It never makes a fee negative and it is
not an incentive.**

**Rounding is material at small size.** Non-direct member balances align to
**$0.01**; Kalshi's worked example turns a **$0.003638 model fee into $0.005
charged — a 39% uplift.** There is therefore a **minimum economic order size**,
and it must be computed before any per-contract number is quoted.

### Account type is a gate on two separate terms

The Liquidity Incentive Program — which pays for resting orders **even unfilled**
— excludes **"Introducing Brokers, FCMs, and their customers."** So a non-direct
account is **ineligible for the maker subsidy** *and* carries the **worse $0.01
rounding grid**. Both cut the same way.

> **REGISTERED: establish whether we are a direct member or an FCM customer
> BEFORE any making number is computed. It changes two terms at once and is an
> operator fact, not a measurable one.** (LIP also ends 2027-01-01 and Kalshi may
> modify it at any time, so it is not a durable edge in any case.)

### The numbers

MEASURED spread: **1.0¢ on all 12 sampled tennis markets** — but the same
survey's catalogue table gives a **3.0¢ median across Sports markets that traded
in 24h**. The depth sample is a liquid subset. **Treat 1.0¢ as the best case and
re-measure on our own tape.**

| | at p=0.50 | at p=0.65 |
|---|---:|---:|
| taker, direct member | **2.25¢** | 2.09¢ |
| taker, non-direct, small order | up to 3.25¢ | up to 3.09¢ |

**Maker, on the four fee-free series:** earns half-spread **+0.50¢**, pays no
fee, pays rounding, pays **adverse selection**.

> **Making is REOPENED as a question, not as an opportunity.** Removing the
> maker fee removes one term. **The binding term is adverse selection, which was
> never the basis of the old "structurally impossible" verdict and remains
> unmeasured.** Break-even needs **adverse selection < 0.50¢ per fill**; CFB
> measured 1.6–2.6¢.
>
> **And the inversion worth stating plainly: the tight 1¢ spread that makes
> TAKING cheap makes MAKING harder.** A wider spread is a maker's revenue.

---

## 3. The frame check — first thing that runs

### It is cheaper here than anywhere else we have worked

`yes_sub_title` names the player. **The venue is self-describing, so there is no
convention to infer.** Run the check anyway, because a self-describing field can
still be mis-consumed by our own code — that is exactly the gap found on
Polymarket, where the field identity was assumed rather than measured.

**Three checks, in this order, before any number is read:**

1. **Free, in-venue, every tick, no external source:** the two markets of one
   event must have **YES mids summing to 1**. Deviation measures book
   inconsistency and is a standing data-quality gate. *(It is also an arbitrage
   detector, though at a 1¢ spread on each leg the round trip costs ~1¢ against
   a $1 payoff, so a dislocation must exceed that to be real.)*
2. **Field identity:** confirm our recorder persists the price of the market
   whose `yes_sub_title` we attribute it to — the Polymarket lesson, where price
   and settlement fields had to be shown to name the same side.
3. **External ground truth:** for settled matches, `yes_sub_title` of the
   market that settled YES must equal the actual winner per the series'
   **declared** settlement source (ATP / ITF / WTA / ESPN / Flashscore).
   **Verify two or three matches at extreme prices, not one at the median** —
   a match at p≈0.55 is consistent with either frame.

### ⚠ Kalshi's own settlement_sources URLs contain errors

**KXITFWMATCH — the women's series — lists a Flashscore URL pointing at
`tennis/itf-men-singles`.** The source NAMES are reliable; **the URLs are not,
and must never be used as automation targets.**

---

## 4. What may not be claimed yet

- **No power claim** until the cumulative-players diagnostic (§1) returns.
- **No making number** until account type (§2) is established.
- **No per-contract number** using `0.07·p(1−p)` without flagging it UNVERIFIED.
- **No cell count** that does not divide by four (§0).
- **No edge number at all** until the three frame checks (§3) pass.
