# Superseded figures — Quant D

Every number in this file was reported by me, then replaced. They are
listed because tonight superseded values kept being cited *after*
supersession: research carried −2.33¢ into a rule entry, and two
retracted k-curve figures reached landed documents.

**Before quoting any figure of mine, grep it here.** If it appears in the
left column, it is dead and the right column says what replaced it.

This is a partial artifact form for "a correction is not a certificate".
It cannot stop an author over-trusting their own fresh correction — that
half is genuinely procedural. It does catch the downstream half, which is
a reader citing a value that has since moved. That was the more frequent
failure tonight, by 2:1.

Scope: my figures only. Other agents' numbers are theirs to track.

| superseded | replaced by | why it moved |
|---|---|---|
| FLATTEN k=1¢ improvement **+$17.55** | **+$10.10** | exclusion method on a partial substrate; both defective |
| FLATTEN k=1¢ improvement **+$30.43** | **+$10.10** | insertion method, but grid missing 62 of 209 markets |
| FLATTEN positive region **{1¢, 2¢, 3¢}** | **{1¢}** alone | artifact of the partial grid |
| FLATTEN k=1¢ per-fill **−2.33¢** | **−2.20¢** | partial substrate |
| FLATTEN k=0 baseline per-fill **−3.62¢** | **−2.94¢** | partial substrate |
| k=2¢/3¢ at **−$38.98 / −$37.83** | **−$16.89 / −$27.88** vs k=0 | phantom-inflated inventory drove the lean |
| Placement / M2: **">10¢ is the only non-negative cell per cycle quoted"** (retracted twice — once on capture basis, once on per-cycle settlement; **one claim, not two findings**) | no width is profitable; >10¢ is the **worst** per-fill cell (−8.39¢, n=166, CI spans zero) | phantom gradient along the width axis (42%→79%), plus a metric whose optimum is "don't quote" |
| Whole-book replay vs fills-table read as **"settlement economics measured twice"** | not a replication — different procedures, **41% row overlap** | different fill-selection procedures = different quantities |
| Replay k=0 and recorded tape as **"convergence, agreeing to half a cent"** | withdrawn; k=0 is a **baseline arm**, unanchored to v1's economics | same defect as above |
| Phantom criterion fidelity **"~92%"** | no percentage; qualitative only | per-order rate used as a per-event rate (~1455× overstatement) |
| Phantom capture **−1.60¢** | **−2.31¢** clean capture | phantom contamination |
| ASOF `age <= 5` as a freshness gate | backward join + `assert age >= 0` | forward join made the cap vacuous; 123 fills, worst 25h lookahead |

## Figures that are current

| figure | value | basis |
|---|---|---|
| phantom share | **63.9%** | 17,339 recorded v1 shadow fills, full tick substrate |
| real fills, recorded tape | **6,255** | same |
| settlement, recorded tape | **−3.38¢/fill** | manager's read; **do not** place beside replay figures |
| FLATTEN k retained | **1¢**, fixed cents (not a fraction of spread) | boundary does not scale with spread |
| FLATTEN k=1¢ | **+$10.10**, per-fill **−2.20¢**, per-game **+0.78 [−3.77, +5.33]** | insertion basis, full substrate, replay's own world |
| every k negative per fill | **yes**, best −2.20¢ | — |
| criterion fidelity | 2/25 orders, 2/36,369 ticks — **supportive and thin, no percentage** | conditioned on execution, all BUY, n=25 |

No in-sample result justifies capital. The forward test is the evidence.
