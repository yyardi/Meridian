# Cricket — pre-registration, written before a single price is looked at

2026-09-14. Registers how the operator's claim will be tested, **before** any
cricket price is examined and before any model exists.

---

## 1. The claim, split — because the halves have different evidential weight

The operator's account: the cricket markets are presented wrongly, people bet
badly as a result, and England v Sri Lanka was taken pregame at even money on
cricket knowledge and moved to eighty within minutes, before a ball was bowled.

**Half A — "the price was wrong at fifty."** This rests on being right about
England. **One correct call at even money is `p = 0.50` against a coin. That is
not weak evidence; it is no evidence.** At a true 60% hit rate a demonstration
needs **154 calls** (80% power, one-sided 5%); at 65%, 69; at 55%, 618. **Half A
cannot be settled by this programme and will not be attempted.**

**Half B — "it moved thirty cents before a ball was bowled."** This is
measurable from our own tape, needs no cricket knowledge and no model, and is
**the half that survives if the model turns out to be wrong.** It is registered
below and is reported first.

---

## 2. ⚠ THE TOSS — the reason a naive wander comparison would be invalid

**Cricket has a scheduled, major pregame information event that football does
not: the toss**, typically ~30 minutes before play. Batting first versus chasing
is worth real win probability, and more on some pitches than others.

> **A pregame move is not "no new information" if the toss happened inside the
> window.** A thirty-cent move across the toss may be perfectly efficient.

**We already record it.** `espn_cricket_events` writes a row on every observed
change of state/period/**toss**/innings/winner, stamped with our observation
instant.

> **REGISTERED: every pregame window is split at the toss. Pre-toss movement is
> candidate-inefficiency; post-toss movement is information and is reported
> separately, never pooled.** A match whose toss time is unknown is excluded and
> counted, not silently assigned.

Without this split the comparison against football is invalid **by
construction**, because the comparator has no equivalent scheduled event.

---

## 3. The primary measurement is REVERSION, not magnitude

Movement magnitude alone cannot distinguish "soft" from "informative". A price
that moves thirty cents and **sticks** has learned something. A price that moves
thirty cents and **reverts** is noise somebody could have faded.

> **PRIMARY, and it needs no comparison league at all: is the late pregame price
> better calibrated than the early one?**
>
> Score `p(T−1h)` and `p(T−6h)` against the settled outcome by Brier and by log
> loss, on the same matches, pre-toss only. **If the late price is better, the
> movement is information and the space is not soft. If it is not better, the
> movement is noise** — and noise that large is the operator's claim, established
> without anyone's cricket knowledge.

### ⚠ AMENDED 2026-09-14 — the T−6h anchor can land in a venue listing gap

**Measured today: the venue's board was empty from 09:35:26Z to 11:40:59Z — 2h05m,
a mid-morning roll, not an incident** (it returned before the MLB slate, and
zero-hours peak at 10–11Z historically).

**For a 17:30Z kickoff — `aec-t20icr-eng-slr-2026-09-15`, a standard afternoon-UTC
start — `T−6h` is 11:30Z, inside that gap.** `T−1h` (16:30Z) is clear.

> **REGISTERED: the anchor is THE LAST QUOTE AT OR BEFORE T−6h, its realised
> offset is reported per match, and the exclusion threshold is named HERE,
> before any price is looked at:**
>
> **The realised early anchor must lie in [T−9h, T−6h] — a tolerance of 3 hours.
> Outside it the match is EXCLUDED AND COUNTED. A match with no quote at or
> before T−6h at all is excluded and counted separately.**
>
> **Why 3 hours, rather than a number chosen later:** it absorbs the measured
> 2h05m gap with ~55 minutes of margin, and it keeps the early anchor at least
> 5 hours before the late one (T−1h) so the contrast stays wide. Both halves are
> properties of the design, not of any result.
>
> **Why it must be named now:** an unnamed tolerance is a tuning knob. **A match
> that anchors badly AND disagrees with the hypothesis is easier to exclude than
> one that anchors badly and agrees**, and nobody making that call would
> experience it as a choice.

Without this the measurement would drop or mis-anchor **precisely the
afternoon-start matches, which are most of the ODI and T20I slate** — a
selection correlated with format, not with noise. The same rule was already
registered for table tennis staleness; it costs nothing to apply here.

This is the measurement that decides whether a model is worth building.

## 4. The wander comparison — with TWO comparators, not one

Secondary, and comparative. **Naming one comparison league confounds thinness
with inefficiency**: cricket is thin, and a thin market wanders for reasons that
have nothing to do with mispricing.

> **REGISTERED COMPARATORS, named in advance: NFL (liquid, deep, presumed
> efficient) AND table tennis (thin, and already measured — 1¢ spreads, 8-minute
> sweep, attenuation slope +0.00007/min).**
>
> - cricket ≈ NFL → no anomaly.
> - cricket ≈ table tennis, both > NFL → **thinness**, not cricket.
> - cricket > both → **specific to cricket**, and that is the finding.

**Matched on:** a common window measured backwards from each market's own start
time, and reported **within matched spread bands**, because spread is the
liquidity proxy we have and an unmatched comparison measures it instead.

