"""A file that charges a fee over RECORDED rows must charge the row's period.

The venue raised its taker coefficient at 2026-09-17 04:07Z. Consolidating it
to one constant (core/fees.py) fixed today and broke every historical read:
each one now charges today's rate to rows the venue priced differently. On the
table-tennis arm that was 16 % -- 0.238c per contract at even prices, against a
median cost bar of about 2.2c -- and every settled match on file is pre-change.

WHY A GUARD AND NOT A LIST. The dispatch for this sweep was made by hand, and a
hand list of a class misses members: it missed cfb/run_scan.py this morning
(found by the fee-literal sweep) and cfb/run_scan_null.py plus
core/pulse/tight_game_reversion.py this evening (found by asking the tree). The
point of this file is not to re-find those. It is that **a new file which
charges a fee cannot be added without a decision being recorded here**, so the
next constant that becomes point-in-time cannot be half-swept.

WHY A CLASSIFICATION AND NOT A REGEX. A bare sweep over "charges a fee AND
mentions market_snapshots" is noisy -- my first version cleared three modules
because `.pytest_cache` contained their names, and it mislabelled
core/tt/money.py, which is point-in-time correct through a PARAMETER and never
mentions the table. So every fee-charging file is assigned a bucket below with
its reason, and the guard asserts the buckets hold. An unclassified file fails
by construction; it is one line to classify and the line has to say why.
"""
from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Anything that means "this file puts a number on a fee".
CHARGES_A_FEE = re.compile(
    r"POLYMARKET_TAKER|KALSHI_TAKER|taker_fee\(|recorded_fee\(|"
    r"fee_per_contract\(|THETA_TAKER|FEE_RATE|DEFAULT_FEE_RATE")

#: The constants, and the aliases a file may import them under. The first
#: version of this guard matched the CANONICAL names only and reported 2
#: failures where there are 15: every runner writes
#: `from core.fees import POLYMARKET_TAKER as FEE`, so the arithmetic reads
#: `FEE * p * (1 - p)` and the canonical name never appears near a `*`. A
#: matcher narrower than the thing it measures is the defect this whole sweep
#: exists to catch, committed inside the sweep.
CANONICAL = ("POLYMARKET_TAKER", "KALSHI_TAKER", "THETA_TAKER", "FEE_RATE",
             "DEFAULT_FEE_RATE")
ALIAS_IMPORT = re.compile(
    r"import\s+(?:" + "|".join(CANONICAL) + r")\s+as\s+(\w+)")


def _fee_names(text: str) -> set[str]:
    """Every local name in this file that holds a fee coefficient."""
    names = {n for n in CANONICAL if re.search(rf"\b{n}\b", text)}
    names |= set(ALIAS_IMPORT.findall(text))
    return names


def bare_constant_fee(text: str) -> list[str]:
    """Fee applications carrying NO period, by shape.

    * `<name> * ...`            -- the coefficient straight into arithmetic
    * `def f(p, k=<name>)`      -- the same thing behind a default argument
    * `taker_fee(x)`            -- one argument, so the default coefficient
    * `fee_per_contract(...)`   -- has no coefficient parameter to pass one to
    """
    hits = []
    for name in sorted(_fee_names(text)):
        for pat, why in ((rf"\b{name}\s*\*", f"{name} * ..."),
                         (rf"=\s*{name}\b", f"default argument = {name}")):
            if re.search(pat, text):
                hits.append(why)
    # A coefficient written as a LITERAL is not the row's either, whatever
    # shape carries it. cfb/run_cross_venue.py passed the first version of this
    # guard because it never imports the constant: line 34 is
    # `FK, FP = 0.07, 0.0695`, and its `fee(p, th)` takes the coefficient as a
    # parameter, so the plumbing looks point-in-time while the value is pinned.
    # Its own docstring says "FP from core/fees.py", which is the kind of claim
    # only a test can keep true.
    for m in re.finditer(r"\b(\w*(?:FEE|FK|FP|THETA|TAKER|COEF)\w*)\s*(?:,\s*\w+\s*)?"
                         r"=\s*[\d.,\s]*0\.0(?:6|69|695|7)\b", text):
        hits.append(f"{m.group(1)} is a hardcoded coefficient literal")
    if re.search(r"(?<!recorded_)\btaker_fee\(\s*[^,()]+\s*\)", text):
        hits.append("taker_fee(price) with no coefficient")
    for m in re.finditer(r"fee_per_contract\(([^)]*)\)", text):
        if "coefficient" not in m.group(1):
            hits.append("fee_per_contract(...) carries no coefficient")
            break
    return sorted(set(hits))

