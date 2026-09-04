# Registration draft — is the −3.4c a directional accident?

**Status:** DRAFT, not registered. Written 2026-09-04 by Quant D at the
manager's request. Nothing here has been run. Measures and buckets are pinned
below **before** anyone looks.

**Why it may outrank the resting-order probe:** the probe stops an existing
number being wrong. This asks whether we have misnamed the entire problem.

---

## 1. The thing to explain

Two measurements that do not sit together comfortably:

- Real-fill settlement P&L is **−3.4c/fill**, game-clustered CI excluding zero.
- Markout after those same fills is **positive** at every horizon out to 300s
  (+0.2 to +1.2c), and **flat by width**.

So the flow reaching us is not immediately toxic, and **the entire loss lives
beyond five minutes**. Something happens between the five-minute mark and
settlement.

## 2. Three rival explanations, one already dead

**H1 — DIRECTIONAL ACCIDENT.** We held net exposure to the games' underlying
outcomes, and across 24 games those outcomes went against us. The loss is
variance wearing a mechanism's clothes.

**H2 — SYSTEMATIC MISPRICING.** The rungs are priced away from their
settlement frequencies and we buy the expensive side.
**Already refuted.** Rung calibration measured price at each rung's first
two-sided live tick against realised settlement, 608 markets / 34 events,
event-clustered: no support for a bias in either direction, anywhere. The
low tail ran *opposite* to the classic favourite-longshot effect.

**H3 — MOMENT SELECTION.** The board is calibrated on average, but the
*instants* at which someone crosses to us are instants when the contemporaneous
mid is a biased estimate of settlement. This is adverse selection that shows
up only at the settlement horizon, which is exactly the shape §1 describes and
is why the 300s markout cannot see it.

H1 and H3 make opposite predictions and the study must separate them, not
confirm either.

## 3. ★ The discriminating control

**The board is the control, and the same games supply it.**

A directional accident moves the whole board: if a game's total lands high,
every "over" rung in that game settles the same way whether we traded it or
not. So H1 predicts our fills and the untraded rungs of the *same games* are
mispriced-in-hindsight **equally**.

H3 predicts a gap: the board calibrates, and the subset we filled does not.

    calibration residual r = (settlement - mid_at_fill), signed by our position

  - measured on OUR FILLS
  - measured on a MATCHED BOARD SAMPLE: the same games, same markets, same
    clock instants, but rungs/moments we did NOT fill, sampled to match our
    fills' distribution over (mid, time-to-settlement, league)

**H1 ⇒ residual_ours ≈ residual_board, both possibly non-zero.**
**H3 ⇒ residual_ours < residual_board, with residual_board ≈ 0.**

This is the whole design. Everything else is bookkeeping.

## 4. Measures, pinned now

