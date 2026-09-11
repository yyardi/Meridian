"""Input-validity and output-sanity guards for the PULSE estimate.

Why this module exists (Track C's calibration, `analysis/fv-calibration-report
.md`, CORRECTION section): at claimed confidence >=0.98 the model missed 22 of
389 rows while the market missed 0 of 170, and row inspection named mechanisms,
not noise — corrupted clock/score states priced as certainty, and a Gaussian
tail asserting 0.0000/1.0000 in regimes it cannot represent (foul game,
overtime, half-length extrapolation).

These guards do NOT change any fair-value math. They refuse to price a state
(guard 1) or refuse to emit an unrepresentable certainty (guard 2). A refusal
ABSTAINS: the engine does not price, does not enter, and records why in
`pulse_abstentions` — a state we refused to price is data; a state that
silently vanishes is not (the `binding_constraint` precedent).

Deliberately flag-independent: `minutes_left_is_estimate` exists only on v1
rows (v3/v4 read the venue clock by construction), so any flag-keyed guard
would harden a version that no longer prices — and the worst recorded miss
(sea-dal, P=1.0000) was v3 and unflagged. See the correction's general lesson.

Every constant below is documented with the recorded failure it must catch
and its measured footprint on the pinned wave tape
(`pulse_decisions_full_20260901T195202Z.csv`, 18,341 priced rows, 34 games).
Reproduce the counts:

    python -m core.pulse.guards --count backups/exports/pulse_decisions_full_20260901T195202Z.csv

Guard 1 — jointly-impossible clock/score states (all strategies)
----------------------------------------------------------------
The state itself is checked: elapsed time versus points scored versus period
bounds. The workhorse is the scoring-rate cap — the sea-dal corruption
("Q2, 30:00 left" with 91 points on the board) passes the period-bounds
check because 30:00 is the legal Q2 boundary; what is impossible is 91
points in <=10 elapsed minutes. Tape footprint: 22 rows / 2 games (0.12%):
the 3-row sea-dal cluster (incl. the P=1.0000 row) and a 19-row conn-la
period seam (11 points at elapsed ~0).

Guard 2 — unrepresentable confidence (totals only)
--------------------------------------------------
Both bands abstain rather than clamp: a clamped fv fed to the entry logic
would manufacture disagreement against a market legitimately at 0.99 and
generate fade-the-certainty entries — the cure would trade more than the
disease. All of C's extreme misses were totals; winner/spread margins are
the regime the Gaussian handles, so the guard does not touch them.

* endgame band: with <= ENDGAME_MINUTES left and the line NOT already
  clinched (total_so_far <= line), fv outside [0.03, 0.97] is refused — the
  Gaussian carries no foul-game mass (por-atl: P(over)=0.0000 at 0:09,
  needing 2.5 points; the foul game produced 3) and structurally zero
  overtime mass (ind-ny: P=0.0004 at 2:05; the game went to OT and the over
  won). A clinched over (points never come off the board) passes through at
  any confidence. Tape footprint: 229 rows / 16 games; 106 of them are
  model-vs-market disagreements >5c — the failure shape — and the rest are
  agreement states where abstention costs nothing because no entry would
  have fired anyway.

* extrapolation band: with >= EXTRAPOLATION_MINUTES left and the line not
  clinched, fv outside [0.05, 0.95] is refused — a half-length
  extrapolation's sigma cannot justify 98% (conn-dal: 105 at the half,
  P(over 173.5)=0.98 held nineteen consecutive minutes; the second half
  scored 63). Tape footprint: 432 rows / 19 games, split ~half agreement /
  half disagreement as above.

Known limit, stated rather than papered over: 13 of the tape's 44 extreme
misses are one v1 estimated-clock game (atl-phx 08-22) whose states are
internally plausible — points-vs-elapsed within physical bounds — and only
the market disagreed. A state-only check cannot catch a stale score with a
consistent-looking clock; catching those would take flag logic (forbidden by
the correction — dead regime) or market-cross checks (pricing logic, out of
scope for an input-validity guard).
"""

from __future__ import annotations

from core.pulse.win_curve import REGULATION_MINUTES

#: Regulation game-minutes remaining spanned by each period label the venue
#: feed emits. HT is the seam between Q2 and Q3. Overtime never reaches the
#: guards — the engine abstains on OT upstream (no registered OT model).
PERIOD_BOUNDS: dict[str, tuple[float, float]] = {
    "Q1": (30.0, 40.0),
    "Q2": (20.0, 30.0),
    "HT": (20.0, 20.0),
    "Q3": (10.0, 20.0),
    "Q4": (0.0, 10.0),
}

#: Clock drift observed at period seams on the pinned tape (HT rows span
#: 19.42–20.16; Q1 dips to 29.55). The tolerance must cover the seams
#: without covering a whole quarter.
CLOCK_TOLERANCE_MINUTES = 0.75

#: Scoring-rate cap: WNBA tape p99.9 is 11.5 pts/min only because elapsed~0
#: seam ticks explode the ratio; sustained combined scoring never nears
#: 6/min (a 162-point final is 4.05/min). The seam allowance absorbs a
#: legitimate handful of points while the clock is still at the period
#: boundary. sea-dal: 91 > 10 + 6.0 x 10 elapsed -> refused.
MAX_POINTS_PER_MINUTE = 6.0
SEAM_ALLOWANCE_POINTS = 10.0

#: The converse corruption — a stale score under a running clock. Loose by
#: design (slowest plausible WNBA combined pace is ~2.5/min): zero rows on
#: the pinned tape trip it; it exists so a dead score feed cannot ride a
#: live clock into certainty unrefused.
MIN_POINTS_PER_MINUTE = 1.5
MIN_RATE_SLACK_POINTS = 10.0

