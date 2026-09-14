"""An instrument must not carry its own copy of a production threshold.

A measuring script that keeps a private copy of the number it measures
against will disagree with production the first time anyone tunes the
threshold, and it will do so SILENTLY — reporting a rate for a gate that no
longer exists. `cfb/run_gate_replay.py` avoids it by construction: it reads
MAX_AGE_S from `core.gridiron.scalp.params_from_env` rather than restating
30.

This sweep looks for the rest of the family. It keys on NAME, not on value:
keyed on value it returned 383 pairs, almost all of them two unrelated
constants that both happen to be 30 or 120. A value match is a coincidence
detector; the matcher has to match the thing, not a proxy for it.
"""

from __future__ import annotations

import ast
import glob
import os
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Same name in `core/` and in an instrument, WITH THE SAME VALUE: a copy
#: waiting to drift. Recorded rather than banned, because sharing a name is
#: not proof of sharing a meaning.
KNOWN_COPIES = {
    ("analysis/quote_v2_markout.py", "REGULATION_MINUTES"),
    ("scripts/export_wnba_trades.py", "PAGE_LIMIT"),
    ("scripts/export_wnba_trades.py", "PAGE_PAUSE_SECONDS"),
}

#: Same name, DIFFERENT value: already drifted. One entry, and it is a real
#: divergence rather than a coincidence — both walk `/v1/portfolio/activities`
#: with the same PAGE_LIMIT and PAGE_PAUSE_SECONDS and the same `for _ in
#: range(MAX_PAGES)` loop, and they also disagree about what exhausting the
#: cap MEANS: core/audit/hand_trades.py logs a warning and returns a PARTIAL
#: list, while the export script raises. Production is the permissive one.
#: Routed 2026-09-14; resolving it is a judgement about which failure mode the
#: audit should have, not a rename.
KNOWN_DRIFT = {("scripts/export_wnba_trades.py", "MAX_PAGES"): (200.0, 50.0)}


def _consts(path: str) -> dict[str, float]:
    """Module-level `NAME = <number>`, including `A * B` forms like 3 * 3600.

    WHAT THIS CANNOT CATCH, and it is the case that motivated the sweep.
    Putting `max_age_s = 30.0` inside `main()` of cfb/run_gate_replay.py —
    the exact defect this exists to prevent — passes. I widened the matcher
    to walk locals and fold case, re-ran the mutation, and it STILL passed:
    copies 3 and drift 1 either way, byte-identical. The reason is on the
    PRODUCTION side, not the instrument side. `core/gridiron/scalp.py` has no
    module-level `MAX_AGE_S`; the threshold lives as a string default inside
    `params_from_env`, so there was never a named constant to collide with. I
    widened the wrong end, and the widening was dead complexity — reverted.

    So this guard covers thresholds that production states as a module-level
    NAMED CONSTANT. A threshold that lives in an env-var default is outside
    its reach, and saying so is better than a guard whose docstring claims
    the case it cannot see.
    """
    try:
        tree = ast.parse(open(path).read())
    except (SyntaxError, UnicodeDecodeError):
        return {}
    out: dict[str, float] = {}
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        v = node.value
        key = node.targets[0].id
        if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) \
                and not isinstance(v.value, bool):
            out[key] = float(v.value)
        elif (isinstance(v, ast.BinOp) and isinstance(v.op, ast.Mult)
              and isinstance(v.left, ast.Constant)
              and isinstance(v.right, ast.Constant)):
            try:
                out[key] = float(v.left.value) * float(v.right.value)
            except (TypeError, ValueError):
                pass
    return out


def _sweep():
    prod = defaultdict(list)
    for f in glob.glob(os.path.join(REPO, "core", "**", "*.py"), recursive=True):
        for n, v in _consts(f).items():
            prod[n].append((os.path.relpath(f, REPO), v))

    copies, drift = set(), {}
    for pat in ("cfb/*.py", "scripts/*.py", "analysis/*.py"):
        for f in sorted(glob.glob(os.path.join(REPO, pat))):
            rel = os.path.relpath(f, REPO)
            for n, v in _consts(f).items():
                for _, pv in prod.get(n, []):
                    if v == pv:
                        copies.add((rel, n))
                    else:
                        drift[(rel, n)] = (v, pv)
    return copies, drift


def test_no_new_instrument_copies_a_production_threshold():
    copies, _ = _sweep()
    new = copies - KNOWN_COPIES
    assert not new, (
        f"an instrument now carries its own copy of a production constant: "
        f"{sorted(new)}. Import it instead — cfb/run_gate_replay.py reads "
        "MAX_AGE_S from params_from_env rather than restating 30, which is "
        "why it cannot silently measure against a gate that no longer exists. "
        "If the name collision is a coincidence, add it to KNOWN_COPIES with "
        "the reason.")


def test_no_new_threshold_has_drifted():
    _, drift = _sweep()
    new = {k: v for k, v in drift.items() if k not in KNOWN_DRIFT}
    assert not new, (
        f"a constant shared with core/ now holds a different value: {new}. "
        "This is the failure the sweep exists for: both copies are right "
        "today and they disagree about a limit that will bind at different "
        "times, silently. Resolve it or record it in KNOWN_DRIFT with the "
        "reason it is not the same quantity.")


def test_the_known_drift_is_still_the_one_we_recorded():
    """A pinned inventory, so RESOLVING the drift also fails and the record
    gets updated. An allowlist nobody has to revisit grows quietly."""
    _, drift = _sweep()
    assert {k: v for k, v in drift.items() if k in KNOWN_DRIFT} == KNOWN_DRIFT, (
        "the recorded drift changed or was fixed — update KNOWN_DRIFT")
