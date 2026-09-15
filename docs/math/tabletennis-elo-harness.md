# Table-tennis Elo harness — specifications and decision rule, written before any fit

2026-09-15. This **specifies** open points in
`tabletennis-rating-preregistration.md`; it does not change what was
registered. Written before a single coefficient exists, and before the sample
can even produce one (zero matches are eligible today).

## 1. Token handling: `mars` and `demciva` stay first-class

712 token-appearances in the settled set are 704 at six characters, four at
seven (`demciva`) and four at four (`mars`).

**Decision: they are first-class tokens. No normalisation to six characters,
no padding, no truncation, no exclusion.** A 4-character token is the case a
naive fixed-width implementation breaks on, so it is pinned by a test rather
than tidied away: `test_a_fixed_width_parser_would_lose_a_player` asserts that
slicing tokens at six characters loses `mars` and mangles `demciva`, which is
the reason the parser splits on `-` and counts instead.

Normalising would be the worse error of the two available. Padding `mars` to
six characters invents a token that the venue never emitted, and truncating
`demciva` to `demciv` risks colliding it with a real player.

## 2. Prior-match counting: WITHIN competition, by construction

The registered spec already says "≥10 prior settled matches in the same
competition" and "a name that appears in two competitions treated as two
entities until proven otherwise". Both are implemented as **one decision**:
player identity is the pair `(competition, token)`, not the token.

So a token in two competitions is two players automatically — there is no code
path in which the two definitions can disagree. What still needs surfacing is
that it **happened**, because the two definitions are indistinguishable on
today's data (0 of 180 tokens cross competitions) and will diverge silently the
first time one does. `cross_competition_tokens()` returns them and the runner
prints them loudly; a test pins the detection.

It is a NOTICE, not a crash. Crashing would stop a run that the registered
spec says how to handle.

## 3. Match ordering: the venue's start time, not the slug's date

The slug carries a date and nothing finer, and 94% of the settled set falls on
one day. Day-granularity ordering would therefore force a choice between
excluding same-day matches from the prior (conservative, and it costs a whole
day of accrual) and including them (which leaks: a match cannot inform its own
prediction).

Neither is necessary. `market_snapshots.game_start_time` gives each match a
start instant, so "strictly before" is exact at second resolution and same-day
matches order correctly. **The harness orders on `game_start_time` and refuses
a match that has none** — counted, not dropped silently.

This corrects an optimism in the accrual projection I published in
`tabletennis-player-identity.md` §3. That projection compared each token's
cumulative match count against the threshold, which is right only if
same-day matches count toward same-day predictions. With exact ordering they
do, so the published curve stands — but had the answer been day-granularity,
every figure would have shifted one day later (50% between +2 and +3 rather
than +1 and +2). The curve depends on the ordering rule, and the ordering rule
was not specified until now.

## 4. Estimator: the registered interval AND the one I think is right

The pre-registration says "game-clustered interval". A match is a **dyad** —
two players, two clusters — and players recur across matches, so a
match-clustered SE treats repeated players as independent and is optimistic.
Per `dyadic-power-saturates`, n_eff → P/(2ρ).

**Both are computed and both are reported, with the estimator named on every
number.** The registered game-clustered interval is the one the
pre-registration's verdict is read from; the two-way player-clustered interval
is reported beside it. If they disagree materially, that disagreement is the
finding and the registered one is not quietly replaced.

`G_eff` is reported for both.

**CORRECTED before it was used, by running it on the positive control.** I
first wrote here that "a large Elo coefficient with a small design effect is a
defect signature". On the positive control the coefficient is **+1.09** and
deff is **1.17** — and there the effect is real by construction, so the
heuristic flags its own control. What deff tracks is the **imbalance of
appearances**: with balanced pairing the player clusters do not concentrate
the residuals and deff sits near 1 whether or not the effect is real. The
settled set is fairly balanced too (180 tokens, 712 appearances, max 9), so it
would likely have flagged a genuine result.

So deff is **reported next to the appearance distribution and is not a verdict
input**. The defect signature is narrower than I wrote: a large coefficient
with deff ~1 *on an UNBALANCED panel*, where a few players carry most
appearances and their clusters therefore should concentrate the residuals.
`test_a_small_design_effect_is_not_by_itself_a_defect_signature` pins the
correction.

## 5. The decision rule, pre-committed

Per competition, never pooled. All four thresholds are from the registered
spec except where noted.

| condition | value | source |
|---|---|---|
| predicted matches | ≥ 200 | registered |
| distinct players | ≥ 25 | registered |
| both players' prior matches | ≥ 10, same competition | registered |
| Elo coefficient interval | must exclude 0 | registered |
| interval used for the verdict | game-clustered | registered |

**PASS** — ≥200 predicted matches, ≥25 distinct players, and the Elo
coefficient's game-clustered 95% interval excludes zero.
**FAIL** — the floors are met and the interval includes zero.
**NOT YET** — a floor is unmet. Report the counts and stop; this is not a fail.

Only on PASS does the secondary run (P&L of taking the rating's side when it
disagrees with the price by more than the half-spread plus fee, per
competition).

## 6. The achievable image of that rule, checked before it runs

Per `check-a-decision-rule-against-its-achievable-image`: project what this
design can produce onto the rule's branches.

| competition | settled (3d) | distinct players | can it ever reach the floors? |
|---|---|---|---|
| setkameua | 256 | 113 | yes — players already clear 25 |
| setkamecz | 48 | 32 | yes |
| setkamemd | 39 | 29 | yes |
| **setkawoua** | 14 | **6** | **NO — 6 players against a ≥25 floor** |

**One of the four competitions can never return PASS or FAIL.** With ~5
matches a day among 6 players, setkawoua cannot reach 25 distinct players
unless its pool grows, so its only reachable branch is NOT YET, permanently.
That is stated now rather than discovered as a mysterious silence later, and
it is a reason to report it separately rather than let it sit in a table of
four looking like a pending result.

For the other three the rule has both branches reachable: an Elo coefficient
is a continuous quantity whose interval can fall either side of zero at the
sample sizes these competitions reach, so neither PASS nor FAIL is
predetermined.

**Today every competition returns NOT YET**, because zero matches are
eligible — the busiest player has 9 priors against a floor of 10. A harness
that cannot run today is a harness debugged on the day it matters, so the
replay is required to produce zero eligible matches and exit cleanly, and
there is a test for exactly that.
