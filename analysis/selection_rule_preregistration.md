# Selection rule — pre-registration

**Written 2026-09-06, before any rung has been scored for money.** A's bridge
reduces money to `E[(|edge| - tau)+]` over a selection rule, and the rule is the
last unregistered object between a Brier number and a money number. Written after
seeing which rungs would have paid, it is a free parameter on the figure that
decides whether we trade.

The projection below was run BEFORE the rule was written, per ce and per the
shape test's §5d — which is the check that mattered there and had a bug of its
own.

---

## 0. THE PROJECTION, RUN FIRST

Model = each ladder's own probit fit; price = observed quotes; 5 games, 75 rungs.

    |edge| = |model - mid|, pp     median 1.46   p75 2.88   p90 4.31   max 7.08
    half-spread at those rungs     median 1.00   p75 2.50   p90 3.50

    would a rule ever fire?  (edge must beat half-spread + tau)
      winner  tau 0.5pp    34/75 rungs (45.3%)   5/5 games
      spread  tau 2.0pp    16/75 rungs (21.3%)   5/5 games
      total   tau 3.5pp     5/75 rungs ( 6.7%)   2/5 games

**The rule is not degenerate: it can both fire and abstain on plausible inputs**,
and the fraction moves sensibly with tau. That is the achievable-image check
passing. It would have failed if any row read 0/75 or 75/75.

### ★ WHAT THE PROJECTION CHANGED IN THE DESIGN

**1. The crossing cost is the same size as the edge.** Median edge 1.46pp against
median half-spread 1.00pp. At p75 it is 2.88 against 2.50. **A rule that measures
edge against the MID and then transacts at the TOUCH keeps a number that is
roughly twice what it earns.** So edge is defined against the touch price
throughout, never the mid.

**2. Rung residuals ALTERNATE SIGN within a game**, roughly balanced above and
below the fit (8/9, 7/8, 2/4, 6/5, 10/16), longest same-sign runs of 2-6:

    a rule firing on many rungs of one game would be taking BOTH SIDES of that
    game and calling it diversification

This is the sharpest thing in the projection and I would not have written the
rule this way without it. Rungs are ~40 views of two parameters; their
disagreements with a model are mostly SHAPE NOISE, which oscillates. A real
directional view — the anchor is wrong, or the scale is wrong — moves neighbouring
rungs the SAME way.

**3. These are not real edges and the numbers above are a NOISE FLOOR.** The
projection's "model" is the ladder's own in-sample fit, so its residuals are
mean-zero by construction. **A genuine edge must clear this floor, not merely be
positive.** Median 1.46pp of pure fit noise is the bar the identity has to beat
before any of it is real.

---

## 1. THE RULE

For each candidate rung, at decision time:

    p_model   the identity's probability for that rung's event
    p_touch   the price we would actually transact at:
                  BUYING  -> best_ask       SELLING -> best_bid
    tau       tau(market_type, p_touch)  -- NEVER a scalar, see §2

    edge_net = (p_model - p_touch) if buying, (p_touch - p_model) if selling
    ENTER iff  edge_net > tau + MARGIN,  MARGIN = 1.50pp

`MARGIN` is set to the projection's **median in-sample residual, 1.46pp, rounded
up to 1.50pp**. It is the noise floor, not a tuned parameter, and it is fixed
here before any scoring. Its justification is §0.3 and it may not be lowered
after seeing a P&L.

### Side

Determined by the sign of `p_model - p_mid`, but transacted and scored at the
touch. No rule may take a side at the mid: the mid is not a price anyone fills at.

### ★ One position per game, and a coherence requirement

**At most ONE rung per game.** Rungs are ~40 views of two parameters and firing
on k of them is one bet at k-times size, not k bets.

Selection among candidates, in order:

1. Discard any rung whose `edge_net <= tau + MARGIN`.
2. **Coherence filter:** keep a rung only if at least 2 of its 3 nearest
   neighbouring rungs (by line) have the same sign of `p_model - p_mid`. An
   isolated sign flip is shape noise by §0.2 and is not tradeable.
3. Among survivors take the **largest `edge_net`**.
4. If none survive, **ABSTAIN**.

### Abstain

The default. Most of the board is abstain and that is the expected outcome, not
a failure of the rule.

---

