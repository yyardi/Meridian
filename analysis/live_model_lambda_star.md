# lambda* on the live model — underpowered, stated before the number

Basis: `pulse_decisions_20260906T174104Z.csv.gz`, entered branch, joined to
`resolved_outcomes` (1.0000 agreement). **Earliest ex-ante row per
(market, side)** — (market, side) is the unit of decision, and the sort is
pinned on `(decided_at, id)`, a verified total order. n = 749, G = 34.
Statistic: lambda* from regressing `(y - mid)` on `(fv - mid)` without
intercept; cluster-robust sandwich, clusters are games.

## POWER FIRST

    cluster-robust SE(lambda*)  0.2124
    95% half-width              0.4321

A blend weight worth acting on is roughly **0.10-0.20**. The half-width is
**more than twice** that. **This test cannot resolve a lambda* of the size that
would matter**, and it is almost exactly as underpowered as the pregame run
(half-width 0.426). Stated before the number, per the standing rule.

## RESULT

    lambda*  +0.2834  [-0.1487, +0.7155]   contains zero
    pregame  -0.0224  [-0.4413, +0.4104]   contains zero

    out-of-sample, leave-one-game-out:
    MSE(mid) - MSE(blend) = -0.000164 [-0.002813, +0.002485]  indistinguishable

**Outcome 2 of the three: not distinguishable from zero.** But the honest
statement is stronger than "no effect" — the interval is consistent with
lambda* = 0, with 0.28, and with 0.7. **We cannot tell**, and the point estimate
sits inside the range that would matter.

## ★ ONE TRAP IN MY OWN OUTPUT

The leave-one-game-out lambda estimates are **very stable**: min +0.199, median
+0.283, max +0.352, **sd 0.038**. That looks like precision and is not.
**Consecutive LOGO folds share 33 of 34 games**, so their spread measures how
much one game moves the fit — not the uncertainty of lambda. The honest SE is
**0.212, five times larger.** Reading fold stability as precision would turn an
unresolvable estimate into a confident one.

## What would change it

Only games. The interval scales as 1/sqrt(G); resolving 0.15 needs a half-width
under ~0.075, which is roughly **34 x (0.432/0.075)^2 ~ 1,100 games**. That is
not an accrual plan, it is a statement that this question is not answerable on
in-play WNBA decisions.
