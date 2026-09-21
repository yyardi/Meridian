"""The taker fee is one constant, and it is the venue's.

    pytest --noconftest tests/test_fee_is_one_constant.py

The venue raised its taker coefficient from 0.06 to 0.0695 on 2026-09-17
(`market_snapshots.fee_coefficient`: 63.5M rows at 0.06 through that day,
every row since at 0.0695). The tree carried 0.06 in ten places under two
provenance claims, and nothing compared any of them to the field, so for
four days every fee was 16 % light with every log green. The sweep on
2026-09-21 touched the ladder scanner, the backtest fill model, the gridiron
scalp, the quote wallet, ten research runners and eight test files that had
pinned arithmetic at 0.06 -- and this test's first run found the tenth
runner (`cfb/run_scan.py`) and three prose sites the hand sweep had missed.

This sweeps the family, not the instance. Three things are checked, by
parsing rather than by grep, so a fee literal inside prose and a fee literal
inside a charge are told apart:

  1. every float literal 0.06 in core/, cfb/ or scripts/ is the value of one
     of the NAMED non-fee constants below (spread caps, a skew threshold) --
     any other 0.06 in code is presumed to be a fee and fails;
  2. no comment or string says the fee is 0.06 (a description has no test,
     so the description is tested here);
  3. `core.fees` holds the venue's numbers.
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import sys
import tokenize

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from core import fees  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TREES = ("core", "cfb", "scripts")

#: 0.06 by coincidence: spread caps and a skew threshold, none a fee. A new
#: non-fee 0.06 is added here with its reason, so the next reader knows it
#: was looked at rather than missed.
NOT_FEES = {
    ("core/api.py", "MAX_TRADEABLE_SPREAD"),
    ("core/pulse/overreaction.py", "ROUND_TRIP_COST"),
    ("cfb/run_making_touch.py", "SKEW_EDGE"),
    ("cfb/run_ladder_rv.py", "MAX_LEG_SPREAD"),
    ("cfb/run_longshot_shadow.py", "SPREAD_CAP"),
}

#: Prose that calls 0.06 a fee: a fee word within 40 characters of the
#: literal, either side. "spread cap 0.06" and "0.06000000000000005 in
#: floats" do not match; "fee 0.06*p*(1-p)" and "theta_taker = 0.06" do.
FEE_PROSE = re.compile(
    r"(?i)(fee|theta|taker)[^\n]{0,40}(?<![\d.])0\.06(?![\d])"
    r"|(?<![\d.])0\.06(?![\d])[^\n]{0,40}(fee|theta|taker)"
)


def _py_files():
    for tree in TREES:
        yield from sorted((ROOT / tree).rglob("*.py"))


def _rel(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT))


def _named_0_06_constants(tree: ast.Module, rel: str):
    """(file, NAME) for every module-level `NAME = 0.06` or a 0.06 inside a
    tuple assignment `A, B = 0.06, ...`."""
    out = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t, v = node.targets[0], node.value
        if isinstance(t, ast.Name) and isinstance(v, ast.Constant) and v.value == 0.06:
            out.add((rel, t.id))
        elif isinstance(t, ast.Tuple) and isinstance(v, ast.Tuple):
            for name, val in zip(t.elts, v.elts):
                if isinstance(name, ast.Name) and isinstance(val, ast.Constant) and val.value == 0.06:
                    out.add((rel, name.id))
    return out


def test_the_venue_s_coefficient_is_the_one_constant():
    assert fees.POLYMARKET_TAKER == 0.0695
    assert fees.taker_fee(0.5) == 0.0695 * 0.25
    assert fees.KALSHI_TAKER == 0.07 and fees.POLYMARKET_MAKER == 0.0


def test_every_0_06_literal_in_code_is_a_named_non_fee_constant():
    """Walk the AST: each `0.06` float is either the value of an allowlisted
    name or an offender. This catches `FEE = 0.06`, `k = 0.06` as a default
    argument, and a bare `0.06 * p * (1 - p)` alike."""
    named, offenders = set(), []
    for p in _py_files():
        rel = _rel(p)
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        mine = _named_0_06_constants(tree, rel)
        named |= mine
        allowed_lines = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and (rel, t.id) in NOT_FEES for t in
                (node.targets[0].elts if isinstance(node.targets[0], ast.Tuple) else node.targets)
            ):
                allowed_lines.add(node.lineno)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float) \
                    and node.value == 0.06 and node.lineno not in allowed_lines:
                offenders.append((rel, node.lineno))
    assert not offenders, f"a 0.06 in code that is not a named non-fee constant: {offenders}"
    assert named == NOT_FEES, (named - NOT_FEES, NOT_FEES - named)


def test_no_comment_or_string_calls_0_06_the_fee():
    """core/fees.py is exempt: it is the provenance, and its job is to say
    what the coefficient was before the venue raised it."""
    offenders = []
    for p in _py_files():
        rel = _rel(p)
        if rel == "core/fees.py":
            continue
        toks = tokenize.generate_tokens(io.StringIO(p.read_text(encoding="utf-8")).readline)
        for tok in toks:
            if tok.type in (tokenize.COMMENT, tokenize.STRING) and FEE_PROSE.search(tok.string):
                offenders.append((rel, tok.start[0]))
    assert not offenders, f"prose that still calls the fee 0.06: {offenders}"
