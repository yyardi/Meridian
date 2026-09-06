"""`decision_hash` — cohort identity for the QUOTE decision path.

WHY NOT THE REPO COMMIT. `engine_commit` moves for docs, dashboards and
unrelated subsystems. On 2026-09-04 a deploy mid-CFB-slate changed a Kalshi
poll interval and a Kalshi column; `core/quote/` was byte-identical across it,
yet 9 of 61 games "straddled a commit boundary" and a sensitivity was run that
measured nothing. Cohort identity has to track the code that decides quotes.

WHY NOT THE TRANSITIVE IMPORT CLOSURE EITHER — measured, not assumed. The
first-party closure from `core/quote/engine.py` is 12 files, which is small
enough to be tempting. But it contains `core/config.py` and
`core/storage/models.py` — **the exact two files that changed in that
non-behavioural deploy.** A transitive hash would have fragmented the cohort
anyway. The closure is the wrong boundary because it is structural; the
boundary we need is semantic.

★ THE BOUNDARY, NAMED EXPLICITLY (and drift-tested below)

    DECISION_FILES — source that maps observations -> quotes -> booked fills
    DECISION_ENV   — environment variables those files READ AT RUNTIME

**The env half is not optional.** `core/quote/engine.py:106` resolves
`MERIDIAN_QUOTE_INTERVAL_SECONDS` (default 5) — the requote cadence, which
determines the entire fill pattern — and `core/leagues.py:115` resolves
`MERIDIAN_LEAGUE`. Hashing source alone would call a run with a 10-second
cycle identical to one with a 5-second cycle. That is "configured is not
measured" in its purest form, and it is why this hash covers resolved VALUES
and not merely the code that reads them.

A change that MUST move the hash:  `MAX_SPREAD` in adverse_selection.py — it
                                   decides which markets are quotable at all.
A change that must NOT move it:    the 2026-09-04 Kalshi poll interval and
                                   `venue_occurrence_time` column.
Both are asserted against real commits in `_selftest`.

★ WHAT THIS CANNOT DETECT — say it before it bites someone

`decision_hash` partitions **code**, not **regime**. Behaviour depends on the
venue and the data too:

- On 2026-09-05 the venue froze prices from ~17:39Z. Fill behaviour changed
  completely — 150/min to 0 — **at a constant decision_hash.**
- Market composition, spread distribution and liquidity all move without any
  deploy. CFB's median spread is 11c against WNBA's 4c; same hash, different
  board.

**So equal `decision_hash` means the code agreed. It does not mean the fills
are comparable.** Cohort identity is a necessary condition for pooling, never
a sufficient one. Anything that pools on hash equality still owes a regime
argument.

It also cannot detect: a dependency version change (numpy, sqlalchemy), a
database schema change reached through the ORM, or a hand-edit on the running
container that never became a commit. The deploy log below closes the last of
those and nothing here closes the first two.
"""
import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Source whose content determines which quotes are placed and which fills are
#: booked. NOT the transitive closure — see the module docstring.
DECISION_FILES = (
    "core/quote/engine.py",            # the loop, requote rule, fill rule
    "core/quote/adverse_selection.py",  # quotable band, Quote
    "core/quote/storage.py",           # BID/ASK/INGAME/PREGAME, fill record
    "core/leagues.py",                 # which markets are in scope
)

#: Environment variables the decision path READS AT RUNTIME. Their resolved
#: values are hashed; the code that reads them is already in DECISION_FILES.
DECISION_ENV = (
    "MERIDIAN_QUOTE_INTERVAL_SECONDS",  # requote cadence -> the fill pattern
    "MERIDIAN_LEAGUE",                  # which league is quoted
)

#: Read by the decision path but deliberately EXCLUDED, with the reason.
EXCLUDED_ENV = {
    "MERIDIAN_QUOTE_ENGINE_COMMIT": "the stamp itself, not behaviour",
    "MERIDIAN_QUOTE_SETTLE_EVERY_SECONDS":
        "settlement sweep cadence; changes when P&L is written, not which "
        "quotes are placed or which fills are booked",
}


