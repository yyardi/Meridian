"""Executable forms of the WAVE_STANDARD rules that prose has failed to enforce.

WHY THIS FILE EXISTS. On 2026-09-03 three authors violated three rules within
minutes of writing them: one reached for "convergence" in the very message
proposing rule 26; one carried a superseded figure into the entry about
superseded figures propagating; one (the manager) published two corrections
inside the twenty-minute window they then identified as the defect.

That is not three lapses of attention. **These failures have no felt signal** —
the writer sees a labelled number and believes the label travels; the reader
sees a number that answers their question and has no cue that a denominator was
ever attached. Neither party experiences a gap, and carefulness is the only
thing a rule written as prose can request.

So: **a rule violated by its own author within the hour is a rule that needs an
artifact, not a reminder.** These are the artifacts. The prose in
analysis/WAVE_STANDARD.md remains as rationale.

The selftests deliberately encode the CONFUSION rather than the arithmetic —
they assert that the wrong-but-plausible call is refused, because the arithmetic
was never what failed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


class GuardViolation(AssertionError):
    """Raised when a guard refuses a report. Never catch this to proceed."""


# --------------------------------------------------------------------------
# Rule 22 — SILENT ABSENCE. A zero is the least self-validating result there is.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ZeroReport:
    """A count, carrying the provenance that makes a zero interpretable."""

    name: str
    count: int
    last_nonzero_at: dt.datetime | None
    last_nonzero_count: int | None

    def __str__(self) -> str:
        if self.count:
            return f"{self.name}={self.count}"
        if self.last_nonzero_at is None:
            return (f"{self.name}=0 [UNPROVEN INSTRUMENT — has never returned "
                    f"non-zero on this substrate; NOT evidence of absence]")
        age = dt.datetime.now(dt.UTC) - self.last_nonzero_at
        return (f"{self.name}=0 [last non-zero {self.last_nonzero_count} at "
                f"{self.last_nonzero_at:%Y-%m-%dT%H:%MZ}, {age.total_seconds()/3600:.1f}h ago]")


def report_count(name: str, count: int, last_nonzero_at=None, last_nonzero_count=None) -> ZeroReport:
    """Build a count that cannot be printed as a bare zero.

    A zero from an instrument that has never returned non-zero on THIS substrate
    is not evidence of absence — it is an untested instrument, and the string
    form says so rather than letting the reader supply the interpretation.
    """
    if count < 0:
        raise GuardViolation(f"{name}: negative count {count}")
    if count == 0 and last_nonzero_at is None and last_nonzero_count:
        raise GuardViolation(
            f"{name}: last_nonzero_count given without last_nonzero_at — "
            "provenance must be complete or absent, never half-stated")
    return ZeroReport(name, count, last_nonzero_at, last_nonzero_count)


# --------------------------------------------------------------------------
# Rule 25 — a metric that moves with activity cannot rank policies that differ
# in activity. Composites never travel alone.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Composite:
    """A ratio that refuses to print without its parts."""

    name: str
    numerator: float
    denominator: float
    events: int

    @property
    def ratio(self) -> float:
        return self.numerator / self.denominator if self.denominator else float("nan")

    @property
    def per_event(self) -> float:
        return self.numerator / self.events if self.events else float("nan")

    def __str__(self) -> str:
        return (f"{self.name}: {self.ratio:+.4f} per opportunity "
                f"[num={self.numerator:+.4f} den={self.denominator:.0f} "
                f"events={self.events} per_event={self.per_event:+.4f}]")


def report_composite(name: str, numerator: float, denominator: float, events: int) -> Composite:
    """A rate-normalised figure, carrying numerator, denominator and per-event mean.

    Reporting the ratio alone is what let the >10c band top a per-cycle table at
    -0.010c while being the worst per-fill cell on the board at -7.15c: it won by
    filling 0.0013 times per cycle, i.e. by barely being in the market.
    """
    if events < 0 or denominator < 0:
        raise GuardViolation(f"{name}: negative counts")
    if events > denominator:
        raise GuardViolation(
            f"{name}: events ({events}) exceed opportunities ({denominator:.0f}) — "
            "the denominator is not counting what you think it is")
    return Composite(name, numerator, denominator, events)


def degenerate_extremes_warning(name: str, per_event_mean: float) -> str | None:
    """Rule 25's test: does a degenerate activity level win?

    If the per-event value has a uniform sign, the rate-normalised optimum is at
    zero activity (negative mean) or unbounded activity (positive mean). Either
    way the ranking is about activity, not policy quality.
    """
    if per_event_mean < 0:
        return (f"{name}: per-event mean is NEGATIVE ({per_event_mean:+.4f}), so this "
                "ratio is maximised by NEVER ACTING. Any argmax over it ranks "
                "inactivity. Report the per-event mean as the primary.")
    if per_event_mean > 0:
        return (f"{name}: per-event mean is POSITIVE ({per_event_mean:+.4f}), so this "
                "ratio is maximised by ACTING ALWAYS. Any argmax over it ranks "
                "activity. Report the per-event mean as the primary.")
    return None


# --------------------------------------------------------------------------
# Rule 23 — a name is a claim. Substrate identity, and the join-direction bug.
# --------------------------------------------------------------------------

def assert_landmark(row_count: int, table: str) -> None:
    """Before trusting any read from a connection, assert a known-non-empty landmark.

    A mislabelled FIELD eventually contradicts something. A mislabelled SUBSTRATE
    is perfectly self-consistent: every query returns a coherent, complete,
    entirely wrong answer about a world that is not ours. This is the one-line
    check that would have caught an empty database presenting as production.
    """
    if row_count <= 0:
        raise GuardViolation(
            f"landmark table {table!r} is EMPTY — this connection is not the "
            "substrate you believe it is. Every result computed on it would be "
            "coherent and wrong.")


def assert_age_non_negative(age_seconds: float, context: str = "") -> None:
    """Assert an age quantity is non-negative BEFORE any cap is applied to it.

    The bug is not 'a negated ASOF join' — negation is fine and often necessary.
    It is a MISMATCH between the join's direction and the sign convention of the
    quantity you then filter on, which turns a one-sided cap into a vacuous one.
    `age <= 5` reads like a freshness gate and admitted books from 25 hours in
    the FUTURE. If this fires, the join points the other way from the filter.
    """
    if age_seconds < 0:
        raise GuardViolation(
            f"age is negative ({age_seconds:.1f}s){' in ' + context if context else ''} — "
            "the join direction disagrees with the filter's sign convention, so any "
            "one-sided cap on it is vacuous.")


# --------------------------------------------------------------------------
# Selftest — encodes the CONFUSION, not the arithmetic.
# --------------------------------------------------------------------------

def _selftest() -> None:
    now = dt.datetime.now(dt.UTC)

    # Rule 22: an unproven zero must ANNOUNCE that it is unproven.
    unproven = report_count("ncaaf_contracts", 0)
    assert "UNPROVEN INSTRUMENT" in str(unproven), str(unproven)
    assert "NOT evidence of absence" in str(unproven)
    proven = report_count("ncaaf_contracts", 0,
                          now - dt.timedelta(hours=3), 431)
    assert "last non-zero 431" in str(proven), str(proven)
    assert "UNPROVEN" not in str(proven)
    print("  22: a zero cannot print bare — unproven says so, proven shows its control")

    # Rule 25: the real specimen. The >10c band tops the per-cycle table while
    # being the worst per-fill cell. The guard must surface both.
    wide = report_composite("width>10c", numerator=-0.010 * 95614,
                            denominator=95614, events=129)
    tight = report_composite("width<=2c", numerator=-0.096 * 98062,
                             denominator=98062, events=2062)
    assert wide.ratio > tight.ratio, "the artifact: wide WINS on the ratio"
    assert wide.per_event < tight.per_event, "and LOSES on the per-event mean"
    assert "per_event=" in str(wide) and "events=129" in str(wide)
    warn = degenerate_extremes_warning("width>10c", wide.per_event)
    assert warn and "NEVER ACTING" in warn, warn
    print("  25: the ratio still ranks wide first — and the guard prints the "
          "per-event mean beside it and warns the optimum is inactivity")

    # The limiting case, which is what makes the guard un-removable: a band
    # quoted 1000 times that never fills scores a perfect zero.
    never = report_composite("never_quotes", numerator=0.0, denominator=1000, events=0)
    assert never.ratio == 0.0
    assert never.ratio > wide.ratio > tight.ratio, "doing nothing beats everything that traded"
    print("  25: a band that NEVER FILLS scores 0.000 and beats every band that traded")

    # A denominator that is not counting opportunities.
    try:
        report_composite("bad", 1.0, denominator=5, events=10)
    except GuardViolation as e:
        assert "not counting what you think" in str(e)
        print("  25: events exceeding opportunities is refused, not averaged")
    else:
        raise AssertionError("should have refused")

    # Rule 23: the empty-substrate confusion.
    try:
        assert_landmark(0, "market_snapshots")
    except GuardViolation as e:
        assert "not the substrate you believe" in str(e)
        print("  23: an empty landmark refuses the connection")
    else:
        raise AssertionError("should have refused")

    # Rule 23: the join-direction confusion. A 'freshness' cap that admits the future.
    assert_age_non_negative(4.2, "backward join")
    try:
        assert_age_non_negative(-90000.0, "placement book lookup")
    except GuardViolation as e:
        assert "vacuous" in str(e)
        print("  23: a book from 25h in the FUTURE trips the age assert, "
              "which 'age <= 5' never would")
    else:
        raise AssertionError("should have refused")

    print("guards selftest: PASS")


if __name__ == "__main__":
    _selftest()
