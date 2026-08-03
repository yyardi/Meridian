# Why sample size is games, not rows

A rule that shows up in every microstructure result here, and the reason all
three of them report "NO DATA" rather than a number.

## The problem

One WNBA game emits ~130 ladder rows *per sample*. At the 1s recorder that is
~130 rows a second, all of them responding to the same score, the same run, the
same crowd noise. They are not 130 observations. They are closer to one
observation, copied 130 times, with a little quote noise sprinkled on top.

Treat them as independent and the standard error shrinks by roughly
$\sqrt{\text{rows per game}}$ — a factor of 11 at 130 rows, and far more once
you multiply by the number of samples in a two-hour game. That is more than
enough to turn autocorrelation into a publishable result.

This is not hypothetical. In the first adverse-selection sample, the row-level
95% interval was [−7.46¢, −3.68¢] on 44 rows from **one game**. Read naively
that is a decisive finding. It is one game.

## The fix

Cluster by game. For a mean $\bar{x}$ over clusters $g$:

$$
\widehat{\operatorname{Var}}(\bar{x}) = \frac{G}{G-1} \cdot \frac{1}{n^2}\sum_{g}\left(\sum_{i \in g}(x_i - \bar{x})\right)^2
$$

with $df = G-1$, so few clusters produce an honestly wide interval rather than
a confident wrong one. Implemented once in
[`core/quote/adverse_selection.py`](../../core/quote/adverse_selection.py) as
`clustered_mean`, and imported by the other two experiments so there is one
copy to be right.

Note what the sandwich does: it sums residuals *within* a cluster before
squaring. If a game's rows all move together, that inner sum is large and the
variance estimate grows. If they were genuinely independent, the inner sums
would partly cancel and it collapses to the ordinary standard error.

## Why the reports print both

Every report shows the clustered interval **and** the row-level one, labelled
`(WRONG)`, plus the ratio between them. Not for balance — so the size of the
lie is visible. A reader who sees "clustering widens the SE by 11×" understands
immediately why the gate is stated in games.

## Why every gate names a game count

| Experiment | Gate |
|---|---|
| [adverse-selection.md](adverse-selection.md) | n ≥ 500 windows across **≥ 10 games** |
| [run-overreaction.md](run-overreaction.md) | n ≥ 30 runs across **≥ 10 games** |
| [depth-signal.md](depth-signal.md) | n ≥ 100 appearances across **≥ 10 games** |

The row condition is easy and the game condition is the one that binds. That is
the point: at 1s sampling, row counts become meaningless almost immediately —
a single game can produce half a million rows — while the number of independent
events stays stubbornly equal to the number of games played.

Making the row count easy to satisfy and the game count hard is what stops a
faster recorder from manufacturing false confidence. **A faster camera does not
give you more games.**
