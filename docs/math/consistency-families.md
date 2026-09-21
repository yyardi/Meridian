# Consistency families: what else on this board must hold by arithmetic

**Status 2026-09-18.** Derivation, scanner, and a real measurement of (a) and
(d) **PREGAME ONLY**, taken from an archived quote dump that is committed in
this repository. **Nothing here is measured in play**, which is the phase where
the spread ladder's money is, and no figure here is in dollars at quoted size
because the archive carries no book quantity. A local recorder database exists
on this machine and is listening, but this session's permission system refused
the connection and I did not work around it; every in-play number remains open.

So each figure below is exactly one of four things, and the reader should not
have to guess which:

1. **measured by me** on `docs/math/ladder_calibration_2026-09-11.out` — 4,456
   markets, 60 CFB + 2 NFL games, pregame close, per contract, no size;
2. **measured by me** on the slug grid of this working tree (the line-grid
   section below);
3. **quoted from a prior STATUS section**, attributed, with its obs count;
4. **named as open**, with the command that would take it.

Scanner: [`core/ladder/families.py`](../../core/ladder/families.py) ·
database runner: [`cfb/run_family_scan.py`](../../cfb/run_family_scan.py)
(**unrun**) · archive runner:
[`cfb/run_family_scan_archive.py`](../../cfb/run_family_scan_archive.py) (this
is where every measured number below comes from, and it re-derives them from a
committed file on any checkout) · tests: `tests/test_ladder_families.py` (27,
green) and `tests/test_family_settlement_frames.py` (3, **needs Postgres, not
run**).

## The headline

| candidate | exact? | coverage | measured pregame | verdict |
|---|---|---|---|---|
| (a) totals ladder | EXACT | 13,169 CFB pairs | **99.38% ordered, 1 violation, max edge +0.07c** | clean pregame; **in play unmeasured and that is the question** |
| (b) winner vs 0-line spread | EXACT | **zero — no 0.0 rung exists** | — | **RETIRED, vacuous** |
| (c) half vs full game | EXACT | containment ~zero; Fréchet form ok | not in the archive | open |
| (d) team totals vs game total | EXACT (both bounds) | 18,288 upper / 17,935 lower splits | **0 violations, and the board never comes within 23c** | **RETIRED as an edge: the bound is too slack to bind** |
| (e) quarter/half additivity | T1–T3 exact on `H1=Q1+Q2`; price additivity NOT implied | not in the archive | open |
| *control:* spread ladder | EXACT | 47,392 CFB pairs | 96.81% ordered, 7 violations, max edge +0.71c | the control can fail, and does |

The single most useful line in that table is the control. Totals and spreads
were scanned on **the same 60 games, the same instrument, the same fee and the
same pregame close**, and the spread board came back measurably dirtier. So (a)'s
near-zero is a property of the totals board, not an instrument that cannot
detect disorder.

## The board's line grid — measured, and it decides two candidates

Every rung slug anywhere in this tree ends in a half point. Sweeping the working
tree for slug-anchored rung tokens gives **94 distinct line magnitudes across
4,617 slug occurrences, and the decimal is `5` on every one of them** — no
integer line has ever been recorded, on any family, league or venue here
(`test_every_line_this_repo_has_ever_recorded_is_a_half_point`, which is
anchored on the slug's date so a Python identifier ending `pt2` cannot enter the
census). Two relations die of it:

* there is **no 0.0 spread rung**, so the winner identity (b) has nothing to
  compare against;
* two half-point part lines sum to an **integer** while every whole line is a
  half point, so `sum(parts) == N` is unreachable and no Fréchet split is ever
  exact.

**This is a fact about the venue's grid, not about the relations.** Both are
still exactly true. If the venue ever lists an integer line the tests above fail
on purpose, and both candidates come back.

### Coverage is now printed before any violation count

`families.coverage` returns, per relation, how many baskets the listed lines can
form **before any price is read**, and the runner prints it above the scan. This
exists because *"0 violations"* over 0 formable baskets and *"0 violations"* over
96,620 of them print identically, and only one of them is a clean board. On the
venue's real grid it prints:

