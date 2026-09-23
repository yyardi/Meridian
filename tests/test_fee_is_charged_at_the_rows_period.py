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


#: A line may charge the constant inside a POINT_IN_TIME file when it prices
#: something NOW and no earlier row exists -- a live quote beside a historical
#: score in the same module. It must say so AT THE LINE with a reason:
#:
#:     ask_now = touch + taker_fee(touch)   # fee-now: the live book, no row
#:
#: An exception that has to be written where it happens is reviewable; a rule
#: that cannot be satisfied gets deleted instead, which is worse. This exists
#: because the seven runners keep their import after the bootstrap rewrite, so
#: a file may legitimately hold both uses.
FEE_NOW_MARKER = re.compile(r"#\s*fee-now:\s*(\S.*)$")


def bare_constant_fee(text: str) -> list[str]:
    """Fee applications carrying NO period, by shape.

    * `<name> * ...`            -- the coefficient straight into arithmetic
    * `k = <name>` / `def f(p, k=<name>)` -- the same, one step removed
    * `taker_fee(x)`            -- one argument, so the default coefficient
    * `fee_per_contract(...)`   -- has no coefficient parameter to pass one to
    """
    # Lines that declare a NOW-priced exception are removed FIRST, so a marker
    # exempts its own line and nothing else.
    #
    # A marker on a `def` line is REFUSED. cfb/run_momentum_scalp.py is the case
    # that showed why: `def fee(p): return FEE * p * (1 - p)` is used at line 98
    # for the entry charge on a recorded tick, at 101 for the exit, and at 178
    # for an illustrative table over hypothetical prices. A marker on the def
    # would exempt the two real historical charges along with the table, and the
    # reviewer of that diff would see one honest-looking comment, not three
    # call sites. The exemption has to sit at the call that needs it.
    lines = [l for l in text.splitlines()
             if not (FEE_NOW_MARKER.search(l) and not re.match(r"\s*def\s", l))]
    text = "\n".join(lines)

    hits = []
    for name in sorted(_fee_names(text)):
        # The second label used to read "default argument = FEE", which was
        # wrong for `c = FEE * p`: the regex cannot tell an assignment from a
        # parameter default, so it must not claim to. One honest label covers
        # both, and a fixing agent is not sent looking for a default that is
        # not there.
        for pat, why in ((rf"\b{name}\s*\*", f"{name} * ... (arithmetic)"),
                         (rf"=\s*{name}\b",
                          f"{name} bound to a name (assignment or default)")):
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
    "cfb/run_pulse_live_scorecard.py": "enter decisions at the recorded touch; the "
        "coefficient is joined from market_snapshots at decided_at, which "
        "pulse_decisions does not store",
    "cfb/run_scan.py": "writes ROWS_JSON and must emit the column it charges",
    "cfb/run_scan_live.py": "recorded closes",
    "cfb/run_scan_null.py": "the NULL's break-even; the reference, not the estimate",
    "cfb/run_slowside.py": "recorded trade prices",
    "cfb/run_wnba_player_model.py": "recorded T-1h closes, a sample spanning the 09-17 change",
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

#: The coefficient is not on the row THIS file reads, but it is recorded one
#: join away. A bucket of its own because the reason is different from TAPE's:
#: TAPE has nothing to charge, this has something nobody has plumbed.
#:
#: Both read `kalshi_snapshots`, which carries `series_ticker` and
#: `event_ticker` and no fee column. Kalshi's own declared `fee_type` and
#: `fee_multiplier` ARE recorded, on `kalshi_event_snapshots` (models.py 553-554),
#: so the period is reachable by joining on the event or series ticker.
#:
#: THIS IS THE SAME DEFECT WAITING, ON A VENUE THAT ANNOUNCES IT. Kalshi
#: publishes fee metadata per SERIES and its changes are SCHEDULED, so 0.07 is
#: a constant of a period there too -- and unlike Polymarket, the change is
#: knowable before it happens. The reason this is not POINT_IN_TIME today is
#: that the RATE itself is not in the venue's payload (only the schedule type
#: and multiplier are), so there is nothing per-row to charge yet. The fix when
#: it matters is to record the rate, not to assume one constant; the wording
#: here says "not plumbed", never "does not exist".
COEFFICIENT_NOT_ON_THE_ROW_READ = {
    "cfb/run_kalshi_dk_lag.py":
        "reads kalshi_snapshots (no fee column); fee_type/fee_multiplier are on "
        "kalshi_event_snapshots, one join away, and Kalshi's changes are scheduled",
    "cfb/run_kalshi_early_vs_close.py":
        "reads kalshi_snapshots (no fee column); same join, same scheduled risk",
}

CLASSIFIED = {**POINT_IN_TIME, **PRICES_NOW,
              **TAPE_LEDGER_OR_INSTRUMENT,
              **COEFFICIENT_NOT_ON_THE_ROW_READ}


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


def test_every_now_priced_exception_carries_a_reason():
    """A marker with no reason is an off switch. Also prints them, because an
    exception nobody reads is how the next one gets added silently."""
    bad, seen = [], []
    for path in sorted(POINT_IN_TIME):
        for i, line in enumerate((REPO / path).read_text(encoding="utf-8")
                                .splitlines(), 1):
            m = FEE_NOW_MARKER.search(line)
            if not m:
                continue
            reason = m.group(1).strip()
            seen.append(f"{path}:{i} {reason}")
            if len(reason) < 12:
                bad.append(f"{path}:{i} reason too short: {reason!r}")
    print("\n  NOW-priced exceptions inside historical readers:")
    for s_ in seen or ["  (none)"]:
        print(f"    {s_}")
    assert not bad, bad


def test_a_marker_on_a_def_line_does_not_exempt_its_callers():
    """The hatch is per LINE, and a definition is not a call.

    `def fee(p): return FEE * p * (1 - p)  # fee-now: ...` would clear every
    caller at once -- including the ones charging recorded rows -- behind a
    single comment the reviewer reads as covering the table.
    """
    on_def = ("from core.fees import POLYMARKET_TAKER as FEE\n"
              "def fee(p): return FEE * p * (1 - p)  # fee-now: an illustrative "
              "table over hypothetical prices\n"
              "charged = fee(row_price)\n")
    assert bare_constant_fee(on_def), "a marker on a def must not exempt callers"

    at_call = ("from core.fees import recorded_fee, POLYMARKET_TAKER as FEE\n"
               "def fee(p, coef): return coef * p * (1 - p)\n"
               "charged = fee(row_price, row['fee_coefficient'])\n"
               "table = fee(0.5, FEE)  # fee-now: an illustration, no row exists\n")
    assert not bare_constant_fee(at_call), bare_constant_fee(at_call)


def test_the_not_plumbed_bucket_says_where_the_data_is():
    """A reason that reads "does not exist" stops the next person looking.

    The first wording for these two was "kalshi_snapshots carries no fee
    column", which is true of the table they read and false as a conclusion:
    fee_type and fee_multiplier are recorded on kalshi_event_snapshots. A bucket
    whose reason closes the question is worse than no bucket.
    """
    for path, reason in COEFFICIENT_NOT_ON_THE_ROW_READ.items():
        assert "kalshi_event_snapshots" in reason or "join" in reason, (
            f"{path}: say WHERE the coefficient is, not only that this row "
            f"lacks it")
