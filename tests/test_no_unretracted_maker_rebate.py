"""No document may assert a maker rebate without its retraction attached.

θ_maker = 0 on this venue: a maker rebate has never been observed in our own
fills, and the original claim was traced to a web search rather than to the
venue. The CODE has been right about this for days —
`core/backtest/fills.py` defaults `THETA_MAKER = 0.0`, `core/quote/wallet.py`
documents "theta_maker=0 (V9/C7)", `core/pulse/tight_game_reversion.py` says
the rebate "has never been observed", STATUS says "no maker rebate on this
venue".

`docs/math/the-rebate.md` was the one place that still asserted the opposite,
for eleven days, in the document whose job is to record the fee facts. It was
found while checking whether a stale branch would re-introduce it; the branch
was never the vector, main already carried it.

This guard exists because the retraction reaching every consumer EXCEPT the
record is a specific, repeatable failure — and the cost of it re-appearing is
a strategy sized against income that does not exist.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Phrasings that assert a rebate as FACT. Deliberately narrow: the word
#: "rebate" alone appears in honest sentences ("the rebate has never been
#: observed"), so matching it would fire on the retraction itself.
ASSERTS = re.compile(
    r"(pays\s+(a\s+)?makers?|PAYS\s+makers?|receives\s+\$?0\.31"
    r"|maker\s+rebate\s+is\s+(roughly|about|approximately))",
    re.IGNORECASE)

#: Any of these near the assertion means the reader is warned.
RETRACTS = re.compile(
    r"(RETRACTED|theta_maker\s*=\s*0|θ_maker\s*=\s*0|never been observed"
    r"|no maker rebate|never observed)", re.IGNORECASE)


def _docs():
    for p in sorted((REPO / "docs").rglob("*.md")):
        yield p


def test_no_document_asserts_a_maker_rebate_without_a_retraction():
    """★ The guard. A file may DISCUSS the episode; it may not assert the
    rebate without the correction where a reader will meet it."""
    offenders = []
    for p in _docs():
        text = p.read_text()
        if not ASSERTS.search(text):
            continue
        # The retraction must appear BEFORE the first assertion, not below it.
        first = ASSERTS.search(text).start()
        if not RETRACTS.search(text[:first]):
            offenders.append(str(p.relative_to(REPO)))
    assert not offenders, (
        "these assert a maker rebate with no retraction above the claim: "
        f"{offenders}. theta_maker = 0 on this venue; the rebate has never "
        "been observed and the original figure came from a web search. A "
        "retraction below the table it retracts is not a retraction.")


def test_the_rebate_document_still_carries_the_episode():
    """The retraction must not have been implemented by DELETING the record.
    The episode is the useful part: a fee fact taken from a web page instead of
    from the venue, and eleven days of every consumer being corrected except
    the document."""
    text = (REPO / "docs/math/the-rebate.md").read_text()
    assert "0.31" in text, "the original figure was deleted rather than retracted"
    assert text.lstrip().startswith(">"), (
        "the retraction is no longer the first thing a reader meets")
    assert "RETRACTED" in text.split("\n")[0].upper()


def test_the_guard_can_see_an_assertion_at_all():
    """A pattern that matches nothing would pass this suite forever. Checked
    against the actual sentence from the document."""
    assert ASSERTS.search("Polymarket US pays a maker 0.31c.")
    assert ASSERTS.search("**Polymarket US PAYS makers.**")
    assert ASSERTS.search("| **maker** | receives $0.31 / 100 |")
    # And it must NOT fire on honest prose about the retraction.
    assert not ASSERTS.search(
        "the maker rebate has never been observed on this venue")
    assert not ASSERTS.search("theta_maker = 0, so the maker fee is ~0")