| relation | formable per fully-listed sweep |
|---|---:|
| `totals_ladder` | 6 (at 4 listed lines) |
| `frechet_upper` | 11 |
| `frechet_lower` | 5 |
| `segment_in_whole` | **0** |
| `winner_is_line_zero` | **0** |

The figure is an **upper bound** on the denominator, not the denominator: it
pools lines across sweeps and assumes every one of them is listed in the sweep
being scanned. The true per-sweep denominator needs the per-sweep line set and
is not computed. It is printed as a coverage figure and must not be divided
into.

## The one theorem

The spread ladder is not a special fact about spreads. It is the k = 1 case of a
statement about any quantity the venue decomposes into non-negative parts. Let
`X = U + V + W` with `U, V, W >= 0`, where `W` is a part the venue may not
quote (overtime, an unlisted segment). Write `P(Y > y)` for the YES price of the
market "Y clears y".

| # | statement | condition | proof |
|---|---|---|---|
| T1 | `P(U > n) <= P(X > n)` | none | `U > n` and `V, W >= 0` give `X >= U > n`. So `{U>n}` is a subset of `{X>n}`. |
| T2 | `P(X > N) >= P(U > u) + P(V > v) - 1` | `u + v >= N` | `U>u` and `V>v` give `X >= U+V > u+v >= N`. So `{U>u} ∩ {V>v}` is a subset of `{X>N}`, and `P(A∩B) >= P(A)+P(B)-1`. |
| T3 | `P(X > N) <= P(U > u) + P(V > v)` | `u + v <= N` **and `W ≡ 0`** | `U<=u` and `V<=v` give `X = U+V <= u+v <= N`. So `{X>N}` is a subset of `{U>u} ∪ {V>v}`, and `P(A∪B) <= P(A)+P(B)`. |

T2 and T3 are the Fréchet–Hoeffding bounds. **They assume nothing about
dependence** — not independence, not a copula, not a model of the sport. That
is what makes them the same kind of object as the spread ladder rather than a
fair-value disagreement.

**The asymmetry is the whole practical content of this file.** T2 survives an
unquoted non-negative residual; T3 does not. T3's argument needs `X = U + V`
exactly, and if overtime points exist outside both quoted parts then `U <= u`
and `V <= v` no longer cap `X`. This is pinned by test
(`test_an_unquoted_residual_breaks_the_UPPER_bound_and_spares_the_LOWER`) on an
enumerated distribution, not asserted in prose, and it is why the runner's
`--allow-upper-frechet` is **off by default**.

### What each is worth as a trade

T1 is a two-leg pair, identical in shape and cost to the spread ladder: sell the
subset at its bid, buy the superset at its ask, pay two fees, and the position
pays `1[superset] - 1[subset] >= 0` in every state.

T2 and T3 are **three-leg baskets**: three fees, three fills, and a size equal
to the *smallest of three* quotes. On a venue where median in-play touch depth
is 50 contracts (CFB) and the spread pair's binding leg is already usually the
smaller one, the third leg is a material haircut before any price disorder is
considered. A half-filled three-leg basket is a directional position, and the
recovery rule for it is not the two-leg one in
[ladder-fill-test.md](ladder-fill-test.md). **No three-leg protocol exists.**

Fees: `f(p) = 0.06·p·(1-p)` per leg at the price paid
(`core.ladder.scan.fee`), charged on every leg including those the screen
expresses as "buy NO at 1 − bid" — `f` is symmetric under `p -> 1-p`, so the NO
leg's fee is `f(bid)` exactly, not approximately.

## The five candidates

### (a) Totals ladder monotonicity — EXACT, and the one real opening

`P(Over N)` is non-increasing in `N`: T1 with `U = X` and two lines, or directly
`{T > N'}` is a subset of `{T > N}` for `N' > N`. Exact, no residual question.