# --------------------------------------------------------------------------- #
# The three buckets. Every file that charges a fee belongs to exactly one.
# --------------------------------------------------------------------------- #

#: Scores RECORDED rows, so it must charge each row's own coefficient. The
#: approved shapes are `recorded_fee(price, coefficient)` or a two-argument
#: `taker_fee(price, coefficient)`; a coefficient reaching the function as a
#: parameter counts, which is how core/tt/money.py does it without ever naming
#: the table.
POINT_IN_TIME = {
    "cfb/run_cross_venue.py": "scores recorded closes on both venues",
    "cfb/run_extreme_hold.py": "per-tick, and its TRAP compares each tick's coefficient",
    "cfb/run_ladder_calibration.py": "recorded pregame closes",
    "cfb/run_ladder_rv.py": "recorded rungs, both legs",
    "cfb/run_longshot_decomp.py": "recorded closes per cell",
    "cfb/run_longshot_shadow.py": "recorded last quote in a window",
    "cfb/run_momentum_scalp.py": "recorded in-game ticks, entry and exit",
    "cfb/run_paper_book.py": "recorded closes, rescored weekly",
    "cfb/run_scan.py": "writes ROWS_JSON and must emit the column it charges",
    "cfb/run_scan_live.py": "recorded closes",
    "cfb/run_scan_null.py": "the NULL's break-even; the reference, not the estimate",
    "cfb/run_slowside.py": "recorded trade prices",
    "cfb/run_tt_elo.py": "last pregame quote per match",
    "core/backtest/fills.py": "the fill model for reads over history",
    "core/backtest/ingame_replay.py": "replays recorded ticks",
    "core/backtest/moneyline.py": "recorded odds and closes",
    "core/gridiron/scalp.py": "recorded in-game ticks",
    "core/pulse/tight_game_reversion.py": "exits priced off recorded ticks",
    "core/tt/money.py": "takes the row's coefficient as a parameter",
}

#: Prices something NOW, at the live book, so today's constant is correct and
#: `recorded_fee` would be wrong. These are not exempt from review -- they are
#: classified, and the reason is that there is no earlier row to charge.
PRICES_NOW = {
    "core/quote/wallet.py": "quotes now, against the live touch",
    "core/kelly_sizing.py": "sizes a bet being placed now",
    "core/executor.py": "places now",
    "core/api.py": "the live ladder path answers a request",
    "cfb/run_stream_executor.py": "reads the stream and proposes now",
    "scripts/launchers/slate_fast.py": "launches tonight's detectors",
}

#: Charges against a TAPE or the LEDGER rather than against market_snapshots.
#: Stream tapes carry no coefficient column and every tape is post-change, so
#: the constant is right today; the ledger row records its own `fee_rate`, so
#: the period travels with the row rather than with the code. fee_drift.py is
#: the instrument that compares the constant to the column and must read both.
TAPE_LEDGER_OR_INSTRUMENT = {
    "core/ladder/scan.py": "scores a tape; all tapes are post-change",
    "core/ladder/stream_episodes.py": "stream tape, no coefficient column",
    "core/ladder/stream_scan.py": "stream tape",
    "core/ladder/tape.py": "the tape's own writer",
    "core/ladder/pnl.py": "reads the ledger, whose row records fee_rate",
    "core/ladder/gamelog.py": "reads the ledger",
    "core/fees.py": "owns the constant and the recorded form",
    "scripts/fee_drift.py": "compares the constant to the column by design",
}

