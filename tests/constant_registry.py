"""Where does this number come from, and does the code still say it?

2026-09-06. Four constants that decide whether we trade — one of them setting
a published floor — turned out to be absent from the repository entirely. Not
unreproducible: UNLOCATABLE. They lived in an untracked STATUS.md, in session
messages, and on unpushed branches, so nobody outside that conversation could
find them, let alone check them. Two were later withdrawn and one corrected,
and both errors flattered us.

c7's general form is why they survived: **a conservative unmeasured constant
survives audit longest, because nobody challenges a figure that argues against
them.**

WHAT THIS GATES (hard failures — these are properties, not opinions)
-------------------------------------------------------------------
  * a registered value must MATCH the assignment at the site that uses it, so
    the registry cannot drift from the code
  * a MEASURED claim must carry dataset + method + n, and n > 0
  * a PROVISIONAL claim must carry its caveat AND a registration that will
    settle it
  * a POLICY claim must say what would change it
  * the UNSOURCED count may not exceed the committed ceiling

WHAT IT REPORTS (loudly, and does not gate)
-------------------------------------------
The unsourced inventory, with an owner each, as a COUNT rather than a list —
14 to 11 to 9 gets attention where a list does not. `scripts/guard_coverage.py`
is this repo's precedent for the shape: three states, exit 0 always, "this
reports, it does not gate". A second convention for the same thing would be
worse than either.

★ THE TEMPLATE ★ `RULE_OF_THUMB_SIGMA` is what a correctly-held unmeasured
constant looks like, and the report points at it: an NBA number used for the
WNBA, LABELLED as such, with the error quantified (1.31x; a 4-point lead at
the half worth 0.63 against 0.68) and a live registration to settle it. An
unmeasured number is not a defect. An unmeasured number pretending otherwise
is.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
from dataclasses import dataclass
from enum import Enum

REPO = pathlib.Path(__file__).resolve().parent.parent

#: The unsourced count may not RISE. Lower it when one is sourced; raising it
#: is a deliberate, visible act in a diff.
UNSOURCED_CEILING = 0


class Kind(Enum):
    MEASURED = "measured"        # from data: needs dataset + method + n
    POLICY = "policy"            # a decision: needs what would change it
    PROVISIONAL = "provisional"  # borrowed/unmeasured, LABELLED, with a
                                 # registration open to settle it
    UNSOURCED = "unsourced"      # no derivation anyone can follow


@dataclass(frozen=True)
class Constant:
    name: str
    value: float
    site: str                    # "path.py" holding the assignment
    kind: Kind
    document: str = ""           # where the derivation is written down
    dataset: str = ""            # MEASURED: the table/export
    method: str = ""             # MEASURED: how, in words, not the doc's own expression
    n: int = 0                   # MEASURED: sample size
    population: str = ""         # MEASURED: the PREDICATE defining the rows.
                                 # "settled = strict post row" vs "post OR
                                 # untied P4 0:00" swung a cohort 18 -> 31,
                                 # a 72% move on an unstated definition.
    changes_if: str = ""         # POLICY: what would move it
    caveat: str = ""             # PROVISIONAL: why it is known-wrong
    registration: str = ""       # PROVISIONAL: what will settle it
    owner: str = ""              # UNSOURCED: who owes the derivation


#: Seeded ONLY with constants verifiable in this repository. The four that
#: prompted this file are deliberately absent: registering them from session
#: chatter would manufacture exactly the authority the gate exists to check.
REGISTRY: tuple[Constant, ...] = (
    Constant("FLOOR_GAMES", 10, "core/pulse/live_report.py", Kind.POLICY,
             document="docs/math/pulse-live.md",
             changes_if="a re-registration before data accrues; the floors "
                        "were fixed before the first cycle and moving them "
                        "after is the thing pre-registration prevents"),
    Constant("FLOOR_ENTRY_FILLS", 100, "core/pulse/live_report.py", Kind.POLICY,
             document="docs/math/pulse-live.md",
             changes_if="as FLOOR_GAMES — same registration, same rule"),
    Constant("MAX_OBSERVATION_AGE_SECONDS", 600.0, "core/quote/engine.py",
             Kind.POLICY,
             document="core/quote/engine.py docstring",
             changes_if="evidence that a stale book can fill; the value is a "
                        "refusal to fill from an observation that old, not a "
                        "measurement of anything"),
    Constant("RULE_OF_THUMB_SIGMA", 2.0, "core/pulse/win_curve.py",
             Kind.PROVISIONAL,
             document="docs/math/win-curve.md:78",
             caveat="an NBA number used for the WNBA, which plays 40 minutes "
                    "not 48 with higher per-minute variance. 1.31x off — at "
                    "the half, a 4-point lead worth 0.63 against 0.68",
             registration="docs/math/nba-constants-registrations.md, arm (c), "
                          "gated on paired Brier with >= 8 forward seasons"),
)


def assigned_value(site: str, name: str) -> float | None:
    """The literal actually assigned at the site, read from the AST.

    Not a regex over the line: a comment or a docstring mentioning the number
    would satisfy that, and the point is what the code DOES."""
    tree = ast.parse((REPO / site).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    if isinstance(node.value, ast.Constant):
                        return float(node.value.value)
    return None


def _tracked() -> set[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files"],
                         capture_output=True, text=True, check=True).stdout
    return set(out.splitlines())


#: A module-level constant worth registering looks like this. Deliberately
#: crude: the point is to COUNT what exists, not to judge it.
_CANDIDATE = "core"


def find_candidates(tracked=None) -> list[tuple[str, str, float]]:
    """Every module-level UPPER_CASE numeric assignment in tracked core/ files.

    ★ WHY THIS EXISTS. A hand-seeded registry reporting "0 unsourced" is a
    clean bill of health produced by ABSENCE — the same presence-blind-to-
    absence failure this repo has hit all day, inside the instrument built to
    catch provenance failures. The registry cannot tell you what it does not
    contain, so something has to count what is out there.
    """
    files = _tracked() if tracked is None else tracked
    out: list[tuple[str, str, float]] = []
    for rel in sorted(f for f in files
                      if f.startswith(_CANDIDATE + "/") and f.endswith(".py")):
        try:
            tree = ast.parse((REPO / rel).read_text())
        except (SyntaxError, FileNotFoundError):
            continue
        for node in tree.body:                       # module level only
            if not isinstance(node, ast.Assign):
                continue
            for t in node.targets:
                if (isinstance(t, ast.Name) and t.id.isupper()
                        and isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, (int, float))
                        and not isinstance(node.value.value, bool)):
                    out.append((rel, t.id, float(node.value.value)))
    return out


def gate(registry=REGISTRY, tracked=None) -> list[str]:
    """Hard failures only. Returns reasons; empty means pass."""
    bad: list[str] = []
    files = _tracked() if tracked is None else tracked
    for c in registry:
        # ★ THE RULE THE WHOLE FILE EXISTS FOR. A constant whose site is not
        # tracked is unlocatable to anyone who was not in the conversation —
        # which is precisely how 1.193c set a published floor from an
        # untracked STATUS.md. scripts/alarm_v5.py is in this state today, so
        # its constants are deliberately NOT registered rather than registered
        # with provenance nobody else can reach.
        if c.site not in files:
            bad.append(f"{c.name}: site {c.site} is not tracked by git — a "
                       "constant in an untracked file cannot be checked by "
                       "anyone else, which is how the 2026-09-06 four became "
                       "unlocatable")
            continue
        actual = assigned_value(c.site, c.name)
        if actual is None:
            bad.append(f"{c.name}: no assignment found in {c.site}")
        elif actual != c.value:
            bad.append(f"{c.name}: registry says {c.value}, {c.site} says "
                       f"{actual} — the registry has drifted from the code")
        if c.kind is Kind.MEASURED and not (c.dataset and c.method and c.n > 0):
            bad.append(f"{c.name}: claims MEASURED without dataset+method+n")
        if c.kind is Kind.MEASURED and not c.population:
            bad.append(f"{c.name}: claims MEASURED without a POPULATION "
                       "predicate — which rows counted is the definition, and "
                       "an unstated one swung a cohort 18 -> 31 on 2026-09-06")
        if c.kind is Kind.PROVISIONAL and not (c.caveat and c.registration):
            bad.append(f"{c.name}: claims PROVISIONAL without a caveat and a "
                       "registration to settle it")
        if c.kind is Kind.POLICY and not c.changes_if:
            bad.append(f"{c.name}: claims POLICY without saying what would "
                       "change it")
        if c.kind is Kind.UNSOURCED and not c.owner:
            bad.append(f"{c.name}: UNSOURCED with no owner")
    # THE CRAWLER MUST WORK, or a small inventory reads as a clean bill of
    # health. Every registered constant must be findable by the search; if it
    # is not, the search is broken and its coverage number is meaningless.
    found = {(site, name) for site, name, _ in find_candidates(tracked)}
    for c in registry:
        if c.site.startswith(_CANDIDATE + "/") and (c.site, c.name) not in found:
            bad.append(f"{c.name}: registered but the crawler does not find "
                       f"it in {c.site} — the search is broken, so any "
                       "coverage figure it reports is worthless")
    n = sum(1 for c in registry if c.kind is Kind.UNSOURCED)
    if n > UNSOURCED_CEILING:
        bad.append(f"{n} unsourced constant(s) against a ceiling of "
                   f"{UNSOURCED_CEILING} — the count may not rise")
    return bad


def report(registry=REGISTRY) -> str:
    """The loud half. Reports, does not gate — guard_coverage.py's shape."""
    out = ["LOAD-BEARING CONSTANTS", "=" * 60]
    for kind in Kind:
        rows = [c for c in registry if c.kind is kind]
        out.append(f"\n{kind.value.upper():<12} {len(rows)}")
        for c in rows:
            out.append(f"  {c.name:<28} {c.value:<8} {c.site}")
            if kind is Kind.UNSOURCED:
                out.append(f"      OWES A DERIVATION — owner: {c.owner or '???'}")
    n = sum(1 for c in registry if c.kind is Kind.UNSOURCED)
    cands = find_candidates()
    reg_sites = {(c.site, c.name) for c in registry}
    unregistered = [x for x in cands if (x[0], x[1]) not in reg_sites]
    out += ["",
            f"UNSOURCED: {n} (ceiling {UNSOURCED_CEILING}, may only fall)",
            "",
            f"COVERAGE: {len(reg_sites)} registered of {len(cands)} module-level "
            f"constants found in {_CANDIDATE}/",
            f"  {len(unregistered)} UNREGISTERED — this number, not the "
            "unsourced count, is what a clean report is hiding behind.",
            "  A small inventory is a failure of the SEARCH until shown "
            "otherwise; the crawler is gated on finding every registered one."]
    tmpl = next((c for c in registry if c.kind is Kind.PROVISIONAL), None)
    if tmpl:
        out += ["",
                "What a correctly-held unmeasured constant looks like:",
                f"  {tmpl.name} — {tmpl.caveat}",
                f"  settled by: {tmpl.registration}",
                "  An unmeasured number is not a defect. One pretending "
                "otherwise is."]
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
    for r in gate():
        print("FAIL:", r)