def _blob(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def decision_hash(sources: dict[str, str], env: dict[str, str | None]) -> str:
    """Stable hash of (named source contents, resolved env values)."""
    h = hashlib.sha256()
    for name in sorted(sources):
        h.update(name.encode())
        h.update(b"\0")
        h.update(_blob(sources[name]).encode())
        h.update(b"\0")
    for name in sorted(env):
        h.update(name.encode())
        h.update(b"=")
        h.update((env[name] if env[name] is not None else "\0unset").encode())
        h.update(b"\0")
    return h.hexdigest()


def sources_at(ref: str | None = None) -> dict[str, str]:
    """DECISION_FILES contents at a git ref, or from the working tree."""
    if ref is None:
        return {f: (REPO / f).read_text() for f in DECISION_FILES}
    out = {}
    for f in DECISION_FILES:
        r = subprocess.run(["git", "show", f"{ref}:{f}"], cwd=REPO,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"{f} not present at {ref}: {r.stderr.strip()}")
        out[f] = r.stdout
    return out


def env_now() -> dict[str, str | None]:
    return {k: os.environ.get(k) for k in DECISION_ENV}


def env_reads_in_decision_files() -> set[str]:
    """Every env var name literally read by DECISION_FILES.

    The drift guard: a new `os.environ.get(...)` in the decision path must be
    classified as DECISION_ENV or EXCLUDED_ENV, or this set stops matching and
    the test fails. Without it the boundary is a comment that rots.
    """
    found: set[str] = set()
    for f in DECISION_FILES:
        tree = ast.parse((REPO / f).read_text())
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            is_env = (
                isinstance(fn, ast.Attribute) and fn.attr in ("get", "getenv")
                and (
                    (isinstance(fn.value, ast.Attribute)
                     and fn.value.attr == "environ")
                    or (isinstance(fn.value, ast.Name) and fn.value.id == "os")
                )
            )
            if is_env and n.args and isinstance(n.args[0], ast.Constant):
                found.add(n.args[0].value)
    return found


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    # ---- ACCEPTANCE: the 2026-09-04 deploy must NOT move the hash ----------
    A = "4529951a6f225d6581ee65f6169b9284bbcd49a1"
    B = "63e7f1b8bcd06dcfaafc4bd000a8ae0904e53fc8"
    env = {k: None for k in DECISION_ENV}
    try:
        ha = decision_hash(sources_at(A), env)
        hb = decision_hash(sources_at(B), env)
        check(f"the Kalshi-only deploy does NOT move the hash ({ha[:12]})",
              ha == hb)
    except RuntimeError as e:
        check(f"acceptance skipped — {e}", False)

    # ---- a real behaviour change MUST move it -----------------------------
    src = sources_at(None)
    mutated = dict(src)
    key = "core/quote/adverse_selection.py"
    assert "MAX_SPREAD = 0.15" in mutated[key], "band constant moved; fix test"
    mutated[key] = mutated[key].replace("MAX_SPREAD = 0.15",
                                        "MAX_SPREAD = 0.25")
    check("changing MAX_SPREAD DOES move the hash",
          decision_hash(src, env) != decision_hash(mutated, env))

    # ---- and an env change must move it, at identical source --------------
    check("changing the requote cadence moves it at identical source",
          decision_hash(src, {**env, "MERIDIAN_QUOTE_INTERVAL_SECONDS": "10"})
          != decision_hash(src, {**env,
                                 "MERIDIAN_QUOTE_INTERVAL_SECONDS": "5"}))
    check("unset and empty-string are distinguishable",
          decision_hash(src, {**env, "MERIDIAN_LEAGUE": None})
          != decision_hash(src, {**env, "MERIDIAN_LEAGUE": ""}))

    # ---- DRIFT GUARD: no unclassified env read in the decision path -------
    reads = env_reads_in_decision_files()
    known = set(DECISION_ENV) | set(EXCLUDED_ENV)
    unclassified = reads - known
    check(f"every env read is classified (found {len(reads)}, "
          f"unclassified {sorted(unclassified)})", not unclassified)

    # ---- the transitive closure would have FAILED acceptance --------------
    # recorded as a test so the reason for the narrow boundary cannot be lost
    changed = subprocess.run(["git", "diff", "--name-only", A, B],
                             cwd=REPO, capture_output=True, text=True).stdout
    closure_extra = {"core/config.py", "core/storage/models.py"}
    check("the transitive closure would have fragmented this cohort "
          "(config.py / models.py changed and are reachable)",
          bool(closure_extra & set(changed.split())))
    return fails




# ---------------------------------------------------------------------------
# PART 2 — the deploy log, and the check that makes cohorts VERIFIABLE
# ---------------------------------------------------------------------------
#
# Part 1 alone is an INTEGRITY record: every fill carries a hash, and the
# hashes reconcile with each other by construction. It cannot reveal a
# stamping fault, because a wrong stamp applied consistently looks exactly
# like a right one.
#
# Two failures it cannot see:
#   1. A deploy during a quiet period leaves NO trace in the fill tape — no
#      commit change is observable because no fills were written — yet it
#      changes the binary for everything afterwards.
#   2. A stamp that is simply wrong (stale env var, hand-edited container,
#      a build that shipped different source than it recorded).
#
# The deploy log is the second, independent source that turns the integrity
# record into a VALIDITY check.

DEPLOY_LOG_SCHEMA = """
CREATE TABLE quote_deploy_log (
    id                 BIGSERIAL PRIMARY KEY,
    deployed_at        TIMESTAMPTZ NOT NULL,
    from_commit        TEXT,
    to_commit          TEXT NOT NULL,
    from_decision_hash TEXT,
    to_decision_hash   TEXT NOT NULL,
    decision_files     JSONB NOT NULL,   -- the file list the hash covered
    decision_env       JSONB NOT NULL,   -- resolved values, so config is auditable
    note               TEXT
);
CREATE INDEX ON quote_deploy_log (deployed_at);
"""


def active_hash_at(log, ts):
    """The decision_hash the log says was live at `ts`, or None if uncovered.

    `log` is rows of (deployed_at, to_decision_hash) sorted ascending.
    Returns None BEFORE the first entry — uncovered is not the same as
    agreeing, and must never be reported as a pass.
    """
    active = None
    for deployed_at, h in log:
        if deployed_at <= ts:
            active = h
        else:
            break
    return active


def validate_fills(fills, log):
    """Cross-check stamped fills against the deploy log.

    fills: iterable of (filled_at, decision_hash)
    Returns (n_agree, n_disagree, n_uncovered).

    A DISAGREEMENT means the stamp and the log describe different code — one
    of them is wrong and neither can adjudicate alone. That is the whole
    point: per-fill stamping cannot produce this signal.
    """
    agree = disagree = uncovered = 0
    for ts, h in fills:
        a = active_hash_at(log, ts)
        if a is None:
            uncovered += 1
        elif a == h:
            agree += 1
        else:
            disagree += 1
    return agree, disagree, uncovered


def _selftest_deploy_log() -> int:
    import datetime as dt
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    T = lambda h: dt.datetime(2026, 9, 4, h, 0, tzinfo=dt.timezone.utc)
    log = [(T(0), "aaa"), (T(12), "bbb")]

    check("hash before the first entry is UNCOVERED, not a pass",
          active_hash_at(log, T(-1) if False else
                         dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc))
          is None)
    check("the active hash is the latest entry at or before the fill",
          active_hash_at(log, T(6)) == "aaa"
          and active_hash_at(log, T(18)) == "bbb")

    good = [(T(6), "aaa"), (T(18), "bbb")]
    check("consistent stamps validate", validate_fills(good, log) == (2, 0, 0))

    # ★ THE MUTATION TEST: the check must be ABLE to fail, or it is decoration.
    # A stamp that is wrong CONSISTENTLY is exactly what per-fill stamping
    # cannot detect — the log catches it.
    bad = [(T(6), "aaa"), (T(18), "aaa")]      # missed the 12:00 deploy
    a, d, u = validate_fills(bad, log)
    check(f"a consistently-wrong stamp is CAUGHT ({d} disagreements)", d == 1)

    early = [(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc), "aaa")]
    check("pre-log fills are counted uncovered, never agreeing",
          validate_fills(early, log) == (0, 0, 1))
    return fails


if __name__ == "__main__":
    rc = _selftest()
    print("\ndeploy-log checks:")
    rc += _selftest_deploy_log()
    if rc:
        sys.exit("selftest failed")
    print(f"\nworking tree decision_hash: "
          f"{decision_hash(sources_at(), env_now())}")
    print(f"  files: {len(DECISION_FILES)}   env: {list(DECISION_ENV)}")
    print("\nEqual hash means the CODE agreed. It does not mean the fills are")
    print("comparable — the venue froze prices on 2026-09-05 at a constant")
    print("hash. Cohort identity is necessary for pooling, never sufficient.")
