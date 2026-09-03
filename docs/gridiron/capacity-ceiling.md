# The capacity ceiling — what this venue can pay, and how fast

**Research agent + manager, 2026-09-03. Every input labelled MEASURED or
ASSUMED. Written because the operator set a hard target and deserves
arithmetic rather than a mood.**

## The target, corrected at the source

The operator first said ~$300k, then $900k, then sent the listing. **Fetched
it: 2018 Ferrari 488 GTB, $286,193**, 9,500 miles, Lehi UT. With Wisconsin
sales tax and transport, **~$305k all-in.** The $900k figure was a misfire;
**the operative target is ~$286–305k**, which is what this document prices.

**As a rate: $286k over 17 weeks (Sept 3 → Dec 31) = ~$16,800/week.**

## The equation, with each factor's status

`revenue = fills/week × contracts/fill × capture/contract`

**CAPTURE — UNPROVEN AND CURRENTLY NEGATIVE.** Measured −1.60¢/fill
(MEASURED, v1, 17,032 fills). Arms below use +0.5¢ and +1¢, both
hypothetical. **This factor has a hard ceiling: traded cells are 5–6¢ wide,
so a maker collects ~2.5–3¢ of half-spread gross and pays adverse selection
out of it. +1¢ NET is already the optimistic end of what the spread
structurally permits; +5¢ does not exist on this board.** Effort cannot
scale this factor.

**FILLS/WEEK — ESTIMATED, doubly uncertain.** WNBA shadow fills ran
1,310/game (MEASURED); shadow ≠ real, and P(fill) is the probe's open
question. At a 1/4 real-fill haircut across 16 NFL games/week: **~5,300/week**,
with 10,000 as the optimistic end. Second uncertainty: **NFL in-play fill
density is unmeasured and plausibly LOWER than basketball's** — football has
long dead intervals between snaps where basketball updates continuously.

**CONTRACTS/FILL — the binding constraint, and it is NOT capital.**

## The depth ceiling — the mechanism, which is not what it looks like

The naive reading is "you'd be most of the book." **The real mechanism is
different and worse:** resting S contracts behind existing depth D does not
lower your fill PROBABILITY — you sit behind D whichever S you choose. It
does three other things: **it raises ADVERSE SELECTION** (a fill large
enough to consume S came from flow large enough to be informed), it makes
you visible in a thin book with few participants, and it scales inventory
risk directly.

**So the true constraint is how adverse selection scales with fill size —
and that is UNMEASURED.** The 5%-of-book figure used below is a desk
convention, not a measurement, and it is this section's largest assumption.

**Depth, MEASURED:** WNBA in-play at our own quote price median ~1,000;
WNBA near-tip pregame top-of-book 781 spread / 570 total; NFL traded cells
pregame 40–620. **NFL in-play depth does not exist until a game is played.**
At 5% of a ~1,000 book, sustainable size ≈ **50 contracts**; at 10%, 100.

## Per-league revenue, one board, at a PROVEN edge

```
                    +0.5¢/contract        +1¢/contract
5,300 fills/wk    $1,325/wk  ($23k)     $2,650/wk  ($45k)
10,000 fills/wk   $2,500/wk  ($43k)     $5,000/wk  ($85k)
                                   (17-week totals in parentheses)
```

**Honest range for one board at a proven edge: $23k–85k over the remaining
year.** The $85k is every assumption at its optimistic end simultaneously.

**CAPITAL PER LEAGUE:** peak concurrent inventory was 702 contracts at UNIT
size (MEASURED); at 50 contracts/quote that is ~35,100 contracts, and with
per-contract loss bounded at $1 the worst-case bound is **~$35k per league**
(~$13k time-weighted). **One board at earning size needs $13k–35k.**

## The three gaps, and they multiply

1. **EDGE SIGN** — unproven, currently negative. Not a matter of scale.
2. **SIZE** — capital-bound at ~1 contract on $1,000 (MEASURED: $702 peak
   bound at unit size). Earning size is ~50. **A 50× gap needing $13–35k.**
3. **BREADTH** — $286k ÷ $23–85k per board = **3.4 to 12.4 boards.**

## THE CONSTRAINT NOBODY HAD PRICED: THE CLOCK, AND IT BINDS HARDEST

**One board took a month of instrumentation and is still not proven.**
Boards 2–N each need their own constants, calibration, venue facts and
gates. At an optimistic one board per month we hold **~4 boards by Dec 31**,
and board one's edge reads at the end of September.

