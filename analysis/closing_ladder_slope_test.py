"""Three closing ladders, properly gated: the sigma SLOPE, tested by difference.

d5's achievable-image check killed my earlier claim. Scoring each game against
`sigma(line)` with a +/-10% band tests the LEVEL and cannot test the SLOPE: the
slope's whole contribution across a 7.7-21.4 line range is 1.62 points, which
fits inside +/-10% of 15 at both ends. Every slope from 0.0 to 0.1182 passed.

**The discriminating statistic is the DIFFERENCE in sigma across the line gap**,
against the difference the surface predicts. ce's framing, and the +/-10% band
never enters.

## COHORT — every selector fixed, none inherited

* gate: `period == 1 AND home_score == 0 AND away_score == 0`, no clock, no
  fallback (d5's `true_kickoff`). All three caught within 20s of first row.
* window: last 15 minutes before that game's own kickoff -> CLOSING ladders, not
  the 95-102-minute-out ones ce flagged as a different object.
* snapshot: **LAST QUOTE PER MARKET, never `captured_at == max`.** The recorder
  writes a 40-rung sweep then 4-rung updates, so equality-on-timestamp returned
  FOUR rungs all within 0.425-0.610 -- pinned at the money, where sigma is
  exactly unidentified. That would have read as "the closing board thins to
  near-the-money", a plausible structural finding that is entirely my own bug.

## RESULT

    venue   line   sigma            n    R2       max|res|   d5 predicts
    16453    8.1   15.98 +/- 0.43   34   0.9778    8.11pp    14.15  (+12.9%)
    16486   23.9   15.98 +/- 0.21   25   0.9959    2.78pp    16.01  ( -0.2%)
    16488   22.5   15.61 +/- 0.39   23   0.9871    4.41pp    15.85  ( -1.5%)

    line gap 15.7 pts      OBSERVED d_sigma  +0.01 +/- 0.48   95% CI [-0.93,+0.94]

      d5 shipped  0.1182  predicts +1.86   z -3.89   EXCLUDED
      mine n=5    0.0623  predicts +0.98   z -2.04   EXCLUDED
      FLAT        0.0     predicts +0.00   z +0.01   not excluded

    implied slope +0.0003 +/- 0.0303

## ★ WHY THE INTERVALS ABOVE ARE TOO NARROW, STATED BEFORE ANYONE ASKS

These are OLS standard errors over rungs, and **rungs are not independent** --
~40 views of two parameters, with residuals correlated along the line. My own
registration says "clusters are games, never rungs; a rung-level interval would
be roughly sqrt(40) too narrow", and this interval is exactly that. Worse, the
residuals are systematic rather than noisy (max 8.11pp on 16453 at R2 0.978), so
the OLS SE is estimating the wrong quantity, not merely a small one.

**So read the point estimate, not the z-scores.** For d5's slope to hold, sigma
at line 8.1 would have to be ~14.15 against an observed 15.98 on a 34-rung fit.
That is a large discrepancy; the z of -3.89 is not the evidence, the 1.83-point
gap is.

## WHAT WOULD STILL OVERTURN IT

* The low-line end rests on ONE game, and it is the worst-fitting of the three
  (R2 0.9778, max residual 8.11pp). If 16453's ladder is misshapen its sigma is
  unreliable, and it is the entire low-line contrast.
* The two high-line games sit at 23.9 and 22.5 -- nearly the same point. So this
  is one low game against two near-coincident high ones, not three spread out.
* G = 3.

Two independent cohorts are now flatter than the shipped surface (mine n=5 at
0.0623, tonight n=3 at ~0.000) and d5's n=14 is the outlier and the only one from
a known-bad selector. That is a converging picture, not a settled one.
"""
