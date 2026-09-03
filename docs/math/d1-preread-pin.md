# D1 pre-read pin — the pregame concession window partition

**Quant D, 2026-09-02. Pinned BEFORE D1's next read, per the round-3
disposition ("window partition pinned before its next read"). Nothing here
is computed; this page exists so the read cannot choose its own buckets.**

D1 (brainstorm round 1): *real resting-order concession, measured on the
quote engine's own fills, is ≤ 0 in dead pregame windows, and the measured
+4.70¢ in-game adverse concession concentrates in the in-play/near-tip
window.* Accruing on the quote engine's real fills; the QUOTE v2 post-mortem
(quote_v2_markout.py, seed 2) showed pregame capture −1.33¢ [−1.68, −0.98]
AGGREGATED — the partition below is what decides whether a dead-window
sub-regime exists inside that aggregate.

## The partition (pinned now, argued never)

Hours-to-tip buckets at QUOTE BIRTH (`quoted_at` vs `game_start_time`):

    >= 6h   ·   2–6h   ·   0.5–2h   ·   < 0.5h (near-tip)   ·   in-game

- Basis: capture at fill (static-study mark, `net_capture_mark`), clustered
  by game via the blessed `clustered_mean`; settlement ROI printed beside
  it, labelled, never mixed.
- D1's claim lives in the `>= 6h` bucket: concession ≤ 0 there.
- Requires `game_start_time` in the fills export — absent from the 09-02
  pin; required for the next one (pre-slate-checklist §5).

## The engine the window measures (dated line per pre-slate-checklist §6)

**2026-09-02:** the restarted quoter is the container started
2026-09-02T16:03:59Z, image built from prod checkout at commit `7a3a217`
(tracked tree clean), and `core/quote/` at `7a3a217` is **byte-identical**
to main head `0addd69` — no commits have touched the engine since the
August run. The restarted build runs the same engine code the v1 window
measured; D1's forward pregame fills are comparable to the parked 307-fill
accrual. Evidence gathered and cited by the manager in
`docs/infra/pre-slate-checklist.md` §6 (landed 3ab4142).

**No in-sample result justifies capital. The forward test is the evidence.**

*Results append below this line, never above it.*


---

**DATED LEAGUE-FILTER LINE (research agent, 2026-09-02):** D1's cohort is
**league = WNBA (basketball) ONLY**, same clause and reason as A1's gate:
the substrate table goes mixed-league with GRIDIRON's NFL recording, and
this pin's buckets and capture basis are WNBA-derived. League filter keys
on the event slug prefix.


## DATED LINE (2026-09-03) — a SECOND, independent mechanism pointing the same way

Measured while resolving an unrelated question: **WNBA pregame top-of-book
depth GROWS toward tip — median 110 contracts at T-1 to T-5 days, 450
inside 24 hours** (40,000 random pregame snapshots joined to their book
rows, `level_index = 0`).

D1's registered thesis argues for resting FAR from tip because informed
flow needs information arrival and dead windows have none. **This adds an
independent reason pointing the same way: dead windows also have THIN
books, and thin books mean SHORT QUEUES.** A maker resting at T-3 is both
less adversely selected AND closer to the front of a much smaller line —
two different mechanisms, one conclusion.

**When D1 reads, interpret it against BOTH**, not the concession story
alone. Caveat carried: measured on WNBA, one basis, and it says nothing
about whether anyone trades in those windows — **thin and quiet is still a
desert.**
