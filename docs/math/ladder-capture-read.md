# Ladder crossings: how much lives long enough for a fast engine to take

2026-10-01. The stream-measured, spread-only ladder crossings over $25 (STATUS §0cd; the
instrument is `core/ladder/stream_episodes.py`, gate 2 s, fee 0.0695, the nightly
`edge_ledger.jsonl`) are the one measured, model-free, riskless inefficiency in this
codebase. This read asks the next question: of those, how much stood long enough for an
engine to hit **both** legs. A two-leg taker needs the reaction (~100 ms with the stream
stack built for BTC) plus a venue round trip per leg (unmeasured; assume 100–200 ms), so
0.5 s of life is a floor for "reachable" and 1 s is comfortable.

Four full football days, every spread-only crossing ≥ $25, best instant at displayed size:

| slate | crossings | Σ best | lived ≥ 0.25 s | ≥ 0.5 s | ≥ 1 s | ≥ 2 s |
|---|---:|---:|---:|---:|---:|---:|
| CFB 2026-09-19 (92 games) | 4 | $270 | 3 / $228 | 2 / $183 | 1 / $69 | 1 / $69 |
| NFL 2026-09-20 (14) | 7 | $754 | 3 / $400 | 3 / $400 | 3 / $400 | 2 / $107 |
| CFB 2026-09-26 (53) | 3 | $146 | 1 / $35 | 1 / $35 | 1 / $35 | 0 |
| NFL 2026-09-27 (13) | 3 | $130 | 2 / $87 | 1 / $37 | 1 / $37 | 0 |
| **four days** | **17** | **$1,300** | 9 / $750 | **7 / $655** | 6 / $541 | 3 / $176 |

The crossings themselves (game, pair, $, life): the biggest were CAR–ATL −23.5/−21.5 $293
for 1.44 s, WAS–DAL 16.5/19.5 $149 for 0.21 s, FSU–ALA 13.5/16.5 $114 for 0.78 s, MIA–SF
28.5/33.5 $96 at a single update (life 0.00 s), OKL–GA 13.5/14.5 $81 at a single update. The
staler leg was ≤ 0.3 s old on all but one (1.2 s), so these are not stale pictures of a
re-quoted rung; the gate did its job.

## What the number means

- **Reachable at displayed size: $70–$580 a weekend**, depending on the weekend ($583 on
  09-19/20, $72 on 09-26/27), from 7 crossings in four days. The second weekend was a
  quarter of the first; two weekends do not say which is typical.
- That is **before two unknowns** that only an order can answer: whether displayed size
  fills (zero ladder pairs have ever been placed; see §0bj), and whether a displayed quote
  is a resting order at all (the phantom check on 2026-09-21 found 8 of 29 printed through
  the display). The phantom check on these four slates is in the last section: of the
  reachable $580, $147 is shown real, $57 phantom and the two biggest ($376) unproven.
- A two-leg taker that gets one leg filled and not the other holds a naked position; the
  engine's unwind rule is part of the cost, not an afterthought.

## What this closes and what it leaves

It closes the question of whether a faster engine turns the ladder into a programme: the
whole reachable pool is a few hundred dollars a weekend at displayed size, concentrated in
one or two crossings, and the part of it a print shows to have been a real quote is under
$100 a weekend (next section). It leaves one cheap, decisive step — place one real two-leg order at
the smallest size on the next reachable crossing and read the fills — which is the
operator's switch, not a measurement.

## The phantom check on these four slates (2026-10-01)

`scripts/launchers/phantom_check.py` replays each crossing's book tape to the instant it
opened, takes both legs' displayed touch, and reads every taker print on either leg while it
stood (plus 0.5 s): a print THROUGH the display (a lift above the displayed ask, a hit below
the displayed bid) says the quote was not there. It consumes the ledger's newest gate-2 rows
for the four slates (re-written 2026-09-21 20:16–20:33Z and 09-27/28, fee 0.0695 recorded on
each row, the episode timestamps the check needs): $1,224 over the same 17 spread-only
crossings, 6 of them ≥ 0.5 s for $580, against the table's $1,300 / 7 / $655, which was
tabulated from the first-written rows. The verdicts are on the newest rows.

| population | n | Σ best | phantom | resting | unproven (no prints) |
|---|--:|--:|---|---|---|
| all 17, registered rule | 17 | $1,224 | 9 / $633 | 2 / $79 | 6 / $513 |
| all 17, first-print rule | 17 | $1,224 | 5 / $426 | 6 / $285 | 6 / $513 |
| lived ≥ 0.5 s, registered | 6 | $580 | 3 / $168 | 1 / $35 | 2 / $376 |
| lived ≥ 0.5 s, first-print | 6 | $580 | 1 / $57 | 3 / $147 | 2 / $376 |

The registered rule is the one the check was written with and run with on the 09-21 slate (8
of 29). The first-print rule is a post-hoc refinement, stated because the registered rule
counts a sweep's tail — prints AT the display first, then beyond it once it is consumed — as
phantom, and a consumed display is what a resting order looks like; it reads only the first
taker print on each leg after the open. Four crossings (IND–KC $74, WAS–DAL 2.5/0.5 $45,
NYJ–DET $50, BAL–DAL $37) flip from phantom to resting under it, each with its first print AT
the display 0.0–0.3 s after opening. The one reachable phantom left, GA–ARK $57, printed
through 0.1 s after the episode closed, which a pulled quote also explains.

- The two biggest reachable crossings, CAR–ATL $272 (1.4 s) and FSU–ALA $104 (0.8 s), had no
  print on either leg while they stood. The tape does not say whether they were there.
- The reachable crossings a print shows to have been real were $147 in four days (three, $35
  to $74 each), and each had its first print at the display within 0.3 s of opening: someone
  is already taking them, faster than this stack's ~100 ms reaction plus a venue round trip.
- So the shown-real reachable pool is about $75 a weekend at displayed size, before fills.
  The $376 above it is unknown and stays unknown until an order rests on one of them.

Reproduction, inside the api image on prod with `artifacts/reads` at `/out`: the registered
rule is `python3 scripts/launchers/phantom_check.py --ledger /out/edge_ledger.jsonl --root
/out/stream --gate 2` (its 61-episode run over every league and date 09-19..09-28 printed
26 phantom / 17 unproven / 18 resting; the four-day spread-only subset above is read off
that table); both rules side by side are `python3 analysis/ladder/phantom_first_print.py`.