**Orientation is inverted relative to spreads and this is a live hazard.** A
*larger* spread line is *easier* to cover (dearer); a *larger* total line is
*harder* to clear (cheaper). `scan.scan_ladder` hard-codes the spread ordering.
Feeding it a correctly-ordered Over ladder makes it report violations — pinned
as a positive assertion in `test_the_spread_scanner_on_a_CORRECT_totals_ladder_manufactures_a_violation`,
so the day someone reuses the wrong function the suite says so.

**Measured by me, pregame close, per contract** (estimator: pair-weighted
pooled rate over all same-game rung pairs; edge is `bid_subset − ask_superset`
net of `f` on both legs; `run_family_scan_archive.py`):

| league | games | pairs | ordered | fee-netted violations | max edge | median edge |
|---|---:|---:|---:|---:|---:|---:|
| CFB | 60 | 13,169 | 99.38% | 1 (0.008%) | **+0.07c** | −34.26c |
| NFL | **2** | 463 | 99.78% | 0 | −2.52c | −37.55c |
| *control:* CFB spread | 60 | 47,392 | 96.81% | 7 (0.015%) | +0.71c | −15.87c |
| *control:* NFL spread | **2** | 1,260 | 98.65% | 7 (0.556%) | +3.18c | −35.57c |

Read the CFB row as: **the totals board is essentially exact pregame.** The
single violation is worth 0.07c per contract, which is below one tick and would
not survive rounding, let alone a fill. The median pair sits 34c *away* from
violation. The NFL rows are **two games** and should be read as nothing at all.

**The leg-gap stratification is the honest control, and it does not move the
answer.** Each archived quote is its own market's last pregame quote, so two
legs can be hours apart (within-game gap: median 156 min, max 3,814). Restricting
to pairs whose legs share a `ttk_min` — the closest thing to simultaneity this
file offers — gives CFB 11,588 pairs at 99.30% ordered with the same single
violation. Staleness is therefore not what is producing the cleanliness.

**Measured pregame, quoted from STATUS 0bk/0bl** (their obs counts, not mine,
and a different population — all pregame sweeps over 3 days, not the close):

| venue | family | pairs | ordering | violations | value |
|---|---|---:|---:|---:|---:|
| Polymarket | CFB game totals (1q/2q/3q/4q/1h/2h), 3 days | 96,620 | 94.0% | 13 | $1.01 |
| Kalshi | totals, all | 2,244,340 | 97.4% | 24 | $0.00 |

My 99.38% and 0bk's 94.0% are **not the same measurement and neither corrects
the other**: mine is one quote per market at the close over 60 games, theirs is
every pregame sweep over 3 days across more segment families. The same gap shows
in the control — I measure CFB spreads at 96.81% pregame where STATUS reports
85.4% — so the direction is consistent across both families and is a property of
the population, not of the totals board. Anyone wanting a like-for-like number
must run `run_family_scan.py --phase pregame` on the database.

**In play, this is unmeasured.** STATUS 0bo established that every one of the
8.1M pairs in 0bl carried `game_start_time > captured_at` — the whole scan was
pregame. STATUS 0bp then ran in-play across **fourteen football families, all of
them spreads**. So the strongest claim the record supports is: *totals ladders
are clean pregame*, and the phase where spreads collapse from 85.4% to 67–78%
has never been run on totals at all. Given that the stated mechanism — the
winner market re-prices every possession while deep rungs sit — has no obvious
totals analogue (there is no "winner" rung inside a totals ladder), **my prior
is that totals stay clean in play, and that is exactly why the measurement is
worth taking: it is the control that can fail.**

Command: `python cfb/run_family_scan.py --league cfb --phase inplay --census`
then without `--census`. Unrun.

### (b) Winner versus the 0-line spread — EXACT, and VACUOUS on this venue. RETIRED.

The winner market is `P(margin > 0)`; the spread at line 0 is
`P(margin + 0 > 0)`. Same event, same YES side: `cfb/run_ladder_calibration.py` settles the
winner as `away > home` and the spread as `(away - home) + line > 0`, the
latter verified 196/196 on the tape. So the two prices must agree in **both** directions,
and a scan in one direction sees half the board. The scanner issues both
implications (`test_the_winner_identity_is_scanned_in_both_directions`).