---

## 5. Coverage gate — checked FIRST, and the honest answer may be "not yet"

### MEASURED 2026-09-14 — both gates fail

**Gate 1, market tape: 17 markets, 17 games, 136 rows, all from the last ~2
days** (county 9, t20icr 3, t20iwcr 2, cplcr 2, odicr 1).

> **But 15 of the 17 have NOT STARTED** (ko 09-15, 09-16) — the forward-listed
> board again. **Only 2 matches are settled**, both thin: 4 quotes over a
> 0.5–1.6h pregame span. **Against a registered minimum of 30, we have 2.**

**Gate 2, toss: `espn_cricket_events` is EMPTY — zero rows. No toss time exists
for any cricket match.**

`meridian-cricket-espn-recorder` **does not exist on the box.** The venue-side
`meridian-cricket-recorder` is up and writing; the ESPN one was never started.
Its compose header reads *"Deploy stays operator-gated"* and states its purpose
as *"so the venue's price move around the toss can be measured"* — this
measurement exactly.

> **⚠ Toss times CANNOT be backfilled — they are only observable live. Every day
> that recorder is down is a day of matches permanently unusable for §2.**

### Two findings that bound what any amount of tape can deliver

**Cadence.** Quotes arrive ~30–60 minutes apart, with a measured **5.4-hour hole**
(09-13 23:57 → 09-14 05:20). **A 30–60 minute cadence cannot resolve a move that
happens "within minutes."** The 6-hour wander window (§3, §4) is measurable at
this cadence; *"thirty cents in minutes"* is not, at any n. **Testing the claim
as the operator phrased it requires a tennis-like cadence and is a different ask
from this registration.**

**The operator's own example, and our tape starts after the move.**
`aec-t20icr-eng-slr-2026-09-15` (ko 09-15 17:30Z): **all 9 quotes sit between
75.5¢ and 78.5¢** from 09-13 22:23 onward — **a 3¢ range, not 30¢.** The market
was already at ~77 when recording began, so **any move predates our first
quote.** Consistent with the account; **not independent confirmation.**

**And the spread is 1¢** (0.77 / 0.78) — as tight as Kalshi tennis. **Tight
spreads are not what a neglected market looks like**, and that is worth knowing
before a model is built on the assumption that it is.

> **REGISTERED: the wander measurement requires a pre-declared minimum of
> matches with (a) a pregame close, (b) a second pregame quote at least four
> hours earlier, and (c) a known toss time. Below that minimum the deliverable is
> "we do not have the tape", stated as such and dated.**
>
> **Minimum: 30 matches.** At n=30 a Brier difference between the early and late
> price is detectable only if it is large; below that nothing is readable and a
> model built on it would be fitted to noise. **A model on six rows is not a
> smaller version of the right answer — it is a different and wrong one.**

---

## 6. The model, if and only if §5 passes and §3 says the space is soft

**Why Monte Carlo is the right instrument here, and worth stating:** a cricket
match is a sequence of discrete states with well-understood transitions — wickets
and overs remaining — and the resource-remaining framework is public and
long-established. **A simulation can therefore produce a fair value that does not
depend on fitting our own price history, which is exactly what makes it capable
of disagreeing with the venue.**

> **REGISTERED: fit to ball-by-ball outcomes from ESPN Cricinfo. NEVER to venue
> prices. A model fitted to the prices it is meant to judge cannot find them
> wrong** — it can only reproduce them and call the reproduction agreement.

---

## 7. Traps

1. **The toss** (§2). The single largest threat to the headline.
2. **Thinness masquerading as inefficiency** (§4). Two comparators, matched
   spread bands.
3. **⚠ Team identity.** A prior session recorded that the venue's **"ENG v SL"
   was England *Lions*** — a development XI, not the senior side. **If that
   holds it is direct evidence FOR the operator's "presented wrongly" claim, and
   simultaneously a caution about this particular trade**, since a call made on
   knowledge of the senior side would have been pricing a different team.
   **Verify against the venue's own market metadata before either use.**
4. **Draws settle at 0.5.** `core/settlements.py` records that first-class
   cricket (`county`) can be drawn and the venue settles a draw at a half.
   **Any binary treatment of cricket settlement is wrong**, and code that tests
   `v in (0, 1)` discards draws silently.
5. **Survivorship in the pregame window.** A match only has an early quote if it
   was listed early. If listing time correlates with anything, the surviving
   sample is selected — report `mins_before` per match, as registered for table
   tennis.
6. **One correct call** (§1). Not to be re-introduced as supporting evidence
   once the measurement is in hand.

---

## 8. Reporting order, which is not negotiable

1. **Coverage** — how many matches qualify. If below 30, stop and say so.
2. **Reversion** (§3) — is the late price better calibrated than the early one?
3. **Wander versus both comparators** (§4).
4. **Only then**, and only if 2 and 3 warrant it, the model.

**The wander and reversion results survive a wrong model. A model reported first
would contaminate them**, because nobody re-reads a calibration table after
they have seen a fair value.
