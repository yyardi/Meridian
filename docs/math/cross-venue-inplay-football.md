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

## The read, run — 2026-10-07, about 38 hours late

Registered for Monday 2026-10-05 14:00Z; run 2026-10-07 ~04Z because its scheduled job died
with a closed session. Same tapes, nothing re-recorded: the archive copy of `reads/` taken
10-07 00:40Z, byte-identical to prod in file count and total size for all four NFL
directories. Script `analysis/cross_venue/inplay_football_read.py`, tests
`tests/test_cross_venue_inplay_football.py` (`--noconftest`). A replay of recorded books is a
measurement of what the two venues displayed, not a result.

**Verdict: CLOSED.** Kalshi leads Polymarket by 1–2 s, but the registered taker rule on the
lagging venue measured **−0.94¢ per fill, 95 % CI [−1.07, −0.80], n = 18,974 fills on 13
games**, and as registered the gap dollars are 80 % in two games. Neither deploy condition
holds. The line is beside the 09-04 verdict in `cross-venue-status.md`.

The registered numbers did not move across the three runs. The second and third runs only
added the columns marked "diagnostic" below, after the first output showed the Polymarket
backlog (defect 2).

### Population

* Polymarket: `reads/stream/nfl-10041320`, `nfl-10041955`, `nfl-10050010` (26 book files,
  13,879,420 rows read). Two slate recorders overlapped 19:56–20:47Z on the early games;
  333,461 cross-recorder duplicates (same transactTime, same touch) were dropped.
* Kalshi: `reads/kalshi/nfl-1004`, 386 tickers (`KXNFLGAME` + `KXNFLSPREAD`, tag 26OCT04),
  2,719,834 touch lines. Socket sequence gaps 0, reconnects 0.
* `nfl-10050010` is the **Sunday** night game (DET@CAR, kick 10-05 00:20Z). It is paired.
  The **Monday** night game (ATL@NO, kick 10-06 00:15Z) is `stream/nfl-10060005`. **No
  Kalshi tape exists for it** because the 26OCT05 recorder never ran, so MNF is
  Polymarket-only and drops out of the pairing.
* Matching: all 386 of 386 Kalshi markets paired to a Polymarket market through ESPN
  identity. Kalshi codes go through `KALSHI_TO_ESPN_NFL`; Polymarket codes go through an
  explicit 32-team table in the script, because `core/team_mapping` holds WNBA only. 0 were
  dropped for orientation. ESPN's away team equals the slug's first team on 14 of 14 games.
  1 Kalshi rung has no Polymarket rung (BAL by over 11.5).
* IND@WSH was the London game (in play 13:32–16:40Z). Kalshi's recorder started at
  16:40:12Z, so its 29 contracts have no in-play overlap.
* In play means ESPN's first play to last play by wallclock. That leaves **13 games and 356
  contracts**: 26 winner pairs (each Kalshi team market against the one Polymarket winner)
  and 330 spread pairs.
* Orientation, checked on values: the median |Polymarket mid − Kalshi mid| per contract over
  evaluable instants was p50 0.75¢ and max 1.25¢ across 355 contracts. A flipped side would
  sit |1 − 2p| apart.
* The control test's four recorded fixtures (winner and spread, sign ±1) all fail when
  `orient` is inverted. This was checked by mutation.

### Tape cadence and validity, before any number

| in play, gap between rows | p50 | p90 | p99 | share ≤ 1 s |
|---|---:|---:|---:|---:|
| Polymarket, all rows, winners | 0.10 s | 0.40 s | 1.3 s | 98 % |
| Polymarket, all rows, spreads | 0.11 s | 0.78 s | 5.1 s | 92 % |
| Kalshi touch lines, winners | 0.34 s | 1.24 s | 4.3 s | 86 % |
| Kalshi touch lines, spreads | 0.47 s | 4.12 s | 24 s | 69 % |