**There is no second price. The venue lists no 0.0 spread rung.** Every recorded
line is a half point (see the grid section above), which is exactly what a
sportsbook does to make a push impossible. So the moneyline is not one of two
prices on the same event that could disagree — it is the *only* price on that
event.

This also explains, rather than contradicts, STATUS 0bi's "57 ladders including
the winner rung as line 0.0": the spread scanner **inserts** the winner market
*as* the synthetic 0.0 rung (`run_ladder_scan.py`, `key = 0.0 if mt == win else
line_of(slug)`). That is a construction, not a listed rung, and it is why the
winner already sits inside every published spread figure. Reading it as evidence
that a 0.0 rung exists is the mistake this section originally made.

`families.coverage` returns 0 for this relation on the venue's grid and 2 the
moment a 0.0 rung is added, so the claim is a test rather than a caveat
(`test_the_winner_identity_has_no_denominator_on_a_half_point_grid`).

**Consequence for the open NFL-tie question: it is moot for this relation.** A
tie settles the winner NO while a 0-line spread would push, so the two would be
different objects in NFL regulation — but with no 0-line rung listed there is no
pair to mis-settle. The tie question still matters for how the *winner* market
itself pays; it no longer gates anything here.

### (c) Half versus full game — EXACT, but the useful form is not the obvious one

The obvious statement `P(1H Over n) <= P(FG Over n)` is T1 and is exactly true
(second-half points are non-negative; overtime only helps). **It is also almost
never binding.** Half-total lines sit near half the full-game line, so the
condition "the whole's line is at or below the segment's line" is met by
essentially no listed pair: at lines 20.5/24.5/27.5 against 44.5/48.5/52.5 the
generator returns the empty list, which is pinned as a test
(`test_containment_has_almost_no_coverage_at_the_venues_real_lines`) precisely
so this claim is falsifiable rather than a caveat in prose.

The form with power is T2/T3 on `FG = 1H + 2H`:

* **lower (T2):** `n1 + n2 >= N` ⟹ `P(FG > N) >= P(1H > n1) + P(2H > n2) - 1`. Safe.
* **upper (T3):** `n1 + n2 <= N` ⟹ `P(FG > N) <= P(1H > n1) + P(2H > n2)` — **only
  if the venue's second-half total includes overtime.** If it does not, overtime
  is an unquoted `W >= 0` and T3 is false. I could not verify the venue's
  settlement rule for `football_game_second_half_total`, so the runner refuses
  the upper bound unless explicitly asked.

Baseball has the same shape with `baseball_team_first_five_total` inside
`baseball_team_full_game_total` — and there the residual (innings 6–9 plus extras)
is definitively non-zero and unquoted, so **only T2 applies to first-five, never
T3.**

### (d) Team totals versus the game total — a BOUND, never an equality. MEASURED, and RETIRED as an edge.

`T = A + B` where `A`, `B` are the two teams' points, both non-negative and both
quoted (`football_team_points_full_game_total`, one market per team, `tt-<team>`
in the slug). Because the parts exhaust the whole, **both** T2 and T3 apply:

    max(0, P(A>a) + P(B>b) - 1)  <=  P(T > a+b)  <=  min(1, P(A>a) + P(B>b))

**What is NOT implied.** `P(T > N)` is not `P(A>a) + P(B>b)` minus an
independence correction, and it is not any function of the two team ladders.
Two boards with identical team-total prices can carry any `P(T>N)` inside the
band above, because the dependence between `A` and `B` is unconstrained by their
margins — and in football it is strongly negative (clock, possessions) in some
regimes and positive (pace, weather) in others. **Anyone pricing the game total
off the team totals is pricing a copula they have not measured.** The bounds are
the only model-free content.

**Coverage is genuinely good here, unlike (c)** — and that is exactly what makes
the measurement damning rather than uninformative. Team lines near 12.5–42.5 and
a game ladder near 29.5–65.5 make both `a+b <= N` and `a+b >= N` reachable from
the same listed rungs, so the band really does bracket quoted prices.

**Measured, pregame close** (`run_family_scan_archive.py`; three-leg baskets, per
contract, no size in the archive):

