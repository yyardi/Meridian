"""Did this recorder cycle do the work it said existed?

THE FAILURE THIS EXISTS FOR, observed in production 2026-09-06 21:37Z onward:

    espn_cycle league=cfb live_games=2 plays_attempted=0 state_rows=0
    warning cfb_summary_failed error='Unconsumed column names: league'

Two live games identified, zero rows written, exception caught and logged as a
warning, cycle returns cleanly, container reports Up, every heartbeat green.
No monitor we own catches it, because every monitor counts rows that ARRIVED
and this writes none.

The discriminator is not a rate. It is EXPECTED versus OBSERVED, and both
numbers are already in the process: `live_games` says work exists,
`state_rows` says none was done. Nobody compares them.

★ THE TRAP THAT MAKES THE NAIVE CHECK WRONG ★

"work identified > 0 and rows written == 0" FALSE-FIRES on a healthy recorder.
`espn_cfb_recorder` writes plays and win-probability with
`on_conflict_do_nothing` keyed on (game_id, play_id), so re-polling a live
game between plays legitimately writes ZERO new rows. Low new-row volume
during live play is the DESIGNED behaviour of an idempotent writer, and a
check that pages on it will be muted within a week.

So each writer must declare which it is:

    APPEND_ONLY   one row per work-item per cycle, always. Zero is a fault.
                  (`espn_cfb_recorder` sets `ns = 1` per game per poll.)
    IDEMPOTENT    ON CONFLICT DO NOTHING. Zero is normal when caught up, and
                  only a swallowed error alongside it is evidence.

Without that distinction the check is either blind or noisy. With it, the live
failure above is unambiguous: state_rows is APPEND_ONLY and it is zero while
two games are live.

★ AND A COUNT OF -1 IS NOT A COUNT ★

`espn_cfb_recorder._write` returns `session.execute(stmt).rowcount or 0`, and
`-1 or 0` is `-1` because -1 is truthy. The driver returns -1 when the
affected-row count is unavailable, so those fields can never carry a real
number. UNKNOWN is a state here, never OK — an unreportable count must not be
read as zero (which would page) nor as fine (which would hide).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

OK, FAULT, UNKNOWN = "OK", "FAULT", "UNKNOWN"


class Kind(Enum):
    APPEND_ONLY = "append_only"
    IDEMPOTENT = "idempotent"


class Counts(Enum):
    """What the reported number MEANS, which decides whether zero is evidence.

    ATTEMPTED is the stronger signal and the one the ESPN side reports, for a
    reason worth keeping: rows BUILT, before de-duplication, so a caught-up
    idempotent writer still reports a positive number. It carries no
    dedupe confound at all.

    It is only trustworthy because of a structural property of the writer:
    in `espn_cfb_recorder.poll_game` the `return` sits AFTER `s.commit()`, so
    any exception propagates before the counters are returned and they stay 0.
    Therefore ATTEMPTED > 0 IMPLIES THE TRANSACTION COMMITTED — there is no
    attempted-but-rolled-back state to defeat a log-only check.

    `test_attempted_counts_are_only_returned_after_commit` pins that. If the
    writer ever catches per-statement, the property dies, that test fails, and
    the contract must move to a DB-side comparison instead of quietly becoming
    wrong.
    """

    ATTEMPTED = "attempted"
    WRITTEN = "written"


@dataclass(frozen=True)
class Write:
    """One writer's result for one cycle. `rows` None or negative = the count
    was not reportable, which is not the same as zero."""

    name: str
    kind: Kind
    rows: int | None
    errors: int = 0
    counts: Counts = Counts.WRITTEN

    @property
    def countable(self) -> bool:
        return self.rows is not None and self.rows >= 0


@dataclass(frozen=True)
class Cycle:
    """`work_identified` is the recorder's own count of things it found to do
    — live games, due markets. None means it could not tell, which is UNKNOWN
    and never OK: an absent schedule must not read as 'nothing scheduled'."""

    work_identified: int | None
    writes: tuple[Write, ...] = ()
    errors: int = 0


@dataclass
class Verdict:
    state: str
    reasons: list[str] = field(default_factory=list)
    codes: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return self.state == OK


def judge(cycle: Cycle) -> Verdict:
    """Three states. FAULT means the cycle claimed work and did none."""
    v = Verdict(OK)

    def fault(code: str, why: str) -> None:
        v.state = FAULT
        v.codes.add(code)
        v.reasons.append(why)

    def unknown(code: str, why: str) -> None:
        if v.state != FAULT:
            v.state = UNKNOWN
        v.codes.add(code)
        v.reasons.append(why)

    if cycle.work_identified is None:
        unknown("WORK_UNKNOWN",
                "the recorder could not say how much work existed; absence of "
                "a schedule is not evidence of no games")
        return v

    for w in cycle.writes:
        if not w.countable:
            unknown("COUNT_UNREPORTABLE",
                    f"{w.name} reported rows={w.rows!r} — an unreportable "
                    "count is not zero and is not fine")

    if cycle.work_identified == 0:
        # Genuinely quiet. Errors still matter, but no work means no fault.
        if cycle.errors:
            unknown("IDLE_WITH_ERRORS",
                    f"no work identified but {cycle.errors} error(s) — the "
                    "reason there is no work may be the error")
        return v

    # Work exists. Two writers make zero unambiguous, for different reasons:
    # ATTEMPTED counts rows BUILT (no dedupe confound at all), and APPEND_ONLY
    # writers do not dedupe. Either reporting zero is a fault.
    for w in cycle.writes:
        if w.countable and w.rows == 0 and w.counts is Counts.ATTEMPTED:
            fault("SILENT_ATTEMPT",
                  f"{cycle.work_identified} work-item(s) identified and "
                  f"{w.name!r} attempted 0 rows — attempted counts rows BUILT, "
                  "so zero means the recorder produced nothing to write")
    # An APPEND_ONLY writer must produce ONE row per work-item, so anything
    # short of that is a fault — not merely zero.
    #
    # ★ THE RULE IS A DISJUNCTION, and neither half is sufficient (D's finding,
    # verified by a1). Each is blind to a failure the other catches:
    #     3 of 5 games throwing  -> plays_attempted = 40, so the ATTEMPTED
    #                               half never fires; state_rows 2 < 5 catches it
    #     parse returning empty  -> state_rows == live_games, so this half
    #                               never fires; plays_attempted == 0 catches it
    # `state_rows == live_games` is code-guaranteed rather than data-dependent:
    # CfbGameState has no UniqueConstraint (only an Index) and `ns = 1` is set
    # in Python, so it carries no dedupe confound.
    #
    # CAVEAT, stated rather than tuned around: `parse_game_state` returns None
    # when a payload has no `header.competitions`, giving ns=0 with no
    # exception — a false positive for this half. a1 owns making that raise;
    # until it does, a short count can mean a payload shape rather than a
    # fault, and this rule is a strong signal rather than an exact one.
    for w in cycle.writes:
        if (w.kind is Kind.APPEND_ONLY and w.countable
                and w.counts is Counts.WRITTEN
                and 0 < w.rows < cycle.work_identified):
            fault("SHORT_APPEND",
                  f"{w.name!r} wrote {w.rows} rows for "
                  f"{cycle.work_identified} work-item(s) — an append-only "
                  "writer owes one per item, so a short count means some "
                  "items produced nothing")
    for w in cycle.writes:
        if (w.kind is Kind.APPEND_ONLY and w.countable and w.rows == 0
                and w.counts is Counts.WRITTEN):
            fault("SILENT_APPEND",
                  f"{cycle.work_identified} work-item(s) identified and "
                  f"append-only writer {w.name!r} wrote 0 rows — it does not "
                  "dedupe, so zero cannot be 'already had it'")

    # Idempotent writers may legitimately write nothing. Zero across ALL of
    # them WITH an error is the swallowed-exception signature.
    idem = [w for w in cycle.writes if w.kind is Kind.IDEMPOTENT and w.countable]
    if idem and all(w.rows == 0 for w in idem) and (cycle.errors or
                                                    any(w.errors for w in idem)):
        fault("SILENT_ERROR",
              "every idempotent writer wrote 0 while an error was recorded — "
              "a caught exception that returns cleanly looks exactly like "
              "'nothing new to write'")
    return v
