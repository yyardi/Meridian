# PULSE tape diagnostics — the why behind every trade

**DESCRIPTIVE. NO VERDICT, NO GATE.**

Every number here was computed *after* seeing the tape, which is exactly what a
pre-registration forbids as evidence. The registered PULSE verdict arms at its
own floor and **nothing on this page may feed it**. Same standing as
[`core/audit/hand_trades.py`](../../core/audit/hand_trades.py): a report, not a
finding.

Produced by [`core/pulse/diagnostics.py`](../../core/pulse/diagnostics.py).
**Run:** `pulse_decisions_20260822.csv`, 846 in-play rows, exported 15:05Z
2026-08-22, read from the off-prod eval copy. The tape grows tonight; this page
describes that export and nothing later.

---

## 0. A decision is not a position

The brief, and the framing everywhere else, treats 116 entries as 116 trades.
They are not. An entry is an *intent* — a limit order resting at the touch —
and most of the interesting behaviour is in whether it was ever hit.

| | |
|---|---|
| entries decided | **116** |
| — filled | **63** (54%) |
| — never filled | **53** (46%) |
| of the filled: exited | 43 |
| of the filled: **rode to settlement** | **20** |
| exit rows | 74 (across 45 entries — some repriced) |

**This corrects the brief's "42 of 116 entries never exited".** The real tail is
**20 of 63 filled positions**. The 42 conflates orders that never became
positions with positions that never exited. Every money figure below is over
the **63 filled** entries; a rate over 116 counts orders that never existed.

**46% of intended entries never fill** is arguably the larger finding, and it is
not an exit-policy question at all.

---

## 1. Exit policy anatomy

Money at price (C11): a YES contract costs the price paid, a NO contract costs
`1 - price`. Verified against the tape's own `stake_usd`.

| path | n | staked | returned | net | ROI |
|---|---|---|---|---|---|
| profit_target | 34 | $27.06 | $30.70 | **+$3.65** | **+13.5%** |
| rode_to_settlement | 20 | $13.58 | $9.93 | **−$3.65** | **−26.9%** |
| fv_adverse | 9 | $5.01 | $3.34 | −$1.67 | −33.4% |
| **total** | **63** | **$45.65** | **$43.97** | **−$1.68** | **−3.7%** |

**The hypothesis the brief asked to expose is visible in the arithmetic.** The
profit target produces 34 winners at +13.5%, and the 20-position settlement tail
returns **−$3.65 against the target's +$3.65** — to the cent, on this export.
The tail does not merely dilute the target's gains; it cancels them, and the
stop takes the rest.

That symmetry is a coincidence of this sample size, not a law. What is not a
coincidence: a fixed profit target truncates winners and leaves losers running
to settlement, which is the shape every one of these three rows shows.

### Counterfactual targets — NOT RUN, and why

The brief asked what the tail would look like at 3%, 5%, 8% and 10%. **That is
not computed here.** It requires replaying each position against the recorded
ticks, and **four of the nine taped games have zero tick coverage** in the eval
copy — verified per game, not assumed. Those four carry **74 of the 116
entries**, so the counterfactual would silently have covered 36% of the tape.

The missing games are named in §5. **This is not a tuning exercise and will not
become one**: any change to the live profit target requires its own
registration, written before the number is computed.

---

## 2. Trade distribution

**Spread-heavy, and front-loaded.**

| market type | decided | filled | fill rate |
|---|---|---|---|
| spread | **96** (83%) | 56 | 58% |
| winner | 14 | 5 | 36% |
| total | 6 | 2 | 33% |

| period | decided | filled | fill rate |
|---|---|---|---|
| Q1 | **50** | 26 | 52% |
| Q2 | 24 | 14 | 58% |
| Q3 | 23 | 9 | 39% |
| HT | 12 | 10 | **83%** |
| Q4 | 7 | 4 | 57% |

Entries cluster early — Q1 alone is 43% of them — and thin out toward the
endgame, which is the opposite of where the operator's own hand trading lives.
Halftime fills best (83%) and Q3 worst (39%).