A Kalshi line is written only when the touch changes (coalesced to 250 ms; 8.84 M changes
in 2.72 M lines). A 4-s gap on a spread is therefore a quiet book, not an absent one. The
registered ≤ 1-s rule still marks Polymarket-driven instants against such a book as stale:
that is 1,155,759 of the 1,338,463 stale instants.

The tapes have three defects. Each one is excluded and counted:

1. **Kalshi ghost levels.** `core/kalshi/lip_scorer.Books` drops a level only when its float
   size reaches ≤ 1e-9. A level of 10^6–10^7 contracts cancelled to zero leaves a float
   residue above that, and the residue stays as the displayed best with size 0.00.
   * 185,705 of 2,719,834 touch lines (6.8 %) are crossed or locked, and every one of them
     carries a side under the venue's 0.01 size resolution. Crossed lines with both sides
     ≥ 0.01: 0. The worst market is DET winner, with 24,002 of 27,673 lines.
   * In play this costs 517,173 instants. On winners it is 451,596 of 1,310,579 (34 %).
   * The true level behind a ghost is not on the tape, so the instant cannot be repaired.
2. **Polymarket stream backlog.** Receive time minus the venue's own transactTime, over all
   10,383,899 in-play rows: p50 68 ms, p90 133 ms, p99 1.24 s, max 102 s.
   * 1.24 % of rows are over 1 s late: about 2 % on the 17:00Z games, about 0.1 % later.
   * In a backlog the stream delivers books that are seconds old on fresh receive stamps,
     so the registered receive-stamp freshness check passes them.
   * **869 of the 1,575 registered gap instants (55 %) carried Polymarket content more than
     1 s old** (p50 2.3 s).
3. **Kalshi coalescing.** One touch line stands for up to 250 ms of changes and is stamped
   at the last of them. A state shown for less than 250 ms may already have changed on the
   venue.

### 1. Gap

Definitions:
* **Instant:** a touch change (prices or sizes) on either venue, in play.
* **Other venue's state:** its last message ≤ 1 s earlier on our receive clock. Both books
  must be two-sided and valid.
* **Net gap:** dearer bid − cheaper ask on the same outcome, minus Polymarket's fee
  0.0695·p(1−p) and minus Kalshi's fee ⌈0.07·p(1−p)⌉ rounded up to the cent.
* **Episode:** consecutive qualifying instants in one direction. Its life runs to the first
  instant that breaks it.
* **Dollars:** the smaller displayed size of the two legs × net gap, per episode, taken at
  its first instant and at its peak instant, then summed.

The right column is the diagnostic: it also requires Polymarket's book content to be ≤ 1 s
old by its own transactTime.

| 13 games, 356 contracts | as registered | + Polymarket content ≤ 1 s (diagnostic) |
|---|---:|---:|
| instants | 6,275,286 | same |
| stale / Kalshi invalid / Polymarket invalid | 1,338,463 / 584,511 / 40,737 | same |
| evaluable | 4,346,600 | 4,279,266 |
| **net gap ≥ 1¢** | **1,575 (0.036 %)** | 706 (0.016 %) |
| winners, spreads | 286 (0.041 %), 1,289 (0.035 %) | 72, 634 |
| episodes (games) | 640 (13) | 522 (13) |
| **life p50 / p90** | **0.084 s / 0.95 s** | 0.069 s / 0.16 s |
| episodes lasting ≥ 250 ms / ≥ 1 s | 120 / 63 | 26 / 2 |
| **dollars, first instant / peak** | **$3,969 / $7,732** | $1,366 / $2,335 |
| peak dollars in episodes ≥ 250 ms | $5,421 | $34 |
| **games carrying 80 %, first / peak** | **3 / 2** | 5 / 4 |
| largest game, peak dollars | DAL@HOU $5,902 (76 %) | DAL@HOU $799 |

