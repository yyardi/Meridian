# What the ride tail costs, per game

**Descriptive, in-sample, hypothesis-generating.** Computed from Quant A's
round-trip ledger (`roundtrip_ledger_20260901T195202Z.csv`, 1,944 filled entries
/ 34 games / 31 with stake > $1). Policy: round-trip, maker fills at recorded
limits, $0 fees — **the optimistic arm**. Game-level, so the unit is a game.

## The number

```
                       n      stake      P&L        per-$      pessimistic
TRIPS (exited)      1,807   $958.47   +$55.86     +5.83%/$      -16.46%/$
RIDES (no exit)       137    $56.93   -$28.82    -50.62%/$      -65.45%/$
```

**7.0% of fills destroy 52% of what the other 93% earn.** A ride — a position
that never got an exit fill and rode to settlement — returns **−50.6¢ per
dollar** on the optimistic arm. That is not a bad trade; it is a different
distribution.

## At the level the operator experiences it

```
book WITH rides       mean +1.97%/$   10 of 31 games lose
book WITHOUT rides    mean +6.07%/$    3 of 31 games lose
```

**Removing the rides roughly triples the book and cuts losing games from 10 to
3.** Scaled to a $1,000 book per game, the observed spread runs **best
+$132.96, worst −$164.34, mean +$19.74.**

The pattern is visible game by game — the games with the most rides are the
losers, the games with none are all winners:

| game | rides | per-$ |
|---|---|---|
| wsh-por 08-23 | 13 | −9.4% |
| min-atl 08-30 | 11 | −3.9% |
| gsv-por 08-30 | 11 | −6.9% |
| ind-tor 08-18 | **0** | **+12.3%** |
| ind-dal 08-20 | **0** | **+7.9%** |
| tor-wsh 08-19 | **0** | **+7.6%** |
| gsv-ny 08-27 | **0** | **+7.1%** |

## What this is NOT

**It is not "we are profitable and need better exits."** Under the measured
4.70¢ concession every arm is negative — trips included, at **−16.46%/$**. The
finding is about **where the loss is concentrated**, not about a surviving edge.

**It is not a strategy.** "Avoid rides" is not executable: a ride is only known
to be a ride afterwards. The tradeable version is a *state* filter chosen in
advance — which is exactly what the crossing-arms state-mask companion
registration tests forward, and its in-sample motivation is quoted there with
this caveat attached.

**The mechanism is measured, not guessed.** Rides concentrate where
`bookless-endgames.md` says the exit book dies: Q4, late minutes, decided games.
Quant B's loss map and Quant D's execution decomposition reached it from
different bases.

---

**No in-sample result justifies capital. The forward test is the evidence.**