| bound | games | splits | violations | **non-vacuous** | closest the board came |
|---|---:|---:|---:|---:|---:|
| upper (T3) CFB | 56 | 13,942 | 0 | 29.6% | −22.88c |
| upper (T3) NFL | **2** | 4,346 | 0 | 20.6% | −27.15c |
| lower (T2) CFB | 56 | 14,273 | 0 | 21.1% | −26.73c |
| lower (T2) NFL | **2** | 3,662 | 0 | 27.7% | −23.58c |

**The zero is not the finding. The slack is.** Two things kill this candidate,
and neither is "the market is efficient":

1. **Roughly three quarters of the splits are VACUOUS.** On 70–79% of them the
   bound is already implied by `0 <= P <= 1` alone — the two parts cost more
   than a dollar, or the two bids sum to under one — so the basket observes
   nothing about the prices at all. A violation count whose denominator is
   mostly vacuous splits is not a measurement of the board, and this is the
   deeper form of the coverage problem that kills (b) and (c): there, no basket
   could be *formed*; here they form and say nothing.
2. **Even where it binds, the board is never close.** The best basket in 36,223
   splits was **23 cents underwater**, against a three-leg fee of about 4.5c at
   even money. A dependence-free bound admits *every* copula, so it is enormously
   wide, and a real board sits deep inside it by construction.

So (d) is exactly true, well covered, cleanly measured — **and worth nothing.**
It would take a ~23c mispricing on one of three legs to pay, which is an order
of magnitude beyond anything the spread ladder ever showed. The right conclusion
is not "scan it in play too" but "a model-free bound this wide cannot be an edge
in any phase", and I would need a specific reason — not a hope — to spend the
in-play query on it. Pinned in
`test_the_frechet_bounds_are_mostly_VACUOUS_on_the_real_board`.

**Availability is SETTLED for CFB pregame, and it was settled by looking rather
than by the venue probe.** `football_team_points_full_game_total` was seen on
the NFL board at the 2026-09-02 probe (`analysis/archive/nfl_day_one_survey.py`),
which is one observation of existence. The archive is stronger: **593 team-total
rungs across 56 CFB and 2 NFL games, with BOTH teams listed in every game the
scan used** (the runner requires exactly two team keys before it forms a split,
and it formed splits on 58 games). Rung density is ~5 per team, half-points, e.g.
`tsc-cfb-akron-wake-2026-09-03-tt-akron-{6,9,12,15,18}pt5` against
`tt-wake-{30,33,36,39,42}pt5`.

*I first wrote here that no `-tt-` slug had ever been recorded in this tree.
That was wrong — my grep was restricted to `*.py` and the slugs live in a `.out`
file. The correction is why (d) could be measured at all, and it is the reason
the availability row has moved out of the open-questions table below.*

The **parse** is now evidenced too, not merely consistent: `team_of` reads
`toks[toks.index("tt") + 1]` and the two teams it recovers are the same two the
slug names in positions 2 and 3, which is what `run_ladder_calibration.settle`
compares against. A swapped attribution would still be invisible to a settlement
check — `A + B` is symmetric — so this rests on the slug, and the `--census`
mean-mid-by-line print remains the guard before any *in-play* (d) number.

**Note on the upper bound here.** The runner passes `allow_upper=True` for team
totals unconditionally, and that is correct rather than an oversight: `A + B = T`
leaves no residual — overtime points enter both the team totals and the game
total — so T3 applies. The `--allow-upper-frechet` flag gates only the
*segment* splits in (c)/(e), where overtime may sit outside the quoted parts.

### (e) Quarter/half additivity — mostly NOT implied

`H1 = Q1 + Q2` exactly, with no residual, so T1/T2/T3 all apply cleanly and the
scanner runs them. That part is real.

**What is not implied, and would be a false positive if scanned:**

