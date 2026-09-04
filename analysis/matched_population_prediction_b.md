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

---

## UNSEALED — scored against D's result (b), 2026-09-04

**My prediction was WRONG, by my own declared threshold.**

    predicted (b)  +1.5 to +2.5pp, "clearly below +4.24pp"
    actual    (b)  +5.48pp  [-1.34, +12.29]   relative 1.249x
    my line        "(b) at or above +4.0pp falsifies my late-game-
                    concentration prediction outright"

5.48 >= 4.0. Falsified. And falsified in the direction opposite to the one I
predicted: I expected attenuation on early ground and the point estimate rose
(+4.24 -> +5.48pp, 1.206x -> 1.249x).

Derived from the published numbers, treating the pooled effect as an
n-weighted mean of phase effects (exact only if control rates match across
phases, so D should confirm with a direct late-phase run): non-early is
**+3.68pp over nT=1,034**, against early's +5.48pp over nT=469. Consumption
is, if anything, elevated MORE early than late — the reverse of the ride-tail
reasoning I registered.

**The power caveat is recorded and is NOT used as a rescue.** At nT=469 the
interval [-1.34, +12.29] contains my predicted range and also zero, so this
does not decisively refute late-concentration; it fails to support it. But I
pre-committed to a threshold on the point estimate and the point estimate
crossed it. Retreating to "the interval still contains my prediction" would
be the same underpowered-therefore-uninformative argument I used to defend
the witness — valid there, self-serving here, and the asymmetry is the whole
problem with using it.

### What survives and what does not

- **FALSIFIED (economic):** consumption concentrates late. The ride-tail loss
  map does not carry over to this phenomenon, and my registered cut resolved
  against it.
- **CONFIRMED (structural):** the witness is blind to late consumption by
  construction, because B sits above the running low once the price has
  ratcheted. D's decomposition shows the all-phase 1.122x was a pooling
  artifact of intervals where the witness cannot fire.

These were two separate claims and I bundled them as one explanation. The
structural half did the work; the phase half was wrong and unnecessary. The
witness's dilution needs no phase effect in the phenomenon to explain it.
