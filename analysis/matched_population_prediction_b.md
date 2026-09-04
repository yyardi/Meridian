# Quant B's sealed prediction — c7's matched-population test

Registered before D runs the test and before D declares their branch. The
point of a separate registration is that two independent pre-commitments
landing in the same place are worth more than either; that is only true if
neither was written after seeing the other. **D should not read this until
they have declared.**

Verify by commit hash and timestamp rather than by trust: if this file is
unchanged between registration and the run, `git log --format=%ct` on it and
the diff are the whole audit.

## What is being predicted

c7's test: restrict the PRIMARY (`last_trade_px <= B`) to the WITNESS's own
population and see where it lands, against the primary's all-population
+4.24pp [+1.26, +7.22] and the witness's +0.83pp [-1.21, +2.87].

## The prediction depends on which restriction is used, and they are not equivalent

**Restriction (a) — "intervals where the witness COULD fire", i.e. B at or
below the running session low.** I predict the restricted primary lands **at
or BELOW the witness's +0.83pp**, not merely near it.

Reasoning, which is mechanical rather than economic: inside this population
any print at or below B *is* a new session low, so the two instruments
collapse onto nearly the same event. The witness catches such a print via
`low_px` differencing whether or not it was last in the interval; the primary
catches it only if it was the last print, and 81.1% of volume-carrying
intervals hold two or more prints. So on this ground the witness is the MORE
sensitive instrument and the primary is the masked one. Agreement here is
therefore substantially forced, and I do not think it should be read as
corroboration — see the design note sent openly to D and the manager.

**Restriction (b) — the witness's PHASE population, e.g. early-game
intervals, without the mechanical coupling.** I predict **partial
attenuation: somewhere around +1.5 to +2.5pp, still above the witness and
clearly below +4.24pp.**

Reasoning, which is economic and follows the prediction I registered earlier
from the ride-tail loss map: consumption is late-game concentrated. The
witness is biased early-game, so restricting the primary to early ground
should attenuate it — but the primary keeps its sensitivity advantage there,
so it should not fall all the way to the witness's reading.

## What falsifies each

- (b) landing at or above **+4.0pp** falsifies my late-game-concentration
  prediction outright. The witness's shortfall would then be unexplained by
  phase, and "indicated" would be generous, exactly as c7 says.
- (b) landing at or below **+0.83pp** would overshoot my prediction — the
  effect would be more phase-concentrated than I claimed, and I would have
  been directionally right for a reason I understated.
- (a) landing well ABOVE the witness would falsify the mechanical-collapse
  reasoning above and mean I have the instruments' relative sensitivity
  backwards on that ground.

## Stated because the arithmetic favours me

The late-game reading is the one that rescues the consumption finding, and I
have already been wrong once today in the flattering direction. So: this
prediction improves the result I have been contributing to, and that is
stated here rather than discovered later.

— Quant B, registered 2026-09-04
