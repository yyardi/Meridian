# The wide book: it barely fills, and the loss is what geometry predicts

Measured 2026-09-15 on CFB, mark-to-mid, 30-second horizon, cap raised from
0.15 to 0.50. Two Saturdays, reported separately and never pooled.

## The identity first, because it decides what can be a finding

For a resting bid at half-spread `h` with mid move `d` over the horizon, the
module's own arithmetic gives

```
filled iff d <= -h   net_bid = (mid+d) - (mid-h) = d + h
filled iff d >= +h   net_ask = (mid+h) - (mid+d) = h - d
```

so on either side **net = h − |d|, conditioned on |d| ≥ h**. Two consequences,
both checked against `core/quote/adverse_selection.py` rather than asserted
(`tests/test_wide_spread.py`):

* **Net is ≤ 0 in every band by identity.** The fill rule and the P&L mark are
  the same variable. "Making loses in every bucket" is not a measurement of
  this instrument, it is a property of it.
* **`earned` is `h`**, the band's own definition — the x-axis plotted against
  itself. So the earned/adverse split is largely algebra and only NET can
  carry information.

## The tail is the parameter, and it points the opposite way to the fear

Under a geometry-only null — one pooled move distribution, so bands differ
only through `h` — net is exactly `−e(h)` where `e(h) = E[|d| − h | |d| ≥ h]`
is the mean excess. So the null's DIRECTION is set by the tail:

| tail | e(h) | null's gradient |
|---|---|---|
| thin (normal σ=.05) | falls 3.64 → 1.20c | net **improves** with width |
| heavy (5% × 8) | rises 5.25 → 25.70c | net **collapses** with width |
| heavy (t3-ish) | rises 9.69 → 15.84c | net collapses |

*(400,000 draws each, `n_distinct` checked — see the provenance note below.)*

**Measured on this tape, e(h) RISES on both Saturdays: 5.00 → 7.03c on 09-13
and 3.03 → 6.92c on 09-06.** The CFB 30-second mid-move distribution is
heavy-tailed at these scales. So geometry here predicts a net that WORSENS
with width, and that is what both days show.

## 2026-09-13 — 94,752 windows, 39 games, 5% sample

| band | windows | zero-d | fills | G | earned | adverse | net/FILL | net/GAME | t(game) | null | e(h) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.01–0.02 | 26,865 | 24,167 | 2,687 | 39 | +0.50 | +5.29 | −4.78 | −4.74 | −15.4 | −4.10 | +5.00 |
| 0.02–0.05 | 11,781 | 8,574 | 1,839 | 39 | +1.37 | +6.16 | −4.80 | −4.83 | −19.8 | −4.76 | +5.03 |
| 0.05–0.10 | 7,717 | 5,281 | 938 | 39 | +3.19 | +8.22 | −5.03 | −5.87 | −12.0 | −5.62 | +6.02 |
| 0.10–0.15 | 5,739 | 4,297 | 366 | 38 | +5.93 | +12.43 | −6.51 | −6.82 | −10.6 | −6.26 | +6.38 |
| 0.15–0.25 | 8,058 | 6,042 | 272 | 39 | +9.27 | +14.94 | −5.67 | −5.59 | −13.3 | −6.41 | +6.61 |
| 0.25–0.50 | 32,828 | 27,481 | 145 | 34 | +16.30 | +24.49 | −8.20 | −9.09 | −7.7 | −6.89 | +7.03 |

## 2026-09-06 — 7,486 windows, but only 3 games

| band | windows | fills | G | net/FILL | net/GAME | null | e(h) |
|---|---|---|---|---|---|---|---|
| 0.01–0.02 | 3,358 | 691 | 3 | −3.29 | −3.72 | −3.03 | +3.03 |
| 0.02–0.05 | 1,004 | 323 | 3 | −3.64 | −3.80 | −3.50 | +3.69 |
| 0.05–0.10 | 876 | 188 | 3 | −4.12 | −3.63 | −4.17 | +4.43 |
| 0.10–0.15 | 589 | 62 | 3 | −4.17 | −3.93 | −4.98 | +5.02 |
| 0.15–0.25 | 779 | 52 | 3 | −5.55 | −4.94 | −5.84 | +6.21 |
| 0.25–0.50 | 872 | 14 | 3 | −7.00 | −4.27 | −6.30 | +6.92 |

**G = 3.** The per-game column on this day is three numbers wearing a mean;
its t values are not usable and are printed only so nobody reconstructs them
later as if they were. The day is a check on the SIGN of the gradient, which
is all the Manager asked it for, and not a second estimate.

## What the two days say

1. **They agree on the sign.** e(h) rises and net worsens with width on both.
   No disagreement to report, which was the outcome that would have outranked
   a tighter interval.
2. **Observed net tracks the null within about a cent in almost every band.**
   09-13: observed −4.78/−4.80/−5.03/−6.51/−5.67/−8.20 against a null of
   −4.10/−4.76/−5.62/−6.26/−6.41/−6.89. The whole net-versus-width shape is
   reproduced by ONE pooled move distribution. **The mark-to-mid instrument
   carries almost no information beyond its own geometry** — the one exception
   is the widest band, worse than the null on both estimators (−8.20 and
   −9.09 against −6.89).
3. **The wide book barely fills.** Fill rate falls from 10.0% of windows
   (0.01–0.02) to **0.44%** (0.25–0.50) on 09-13, and 20.6% to 1.6% on 09-06.
   The 0.25–0.50 band is the second-most-QUOTED band — 32,828 windows — and
   the least filled. "Can you make money quoting wide" has an answer that is
   not about edge: almost nothing comes to you.
4. **85–90% of windows have a mid that did not move at all** in 30 seconds
   (24,167 of 26,865 in the narrowest band). That is the `is_live`
   contamination the module documents — 11,227 of 12,290 markets whose last
   row says live were last written over 600s ago — plus genuine stillness. It
   suppresses the FILL RATE and not the net, since a zero-move window never
   fills.

## For §0ag: the threat to the per-game column is refuted, not confirmed

The hypothesis was that §0ag's monotone-improving per-game net (−2.65 → −0.78)
might be exactly what a thin-tailed geometry null produces on its own. **It is
not.** The tail on this tape is heavy, and a heavy tail produces the opposite
gradient — net collapsing with width, which is what both Saturdays show here.
So that particular threat does not apply.

Two limits on how far that carries. §0ag marks to **settlement** and this marks
to **mid**, and those are different instruments on different populations, so
this measures the stated hypothesis rather than validating the column by
another route. And a heavy tail at the 30-second horizon need not be heavy at
a settlement horizon; the tail is a property of the horizon as much as the
market.

## Provenance note, because this number is now load-bearing

I earlier told the Manager that my first test asserted the null's direction
backwards, failed, and that "the failure was the finding". **That account was
wrong and the number is right.** The first test built its sample as
`[random.Random(1).gauss(...) for _ in range(2000)]`, which constructs a NEW
generator per iteration and yields 2,000 IDENTICAL values. It failed because
`0.10 > 0.01` on a degenerate sample, not because of any tail. The direction
finding came from a separate standalone check on a correctly drawn sample, and
has since been re-verified on 400,000 draws per distribution with
`n_distinct` asserted. The same bug was present twice in the file; the second
copy is what exposed it, because a single-valued sample makes `mean_excess`
return None and the TypeError was unmissable.