* **Quarter *spreads* inside a half spread, or half spreads inside the full-game
  spread.** Margins are not non-negative — a team can lead at half and lose — so
  nothing is contained in anything and no Fréchet bound exists. STATUS 0bl's
  90.4% ordering figure for CFB half/quarter *spread ladders* is the
  monotonicity **within** each such ladder, which is (a)'s relation applied to a
  different market, not a cross-segment claim. Registered in
  `families.RELATIONS` as EXPECTED-not-exact and not scanned.
* **Price additivity.** `E[H1] = E[Q1] + E[Q2]` is exact for the *means*, but a
  binary option is not a mean. Recovering `E[X]` from an Over ladder needs
  `E[X] = Σ_k P(X > k)` over every integer `k`, and the venue quotes a handful of
  half-point rungs, which yields a bound so wide it cannot bind. Not scanned.

## How the numbers must be reported, and how they have not been

Three things about the published figures that a reader should not inherit:

1. **"Within-ladder ordering" is a pair-weighted pooled rate and carries no
   interval.** The 94.0% and 97.4% above pool pairs across games, and pairs are
   not independent: one ladder of `k` rungs contributes `k(k-1)/2` pairs that
   share legs, so a single stale rung moves many "observations" at once. A
   binomial interval on those `n` is wrong by a large factor. The two defensible
   estimators are the **pair-weighted pooled rate** (what is published) and the
   **equal-weight mean of per-game rates**; they diverge whenever ladder depth
   varies across games.

   **I computed both on the archive, and here they do not diverge** — which is a
   checked negative, not an assumption:

   | | pooled (pair-wt) | equal-wt (per-game mean) | diff | worst game |
   |---|---:|---:|---:|---:|
   | CFB totals, 60 games | 99.38% | 99.37% | −0.00pp | 93.33% |
   | CFB spread, 60 games | 96.81% | 96.84% | +0.02pp | **73.64%** |

   The reason is that pregame ladder depth is nearly uniform here (totals: median
   210 pairs per game, max 253), so the weights are almost equal and the two
   estimators cannot separate. **That is a property of this population and must
   not be carried in play**, where rung counts vary far more; the divergence that
   bit CFB 1.3c came from exactly that unbalance. Note also the spread board's
   worst single game at 73.64% against the totals board's 93.33% — the pooled
   rate hides a heterogeneity that is real and is where a per-game estimator
   would start to matter. **No clustered interval has been computed for any
   family.**

2. **Dollar figures are `best single basket per game, summed` — and the "per
   game" must now be taken across ALL relations jointly, not per relation and
   added.** One mispriced game-total rung contradicts its own ladder *and* every
   Fréchet split it appears in; those baskets share a leg and compete for the
   same depth. Summing per-relation subtotals is STATUS 0bi's 2.5× double-count
   one level up. The runner prints both and labels the joint figure as the
   defensible one; `test_best_per_game_must_be_taken_JOINTLY_across_relations`
   pins the arithmetic.

3. **Size is quoted, never filled**, and the depth cap
   (`MAX_PLAUSIBLE_SIZE = 10,000`) applies unchanged — it is the reason NFL's
   in-play spread headline fell from $24,040 to $5,454 when one reading of
   978,801 contracts was capped (STATUS 0bp).

## The three retraction-shaped risks, and what this build does about each

The spread programme's retractions (STATUS 0bp–0bs) were: summing pairs that
share a leg, trusting depth, and treating a sweep timestamp as simultaneous.

| risk | here | mitigation |
|---|---|---|
| shared legs | **worse** — a rung now appears in its own ladder and in every basket | joint `best_per_game` across relations, tested |
| depth | **worse** — three-leg size is the min of three quotes | same cap; three-leg size reported separately from two-leg |
| simultaneity | **worse than the spread ladder, not merely as bad** | see below |

**Simultaneity is the risk I cannot mitigate in code and it is the reason I
would not trade any figure this scanner produces.** Legs are keyed on
`(game_id, captured_at)`, which is one recorder *sweep*, not one instant: the
cycle is stamped at its start and measured fetch spread inside a stamp is median
5s, p90 14s, max 110s (STATUS 0bs). Within one spread ladder the rungs are at
least adjacent inside the sweep, and STATUS 0bu still had to refute the skew
explanation with a genuinely simultaneous venue fetch before the in-play result
could stand. **Across families nothing orders the fetches at all** — a totals
rung and a team-total rung may sit at opposite ends of a 110-second stamp with a
touchdown between them. A cross-family in-play "violation" from recorded data is
therefore a *candidate*, and the only thing that can promote it is the 0bu
route: a live simultaneous read of all legs.

