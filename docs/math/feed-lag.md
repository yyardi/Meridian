# The feed-lag bound (F8)

**Status: measured twice, bound confirmed at 16 games, 2026-08-25.** For scoring plays (>=2 pts, second half): time from the play's ESPN wallclock to (a) our feed learning it (first_seen_at) and (b) the winner-market mid completing its signed move (window −30s to +60s around wallclock; move >=1c).

| | pilot (2 games / 36 moves) | full (16 games / 328 moves) |
|---|---|---|
| feed lag p50 | 36.7s | 36.4s |
| move complete at feed time, p50 | 100% | 100% |
| per-game median, minimum | — | 83% |
| moves >=half done by feed time | 83% | 83% |

**Provenance of the two p50s:** 36.7s appears in pulse-reversion-shrink.md's commentary because it was the only measurement when that page was written; 36.4s is the full-sample figure. Both were accurate when written — an estimate sharpening under 8x the data, not a drift. Cite 36.4s (16 games) going forward; do not "correct" the older page.

**The bound:** the market reprices from the broadcast within seconds; our feed learns the play ~36s later, after the move is complete. STATE-based prediction (what the game is) survives. EVENT-reaction (what just happened) is structurally dead at this feed, and accruing more signal data never changes that — the half-minute lives in ESPN's pipeline. Mechanism note: this is also why in-game maker fills carry the measured 4.70c concession — a resting order quotes against people half a minute ahead.

**The fade caveat (do not re-derive):** #1 and #2 (the fade family) are closed on their own pre-registered numbers, and a faster feed would NOT revive them. A fade's premise is that the completed move is WRONG; F8's "move complete by feed time" is the fade's precondition, not its obstacle. The fades died because completed moves were right — prices reprice, they don't panic (ledger #1/#2). The bound kills reaction-speed CHASING strategies; the fade family was killed separately, by the market being correct.

**Reproduction:** scratchpad survey/f8_full.py, run 2026-08-25 against the local mirror (espn_live_* synced to parity) plus backups/exports/live_snapshots_since0820.csv.gz. 6,821 plays, 0% junk wallclock stamps.

---

*Measured and written by the research agent. Landed by Builder D, who computed
nothing. Transcription note: `>=` and `<=` arrived HTML-escaped by the message
transport and are restored to the characters the draft was written with; nothing
else was altered.*
