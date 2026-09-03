#!/usr/bin/env python3
"""Which WAVE_STANDARD rules are ENFORCED, and which are merely written down.

DERIVED, NEVER HAND-MAINTAINED. A hand-kept column claiming "enforced by code"
is a name asserting a property (rule 23), and its absent red mark reads as
evidence of enforcement (rule 22). It would drift into claiming coverage we do
not have, which is worse than having no column at all.

THREE STATES, because two would hide the uncomfortable one:

  PROSE       no guard function exists — the rule asks for carefulness
  UNWIRED     a guard exists but nothing calls it outside its own selftest
              -- "a guard that exists and isn't called is a prose rule with
              extra steps"
  WIRED       called from at least one path that is not the guard's own tests

Run from the repo root:  python3 scripts/guard_coverage.py
Exit code is 0 always; this reports, it does not gate.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARDS = ROOT / "analysis" / "guards.py"

#: rule number -> (short name, guard callables that would enforce it)
RULES: dict[int, tuple[str, tuple[str, ...]]] = {
    21: ("profit-mechanism audit", ()),
    22: ("silent absence", ("report_count",)),
    23: ("a name is a claim", ("assert_landmark", "assert_age_non_negative")),
    24: ("counterfactual contains itself", ()),
    25: ("activity-dependent metrics", ("report_composite",
                                        "degenerate_extremes_warning")),
    26: ("a correction is not a certificate", ()),
}

#: Rules whose enforcement is a document rather than a callable. Listed
#: explicitly so an artifact that is not a function is not scored as PROSE.
DOC_ARTIFACTS: dict[int, str] = {
    26: "analysis/SUPERSEDED_FIGURES.md",
}

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "alembic"}


def _sources() -> list[pathlib.Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _defined() -> set[str]:
    if not GUARDS.exists():
        return set()
    return set(re.findall(r"^def (\w+)\(", GUARDS.read_text(), re.M))


def _call_sites(fn: str) -> list[str]:
    """Files calling `fn` that are not the guard module or a test of it."""
    pat = re.compile(rf"\b{re.escape(fn)}\s*\(")
    hits = []
    for p in _sources():
        rel = p.relative_to(ROOT).as_posix()
        if rel == "analysis/guards.py" or "test" in p.name.lower():
            continue
        txt = p.read_text(errors="ignore")
        # a definition is not a call site
        if pat.search(txt) and not re.search(rf"^def {re.escape(fn)}\(", txt, re.M):
            hits.append(rel)
    return sorted(hits)


def main() -> int:
    defined = _defined()
    rows = []
    for num in sorted(RULES):
        name, fns = RULES[num]
        if not fns:
            doc = DOC_ARTIFACTS.get(num)
            if doc and (ROOT / doc).exists():
                rows.append((num, name, "PART-CODED", f"artifact: {doc}"))
            else:
                rows.append((num, name, "PROSE", "no guard function"))
            continue
        missing = [f for f in fns if f not in defined]
        if missing:
            rows.append((num, name, "PROSE", f"guard(s) absent: {', '.join(missing)}"))
            continue
        sites: list[str] = []
        for f in fns:
            sites += _call_sites(f)
        sites = sorted(set(sites))
        if sites:
            rows.append((num, name, "WIRED", ", ".join(sites[:3])))
        else:
            rows.append((num, name, "UNWIRED",
                         f"{', '.join(fns)} — defined, called by nothing"))

    w = max(len(r[1]) for r in rows)
    print(f"{'RULE':<5} {'NAME':<{w}}  {'STATE':<10} DETAIL")
    print("-" * (5 + w + 14 + 40))
    for num, name, state, detail in rows:
        print(f"{num:<5} {name:<{w}}  {state:<10} {detail}")

    counts: dict[str, int] = {}
    for _, _, state, _ in rows:
        counts[state] = counts.get(state, 0) + 1
    print()
    print("  " + " · ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if counts.get("UNWIRED"):
        print()
        print("  UNWIRED guards enforce nothing. A guard that exists and is not")
        print("  called is a prose rule with extra steps — and it is WORSE than")
        print("  prose, because its existence reads as coverage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
