#!/usr/bin/env python3
"""Which decision-path functions are named by NO test, and which are covered
only by a file that happens to import their module.

WHY THIS EXISTS, in one measurement: `core/backtest/exp_devigged_clv.py` has
a test file, `tests/test_devigged_clv.py`. That file never mentions
`analyse()`. A sign error at exp_devigged_clv.py:133 would have flipped every
CLV number in the project and the suite would have stayed green. Module-level
coverage calls that module COVERED. Symbol-level does not.

Three properties chosen deliberately:

  STATIC.   It parses definitions with ast and greps the tests as text. It
            never runs pytest, so an unrelated red test cannot redden it.
            That matters here: one test is red on main and a gate that goes
            red on day one gets disabled on day one.
  FAST.     Milliseconds. Cheap enough to sit in the pre-commit hook, which
            is the only automation in this repo that actually runs.
  BASELINED. It reports a rise, not an absolute. Driving UNNAMED to zero
            would mean writing tests for __main__ wrappers.

WHAT IT DOES NOT DO, stated because the gap is the whole point of the tool
next to it: naming is not exercising. A symbol named once in an import line
and never called reads as NAMED here. This finds the symbols with no test
AT ALL -- the cheapest and largest class -- and is blind to a test that runs
a function while asserting nothing that could fail. Only a mutation check
answers that one; see the ROI assertions c7 found on 2026-09-06, where the
symbol was named, the test ran, and the assertion could not fail.

    python3 scripts/symbol_test_naming.py [module.py ...]
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The decision path: modules whose behaviour decides a quoted price, a fill,
#: or a reported number. Deliberately a NAMED LIST rather than "everything" --
#: a whole-repo scan reports hundreds of untested __main__ helpers and gets
#: ignored, which is how a guard dies.
TARGETS = (
    "core/quote/engine.py",
    "core/quote/adverse_selection.py",
    "core/quote/storage.py",
    "core/quote/report.py",
    "core/quote/depth_signal.py",
    "core/backtest/exp_devigged_clv.py",
    "core/leagues.py",
    "core/live_fv.py",
)

#: Measured 2026-09-06 at 5. The five are `run_forever` and `main`-style
#: entry points plus two loaders and one analysis function; the loaders and
#: `analyse` are REAL and are the reason this exists. Lower it as they are
#: covered -- that locks the improvement in. Raise it only with the reason in
#: the same commit.
BASELINE_UNNAMED = 5


def public_symbols(path: pathlib.Path) -> list[str]:
    """Top-level functions and public methods, excluding _private ones."""
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except (OSError, SyntaxError):
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                out.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if (isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and not sub.name.startswith("_")):
                    out.append(f"{node.name}.{sub.name}")
    return out


def test_corpus(tests: pathlib.Path) -> str:
    if not tests.is_dir():
        return ""
    return "\n".join(p.read_text(errors="replace")
                     for p in sorted(tests.rglob("test_*.py")))


def unnamed(path: pathlib.Path, corpus: str) -> list[str]:
    """Public symbols of `path` that no test mentions by name."""
    out = []
    for name in public_symbols(path):
        bare = name.split(".")[-1]
        if not re.search(rf"\b{re.escape(bare)}\b", corpus):
            out.append(name)
    return out


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "tests").mkdir()
        (root / "tests" / "test_x.py").write_text(
            "from m import kept, C\n"
            "def test_kept():\n    assert kept()\n"
            "def test_method():\n    assert C().method_seen()\n")
        mod = root / "m.py"
        mod.write_text(
            "def kept():\n    return 1\n"
            "def missing():\n    return 2\n"
            "def _private():\n    return 3\n"
            "class C:\n"
            "    def method_seen(self):\n        return 4\n"
            "    def method_gone(self):\n        return 5\n")
        corpus = test_corpus(root / "tests")
        syms = public_symbols(mod)
        check(f"private functions excluded ({syms})", "_private" not in syms)
        check("methods are found as Class.method",
              "C.method_seen" in syms and "C.method_gone" in syms)
        got = unnamed(mod, corpus)
        check(f"exactly the unnamed ones reported ({got})",
              got == ["missing", "C.method_gone"])

        # THE REGRESSION THIS FILE'S SIBLING SHIPPED WITH: the argument path
        # of main() was never exercised, so it raised on every relative path
        # while the selftest stayed green. Run main() here, for real.
        import contextlib
        import io
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main([str(mod)])
            # NOT asserting on `missing` here: with explicit paths main()
            # greps the REPO's tests, where a common word may well appear.
            # The property under test is that the path runs and reports.
            ok = rc == 0 and "m.py" in buf.getvalue()
        except Exception as exc:                       # noqa: BLE001
            ok = False
            print(f"    main() raised {type(exc).__name__}: {exc}")
        check("main() runs on an explicit path outside ROOT", ok)

        # A named-but-vacuous test still reads as NAMED. Pinned so nobody
        # mistakes this tool for one that measures whether a test can fail.
        (root / "tests" / "test_y.py").write_text(
            "import m\ndef test_nothing():\n    assert m.missing is not None\n")
        check("naming is not exercising: a vacuous test marks it NAMED",
              "missing" not in unnamed(mod, test_corpus(root / "tests")))
    return fails


def main(argv: list[str]) -> int:
    corpus = test_corpus(ROOT / "tests")
    if argv:
        paths = [pathlib.Path(a) for a in argv]
        # an explicit path may sit outside ROOT (the selftest passes one);
        # fall back to its own sibling tests/ so the run still means something
        if not corpus:
            corpus = test_corpus(paths[0].resolve().parent / "tests")
    else:
        paths = [ROOT / t for t in TARGETS]

    total = named = 0
    misses: list[tuple[str, str]] = []
    for p in paths:
        if not p.exists():
            print(f"  {str(p):46s}  ABSENT on this branch")
            continue
        syms = public_symbols(p)
        miss = unnamed(p, corpus)
        total += len(syms)
        named += len(syms) - len(miss)
        try:
            rel = str(p.resolve().relative_to(ROOT))
        except ValueError:
            rel = str(p)
        tail = "" if not miss else "  <-- " + ", ".join(miss[:6])
        print(f"  {rel:46s}  {len(syms) - len(miss)}/{len(syms)}{tail}")
        misses.extend((rel, m) for m in miss)

    n = len(misses)
    print(f"\n  {named}/{total} public symbols named by at least one test "
          f"({n} unnamed)")

    if argv:
        return 0
    if n > BASELINE_UNNAMED:
        print(f"\n  *** REGRESSION: {n} unnamed against a baseline of "
              f"{BASELINE_UNNAMED} (+{n - BASELINE_UNNAMED}) ***")
        print("  A new decision-path function has no test naming it. Either")
        print("  write one, or raise BASELINE_UNNAMED with the reason here.")
    elif n < BASELINE_UNNAMED:
        print(f"\n  improved: {n} against a baseline of {BASELINE_UNNAMED};"
              " lower the baseline to lock it in.")
    else:
        print(f"\n  at baseline ({BASELINE_UNNAMED}).")

    print("\nNAMED is not TESTED. This finds symbols with no test at all;")
    print("a test that runs a function and asserts nothing that can fail")
    print("reads as NAMED here and needs a mutation check instead.")
    return 0


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    print()
    sys.exit(main(sys.argv[1:]))
