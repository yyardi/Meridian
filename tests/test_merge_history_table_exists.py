"""`table_exists` in deploy/aws/merge_history.sh must not call a failure absent.

The helper is extracted and run with a stub `DST`, so both branches execute
without a database.
"""
from __future__ import annotations

import pathlib
import subprocess

import pytest

SH = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "aws" / "merge_history.sh"
SRC = SH.read_text()


def _run(dst_body: str, arg: str = "s.t"):
    """Source just the helper, with DST replaced by a stub."""
    fn = SRC[SRC.index("table_exists() {"):]
    fn = fn[:fn.index("\n}\n") + 3]
    script = f"set -uo pipefail\nDST() {{ {dst_body} }}\n{fn}\n" \
             f"if table_exists '{arg}'; then echo PRESENT; else echo ABSENT; fi\n"
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


def test_present_when_the_query_says_t():
    r = _run("echo t;")
    assert r.returncode == 0 and "PRESENT" in r.stdout, (r.stdout, r.stderr)


def test_absent_when_the_query_says_f():
    """The control. If this failed, the helper would be refusing everything and
    the test below would pass for the wrong reason."""
    r = _run("echo f;")
    assert r.returncode == 0 and "ABSENT" in r.stdout, (r.stdout, r.stderr)


def test_an_UNREACHABLE_database_aborts_instead_of_answering_absent():
    """★ THE POINT, AND IT IS A MIGRATION SCRIPT. Five sites read table
    existence through `... | grep -q t` and mapped the result onto
    absent/present with `&&`, `||` or `if`. `set -o pipefail` is on, so the
    STATUS was already correct -- and the logic still turned a psql failure into
    "the table is not there": an existing remap looked absent and got rebuilt, a
    present parent looked absent and the remap was silently skipped, one loop
    did `|| continue`, and two `if`s took the else branch. A partial migration
    that reports success.

    `set -e` does NOT protect a condition -- it is suspended for commands in
    `&&`/`||`/`if` -- which is exactly why the defect clustered there and why
    the sibling at line 293, a plain assignment, is safe: `V=$(failing)` does
    abort under `set -e` (verified)."""
    r = _run("return 7;")
    assert r.returncode != 0, f"a database failure answered the question: {r.stdout}"
    assert "ABSENT" not in r.stdout and "PRESENT" not in r.stdout
    assert "cannot query the database" in r.stderr
    assert "absent table" in r.stderr


def test_no_existence_check_bypasses_the_helper():
    """Every `to_regclass` existence test must go through it, or the next one
    added reintroduces the conflation. The two allowed mentions are the helper's
    own query and its docstring."""
    lines = [ln.strip() for ln in SRC.splitlines()
             if "to_regclass" in ln and not ln.strip().startswith("#")]
    # Exactly two live uses, and each is accounted for:
    #   1. the helper's own query
    #   2. line ~293's `HAS=$(SRC ... | tr -d)`, which is an ASSIGNMENT and
    #      therefore safe -- `set -e` aborts on a failing assignment
    #      substitution, verified, which is why it was never the defect.
    assert len(lines) == 2, "an unaccounted existence check:\n" + "\n".join(lines)
    assert any("out=$(DST" in ln for ln in lines), lines
    assert any(ln.startswith("HAS=$(SRC") for ln in lines), lines
    # and the piped condition form is gone from the CODE. Scoped to non-comment
    # lines because the helper's own comment quotes the old form verbatim -- the
    # third time today a source-text assertion matched prose describing the
    # thing it was banning.
    code = [ln for ln in SRC.splitlines() if not ln.strip().startswith("#")]
    assert not [ln for ln in code if "grep -q t" in ln], (
        "a piped existence check remains in the code")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