## 2. tau IS A FUNCTION, NOT A NUMBER

A measured tau on CFB at roughly **winner 0.5pp / spread 2.0pp / total 3.5pp**,
and the fee term alone varies **7x across the price axis**. So a scalar threshold
is a four-population mixture wearing a decision rule's clothes — the same defect
as every other mixture statistic this programme has produced.

**Every candidate is compared against tau evaluated at ITS OWN market type and
ITS OWN touch price.** This is in the rule rather than in a caveat because a
caveat has no test. Implementations must take `tau(market_type, price)` as a
callable and must fail loudly, not default, on an unknown market type.

---

## 3. WHAT WOULD MAKE THIS RULE WRONG

Declared now so it is falsifiable:

* **If it fires on more than ~40% of rungs**, MARGIN is too low and it is
  trading fit noise. The projection puts spread-tau firing at 21.3% with a
  ZERO-noise-floor rule; adding MARGIN must reduce that.
* **If it fires on fewer than 2 games in 10**, it is inert and no money
  statement can be made from it — report as "admitted nothing", which is a
  finding and not a failure.
* **If P&L is carried by one game**, the same leave-one-out instability that
  made the winner-market result fragile applies; report LOO range alongside.
* **If the coherence filter never binds**, it is decoration — report how many
  candidates it removed.

---

## 4. WHAT THIS RULE IS NOT

* Not a sizing rule. One position per game, unit size. Kelly, bankroll and
  correlation across games are out of scope and must not be smuggled in later
  as "tuning".
* Not validated. It has been PROJECTED, not run. The projection uses in-sample
  ladder residuals as a stand-in for the identity's edge, so §0's magnitudes are
  a noise floor and not an expected P&L.
* Not applicable live. Everything above is pregame. The live case needs the
  identity's update term, which the winner-market work found decayed to 3.50pp
  of disagreement by the last 15 minutes.

G will be quoted on every row it ever produces.

---

## 5. THE EMIT CONTRACT (A's money conversion)

One row per CANDIDATE rung, not per fired rung — A needs the abstains to compute
`E[(|edge| - tau)+]` over the rule, and a file containing only winners is a
selection effect wearing a schema.

    game_id            cluster key. MONEY CLUSTERS BY GAME, NEVER BY RUNG.
    market_slug        the rung
    sports_market_type winner | spread | total  -- tau's first argument
    line               signed, for the coherence filter and for diagnosis
    mid                (bid+ask)/2  -- FORECAST comparison ONLY, never P&L
    touch              the price we would transact at: ask if buying, bid if
                       selling. THIS is what tau is evaluated at and what P&L
                       uses.
    model_p            the model's probability for this rung's event
    y                  settlement 0/1, NULL until the game resolves
    side               buy | sell, from sign(model_p - mid)
    trade_flag         the rule's predicate, §1
    abstain_reason     which test rejected it, or NULL if traded

### ★ ONE CORRECTION TO A's FORMULA, AND IT IS ROUGHLY A FACTOR OF TWO

A proposed `realized = sign(edge) * (y - venue_p) - tau(type, price)`. If
`venue_p` is the mid, **that books entry at a price nobody fills at.** From §0:

    median |edge| 1.46pp      median half-spread 1.00pp

**The half-spread is about two thirds of the typical edge.** Entering at the mid
and settling against truth overstates P&L by roughly the half-spread on every
trade, which on these numbers is most of it. This is c7's registered separation —
mid for the forecast comparison, touch for any P&L — and it is why both columns
are emitted rather than one `venue_p`.

So: `edge_for_decision = model_p - touch`, and `realized = sign * (y - touch) - tau(type, touch)`.

### WHAT I CANNOT EMIT YET, STATED SO IT IS NOT ASSUMED

**There is no scored model on ladders.** The identity predicts P(home wins), a
winner-market quantity; porting it to a spread rung needs the scale surface, and
**neither scale surface has a sound selector** (see `ladder_shape_test.py`) —
d5's kickoff was first-SEEN, mine was a batch `is_live` flip, and my defensible
cohort is ONE game. So `model_p` cannot be filled today.

`tau` for CFB spread is itself G=1 tonight.

**The schema is real and the rule is registered; the data behind both is not.**
Emitting a file now would produce a money number whose every input is
provisional, and the format's readiness is not the study's readiness.
