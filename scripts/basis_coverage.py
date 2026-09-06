#!/usr/bin/env python3
"""Which cent figures name their BASIS, and which leave it to the reader.

The defect: "game-clustered" describes the INTERVAL, not the ESTIMATE. A reader
who takes it as "averaged over games" computes a different number and believes
they reproduced ours. Measured on the CFB headline the gap is 1.28c (per-fill
-2.0765c against per-game -3.3526c) — LARGER than the CI half-width of 1.55c.

Three collisions in one day: -3.419 vs -3.376 earlier, the CFB headline, and
B against d5 at -0.00479 vs -0.00979 on IDENTICAL ROWS. None was an error;
every one cost a reconciliation cycle a rendered label would have prevented.

THREE STATES, because two would hide the uncomfortable one:

  LABELLED    a basis word on the same line as the figure
  INHERITED   a basis word within LOOKBACK lines above — a table header or a
              section heading covering it. Legitimate, and weaker: the header
              can be scrolled away from, quoted without, or reordered.
  UNLABELLED  no basis word in range. The reader supplies it.

Reports, does not gate — same as scripts/guard_coverage.py. A guard that
blocks on a heuristic gets disabled; one that reports gets read.

    python3 scripts/basis_coverage.py [paths...]
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: A cent figure: a signed decimal immediately followed by a cent marker.
#: Percentages are deliberately NOT matched — a share (63.9% phantom) has no
#: per-fill/per-game basis to name, and matching them would drown the signal.
FIGURE = re.compile(r"[+-]?\d+\.\d+\s*(?:c\b|¢)")

#: The basis vocabulary is DOMAIN-SPECIFIC PER STATISTIC, which the first
#: version missed: a fill P&L's rows are fills, but a venue-gap statistic's
#: rows are contract-observation PAIRS, and a markout's are quotes. Assuming
#: the fill/game dichotomy would mark a correctly-labelled figure UNLABELLED.
_UNIT = (r"fill|game|pair|contract|cycle|dollar|\$|market|order|observation"
         r"|row|trip|ride|quote|window|event|leg")
#: ★ A CLOSED VOCABULARY IS THE WRONG DESIGN HERE, and four separate misses
#: proved it: "per pair", "per filled quote", "+8.5c/$", then "per run" and
#: "per trade". Row units are open-ended — every study introduces its own
#: (fill, game, pair, window, run, trade, leg, observation, first-score
#: event...) and a fixed list will always lag the next document.
#:
#: The guard's question is whether a basis is STATED, not whether it is one
#: this file has heard of. So match the SHAPE of a basis phrase and accept any
#: noun. A false positive ("per cent") is cheap and stoplisted; a false
#: negative marks correct work as defective, which is what got four figures
#: wrongly flagged and would eventually get the guard ignored.
_STOP = r"(?!cent\b|cents\b)"
BASIS = re.compile(
    # NOTE the missing \b after the /UNIT alternative: "+8.5c/$" failed to
    # match because \b never fires after "$", which is not a word character.
    rf"per[-\s]{_STOP}(?:\w+[-\s]){{0,2}}\w+"
    rf"|/(?:{_UNIT}|\w+)|\w+-weighted"
    r"|mean of (?:\w+ )?means|median of (?:\w+ )?medians"
    rf"|over (?:all |the )?(?:\w+[-\s]){{0,3}}(?:{_UNIT})s?\b", re.I)

#: A cent figure only NEEDS a basis if it is an AVERAGE OVER A POPULATION.
#: A spread, a price move, a concession or a tick size is a cent figure with
#: no per-fill/per-game meaning at all. Without this the guard flags them and
#: gets dismissed: measured on this corpus the naive version called 73.6% of
#: figures unlabelled, and most were spreads.
ESTIMATE = re.compile(
    r"\bmean\b|\bavg\b|\baverage\b|P&L|\bpnl\b|\bcapture\b|\bROI\b"
    r"|\bexcess\b|\bmarkout\b", re.I)
#: ...or it is rendered with a confidence interval, which only an estimate has.
#: A CI is [lo, hi] — the comma is what distinguishes it from a mermaid
#: node label like T1["cross the spread<br/>-1.0c"], which is a PRICE.
INTERVAL = re.compile(
    r"\[[^\]]*[+-]?\d+\.\d+\s*(?:c\b|¢)[^\]]*,[^\]]*\]")

#: How far above a figure a header may sit and still be taken to cover it.
LOOKBACK = 12

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "backups"}


def scan(path: pathlib.Path):
    """Yield (lineno, state, line) for each cent figure in the file."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return
    for i, line in enumerate(lines):
        if not FIGURE.search(line):
            continue
        # only an average over a population has a basis to name
        if not (ESTIMATE.search(line) or INTERVAL.search(line)):
            continue
        if BASIS.search(line):
            yield i + 1, "LABELLED", line
            continue
        lo = max(0, i - LOOKBACK)
        if any(BASIS.search(x) for x in lines[lo:i]):
            yield i + 1, "INHERITED", line
        else:
            yield i + 1, "UNLABELLED", line


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "t.md"
        p.write_text(
            "the per-fill mean is -2.08c here\n"          # LABELLED
            "## per-game table of means\n"
            "| row one | mean -3.35c |\n"                 # INHERITED
            + "\n" * (LOOKBACK + 2) +
            "orphaned mean -1.11c far below the header\n"  # UNLABELLED
            "phantom share was 63.9% of fills\n"          # not a cent figure
            "median quoted spread is 11.0c on CFB\n"      # a SPREAD, not an
                                                          # estimate -> skipped
            "tick size 1.0c and a 0.5c concession\n"      # prices -> skipped
            "excess +4.24c [+1.26c, +7.22c]\n"            # interval -> counted
        )
        got = list(scan(p))
        states = [s for _, s, _ in got]
        check(f"four estimates found; spreads and prices ignored ({len(got)})",
              len(got) == 4)
        check(f"states are LABELLED/INHERITED/UNLABELLED/UNLABELLED ({states})",
              states == ["LABELLED", "INHERITED", "UNLABELLED", "UNLABELLED"])
        check("a header beyond LOOKBACK does NOT cover a figure",
              states[2] == "UNLABELLED")
        # THE FALSE-POSITIVE GUARD: a spread is a cent figure with no basis to
        # name. Flagging it is what would get this script disabled.
        flagged = [ln for ln, _, ln_text in
                   [(a, b, c) for a, b, c in got] if "spread" in ln_text]
        check("a median SPREAD is not flagged as needing a basis",
              not flagged)
    return fails