**And boards added later earn for less of the year.** Optimistically:
board 1 live ~Oct (13 wks), board 2 ~Nov (9 wks), board 3 ~Dec (4 wks).
Even at the $85k/17-week rate that sums to roughly **$130k — with every
assumption optimistic and a positive edge that does not yet exist.** At the
$23k end it is roughly **$35k.**

**So: ~$35k–130k is the honest year-end range if the sign flips soon and
capital arrives. That is 12%–45% of the car.** The gap is CLOCK and
CAPACITY, not ambition.

## What $1,000 alone supports

Unit size, one board, 5,300–10,000 fills/week at +1¢ = **$53–100/week, i.e.
$900–1,700 by Dec 31.** Compounding $1,000 → $286k in 17 weeks is 286×,
about 40%/week — **no market-making edge produces that at any capacity.**
It is not a capacity question; it is arithmetic. **The target is a
deployment proposition, not an earnings-from-$1,000 proposition, and must be
stated that way.**

## One breadth asset already owned

**Kalshi is already recorded.** Breadth means VENUES as well as leagues, and
that is one additional board with instrumentation partly built — the
cheapest second board available.

## The sequencing, which is the actual answer

**Focus is the sequencing; breadth is the scaling. Consecutive, not
competing. An unproven edge multiplied across ten boards is ten times the
loss — that is the entire argument for proving one first, and the fastest
route to a large number runs through the small one.**

**Reachable and worth doing: prove the sign on NFL by late September.** If
it is real, the question becomes how much capital to deploy against a
$23–85k/board/year machine and how fast boards can be added — which is a
business, and a real answer to give someone who says they will not stop.

**No in-sample result justifies capital. The forward test is the evidence.**

---

## SUPERSEDING MEASUREMENT (D, 2026-09-03) — the constraint is ABSORPTION RATE, not depth

**Depth was the wrong object.** Depth tells you what is VISIBLE; **rate
tells you what actually transacts in the window you own.** A quote that
requotes every 5 seconds owns 5 seconds.

**MEASURED, 129 real resting orders (requested vs filled quantity over
their own rest time):**

```
absorption rate, all orders:           median 0.050 contracts/second
size-testing subset (requested ≥100):  median 0.193/s  (p90 5.71, max 145)
WNBA only:                             median 0.008/s  (median rest 1,404s)
```

**What a 5-second quote cycle absorbs at those rates: ~0.25 contracts
(all), ~1 contract (size-testers), 28–169 at the p90 of the most aggressive
subset.** Against the ~170–530 contracts/quote the target requires, that is
a shortfall of roughly **500× at the median.**

**Why absorbed QUANTITY flatters and rate does not:** those orders absorbed
a median of 34 contracts (155 for size-testers, max 7,285) — survivable
sounding, until you see they rested a **median 495 seconds and p75 1.6
HOURS** to get it.

**PER LEAGUE PER WEEK at measured rates**, using v1's own quoting footprint
(~16 markets/game × 13 games/wk × 2.5h live ≈ 250–500 market-hours/week):
≈25k–50k contracts/week → **$250–500/week at +1¢**, half at +0.5¢. WNBA's
own 0.008/s gives **$40–80/week.** Against ~$16,800/week for the corrected
$286k target, that needs **34–67 leagues at measured rates.**

**THE CAVEAT, AND ITS DIRECTION IS KNOWN: these are PATIENT orders, not
touch-joining ones** (median rest 495s — the population finding). An order
resting AT the touch absorbs faster than one resting away from it, so
**every rate above is a LOWER BOUND for a quoter, plausibly by a large
factor.** Granting an optimistic 10×, the requirement falls to ~3–7 leagues
— which is within sight of the ~4 boards the clock permits, and is
therefore the entire difference between "impossible" and "hard."

**THAT IS EXACTLY WHAT THE HAND-PLACED FILL PROBE MEASURES.** It bounds
this number from the other side, and it just became the most valuable
instrument the program has. **No capital should be committed against a size
assumption before it runs.**

**And the caveat that leads: this is a ceiling on EXTRACTION, conditional
on a positive capture we have never observed. A capacity ceiling times a
negative edge is a loss ceiling.** Every capture number this program owns is
negative or straddles zero. The measurement says how big the prize could be
if the sign flips. It says nothing about the sign.
