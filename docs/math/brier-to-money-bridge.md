# Does B's identity model clear τ? The Brier→money conversion

**Question (ce).** B's zero-parameter identity beats ESPN by **+0.02456** Brier and
an anchor by **+0.02043** on 31 settled CFB games. Does that clear the taker
threshold τ? I own both sides of the conversion, so here it is — honestly, with the
one number that would settle it and is missing.

**Answer up front: it cannot be converted to a clears/fails verdict yet, and the
blocker is a baseline, not a subtlety.** The improvements given are vs **ESPN** and
vs an **anchor** — neither is the **in-game venue price** the model would trade
against. Beating ESPN is not beating the venue, and the machinery below only
converts a *model-vs-market* Brier. What B must supply to unblock it is named at
the end.

---

## The machinery (from `football-money-bar.md` §5)

Per market, for a calibrated model, Brier improvement **against the market price**
`q` equals the squared trading edge: `Brier(q) − Brier(p) = (q − p)² = edge²`.
So `√(Brier improvement) = RMS edge` — and by Jensen the RMS is an **upper bound**
on the mean tradeable edge `E|q − p|`. The population Brier is
`E[edge²] = (mean edge)² + Var(edge)`, dominated by dispersion, so the naive square
root overstates the per-trade edge.

Crucially, the identity holds **only when `q` is the price you trade against.**
`Brier(ESPN) − Brier(identity)` is the squared *distance from the identity to
ESPN*, not an edge over the market — two models can differ by 16pp and both lose to
the venue.

---

## The four reasons a clean verdict is not available

**1. Wrong baseline — the decisive one.** The tradeable edge is
`identity − venue_price`, and `Brier(venue)` is not among the numbers. The four
Brier levels given — identity 0.02948, anchor 0.04991, ESPN 0.05404, base-rate
0.09856 — establish the identity is the **most accurate of the four**, but none is
the in-game venue. And the venue is a *strong* baseline (pregame WP sd **0.2663**)
while ESPN is nearly uninformative (sd **0.0222**, ce) — so beating ESPN by 0.0246
says almost nothing about beating the venue. **If `Brier(venue) < 0.02948`, the
identity has negative edge over what it trades and clears no τ at all.** That number
is unmeasured.

| baseline | √(improvement) = RMS *distance* to it | is it the venue? |
|---|---:|---|
| vs ESPN | 15.7pp | no (near-uninformative) |
| vs anchor | 14.3pp | only if the anchor is the venue's *pregame* price — still not the in-game price at the trading moment |
| vs in-game venue | **—** | **the number that matters, absent** |

**2. RMS ≠ mean, and money lives in the tail.** Even against the right baseline,
√(population Brier) is an upper bound on the *mean* edge; the taker's money is
`E[(|edge| − τ)⁺]` over the markets it selects, which depends on the **upper tail**
of the edge distribution and the **selection rule** — not recoverable from a single
population Brier. So "population Brier → per-trade edge" needs B's selection rule.

**3. Wrong window for PULSE.** PULSE trades the **last 15 minutes**, where the edge
**spans zero**: late `+0.01320 [−0.0171, +0.0435]`. The significant edge is **early**
(`>35m: +0.05115 [+0.0098, +0.0925]`). So even before the baseline problem, the
edge is not established in the window PULSE trades — clearing τ there would be a
*different* strategy ("trade earlier"), which is the route the money-bar doc
flagged as open.

**4. Population-mismatched τ.** The identity is a **winner-market** model, so it
faces the CFB **winner** τ. That is **unmeasured at competitive prices** — tonight's
only live game was a blowout (winner market 100% at mid 0.02–0.08, τ≈0.5pp there,
p=0.5 unmeasured; Saturday fixes this). The only winner τ I have at p≈0.5 is the
**WNBA** proxy, ~1.93pp — and a CFB Brier against a WNBA τ is the exact splice we
caught d5 make with λ*. Say which τ, on which population.

---

## The conditional ceiling (so the news is not only negative)

*If* the edge were measured vs the in-game venue, *and* in the early window, *and*
real, then √0.05115 = **22.6pp RMS** would clear a ~1.9pp winner τ even after a
large RMS→mean discount for dispersion. So the *ceiling* is promising — the edge is
big relative to any plausible τ. The entire question is whether it survives being
re-measured **against the venue** rather than ESPN; leg 1 is load-bearing and
everything else is secondary to it.

---

## What B must supply to make it convertible

1. **`Brier(in-game venue)` on the same 31 games**, at `<15m` (PULSE's window) and
   at the early window — so the edge is `identity − venue`, not `identity − ESPN`.
2. **The selection rule** — which markets/prices the strategy trades — so the
   population Brier becomes `E[(|edge| − τ)⁺]`.
3. **Matched-population τ** — CFB winner-market τ at competitive prices, which needs
   Saturday's non-blowout games.

With those three, the conversion is mechanical: per-market `edge = identity − venue`,
compare to `τ(type, price)` at each trade, money `= E[(|edge| − τ)⁺]`. Until then,
"+0.02456 Brier vs ESPN" is a real accuracy result and **not** a money result.

---

*Populations: B's Brier is CFB, 31 games, out-of-fold, loose predicate, 90.3% home.
τ: CFB winner is G=1 (tonight, blowout) so unmeasured at p≈0.5; WNBA winner ~1.93pp
is the only competitive-price proxy. Mapping and τ surface from
`football-money-bar.md`. The venue-baseline Brier is B's to compute.*