def main(argv: list[str]) -> int:
    targets = [pathlib.Path(a) for a in argv] or [ROOT / "docs" / "math",
                                                  ROOT / "analysis"]
    counts = {"LABELLED": 0, "INHERITED": 0, "UNLABELLED": 0}
    unlabelled: list[tuple[str, int, str]] = []
    for t in targets:
        files = [t] if t.is_file() else [
            f for f in t.rglob("*")
            if f.is_file() and f.suffix in (".md", ".py")
            and not (SKIP_DIRS & set(f.parts))]
        for f in files:
            for ln, state, line in scan(f):
                counts[state] += 1
                if state == "UNLABELLED":
                    unlabelled.append(
                        (str(f.relative_to(ROOT)), ln, line.strip()[:90]))

    total = sum(counts.values())
    print(f"cent figures scanned: {total:,}")
    for k in ("LABELLED", "INHERITED", "UNLABELLED"):
        share = counts[k] / total if total else 0.0
        print(f"  {k:11s} {counts[k]:>5,}  {share:6.1%}")

    if unlabelled:
        print(f"\nUNLABELLED (first 15 of {len(unlabelled)}):")
        for f, ln, line in unlabelled[:15]:
            print(f"  {f}:{ln}  {line}")

    print("\nINHERITED is not a pass. A header covers a figure until someone")
    print("quotes the row without it, which is how all three of today's")
    print("collisions happened.")
    return 0


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    print()
    sys.exit(main(sys.argv[1:]))
