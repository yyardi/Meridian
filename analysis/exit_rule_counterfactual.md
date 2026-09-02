# Do the exit rules earn their keep? — the counterfactual

**Descriptive, in-sample, hypothesis-generating.** From Quant A's round-trip
ledger (1,807 exited positions / 32 games). Optimistic arm throughout: maker
fills at recorded limits, $0 fees.

## The naive cut, which is nearly circular

```
exit reason        n     per-$    game-mean   pessimistic
profit_target   1,191  +11.76%     +11.93%      -10.35%
ev_stop           486   -1.34%      -0.91%      -25.94%
fv_adverse        130  -29.77%     -29.34%      -51.73%
rode_to_settle    137  -50.62%     -75.88%      -65.45%
```

**Read alone this says "the profit target is the whole business and the
adverse-move exit is broken." That read is close to circular:** a position exits
on `profit_target` *because* the price moved our way, and on `fv_adverse`
*because* it moved against. **The exit reason partly defines the sign of the
P&L.**

## The non-circular question

**Conditional on having entered, did the rule beat holding to settlement?**
Settlement needs no book — holding is always executable — so the counterfactual
is well defined: value at settlement is `settlement` for a YES position,
`1 − settlement` for a NO, minus entry cost.

```
exit reason      n     ACTUAL     HELD    unweighted game-mean of (actual - held)
ev_stop        486     -1.34%   -9.52%          +5.33%
fv_adverse     130    -29.77%  -44.46%         +30.68%
profit_target 1,191   +11.76%  +14.94%         -15.20%
```

**The signs invert.** On these point estimates the two "losing" rules are
cutting positions that would have lost more, and the profit target — which
looks like the whole business — is selling winners early.

## And it does not survive its own interval

Dollar-weighted, **game-clustered bootstrap, 10,000 resamples, seed 20260902**:

```
                G    (exit - hold)              verdict
profit_target  32    -3.18%  [-33.54, +22.46]   inconclusive
ev_stop        16    +8.18%  [-10.48, +27.71]   inconclusive
fv_adverse     13   +14.69%  [ -2.91, +33.82]   inconclusive
ALL TRIPS      32    -0.18%  [-25.04, +20.72]   inconclusive
```

**Every interval spans zero, widely. At 32 games the exit-policy question is not
answerable in either direction.**

Note the unweighted game-mean (−15.20% for `profit_target`) and the
dollar-weighted bootstrap point (−3.18%) disagree in magnitude by 5×. **The
unweighted figure gives a $2 game the same vote as a $200 one** — worth stating,
because the more dramatic number is the less defensible one.

## What this is worth

**It kills a plausible fix before anyone builds it.** The naive cut invites
"loosen the profit target, it's selling winners early" — and the counterfactual
point estimate agrees, and the interval says we cannot tell. **A change to the
exit policy on this evidence would be a coin flip dressed as a repair.**

**It also protects the adverse-move rule.** Someone reading only the naive table
would conclude `fv_adverse` is broken and remove it; the counterfactual points
the other way — it may be saving ~15–30¢/$ — though again, not established.

**What would answer it:** the same comparison at 3–4× the games, or a registered
forward arm varying only the profit target. Neither is available before the WNBA
resumes.

---

**No in-sample result justifies capital. The forward test is the evidence.**