**Net position (per game).** Each fill's signed exposure to the game's
underlying: long YES on a rung is +1 toward "higher" (over the line / the
favoured side under V14's YES frame), short YES is −1. `Net_g` = sum over the
game's fills. Reported alongside gross fills, because a game can be busy and
flat.

**Outcome direction (per game).** `z_g = (X_g − M_g) / S_g`, where `X_g` is
the realised underlying (total points or margin), and `M_g`, `S_g` are the
median and dispersion of the **market-implied distribution** read off the rung
ladder at the game's first two-sided live tick. The ladder is the implied CDF;
we do not need an external model.

**The accident regression.** `PnL_g ~ a + b · (Net_g × z_g)`. H1 predicts
`b > 0` and that `Net_g × z_g` explains the aggregate loss. If the total loss
survives with `Net_g × z_g` partialled out, H1 is dead as the primary cause.

**Calibration residual.** As in §3, clustered by game.

## 5. Buckets, pinned now

Fixed before any look, and not to be refined afterwards:

- mid at fill: [0.20, 0.35), [0.35, 0.50), [0.50, 0.65), [0.65, 0.80]
- time from fill to settlement: <10 min, 10–60 min, >60 min
- league: WNBA, CFB
- side: bid, ask

The time bucket is the one that matters most: §1 localises the loss beyond
300s, so the loss should concentrate in the longer buckets under every
hypothesis, and its **shape across them** is what separates a slow drift from
a settlement-only jump.

## 6. Decision rule, fixed in advance

| outcome | reading |
|---|---|
| `residual_board ≈ 0` and `residual_ours` significantly worse | **H3.** Moment selection. The problem is *when* we trade, not *what* we hold |
| `residual_ours ≈ residual_board`, both negative, and `b > 0` explains the loss | **H1.** Directional accident. The program has misnamed the problem and the fix is exposure management, not microstructure |
| both ≈ 0 | the −3.4c is not reproduced by this decomposition — an error upstream, and the settlement figure needs re-deriving before anything else |
| `residual_ours ≈ residual_board`, both negative, `b` explains nothing | neither; a fourth mechanism, and the study reports that rather than picking the nearer of two |

## 7. Power, and it is the weak point

**24 games.** The existing game-clustered CI on our fills is [−4.75, −2.01],
so the effective N for anything game-level is 24, not 13,651.

The accident regression has one observation per game. With 24 points, only a
strong relationship is detectable; a real but moderate directional effect
will not clear. **So a null on `b` must be reported as "not detected at
n=24", never as "direction ruled out".**

The calibration comparison is stronger, because the matched board sample can
be made large within the same games — it is a paired comparison, and the
game-level variance that ruins the regression largely cancels. This is the
reason §3 is the primary and the regression is secondary.

## 8. Confounds

1. **Matching quality.** If the board sample is not matched on (mid,
   time-to-settlement, league), the comparison measures the matching, not
   selection. Match first, then compare; report the achieved balance.
2. **The ladder is not independent across rungs.** Rungs of one game are one
   observation wearing many hats — the error this program has made twice.
   Cluster by game, and report game counts beside row counts everywhere.
3. **Implied distribution from a coarse ladder.** `M_g` and `S_g` are only as
   good as the rung spacing. Where the ladder is sparse, `z_g` is noisy;
   report ladder width per game and exclude games below a pinned rung count
   (**≥5 rungs with two-sided quotes**).
4. **Our own fills move the mid.** The board sample must exclude instants
   contaminated by our own quoting where identifiable.
5. **Settlement-time leakage.** A fill 30 seconds before settlement has almost
   no uncertainty left; those rows will dominate a naive calibration. This is
   what the time buckets are for.

## 9. What this cannot rule out

- With 24 games, H1 cannot be excluded, only bounded. A finding of H3 does
  not prove direction contributed nothing.
- Both H1 and H3 could be true at once; the design attributes, it does not
  partition cleanly.
- It says nothing about whether the fills would have been *received*
  (A2/P1 in the resting-order registration). This study takes the recorded
  real-fill population as given, and that population is an upper bound.

## 10. Crossing size, if it is wanted here

`market_trade_stats` carries `last_trade_px` / `last_trade_qty` /
`last_trade_at` on a polling cadence, plus cumulative `shares_traded`. **There
is no full trade-print stream in the schema.** So a crossing-size distribution
can be *sampled* — whatever trade happened to be last when the poller looked —
and interval volume recovered by differencing the counter, but it cannot be
measured. Any use here must be labelled an estimate carrying that sampling
bias, and it is secondary to §3 either way.

## 11. Substrate caveat to carry everywhere

Any number computed off `qv2_queue_ahead_20260904T144200Z` carries the
compounded conditioning: **69.4% (price-identity valid) of an already-
conditioned 20.4% (cycles where a depth fetch landed), over 4h35m of stream
life, covering 532 of 833 fill markets and none of the fills in 20 of the 24
games.** It is a distributional input, not a result.

---

No in-sample result justifies capital. The forward test is the evidence.
