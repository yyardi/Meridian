# Extreme-price hold to settlement — CFB in-game winner, 2026-09-13

`cfb/run_extreme_hold.py`, prod read-only, 59 CFB games scored of 86 in plays+map, venue-settled
through `core/settlements.py`. Nothing was traded.

**The question.** The taker fee is `0.06·p·(1−p)` per side, so it collapses at the extremes: a
round trip costs 6.0% of the ticket at 50¢ but 0.4% at 95¢. Holding to settlement pays **one**
fee and **one** half-spread. Every strategy this programme has measured died at mid prices
paying two of each. So: buy the near-certain side of the in-game winner market at the ask and
hold. Pre-registered primary = band × side pooled over periods, 8 cells; the 48 period/half
cells are exploratory and are not the answer.

## The answer: the cost thesis is right and it does not matter

| band / side | net @ ask (¢/$1) | calib | cross | fee | win | CP 95% lo | break-even | n=G |
|---|---|---|---|---|---|---|---|---|
| [0.900,0.925) YES/away | −17.67 [−50.01,+14.66] | −15.41 | −1.84 | −0.42 | 75.0% | 40.0% | 92.7% | 8 |
| (0.075,0.100] NO/home | −0.85 [−12.61,+10.91] | +0.15 | −0.54 | −0.46 | 91.3% | 75.1% | 92.2% | 23 |
| [0.925,0.950) YES/away | −19.63 [−52.00,+12.73] | −18.19 | −1.12 | −0.32 | 75.0% | 40.0% | 94.6% | 8 |
| (0.050,0.075] NO/home | **+0.99** [−8.01,+9.98] | +1.86 | −0.55 | −0.33 | 95.5% | 80.2% | 94.5% | 22 |
| [0.950,0.975) YES/away | −8.97 [−33.41,+15.47] | −8.00 | −0.75 | −0.22 | 87.5% | 52.9% | 96.5% | 8 |
| (0.025,0.050] NO/home | −0.21 [−7.22,+6.80] | +0.38 | −0.38 | −0.21 | 96.4% | 84.1% | 96.6% | 28 |
| [0.975,0.990) YES/away | **+1.68** [+1.41,+1.96] | +2.21 | −0.43 | −0.11 | 100.0% | 65.2% | 98.3% | 7 |
| (0.010,0.025] NO/home | −1.70 [−8.22,+4.82] | −1.25 | −0.35 | −0.10 | 96.7% | 85.1% | 98.4% | 30 |

`net = (y − mid) calibration − (ask − mid) crossing − fee(p)`, exact and additive, y ∈ {0, 0.5, 1}.

**Crossing plus fee is 0.45–2.26¢ in every cell**, against the momentum scalp's 3.8–5.7¢ of
half-spreads plus 4.1–5.4¢ of fees. The fee collapse is real and holding does capture it —
about 8¢ per contract. **Calibration then carries everything, at −18.19 to +2.21¢.**

This is a *different* negative from every earlier one. The scalp died of cost with drift ≈ 0.
This dies of calibration with cost ≈ 1¢. **"The fee killed it" is no longer a general
explanation of this programme's results**, and that changes what is worth trying next.

**Entry at the mid** (not tradeable) moves the cells by only 0.4–1.8¢: −17.67 → −15.93,
−0.85 → −0.33, +1.68 → +2.08. A resting maker entry recovers the crossing term only, and
crossing was never the binding cost. **It cannot rescue any cell.**

## ★ The one cell that excludes zero is degenerate. Do not quote it.

`[0.975,0.990) YES/away` reads **+1.68 [+1.41, +1.96]** — the tightest interval on the board.
It is tight *because nothing varied*: all 7 games won, so the P&L has no outcome variance left
and the game-clustered sandwich collapses onto the band's own price dispersion. The interval is
measuring the band's width.

The honest instrument is binomial on the win count. **7/7 gives a one-sided 95% Clopper-Pearson
lower bound of 65.2% against a break-even of 98.3%** — consistent with a true rate of 65%.
Games needed for the bound to clear break-even *at the observed rate*: **175** here, **1,366**
for (0.050,0.075], and never for the rest, whose win rates sit below their break-evens.

**No cell's win rate exceeds its break-even by more than 1.7pp**, and the two that exceed it at
all do so by 1.0pp (n=22) and 1.7pp (n=7).

## ★ A defect in this study's own instrument, and why the numbers survive it

The registered freshness gate required the **mid to have changed** within 120 s, to stop a
frozen board looking like a held price. It dropped **zero** entries, which I first read as
"no frozen boards". It is not: **writes are change-detected, so nearly every written row *is* a
change.** Measured over all 134 entries, the age of the last mid change is **identically 0.0 s**.
The gate tested a quantity that is always zero — it could only ever pass.

A frozen board is a **gap**, not an unchanged mid. Measured on the correct quantity, seconds
since the previous write, at entry: **median 3.1, p90 6.4, max 10.7, and 0 of 134 over 600 s.**
So the in-game winner tape carries no stale entries here and the manager's 600 s paired cut
drops nothing — the cells are identical under it. The tape-wide finding that 12,290 markets
still say `is_live` on their last row, 91.4% unwritten for 600 s, is about markets' **final**
rows at end of life; these entries are mid-game and structurally not exposed to it.

## Substrate checks that passed

* `fee_coefficient` asserted per tick on every scored game: **0.060000**, never quoted.
* Settlement is the **venue's own**, not `espn_cfb_game_state` — only ~41% of games reach
  `state='post'`, so ESPN settlement would drop half the cohort *and* select survivors on our
  own recorder. ESPN's score is used only to cross-check, on the 27 games where it exists.
* A **draw settles at 0.5** and is a real settlement; `y` is a float, so an NFL tie is not
  booked as a loss on both sides of a twin (where it would still have summed consistently).
* **58 of 59 windows reach period 4**, so window truncation does not under-sample the high
  bands, which occur late.
* Max single-game share of any cell is **exactly 1/n by construction** (one entry per game per
  band per side). Proof is printed: `G_eff == n` in every row.
* 6 of 59 games have a last in-game mid on the wrong side of the venue label. All benign, and
  they **confirm orientation**: ESPN's score direction matches the venue label in all 6. Two
  are tapes ending 65 and 121 min before the last play, two are OT, two are one-point games.

## What would change the answer

The away side is structurally scarce — n = 7–8 per band against 22–30 for home — because away
teams rarely become near-certain in CFB weeks 1–2, which is the same whole-ladder home shift
`cfb/run_longshot_decomp.py` measured. So the twin comparison is badly unbalanced and the YES
cells cannot be read at all.

Bands **share games** (a game climbing 0.90 → 0.98 enters several), so the cells are not
independent of each other: "three of four bands negative" is closer to one observation repeated
than to three. The clustered interval covers within-cell dependence only.

At ~175 games for the best cell, this needs a full season of tape, not another Saturday.
