"""The resting-order probe: a code path that is INERT until the operator arms it.

WHY THIS EXISTS, and it is not "the simulator is imprecise"
===========================================================
`core/quote/engine.py` books a bid fill when ``mid <= standing.bid_price``.
With a positive spread ``mid <= bid`` is arithmetically impossible, so a fill
is recorded only when the NEW mid has fallen to or below our OLD bid — the
book moving down through our quote. That is the adverse case.

**The profitable maker case produces no row at all.** A seller crossing to our
resting bid while the ask holds leaves the mid above our bid, so the simulator
never books it. Every making result this programme has produced is therefore
computed on a population that STRUCTURALLY EXCLUDES the winning case. We have
not been measuring market making badly; we have been measuring a subset chosen
so that capture <= 0 by construction.

No amount of additional tape fixes that, because the missing variable is our
own order, which was never in the book. Only real resting orders can settle:

  (a) whether a passive join is ever filled benignly, and how often;
  (b) what the venue ACTUALLY charges or pays on a maker fill;
  (c) where we sit in the queue (simulator uncorrected: median 15 contracts
      ahead, 90th percentile 850).

SAFETY, stated once and enforced structurally
==============================================
This module NEVER places an order. `plan()` returns an intent; `execute()`
raises unless `armed=True` is passed explicitly by a caller the operator
controls, and even then it delegates to an injected `submit_fn`. There is no
venue client here and no credentials are read. The database CHECK constraint
barring autonomous orders is untouched and must stay untouched — if this
harness ever cannot be exercised without weakening it, that is a design
finding to report, not an obstacle to route around.

Nothing in this file is reachable from the running engine. It is imported by
tests and by an operator-run script, and by nothing else.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
from dataclasses import dataclass, field

# --- the pre-registration, written BEFORE any order can be armed --------- #
#: What the probe measures, and what would refute the making thesis. Recorded
#: here rather than in a doc so it cannot drift from the code that runs.
PRE_REGISTRATION = {
    "question": (
        "Does a passive order resting at or behind the touch get filled, and "
        "when it does, is the fill benign (the counterparty crossed to us "
        "while the far side held) or adverse (the book moved through us)?"
    ),
    "primary_outcome": "benign_fill_rate = benign_fills / total_fills",
    "confirms_making": (
        "benign_fill_rate materially above zero AND realised P&L per fill, "
        "net of the fee the venue actually charged, has a game-clustered "
        "interval excluding zero on the positive side."
    ),
    "refutes_making": (
        "benign_fill_rate indistinguishable from zero — i.e. we are filled "
        "only when the book moves through us. That is the simulator's implied "
        "world being true, and it means passive joining cannot pay at any "
        "price offset, which kills the thesis rather than tuning it."
    ),
    "uninformative": (
        "too few fills to separate the two (<25 games, or zero fills at every "
        "offset). Reported as UNDERPOWERED, never as a refutation — an "
        "unprovenanced zero supports no conclusion in either direction."
    ),
    #: The achievable-image check. Every branch must be REACHABLE by some
    #: possible outcome, and no branch may be forced. Verified by
    #: `check_achievable_image()` below, which enumerates the outcome space.
    "achievable_image_checked": True,
}


@dataclass(frozen=True)
class BookAtSubmission:
    """The book as it stood when we submitted. Recorded, never inferred."""
    best_bid: float
    best_ask: float
    depth_at_our_level: int | None
    #: True queue position if the venue exposes it; else None and
    #: `queue_estimate` carries our guess. WHICH ONE IS ALWAYS RECORDED.
    queue_position_venue: int | None = None
    queue_estimate: int | None = None
    queue_source: str = "estimate"          # "venue" | "estimate" | "unknown"


@dataclass(frozen=True)
class ProbeIntent:
    """What we WOULD submit. Returned by plan(); never sent by this module."""
    market_slug: str
    side: str                                # "bid" | "ask"
    price: float
    size: int
    offset_ticks: int                        # the randomised offset DRAWN
    seed: str                                # so the draw is reproducible
    book: BookAtSubmission
    planned_at: dt.datetime


@dataclass
class ProbeRecord:
    """Ground truth for one probe order. Every field the harness must capture."""
    intent: ProbeIntent
    submitted_at: dt.datetime | None = None
    #: fill/cancel/expiry
    resolved_at: dt.datetime | None = None
    outcome: str = "pending"                 # filled|cancelled|expired|rejected
    fill_price: float | None = None
    #: READ FROM THE VENUE RESPONSE. Never computed from our own fee formula —
    #: computing it would make the fee check circular, which is the failure
    #: mode this probe exists to avoid.
    fee_charged_venue: float | None = None
    fee_field_present: bool = False
    no_fill_reason: str | None = None
    #: the book at resolution, so benign-vs-adverse is decidable
    ask_at_resolution: float | None = None
    bid_at_resolution: float | None = None

    @property
    def time_at_risk_s(self) -> float | None:
        if self.submitted_at is None or self.resolved_at is None:
            return None
        return (self.resolved_at - self.submitted_at).total_seconds()

    @property
    def benign(self) -> bool | None:
        """A fill is BENIGN if the far side held while we were hit.

        This is the whole measurement. For a resting BID, benign means the ask
        did not fall to our price — someone chose to sell to us rather than the
        book collapsing through us. Undecidable without the resolution book, in
        which case it returns None rather than guessing.
        """
        if self.outcome != "filled":
            return None
        if self.intent.side == "bid":
            if self.ask_at_resolution is None:
                return None
            return self.ask_at_resolution > self.intent.price
        if self.bid_at_resolution is None:
            return None
        return self.bid_at_resolution < self.intent.price


def draw_offset(market_slug: str, seed: str, max_ticks: int = 3) -> int:
    """Deterministic per (market, seed) offset in [0, max_ticks].

    Randomised so the probe does not systematically sit at one distance, and
    deterministic so a run is reproducible and the draw can be audited after
    the fact rather than trusted.
    """
    h = hashlib.sha256(f"{seed}:{market_slug}".encode()).digest()
    return h[0] % (max_ticks + 1)


def plan(*, market_slug: str, side: str, book: BookAtSubmission, seed: str,
         size: int = 1, tick: float = 0.01, now: dt.datetime) -> ProbeIntent:
    """Compute what we WOULD rest, and where. Places nothing."""
    if side not in ("bid", "ask"):
        raise ValueError(f"side must be bid|ask, got {side!r}")
    off = draw_offset(market_slug, seed)
    price = (round(book.best_bid - off * tick, 4) if side == "bid"
             else round(book.best_ask + off * tick, 4))
    return ProbeIntent(market_slug=market_slug, side=side, price=price,
                       size=size, offset_ticks=off, seed=seed, book=book,
                       planned_at=now)


class NotArmed(RuntimeError):
    """Raised when execute() is called without an explicit operator arm."""


def execute(intent: ProbeIntent, *, armed: bool = False, submit_fn=None) -> ProbeRecord:
    """INERT BY DEFAULT. Raises unless the operator explicitly arms it.

    `submit_fn` is injected by the operator's own script. This module holds no
    venue client and reads no credentials, so it cannot place an order even if
    `armed=True` is passed by mistake — there would be nothing to call.
    """
    rec = ProbeRecord(intent=intent)
    if not armed:
        rec.outcome = "not_armed"
        rec.no_fill_reason = (
            "harness is INERT: execute(armed=True) plus an operator-supplied "
            "submit_fn is required. No order was placed."
        )
        return rec
    if submit_fn is None:
        raise NotArmed(
            "armed=True but no submit_fn supplied. This module deliberately "
            "holds no venue client; the operator injects one."
        )
    return submit_fn(intent, rec)


# --- the achievable-image check ----------------------------------------- #
def check_achievable_image() -> dict:
    """Project the outcome space onto the pre-registered branches.

    A probe has previously been designed here that returned REFUTED on all 41
    of its possible outcomes. So before any capital is requested: enumerate
    what can happen and confirm each branch is REACHABLE and none is FORCED.
    """
    branches = {"confirms": 0, "refutes": 0, "uninformative": 0}
    # outcome space: (fills out of N, benign out of fills, games)
    for games in (5, 30, 120):
        for fills in (0, 1, 10, 200):
            for benign in range(0, fills + 1, max(1, fills or 1)):
                if games < 25 or fills == 0:
                    branches["uninformative"] += 1
                elif benign == 0:
                    branches["refutes"] += 1
                else:
                    branches["confirms"] += 1
    unreachable = [k for k, v in branches.items() if v == 0]
    return {
        "branch_counts": branches,
        "all_branches_reachable": not unreachable,
        "unreachable": unreachable,
        "verdict": ("OK — every branch reachable, none forced"
                    if not unreachable else
                    f"BROKEN — unreachable branches: {unreachable}"),
    }


def _selftest() -> None:
    now = dt.datetime(2026, 9, 6, 12, 0, tzinfo=dt.timezone.utc)
    book = BookAtSubmission(best_bid=0.40, best_ask=0.44,
                            depth_at_our_level=12, queue_estimate=15,
                            queue_source="estimate")

    # * the harness must be INERT by default
    i = plan(market_slug="m1", side="bid", book=book, seed="s1", now=now)
    r = execute(i)
    assert r.outcome == "not_armed" and "INERT" in (r.no_fill_reason or "")

    # * armed without an injected submitter must RAISE, not silently no-op
    try:
        execute(i, armed=True)
        raise AssertionError("armed with no submit_fn must raise")
    except NotArmed:
        pass

    # * the offset must actually vary across markets, or "randomised" is a lie
    offs = {draw_offset(f"m{n}", "s1") for n in range(40)}
    assert len(offs) > 1, f"offset never varies: {offs}"

    # * BENIGN vs ADVERSE must be decidable, and undecidable when the
    #   resolution book is missing -- never guessed
    b = ProbeRecord(intent=i, outcome="filled", ask_at_resolution=0.44)
    assert b.benign is True, "ask held above our bid -> benign"
    a = ProbeRecord(intent=i, outcome="filled", ask_at_resolution=0.39)
    assert a.benign is False, "ask fell through our bid -> adverse"
    u = ProbeRecord(intent=i, outcome="filled")
    assert u.benign is None, "no resolution book -> undecidable, not a guess"

    # * the fee must be READ, not computed -- absence is visible
    assert b.fee_charged_venue is None and b.fee_field_present is False

    # * time at risk is None until both stamps exist
    assert b.time_at_risk_s is None

    # * and the pre-registration's branches must all be reachable
    img = check_achievable_image()
    assert img["all_branches_reachable"], img["verdict"]

    print("selftest OK — inert by default, armed-without-submitter raises, "
          "offset varies, benign/adverse decidable-or-None, fee not computed, "
          "all pre-registered branches reachable")
    print(f"  achievable image: {img['branch_counts']}  -> {img['verdict']}")


if __name__ == "__main__":
    _selftest()
