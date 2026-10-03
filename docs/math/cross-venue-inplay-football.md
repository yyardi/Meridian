# Polymarket vs Kalshi in play, football, at message cadence — registered before the weekend

2026-10-02. `docs/math/cross-venue-status.md` (09-04) left the in-play cross-venue gap
UNMEASURED: Kalshi was sampled every 120 s against a streaming Polymarket, and the five
instants that cleared 2¢ were one game at sub-second lag. The BTC work since then measured
the same pair on a contract both venues price off one index, at message cadence on both
sides, and found a 0.4¢ median same-second gap — pro makers keep them aligned there. Football
in play is a different population: the information is the game, both venues' books move on
it, and whether one moves first by more than the fees has never been measured at the right
cadence. This weekend it is.

## Instrument

* Polymarket: the slate stream recorder as every weekend (`cfb/run_stream_slate.py`, books and
  prints per game under `reads/stream/<tag>`), installed by the 12:10Z scheduler.
* Kalshi: `core/kalshi/book_recorder.py` via `scripts/launchers/launch_kalshi_slate.sh` —
  the LIP scorer's signed socket, `orderbook_delta` + `trade` for every open market of
  `KXNFLGAME`/`KXNFLSPREAD` (Sunday, 14 games) and `KXNCAAFGAME`/`KXNCAAFSPREAD` (Saturday,
  108 games) carrying the slate's date tag, every message raw with its receive stamp under
  `reads/kalshi/<tag>`. Both recorders stamp with the same box's clock.
* Matching: NFL by the two code tables (`core/kalshi/mapping.KALSHI_TO_ESPN_NFL`,
  `core/team_mapping`) through ESPN abbreviations and the game date; winner = Kalshi's
  `-<TEAM>` market against Polymarket's winner YES/NO by which team is away (YES is the away
  team on Polymarket US); spreads where the lines coincide, Kalshi "TEAM wins by over L"
  against the Polymarket rung ±L oriented the same way. CFB joins are attempted second and
  reported separately; a pair whose orientation cannot be established from both tables is
  dropped, not guessed.

## The read, written before any tape exists (run once, Monday 2026-10-05, on the two tapes)

For each matched contract, each book change on either venue is an instant; the other venue's
state at that instant is its last message ≤ 1 s earlier (an older state is "stale", excluded
from the gap statistics and counted).

1. **Gap.** Net gap at displayed size = the cheaper venue's displayed ask vs the dearer venue's
   displayed bid for the same outcome, minus both venues' taker fees at those prices (Polymarket
   0.0695·p(1−p); Kalshi `quadratic_with_maker_fees`, 0.07·p(1−p) rounded up to the cent per
   contract). Report, per league: the share of instants with net gap ≥ 1¢, the median and 90th
   percentile life of those episodes, the dollars at displayed size (min of the two sides),
   and how many games carry 80 % of the dollars.
2. **Lead.** For 1, 2, 5 and 10 s horizons: corr(venue A's mid change over the last horizon,
   venue B's mid change over the next horizon) and the reverse, per league, with a game-cluster
   SE. The venue whose past predicts the other's future leads; symmetric ≈ 0 means neither.
3. **The rule.** If a lead exists: a taker on the lagging venue at its displayed touch whenever
   the leader has moved by more than the round-trip fees, held 60 s and marked to the lagging
   venue's mid — mean per fill, n, game-cluster 95 % CI, counted ONLY on instants where the
   lagging venue's displayed size covers one contract and the quote is ≤ 1 s old.

**What deploys.** A paper arm on next weekend's slate stream, zero credits, only if 3 is
positive with the cluster CI excluding zero on ≥ 10 games and the dollars in 1 are not 80 %
in two games. Anything else closes cross-venue in-play football in one line, and that line
goes next to the 09-04 "unmeasured" verdict. No number from a replay is a result; the read
chooses what runs live.

## Capacity note, stated first

Kalshi's displayed depth on NFL winners is large (DET–CAR showed five- and six-figure
contract counts a level on 10-02); Polymarket's in-play books are thinner. The binding size
will be Polymarket's, and the read says so by reporting min-of-two-sides dollars.