#: Guard-2 endgame band. 3.0 minutes covers the recorded OT miss at 2:05
#: (ind-ny) and the foul-game miss at 0:09 (por-atl). 0.03 is the venue's
#: own floor for a tail it will still pay 3c for.
ENDGAME_MINUTES = 3.0
ENDGAME_BAND = 0.03

#: Guard-2 extrapolation band. 15.0 minutes = the half-length horizon where
#: the recorded 0.98-for-nineteen-minutes miss lived (conn-dal, 20.6 left);
#: 0.05 mirrors the calibration report's own extreme-tail definition.
EXTRAPOLATION_MINUTES = 15.0
EXTRAPOLATION_BAND = 0.05

GUARD_STATE = "implausible_state"
GUARD_CONFIDENCE = "unrepresentable_confidence"


def implausible_state(*, period: str | None, minutes_left: float,
                      total_so_far: int | None,
                      margin: int | None) -> str | None:
    """Guard 1: the refusal reason for a jointly-impossible state, or None.

    Checks the state itself — elapsed vs points vs period bounds — never a
    flag. `minutes_left` is regulation game-minutes remaining (the engine's
    frame everywhere).
    """
    if not 0.0 <= minutes_left <= REGULATION_MINUTES:
        return f"minutes_out_of_range:{minutes_left:.2f}"
    bounds = PERIOD_BOUNDS.get(period or "")
    if bounds is not None:
        lo, hi = bounds
        if not (lo - CLOCK_TOLERANCE_MINUTES <= minutes_left
                <= hi + CLOCK_TOLERANCE_MINUTES):
            return f"period_clock_mismatch:{period}@{minutes_left:.2f}"
    if total_so_far is None:
        return None
    if total_so_far < 0:
        return f"negative_total:{total_so_far}"
    elapsed = REGULATION_MINUTES - minutes_left
    if total_so_far > SEAM_ALLOWANCE_POINTS + MAX_POINTS_PER_MINUTE * elapsed:
        return f"score_too_high_for_elapsed:{total_so_far}pts@{elapsed:.2f}min"
    if total_so_far < MIN_POINTS_PER_MINUTE * elapsed - MIN_RATE_SLACK_POINTS:
        return f"score_too_low_for_elapsed:{total_so_far}pts@{elapsed:.2f}min"
    if margin is not None and abs(margin) > total_so_far:
        return f"margin_exceeds_total:{margin}vs{total_so_far}"
    return None


def unrepresentable_confidence(*, fair_value: float, minutes_left: float,
                               line: float | None,
                               total_so_far: int | None) -> str | None:
    """Guard 2 (TOTALS only — the caller enforces the strategy): the refusal
    reason for a certainty the Gaussian tail cannot represent, or None.

    Abstains, never clamps — see the module docstring for why a clamped
    value must not reach the entry logic. A clinched over
    (total_so_far > line) passes at any confidence: points never come off
    the board, so that certainty is arithmetic, not a tail claim.
    """
    if line is None or total_so_far is None:
        return None
    if total_so_far > line:
        return None                    # clinched — certainty is legitimate
    if minutes_left <= ENDGAME_MINUTES:
        if fair_value < ENDGAME_BAND or fair_value > 1.0 - ENDGAME_BAND:
            return (f"endgame_tail:fv={fair_value:.4f}@{minutes_left:.2f}min,"
                    f"need={line - total_so_far:.1f}pts")
    if minutes_left >= EXTRAPOLATION_MINUTES:
        if fair_value < EXTRAPOLATION_BAND or fair_value > 1.0 - EXTRAPOLATION_BAND:
            return (f"extrapolation_tail:fv={fair_value:.4f}"
                    f"@{minutes_left:.2f}min")
    return None


def _count_tape(path: str) -> None:
    """Refusal counts on a decisions CSV — the shipping tightness check.

    Reads the same columns the engine reads and applies the guards row by
    row, so the printed counts are the guards' own answer, not a parallel
    reimplementation.
    """
    import csv
    from collections import Counter

    counts: Counter[str] = Counter()
    priced = 0
    games: dict[str, set[str]] = {GUARD_STATE: set(), GUARD_CONFIDENCE: set()}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("fair_value") or not row.get("minutes_left") \
                    or not row.get("total_so_far"):
                continue
            priced += 1
            minutes = float(row["minutes_left"])
            total = int(float(row["total_so_far"]))
            margin = int(float(row["margin"])) if row.get("margin") else None
            g1 = implausible_state(
                period=row.get("period") or None, minutes_left=minutes,
                total_so_far=total, margin=margin)
            if g1 is not None:
                counts[f"{GUARD_STATE}:{g1.split(':')[0]}"] += 1
                games[GUARD_STATE].add(row["event_slug"])
                continue               # the engine never reaches guard 2
            if row.get("strategy") == "total":
                line = float(row["line"]) if row.get("line") else None
                g2 = unrepresentable_confidence(
                    fair_value=float(row["fair_value"]), minutes_left=minutes,
                    line=line, total_so_far=total)
                if g2 is not None:
                    counts[f"{GUARD_CONFIDENCE}:{g2.split(':')[0]}"] += 1
                    games[GUARD_CONFIDENCE].add(row["event_slug"])
    print(f"priced rows: {priced}")
    total_refused = sum(counts.values())
    for key in sorted(counts):
        print(f"  {key}: {counts[key]}")
    print(f"refused: {total_refused} ({100.0 * total_refused / priced:.2f}%) | "
          f"games touched: state={len(games[GUARD_STATE])} "
          f"confidence={len(games[GUARD_CONFIDENCE])}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--count":
        _count_tape(sys.argv[2])
    else:
        print("usage: python -m core.pulse.guards --count <decisions.csv>")
        raise SystemExit(2)