Per game, entries range 1–27 across 9 games and 5–8 markets per game, so
concentration is real but not extreme: the three 08-21 games carry 65 of 116.

---

## 3. Edge → outcome

The pregame model's killer diagnostic (−0.069 edge/outcome correlation) applied
in-game. **Three of six buckets report NO DATA** rather than a shape from a
handful of fills.

| claimed edge | decided | filled | realised ROI |
|---|---|---|---|
| 0–5% | 21 | 6 | **NO DATA** |
| 5–8% | 32 | 19 | −7.8% |
| 8–10% | 22 | 15 | +22.1% |
| 10–15% | 27 | 18 | −26.1% |
| 15–25% | 9 | 5 | **NO DATA** |
| 25–100% | 5 | **0** | **NO DATA** |

Where there is data the ordering is **non-monotonic** — the middle bucket is the
only positive one, and the largest measured bucket is the worst. On n=15–19 per
bucket that is as consistent with noise as with a real shape, and no correlation
is quoted here because three buckets are empty.

**The clearest signal is in the fill column, not the ROI column.** The five
entries claiming 25%+ edge produced **zero fills**. The biggest claimed edges
are the ones the book never trades through — the signature of adverse selection,
which failed its own gate at −2.66¢ per filled quote.

---

## 4. What the bankroll decided, not the model

**The brief's framing needs one correction.** `binding_constraint` names what
*set the size* of an entry, not what refused it. Rows annotated
`below_minimum_trade_qty` were still placed and 14 of 24 still filled — the
venue minimum pushed their size **up**, it did not suppress them.

| binding constraint | entries | filled | desired stake |
|---|---|---|---|
| max_game_exposure_pct | **40** | 25 | $36.13 |
| kelly | 39 | 17 | $18.13 |
| below_minimum_trade_qty | 24 | 14 | $21.49 |
| max_daily_exposure_pct | 7 | 3 | $1.97 |
| max_position_size_pct | 6 | 4 | $6.94 |

All 116 entries carry exactly one constraint, and the categories sum to 116.

So the honest answer to "what fraction of intent is invisible because the
bankroll is $23": **on this tape, none of it is invisible** — every constrained
entry was still placed. What the bankroll changes is *size*, and the largest
sizing authority is not the venue minimum but `max_game_exposure_pct` (40
entries, $36.13 of desired stake), which is our own risk cap rather than the
venue's floor.

> **Two of the brief's cap figures do not match this export.** The brief states
> 18 `max_game_exposure_pct` and 3 `max_position_size_pct`; this export has 40
> and 6. `below_minimum_trade_qty` matches exactly at 24, and the categories sum
> to the entry count, so the export is internally coherent. The brief also omits
> `kelly` (39) and `max_daily_exposure_pct` (7). Likely a stale or filtered
> count on the brief's side; flagged rather than reconciled silently.

---

## 5. What this page does not cover

* **The counterfactual targets** (§1). Per-game tick coverage in the eval copy,
  checked rather than assumed:

  | game | entries | live ticks |
  |---|---|---|
  | `wnba-por-tor-2026-08-21` | 27 | **0** |
  | `wnba-min-wsh-2026-08-21` | 22 | **0** |
  | `wnba-gsv-chi-2026-08-21` | 16 | **0** |
  | `wnba-ind-dal-2026-08-20` | 9 | **0** |
  | `wnba-tor-wsh-2026-08-19` | 12 | 644,129 |
  | `wnba-min-gsv-2026-08-19` | 8 | 663,942 |
  | `wnba-ind-tor-2026-08-18` | 11 | 316,655 |
  | `wnba-la-conn-2026-08-18` | 10 | 296,078 |
  | `wnba-ny-chi-2026-08-18` | 1 | 280,245 |

  **Four** games are missing, not the three the brief predicted —
  `wnba-ind-dal-2026-08-20` is absent too, despite eval's snapshots running
  through 08-20. Together they hold 74 of 116 entries.
* **Tonight's three games**, which cross the registered 10-game floor. This page
  describes a 9-game tape and will be re-run against the floor-crossing export.
* **Anything resembling a verdict.** The registered measurement is elsewhere and
  must stay uncontaminated by everything above.
