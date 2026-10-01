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
  the display). The phantom check on these four slates is appended below when it finishes.
- A two-leg taker that gets one leg filled and not the other holds a naked position; the
  engine's unwind rule is part of the cost, not an afterthought.

## What this closes and what it leaves

It closes the question of whether a faster engine turns the ladder into a programme: the
whole reachable pool is a few hundred dollars a weekend at displayed size, concentrated in
one or two crossings. It leaves one cheap, decisive step — place one real two-leg order at
the smallest size on the next reachable crossing and read the fills — which is the
operator's switch, not a measurement.