* DAL@HOU's two largest episodes ($2,526 and $2,510 peak) fall at 19:37:34–39Z, when the
  Polymarket content was 8–11 s old. Kalshi's HOU bid fell from 0.41 to 0.31 between
  19:37:28 and :38. The Polymarket books delivered at those receive times had been
  transacted 7–11 s earlier. Those episodes are the backlog, not a price.
* Sensitivity (diagnostic): drop the ≤ 1-s rule entirely and keep the content check. Both
  tapes are written on change and Kalshi's socket had no sequence gap. The result is 720
  qualifying instants out of 5,226,461, with peak dollars the same $2,335. The staleness
  rule is not what the answer turns on.

**Spot check, one row a reader can reproduce.** The pair is DEN@SF, Kalshi
`KXNFLGAME-26OCT04DENSF-SF` against `aec-nfl-den-sf-2026-10-04`. The Kalshi market pays if
SF wins. SF is the slug's second team, so the sign is −1 and the matching Polymarket side is
NO (Polymarket's YES is Denver). The instant is a Polymarket change at
2026-10-04T20:58:39.954Z:

```
poly   {"recv":"2026-10-04T20:58:39.954+00:00","slug":"aec-nfl-den-sf-2026-10-04","line":0.0,"bid":0.5225,"ask":0.525,"bid_size":1143.46,"ask_size":1664.45,"tt":"2026-10-04T20:58:39.931331653Z","state":"MARKET_STATE_OPEN"}
kalshi {"recv":"2026-10-04T20:58:39.703Z","type":"touch","yes_bid":0.55,"yes_bid_size":1111.27,"no_bid":0.44,"no_bid_size":2503.65,"changes":2}
```

* **Freshness:** the Kalshi state is 0.251 s old, so it passes the ≤ 1 s rule. The
  Polymarket content is 23 ms old.
* **Books on outcome SF:**
  * Kalshi: bid 0.55 × 1,111.27, ask 1 − 0.44 = 0.56 × 2,503.65.
  * Polymarket: bid 1 − 0.525 = 0.475 × 1,664.45, ask 1 − 0.5225 = 0.4775 × 1,143.46.
* **The trade:** buy SF on Polymarket at 0.4775 and sell it on Kalshi at 0.55. That is
  7.25¢ gross, minus Polymarket 0.0695 × 0.4775 × 0.5225 = 1.734¢, minus Kalshi
  ⌈0.07 × 0.55 × 0.45 = 1.7325¢⌉ = 2¢. **Net 3.516¢**, × min(1,143.46, 1,111.27) =
  **$39.07**.
* **Life:** the next instant is Polymarket at :40.055, where the SF ask is 0.505 and the net
  falls to 0.76¢. The episode lived 101 ms.
* **Why it is not a price anyone could take:** both books whipsawed that second. Kalshi SF
  went 0.51 → 0.55 at :39.468, then → 0.48 at :40.064, and that last line coalesces 53
  changes. This is defect 3: a measured instant only.

### 2. Lead

Estimator:
* A 1-s grid inside each game's in-play window.
* An as-of mid per venue, NaN wherever the current book is invalid.
* x = A's mid change over [t−h, t]; y = B's mid change over [t, t+h].
* Pooled Pearson r over the 356 contracts.
* Game-cluster SE by the influence-function sandwich, and again by a 2,000-draw game
  bootstrap. The two agree within 0.001.

| h | Polymarket past → Kalshi next | Kalshi past → Polymarket next |
|---|---:|---:|
| 1 s | 0.060 ± 0.007 | **0.132 ± 0.011** |
| 2 s | 0.061 ± 0.007 | **0.140 ± 0.013** |
| 5 s | 0.043 ± 0.009 | 0.117 ± 0.010 |
| 10 s | 0.027 ± 0.013 | 0.089 ± 0.010 |

* Each cell has about 3.38 M grid pairs on 13 games. Kalshi leads, and the lead is
  strongest at 2 s.
* Diagnostic: placing the Polymarket rows at the venue's transactTime instead of our receive
  time gives Kalshi → Polymarket 0.120 at 1 s and 0.131 at 2 s, and Polymarket → Kalshi
  0.066 and 0.063. The lead is not our feed's delivery delay.
* The tick grids differ (Kalshi 1¢, Polymarket 0.25–0.5¢). Part of an asymmetry at 1–2 s
  can therefore be Polymarket stepping through cents that Kalshi jumps in one move. Rule 3
  is what decides.

### 3. The rule (Kalshi leads, so it ran, with h = 2 s)

Estimator:
* **Trigger:** at each Kalshi touch change in play (from 2 s after the first play to 60 s
  before the last), take Kalshi's mid change over the last 2 s. It must exceed Polymarket's
  round-trip taker fee at Polymarket's touch (the fee at its ask plus the fee at its bid).
* **Trade:** take the Polymarket touch in that direction.
* **Conditions:** Polymarket's last message is ≤ 1 s old, its book is valid, and its
  displayed size on that side is ≥ 1 contract.
* **Position:** one per contract at a time, held 60 s and marked to Polymarket's mid. The
  entry fee is paid; the exit is neither crossed nor charged.
* **Statistic:** mean per fill with a game-cluster 95 % CI using t(12). The bootstrap
  duplicate is in brackets.

| | n fills | games | mean per fill | 95 % CI |
|---|---:|---:|---:|---|
| **all** | **18,974** | **13** | **−0.94¢** | **[−1.07, −0.80]** (boot [−1.05, −0.82]) |
| winners | 560 | 13 | −0.42¢ | [−0.77, −0.08] |
| spreads | 18,414 | 13 | −0.95¢ | [−1.09, −0.81] |
| Polymarket content ≤ 1 s (diagnostic) | 18,636 | 13 | −0.96¢ | [−1.10, −0.82] |

* Per fill, the lagging mid did move the leader's way: +0.68¢ over 60 s. Against that, each
  fill paid 0.82¢ of half-spread and 0.80¢ of fee at entry.
* Triggers skipped: 5,196 for size under 1, 1,588 for a stale Polymarket book, 1,337 for an
  invalid one, and 1,472 that could not be marked at +60 s.
* The replay fills at the displayed touch with no queue and no latency, which flatters a
  taker. It is negative anyway.

### Decision, as registered

Rule 3 is negative, with its interval excluding zero, on 13 games: **no paper arm.** As
registered, the dollars in read 1 are also 80 % in two games; DAL@HOU alone carries 76 %, and
most of that is the backlog. **Cross-venue in-play football closes.**

### CFB, second, reported separately — 0 games matched

* **Tapes.** Kalshi `reads/kalshi/cfb-1003` has `KXNCAAFGAME` only (winners; spreads were
  never taped): 216 markets on 108 games, tags 26OCT03–04. Polymarket
  `stream/cfb-10031450`, `-10031850` and `-10032250` have 85 games.
* **Why nothing pairs.** Orientation must come from both code tables, and neither exists in
  usable form:
  * `KALSHI_TO_ESPN_NCAAF` maps every code to None on purpose. 214 markets drop there, and 2
    more have keys that do not split.
  * There is no Polymarket CFB code table (85 games). Its slug codes are a fourth code space,
    e.g. `aubrn`, `boscol`, `mspst`.
* **What a guess would do.** Exact string coincidence of both codes on the same date would
  pair 13 games. One of them is already suspect: Kalshi's CHS is Chicago St., and nothing
  says Polymarket's `chs` is. These are counted, not used.
* CFB in play stays unmeasured until a verified college code table exists on both sides.

### Not fixed here

* The `lip_scorer.Books` ghost level. The LIP scorer reads the same `Books.side()`, so its
  touch carries the ghost too. The fix is to pop a level when its size rounds to 0.00.
* The recorder's 250-ms coalescing. Any read about sub-second episodes needs the raw deltas
  (`--raw`).