CLASSIFIED = {**POINT_IN_TIME, **PRICES_NOW, **TAPE_LEDGER_OR_INSTRUMENT}


def _fee_charging_files() -> list[str]:
    out = []
    for pat in ("core/**/*.py", "cfb/*.py", "scripts/**/*.py"):
        for p in REPO.glob(pat):
            if ".venv" in p.parts or "__pycache__" in p.parts:
                continue
            if CHARGES_A_FEE.search(p.read_text(encoding="utf-8", errors="ignore")):
                out.append(str(p.relative_to(REPO)))
    return sorted(set(out))


def test_the_sweep_finds_files_at_all():
    """If the pattern or the glob breaks, every case below vacuously passes."""
    found = _fee_charging_files()
    assert len(found) >= 25, found
    assert "core/fees.py" in found


def test_every_fee_charging_file_is_classified():
    """A new one fails here until a bucket and a reason are written down."""
    unclassified = [f for f in _fee_charging_files() if f not in CLASSIFIED]
    assert not unclassified, (
        "these charge a fee and are in no bucket: " + ", ".join(unclassified)
        + ". Add each to POINT_IN_TIME (scores recorded rows -> must charge the "
        "row's coefficient), PRICES_NOW (no earlier row exists) or "
        "TAPE_LEDGER_OR_INSTRUMENT, with the reason.")


def test_no_classified_file_has_disappeared():
    """A rename must move its classification, not silently drop it."""
    missing = [f for f in CLASSIFIED if not (REPO / f).exists()]
    assert not missing, f"classified but gone: {missing}"


def test_the_table_classifies_only_files_that_charge_a_fee():
    """Dead weight in the table reads as coverage.

    core/pulse/replay_eval.py was in it until this test: it is in the sweep's
    brief but charges no fee of its own, so classifying it asserted nothing and
    would have looked like one more file handled.
    """
    charging = set(_fee_charging_files())
    idle = sorted(f for f in CLASSIFIED if f not in charging)
    assert not idle, (
        "classified but charges no fee, so the entry asserts nothing: "
        + ", ".join(idle))


@pytest.mark.parametrize("path", sorted(POINT_IN_TIME), ids=lambda p: p)
def test_a_historical_read_charges_the_rows_period(path):
    text = (REPO / path).read_text(encoding="utf-8")
    bare = bare_constant_fee(text)
    assert not bare, (
        f"{path} scores recorded rows ({POINT_IN_TIME[path]}) and applies a fee "
        f"at the module constant: {bare}. Charge the row's coefficient -- "
        f"core.fees.recorded_fee(price, row['fee_coefficient']), or pass the "
        f"coefficient in as a parameter. The venue raised it at 2026-09-17 "
        f"04:07Z, so one rate across a spanning window is two regimes averaged."
        f"\n\nA DEFAULT COEFFICIENT DOES NOT SATISFY THIS, deliberately: "
        f"`def fee(p, k=FEE)` is the silent path that let one rate stand wrong "
        f"for four days, and it is the same reason core.fees.recorded_fee "
        f"raises on None instead of falling back. Make the parameter required "
        f"and pass row['fee_coefficient'] at every call.")


@pytest.mark.parametrize("path", sorted(PRICES_NOW), ids=lambda p: p)
def test_a_live_pricer_does_not_pretend_to_be_historical(path):
    """`recorded_fee` here would be a coefficient invented for a row that does
    not exist. The bucket is the claim; this pins that it stays true."""
    text = (REPO / path).read_text(encoding="utf-8")
    assert "recorded_fee(" not in text, (
        f"{path} is classified PRICES_NOW ({PRICES_NOW[path]}) but calls "
        f"recorded_fee. If it now scores recorded rows, move it to "
        f"POINT_IN_TIME; if it prices now, charge core.fees.taker_fee.")
