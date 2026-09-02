# B1 census report — Quant B, 2026-09-02 (speed-1 item 4)

**Artifact:** `analysis/cross_market_census.py` (four mutations: coherent
synthetic → gap 0.00¢; injected 12¢ desync → episodes found; 1.5s co-move
lag → recovered at 1.6s; independent-jitter null → zero episodes
invented). **Pins:** the 200ms tick export, 34 events. Descriptive; no
capture economics assumed anywhere; counts before ratios.

**No in-sample result justifies capital. The forward test is the evidence.**

## Instrument provenance — three artifacts caught before any number shipped

The first run of this census reported 1,462 persistent >10¢ triangle
episodes and 18-second ladder lags. All three headline numbers were
instrument artifacts, caught by the standard's own checks:

1. **Unbounded forward-fill**: dead rungs contributed hour-stale mids to
   the triangle, manufacturing fake gaps exactly in decided games. Fixed
   with a 2s staleness bound (a rung older than 2s is not a quote).
2. **Wide-bracket interpolation**: the largest surviving "episode"
   (por-atl 08-28, gap 39¢) was hand-checked against raw rows — a
   22-point bracket around x=0.5 in a blown-out game, where the venue's
   quotes were in fact perfectly coherent and linear interpolation is
   meaningless. Fixed with a bracket-width bound (≤7 points), which
   **structurally excludes 18 of 34 events**: ladders are seeded around
   the pregame line, so a heavy favourite's board never carries rungs
   near even — the winner↔spread consistency check only exists where the
   ladder straddles zero margin. A coverage finding in its own right.
3. **A lag definition that measured jitter**: the original episode rule
   piled up at its own 30s window cap. The jitter-null mutation (which
   the first self-test lacked) forced the redesign to directional
   co-moves (≥3¢ trigger, same-direction ≥2¢ response, 10s cap).

## Part 1 — the winner↔spread triangle: coherence largely HOLDS

Coverage: winner rows 1,244,422, two-sided 85% (the winner-book death of
`bookless-endgames.md` lives in that 15%); triangle computable — both
bracketing rungs two-sided within 2s AND bracket ≤ 7 pts — **25.6% of the
winner grid, 16 of 34 events**. |gap| p50 1.8¢ · p90 4.0¢ · p99 7.3¢ ·
max 20.2¢; median interpolation bound 8.0¢.

Episodes (|gap| above threshold AND above bracket/2, persisting):

| threshold | ≥1s | ≥5s | events with any |
|---|---|---|---|
| 2¢ | 3,072 | 585 | 16 |
| 5¢ | 511 | 88 | 12 |
| 10¢ | 18 | **1** | 3 |

**The 10¢ family is empty for practical purposes — one persistent episode
on the whole tape** — echoing, cross-type, the research agent's
within-totals coherence closure (1 violation / 34 games). The 5¢ family
(88 persistent episodes, 12 events) is the only residual: it sits against
a toll of winner-spread/2 + rung-spreads/4 + fee (typically 4–8¢ where
these books trade), was NOT hand-verified episode-by-episode (the one
episode we did hand-verify, at 10¢+, died), and is in-sample. **B1's
entry-policy claim does not survive at the ≥10¢ scale and is unproven at
5¢**; the honest next step, if anyone wants it, is hand-verification of a
sample of the 5¢ family before any registration — not a forward gate.

## Part 2 — update-lag attribution (B2's fold; no capture claims)

Censoring header per C: the observable lag population is the ≳400ms tail,
≈ the capturability bar; sub-0.4s mass is left-censored, not fast.

* spread ladders: 7,396 directional response lags — p50 3.0s, p90 8.3s
  (cap 10s); totals: 12,390 — p50 3.3s, p90 8.4s. **The venue's ladder
  repricing propagates over SECONDS**, a timescale a ~300ms reaction can
  in principle race — this is the flow-structure fact B1's mechanism
  needed, delivered as attribution.
* **C's congestion check FIRES**: long-lag (≥5s) episodes are strongly
  clustered in wall-clock — 55% (spread) / 70% (totals) occur within 30s
  of the next long-lag episode, vs 7% / 12% under uniform shuffle.
  Venue-wide slow periods exist, and capture attempts during them would
  face a slowed venue on OUR order too — C's marginal-capture-selects-
  against-us confound is live, now measured rather than hypothesized.

Even a null census is the venue's flow-structure map; this one delivered
three: the coherence extension, the seeded-ladder coverage hole, and the
congestion clustering.

**No in-sample result justifies capital. The forward test is the evidence.**