**The archived measurement is worse again on this axis, and it is the reason its
numbers are reported with a leg-gap stratification rather than as a headline.**
Each archived row is its own market's *last pregame quote*, so the within-game
leg gap is median **156 minutes**, max 3,814 — three orders of magnitude worse
than a sweep. What makes the (a) and (d) results survivable is not that the gap
is small but that **the answer does not move when it is closed**: restricting to
legs sharing a `ttk_min` changes CFB totals ordering from 99.38% to 99.30% and
leaves the violation count at one. A result that had *appeared* only in the
wide-gap stratum would have been staleness; this one does not.

## A settlement check on DERIVED settlements cannot test the YES frame

The archive carries a settlement column, and running the relations against it
returns **0 totals-ladder inversions in 13,632 pairs and 0 Fréchet violations in
36,223 splits**. *That result is worth nothing as a frame check and must not be
quoted as one.*

The column is `y` from `run_ladder_calibration.py`, which **derives** settlement
from ESPN finals under the venue's frames: `(home + away) − line > 0` for a
total. So if YES were really UNDER, `settle` would compute OVER for *both* rungs
of every pair and the monotonicity would still come back perfect. The instrument
imposes the very convention the check is supposed to test, and the tell is that
the answer arrived exactly clean. The Fréchet version is worse still: `T = A + B`
holds identically in ESPN's own numbers, so those 36,223 splits are checking
arithmetic against itself.

Only the **venue's** settlements (`resolved_outcomes.settlement`) can test the
frame, which is what `tests/test_family_settlement_frames.py` uses and why it
needs Postgres. The strongest thing in the repo remains a docstring at
`core/api.py:179` claiming YES-is-OVER was "verified against 490 settled
markets" — attributed, not re-derived by me, and I could not find the script
that produced it.

## What I could not check, and what it would take

| claim | why it is open | what settles it |
|---|---|---|
| YES on a totals market is OVER | three places in this repo say so (`run_ladder_calibration.settle`, `core/api.py`'s OVER/UNDER label, `live_totals_fv.over_probability`) and all three are one reading of one convention. `core/api.py:179` adds "verified against 490 settled markets" — attributed, **not re-derived by me, and I could not find the producing script**. The archive cannot test it (see the section above) | `tests/test_family_settlement_frames.py::test_a_higher_totals_line_never_paid_while_a_lower_one_did_not` against **venue** settlements. Needs `DATABASE_URL`. |
| **(a) totals ladder IN PLAY — the one question worth the query** | the archive is pregame-only; the phase where spreads fall to 67–78% has never been run on totals for any league | `python cfb/run_family_scan.py --league cfb --phase inplay --census`, then without `--census` |
| (c) and (e) at all | the archive holds only winner/spread/total/team_tot — **no half or quarter totals** — so neither the containment nor the `FG = 1H + 2H` split could be measured here, pregame or in play | the same runner; `SEGMENTS` already names the families |
| the venue's 2H total includes overtime | not stated anywhere in the repo; decides whether T3 is exact for `FG = 1H + 2H` | one settled overtime game, by hand, or the venue's rules page |
| in-play dollars at quoted size, for any family | the archive carries **no book quantity**, so every figure above is per contract and no dollar total is computable from it | the database runner, which reads `book_levels` |
| whether any of it fills | unchanged from the spread work: quoted size is not filled size, and three legs is a harder protocol than two | a three-leg version of [ladder-fill-test.md](ladder-fill-test.md), which does not exist |

**Closed by this pass, and how:** a 0.0 spread rung does not exist (grid sweep,
94 magnitudes, all half-points) — (b) retired. Both team totals are listed and
recorded, on 58 games with ~5 rungs each — (d) measurable, and measured, and
retired on slack rather than on availability.
