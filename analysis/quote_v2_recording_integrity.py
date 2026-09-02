"""QUOTE v2 recording-integrity scorer — the standing checks B signed off on
for the `quote_v2_observations` table (see the model docstring in
core/quote/storage.py and docs/math/quote-v2-observation-schema.md).

    .venv/bin/python analysis/quote_v2_recording_integrity.py --selftest
    .venv/bin/python analysis/quote_v2_recording_integrity.py --db   # once data exists

Three checks, per game — two INTEGRITY (was the stream faithfully recorded)
and one VALIDITY (was the RIGHT clock recorded). The distinction is load-
bearing: an integrity check reconciles what was recorded against itself, so a
wrong-but-internally-consistent input passes it; a validity check asserts a
property only the RIGHT input can have. Check 3 exists because checks 1–2
structurally cannot see a wrong-clock regression.

1. REPLAY-RECONCILIATION. The engine wrote `det_in_window`/`det_confirm_t0`
   LIVE, feeding B's congestion detector from the quoter's own stream
   (core/quote/engine_v2.py `record_cycle`). This scorer recomputes those two
   columns OFFLINE by replaying the detector over the table's RAW columns
   (`observed_at`, `best_bid`/`best_ask`, `sports_market_type`, `market_slug`)
   and asserts they match the recorded values, row for row. Match ==> the
   recorded detector columns are verified provenance: they are exactly what a
   causal detector produces from the stream the table claims to hold. A
   mismatch means the raw stream and the recorded columns are NOT two faithful
   captures of one process — a dropped/duplicated/corrupted observation, or a
   feed-order the replay cannot reconstruct.

   Why this is not vacuous (the attributor lesson, quote_v2_replay_proof.py):
   the recorded `det_*` were produced from the LIVE stream; the replay is fed
   from the STORED raw columns. They are independent captures. If the stored
   raw is complete and faithful, they agree; corrupt the raw and they diverge.
   The --selftest plants prove exactly this: each plant perturbs ONLY the raw
   columns, leaves `det_*` as recorded, and the scorer catches the divergence
   as a named mismatch. A check that can fail, shown failing.

2. CADENCE SELF-MEASUREMENT. Per market, the inter-observation gap in
   `observed_at`. Reported (median / p99 / max), and gaps > CADENCE_SPEC_S are
   counted as violations. CADENCE_SPEC_S = 1.0s is the schema's PRE-DECLARED
   target ("Written by the v2 quoter at <=1s cadence"), not a bar authored
   after the numbers exist — it is measured against the spec, never fitted to
   the data. The <=1s cadence is what keeps this stream from over-firing the
   detector the way the ~200ms recorder tape does (the recorder-proxy lesson);
   this check makes compliance MEASURED, not assumed.

3. CROSS-CLOCK VALIDITY. `observed_at` (quoter's own stamp) and
   `source_captured_at` (the upstream recorder stamp carried through) are two
   clocks on one event. Recording both gives the wrong-clock regression an
   ASSERTABLE SIGNATURE that checks 1–2 cannot: `observed_at ==
   source_captured_at` EVERYWHERE is exactly what the fixed bug
   (`observed_at = r.captured_at`) looked like, and it alarms. Also asserts the
   ordering only the right clocks produce — `observed_at >= source_captured_at`
   (the quoter receives no earlier than the recorder captured), and median skew
   within the DECLARED [0, SKEW_BOUND_S]s (B's pre-data expectation from the
   ≤1s cycle, not a bar fitted to data). A clock inversion or an out-of-band
   median alarms too. `source_captured_at` NULLs are counted as a coverage
   hole (never dropped), not an alarm.

CANONICAL FEED ORDER (now closed). The detector is order-sensitive only when a
trigger and a same-ladder response share one receive instant. This scorer
replays in the detector's canonical order (`observed_at`, then `market_slug` —
the c78432d ordering discipline), which is the detector's REGISTERED input
contract. The recording engine now conforms: `record_cycle` feeds
`_record_observations(s)` sorted `(observed_at, market_slug)` (B's ruling), and
with the per-cycle quoter read-stamp all within-cycle `observed_at` are equal so
the sort reduces to `market_slug`. The equal-instant collision LABEL is kept as
a should-never-fire assertion: post-sort, a collision that ever diverges is the
engine drifting OUT of the registered contract — the cheapest detector for that
regression, so it is reported (never papered over), not expected.

DECLARED BLIND SPOT (rule 19 — a checker names what it cannot see). This scorer
reads what is IN the table; it CANNOT see observations that were never recorded.
So an EMPTY read is ambiguous and must never be reported as health: "empty and
clean" can mean "no board is live yet" OR "a board is live but its rows were
born invisible" — stamped older than the engine's 600s observation window before
they became visible, so the quoter never ingested them (the RPS-2 slow-sweep
defect, 2026-09-02: a ~15min sweep stamped `captured_at` at sweep start and
committed at sweep end, so rows surfaced already ~16min stale and the quoter was
structurally blind to the whole board while `record_s` sat at 2-3ms). No
in-table check — not cadence, not reconciliation, not cross-clock — can
distinguish these two, because all three operate on rows that exist. The
compensator is an OUT-OF-BAND row-visibility probe (does the table receive rows
at all while a board is known live), which is what caught the defect; this
scorer defers the empty verdict to that probe rather than pronouncing it clean.

--selftest validates the instrument on synthetic streams whose `det_*` this
module itself produced via the engine's recording logic; it is ready the moment
real (non-empty) rows land. --csv scores an offline export for the same reason.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from analysis.congestion_detector import (  # noqa: E402
    LONG_S,
    CongestionDetector,
)

UTC = dt.timezone.utc

CADENCE_SPEC_S = 1.0          # schema pre-declared target, not a fitted bar
CONFIRM_TOL_S = 1e-3         # confirm_t0 float->datetime round-trip tolerance
SKEW_BOUND_S = 2.0          # B's DECLARED cross-clock expectation (pre-data:
                            # quoter reads within ~1-2 cycles of the recorder
                            # capture), not a bar fitted to observed skew

# Columns the reconciliation reads from the table. Kept explicit so a schema
# drift surfaces as a KeyError here, not as a silent pass.
RAW_COLS = ["game_id", "market_slug", "sports_market_type",
            "observed_at", "best_bid", "best_ask"]
DET_COLS = ["det_in_window", "det_confirm_t0"]


def _epoch_seconds(ts) -> float:
    """Match the engine's clock: seconds since epoch, tz-aware or naive-as-UTC.
    Explicit ns normalization (the verify-clock-and-timezone class of bug —
    datetime64[us] silently rescales duration comparisons)."""
    t = pd.Timestamp(ts)
    if t.tz is None:
        t = t.tz_localize(UTC)
    return t.tz_convert(UTC).value / 1e9   # .value is ns regardless of unit


# --------------------------------------------------------------------------- #
#  Check 1: replay-reconciliation
# --------------------------------------------------------------------------- #

@dataclass
class Mismatch:
    game_id: str
    market_slug: str
    observed_at: object
    kind: str                    # "in_window" | "confirm_t0"
    recorded: object
    replayed: object
    equal_instant: bool          # True if this row shares observed_at with the
                                 # prior row (the feed-order collision hazard)


def _replay_recording(g: pd.DataFrame) -> list[tuple]:
    """Reproduce, row for row, the (in_window, confirm_t0) that
    engine_v2.record_cycle WOULD write for one game, feeding B's detector from
    the RAW columns in canonical (observed_at, market_slug) order. This mirrors
    record_cycle exactly — including that a new confirm is recorded only on the
    first row after `len(confirms)` grows, as max(confirms) - LONG_S — so any
    divergence from the stored columns is a property of the STREAM, not of a
    reimplementation gap."""
    det = CongestionDetector()
    seen = 0
    out: list[tuple] = []
    for r in g.itertuples():
        t = _epoch_seconds(r.observed_at)
        kind = str(r.sports_market_type).rsplit("_", 1)[-1]
        mid = (float(r.best_bid) + float(r.best_ask)) / 2.0
        det.feed(t, kind, r.market_slug, mid)
        confirm_t0 = None
        if len(det.confirms) > seen:
            confirm_t0 = dt.datetime.fromtimestamp(
                max(det.confirms) - LONG_S, tz=UTC)
            seen = len(det.confirms)
        out.append((det.is_congested(t), confirm_t0))
    return out


def _confirm_equal(recorded, replayed) -> bool:
    rec_null = recorded is None or (isinstance(recorded, float)
                                    and np.isnan(recorded)) or pd.isna(recorded)
    rep_null = replayed is None
    if rec_null and rep_null:
        return True
    if rec_null or rep_null:
        return False
    return abs(_epoch_seconds(recorded) - _epoch_seconds(replayed)) <= CONFIRM_TOL_S


def reconcile(df: pd.DataFrame) -> list[Mismatch]:
    """Per game, replay the detector from raw and compare to recorded det_*.
    Returns every mismatch (empty == the recorded columns are verified
    provenance of the stored raw stream). Pure function of `df`."""
    missing = [c for c in RAW_COLS + DET_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"table missing columns {missing}")
    out: list[Mismatch] = []
    for game_id, g in df.groupby("game_id", sort=True):
        g = g.sort_values(["observed_at", "market_slug"], kind="stable")
        replay = _replay_recording(g)
        prev_t = None
        for (row, (rep_win, rep_c0)) in zip(g.itertuples(), replay):
            t = _epoch_seconds(row.observed_at)
            collision = prev_t is not None and abs(t - prev_t) < 1e-9
            prev_t = t
            rec_win = bool(row.det_in_window) if not pd.isna(
                row.det_in_window) else None
            if rec_win != rep_win:
                out.append(Mismatch(game_id, row.market_slug, row.observed_at,
                                    "in_window", rec_win, rep_win, collision))
            if not _confirm_equal(row.det_confirm_t0, rep_c0):
                out.append(Mismatch(game_id, row.market_slug, row.observed_at,
                                    "confirm_t0", row.det_confirm_t0, rep_c0,
                                    collision))
    return out


# --------------------------------------------------------------------------- #
#  Check 2: cadence self-measurement
# --------------------------------------------------------------------------- #

@dataclass
class Cadence:
    game_id: str
    n_gaps: int
    median_s: float
    p99_s: float
    max_s: float
    n_violations: int            # gaps > CADENCE_SPEC_S
    markets: int = field(default=0)


def measure_cadence(df: pd.DataFrame) -> list[Cadence]:
    """Per game, the per-market inter-observation gap (the granularity the
    detector consumes each rung at). Median/p99/max reported; gaps beyond the
    pre-declared CADENCE_SPEC_S counted. Pure function of `df`."""
    out: list[Cadence] = []
    for game_id, g in df.groupby("game_id", sort=True):
        gaps: list[float] = []
        for _mkt, m in g.groupby("market_slug", sort=True):
            ts = sorted(_epoch_seconds(x) for x in m["observed_at"])
            gaps.extend(np.diff(ts).tolist())
        if not gaps:
            out.append(Cadence(game_id, 0, float("nan"), float("nan"),
                               float("nan"), 0, g["market_slug"].nunique()))
            continue
        arr = np.array(gaps)
        out.append(Cadence(
            game_id=game_id, n_gaps=len(arr),
            median_s=float(np.median(arr)),
            p99_s=float(np.percentile(arr, 99)),
            max_s=float(arr.max()),
            n_violations=int((arr > CADENCE_SPEC_S).sum()),
            markets=g["market_slug"].nunique()))
    return out


# --------------------------------------------------------------------------- #
#  Check 3: cross-clock validity (the ONE validity check; 1-2 are integrity)
# --------------------------------------------------------------------------- #

@dataclass
class CrossClock:
    game_id: str
    n: int
    n_missing: int               # source_captured_at NULL (coverage hole)
    n_inversion: int             # observed_at < source_captured_at (impossible)
    median_skew_s: float
    p99_skew_s: float
    all_zero: bool               # == everywhere -> the wrong-clock regression
    bounded: bool                # median within declared [0, SKEW_BOUND_S]
    alarm: bool
    reasons: list[str]


def check_cross_clock(df: pd.DataFrame) -> list[CrossClock]:
    """Per game, assert the two clocks have the shape only the RIGHT pair can:
    `observed_at` (quoter) recorded no earlier than `source_captured_at`
    (upstream), a small-positive median skew, and — the signature integrity
    cannot see — NOT identical everywhere. `observed_at == source_captured_at`
    for every row is exactly the fixed `observed_at = r.captured_at` bug, so it
    ALARMS. Pure function of `df`."""
    out: list[CrossClock] = []
    for game_id, g in df.groupby("game_id", sort=True):
        n = len(g)
        if "source_captured_at" not in g.columns:
            out.append(CrossClock(game_id, n, n, 0, float("nan"), float("nan"),
                                  False, False, True,
                                  ["source_captured_at column absent"]))
            continue
        miss = g["source_captured_at"].isna()
        n_missing = int(miss.sum())
        gg = g[~miss]
        if gg.empty:
            out.append(CrossClock(game_id, n, n_missing, 0, float("nan"),
                                  float("nan"), False, False, False,
                                  [f"{n_missing} rows missing source_captured_at "
                                   "(coverage hole)"]))
            continue
        skew = np.array([_epoch_seconds(o) - _epoch_seconds(s) for o, s in
                         zip(gg["observed_at"], gg["source_captured_at"])])
        n_inv = int((skew < 0).sum())
        med = float(np.median(skew))
        p99 = float(np.percentile(skew, 99))
        all_zero = bool((skew == 0).all())
        bounded = 0.0 <= med <= SKEW_BOUND_S
        reasons: list[str] = []
        if all_zero:
            reasons.append("observed_at == source_captured_at everywhere "
                           "(wrong-clock regression)")
        if n_inv:
            reasons.append(f"{n_inv} rows observed_at < source_captured_at "
                           "(clock inversion)")
        if not bounded:
            reasons.append(f"median skew {med:.3f}s outside declared "
                           f"[0,{SKEW_BOUND_S}]s")
        if n_missing:
            reasons.append(f"{n_missing} rows missing source_captured_at "
                           "(coverage hole, counted not dropped)")
        alarm = all_zero or n_inv > 0 or not bounded
        out.append(CrossClock(game_id, n, n_missing, n_inv, med, p99,
                              all_zero, bounded, alarm, reasons))
    return out


# --------------------------------------------------------------------------- #
#  Synthetic substrate for --selftest (the engine's own recording logic writes
#  the det_* columns from a CLEAN raw stream; plants then corrupt raw ONLY).
# --------------------------------------------------------------------------- #

def _synth_clean_game(game_id: str = "g1") -> pd.DataFrame:
    """A one-game stream with a planted congestion episode: rung s1 makes an
    unanswered 3c move (s2 stays flat), so the detector confirms at t0+5s and a
    30s window opens. Sampled at 0.5s (spec-compliant). det_* are written by
    the SAME recording logic the engine uses, from this clean raw — so a
    reconcile() over the untouched table returns zero mismatches by
    construction, and any later divergence is the plant, not the fixture."""
    t0 = pd.Timestamp("2026-09-20T00:00:00", tz="UTC")
    rows = []
    for i, s in enumerate(np.arange(0.0, 120.0, 0.5)):
        m1 = 0.60 if s < 40.0 else 0.55          # unanswered 3c drop at t=40
        for mkt, m in (("s1", m1), ("s2", 0.40)):
            rows.append({
                "game_id": game_id, "market_slug": mkt,
                "sports_market_type": "basketball_team_full_game_spread",
                "observed_at": t0 + pd.Timedelta(seconds=float(s)),
                "best_bid": round(m - 0.01, 4), "best_ask": round(m + 0.01, 4)})
    df = pd.DataFrame(rows)
    # write det_* by the engine's recording logic, per game, canonical order
    df = df.sort_values(["observed_at", "market_slug"], kind="stable"
                        ).reset_index(drop=True)
    win, c0 = [], []
    for _gid, g in df.groupby("game_id", sort=True):
        for (w, c) in _replay_recording(g):
            win.append(w)
            c0.append(c)
    df["det_in_window"] = win
    df["det_confirm_t0"] = c0
    df["det_version"] = "selftest"
    # upstream stamp = recorded 0.3s BEFORE the quoter observed it: a healthy
    # small-positive skew (quoter receives after the recorder captured). The
    # cross-clock plants below overwrite this column only.
    df["source_captured_at"] = df["observed_at"] - pd.Timedelta(seconds=0.3)
    return df


def selftest() -> int:
    ok = True
    clean = _synth_clean_game()

    # sanity: the fixture actually contains a confirmed window, else the plants
    # below would have nothing causal to disturb (a vacuous clean pass).
    n_win = int(clean["det_in_window"].sum())
    n_confirm = int(clean["det_confirm_t0"].notna().sum())
    live = n_win > 0 and n_confirm == 1
    print(f"fixture: {n_win} in-window rows, {n_confirm} confirm row -> "
          f"{'OK (a real episode to disturb)' if live else 'FAIL (inert fixture)'}")
    ok &= live

    # CLEAN: reconcile returns zero (raw untouched == recorded provenance).
    m = reconcile(clean)
    print(f"clean reconcile: {len(m)} mismatches -> "
          f"{'OK (empty)' if not m else 'FAIL'}")
    ok &= not m

    # PLANT A: drop a load-bearing raw row (the trigger observation on s1 at
    # t=40). Its det_* leaves with it; replaying the survivors no longer
    # confirms the episode, so later rows' recorded det_in_window (still True)
    # diverge from the replay (now False). Caught as in_window mismatches.
    pa = clean.copy()
    trig = pa[(pa.market_slug == "s1") &
              (pa.observed_at == pd.Timestamp("2026-09-20T00:00:40", tz="UTC"))]
    pa = pa.drop(index=trig.index)
    ma = reconcile(pa)
    caught_a = any(x.kind == "in_window" and x.recorded is True
                   and x.replayed is False for x in ma)
    print(f"plant A (drop trigger obs): {len(ma)} mismatches, "
          f"in_window True->False present -> "
          f"{'OK (caught)' if caught_a else 'FAIL (missed a dropped obs)'}")
    ok &= caught_a

    # PLANT B: corrupt one raw mid so the trigger never crosses 3c (0.60->0.58
    # is a 2c move, below TRIGGER_MOVE). det_* untouched. Replay finds no
    # confirm; recorded confirm_t0 + in-window rows diverge.
    pb = clean.copy()
    idx = pb[(pb.market_slug == "s1") &
             (pb.observed_at >= pd.Timestamp("2026-09-20T00:00:40", tz="UTC"))].index
    pb.loc[idx, "best_bid"] = 0.57
    pb.loc[idx, "best_ask"] = 0.59
    mb = reconcile(pb)
    caught_b = any(x.kind == "confirm_t0" for x in mb) and any(
        x.kind == "in_window" for x in mb)
    print(f"plant B (corrupt trigger mid below threshold): {len(mb)} "
          f"mismatches, confirm_t0 + in_window present -> "
          f"{'OK (caught)' if caught_b else 'FAIL (missed a corrupted mid)'}")
    ok &= caught_b

    # PLANT C (cadence): the clean fixture is 0.5s-sampled, so it must PASS the
    # <=1s spec; then widen one gap to 3s and it must be flagged. Both
    # directions, so the cadence check is shown able to pass AND fail.
    cad_clean = measure_cadence(clean)[0]
    cad_ok = cad_clean.n_violations == 0 and cad_clean.p99_s <= CADENCE_SPEC_S
    print(f"cadence clean: p99={cad_clean.p99_s:.3f}s, "
          f"{cad_clean.n_violations} violations -> "
          f"{'OK (<=1s spec met)' if cad_ok else 'FAIL'}")
    ok &= cad_ok

    pc = clean[~((clean.market_slug == "s1") & (clean.observed_at.between(
        pd.Timestamp("2026-09-20T00:00:10", tz="UTC"),
        pd.Timestamp("2026-09-20T00:00:12.4", tz="UTC"))))].copy()
    cad_gap = measure_cadence(pc)[0]
    cad_caught = cad_gap.n_violations >= 1 and cad_gap.max_s > CADENCE_SPEC_S
    print(f"plant C (3s gap on s1): max={cad_gap.max_s:.3f}s, "
          f"{cad_gap.n_violations} violations -> "
          f"{'OK (caught)' if cad_caught else 'FAIL (missed a cadence gap)'}")
    ok &= cad_caught

    # CHECK 3 clean: healthy 0.3s skew — not identical, no inversion, bounded.
    xc_clean = check_cross_clock(clean)[0]
    xc_ok = (not xc_clean.alarm and not xc_clean.all_zero
             and xc_clean.n_inversion == 0 and xc_clean.bounded)
    print(f"cross-clock clean: median skew={xc_clean.median_skew_s:.3f}s, "
          f"all_zero={xc_clean.all_zero}, inversions={xc_clean.n_inversion} -> "
          f"{'OK (healthy two-clock shape)' if xc_ok else 'FAIL'}")
    ok &= xc_ok

    # PLANT D (the fixed bug's signature): observed_at == source_captured_at
    # EVERYWHERE. Integrity checks 1-2 pass this unchanged (same stored stamp);
    # only the validity check sees it.
    pd_ = clean.copy()
    pd_["source_captured_at"] = pd_["observed_at"]
    xc_reg = check_cross_clock(pd_)[0]
    reg_caught = xc_reg.all_zero and xc_reg.alarm
    # and prove checks 1-2 are BLIND to it (the whole reason check 3 exists)
    blind = not reconcile(pd_) and measure_cadence(pd_)[0].n_violations == 0
    print(f"plant D (observed_at==source everywhere): all_zero={xc_reg.all_zero}"
          f", alarm={xc_reg.alarm}; integrity blind={blind} -> "
          f"{'OK (only validity catches it)' if reg_caught and blind else 'FAIL'}")
    ok &= reg_caught and blind

    # PLANT E: clock inversion — quoter stamped 5s BEFORE the recorder captured.
    pe = clean.copy()
    pe["source_captured_at"] = pe["observed_at"] + pd.Timedelta(seconds=5)
    xc_inv = check_cross_clock(pe)[0]
    inv_caught = xc_inv.n_inversion > 0 and xc_inv.alarm
    print(f"plant E (5s clock inversion): inversions={xc_inv.n_inversion}, "
          f"alarm={xc_inv.alarm} -> "
          f"{'OK (caught)' if inv_caught else 'FAIL (missed an inversion)'}")
    ok &= inv_caught

    print()
    print("SELFTEST:", "PASS — integrity (checks 1-2) catches a dropped and a "
          "corrupted raw observation and a sub-spec cadence gap; validity "
          "(check 3) catches the wrong-clock regression that integrity is "
          "structurally BLIND to, plus a clock inversion; clean passes all "
          "three. The scorer can fail." if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
#  --db: run the checks against the real table (clean no-op while empty)
# --------------------------------------------------------------------------- #

def _load_db() -> pd.DataFrame:
    from core.storage.base import get_engine  # lazy: selftest needs no DB
    eng = get_engine()
    q = ("SELECT game_id, market_slug, sports_market_type, observed_at, "
         "source_captured_at, best_bid, best_ask, det_in_window, "
         "det_confirm_t0, det_version "
         "FROM quote_v2_observations")
    return pd.read_sql(q, eng)


def run_db() -> int:
    try:
        df = _load_db()
    except Exception as exc:  # noqa: BLE001 — pre-deploy: table/DB may be absent
        msg = str(exc).lower()
        absent = ("does not exist" in msg or "no such table" in msg
                  or "could not connect" in msg or "connection refused" in msg
                  or "operationalerror" in type(exc).__name__.lower())
        if absent:
            print("quote_v2_observations not present / DB unreachable from "
                  "here. Cannot score — this is an absent-table / no-DB-route "
                  "condition, distinct from an EMPTY table (see the blind-spot "
                  "note for what empty does and does not mean).")
            return 0
        raise
    if df.empty:
        return _empty_verdict("quote_v2_observations")
    return _run_checks(df)


def _empty_verdict(source: str) -> int:
    """Empty is AMBIGUOUS, never health (the module's declared blind spot).
    Say so loudly and defer to the out-of-band row-visibility probe."""
    print(f"{source}: EMPTY — 0 rows. This is NOT a clean pass. An in-table "
          "scorer cannot tell 'no board live yet' from 'board live but its "
          "rows were born invisible' — stamped past the engine's 600s window "
          "before they surfaced (the RPS-2 slow-sweep defect, 2026-09-02). "
          "Confirm which with the OUT-OF-BAND row-visibility probe (does the "
          "table receive rows while a board is known live), not this scorer.")
    return 0


def _parse_bool(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return None
    s = str(v).strip().lower()
    if s in ("t", "true", "1"):
        return True
    if s in ("f", "false", "0"):
        return False
    return None


def _load_csv(path: str) -> pd.DataFrame:
    """Load a CSV export of quote_v2_observations (e.g. psql
    `\\copy (SELECT ...) TO 'f.csv' CSV HEADER`) into the same frame the checks
    consume. Coerces postgres CSV quirks: booleans as t/f, NULLs as empty,
    ISO timestamps. Lets a real board be scored offline when the DB isn't
    reachable from where the scorer runs."""
    df = pd.read_csv(path, dtype=str, na_values=[""], keep_default_na=True)
    for col in ("observed_at", "source_captured_at", "det_confirm_t0"):
        if col in df.columns:
            # format="ISO8601", not inference: postgres exports whole-second
            # stamps without a fractional part and sub-second ones with, and
            # format inference locks onto the first value and coerces the rest
            # to NaT (the verify-clock-and-timezone class of bug). ISO8601
            # parses the mixed precision — and the space/'T' separator — as one.
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True,
                                     format="ISO8601")
    for col in ("best_bid", "best_ask"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "det_in_window" in df.columns:
        df["det_in_window"] = df["det_in_window"].map(_parse_bool)
    return df


def run_csv(path: str) -> int:
    df = _load_csv(path)
    if df.empty:
        return _empty_verdict(path)
    return _run_checks(df, source=path)


def _run_checks(df: pd.DataFrame, source: str = "quote_v2_observations") -> int:
    games = df["game_id"].nunique()
    print(f"scoring {len(df):,} rows across {games} game(s) from {source}\n")
    mm = reconcile(df)
    print(f"CHECK 1 replay-reconciliation: {len(mm)} mismatch(es)")
    for x in mm[:20]:
        flag = " [equal-instant collision]" if x.equal_instant else ""
        print(f"  {x.game_id} {x.market_slug} {x.observed_at} {x.kind}: "
              f"recorded={x.recorded} replay={x.replayed}{flag}")
    if len(mm) > 20:
        print(f"  ... and {len(mm) - 20} more")
    print(f"  -> {'PASS (recorded det_* are verified provenance)' if not mm else 'FAIL'}\n")

    print("CHECK 2 cadence self-measurement (spec <=%.1fs):" % CADENCE_SPEC_S)
    cad = measure_cadence(df)
    tot_viol = sum(c.n_violations for c in cad)
    for c in cad:
        if c.n_gaps == 0:
            print(f"  {c.game_id}: {c.markets} mkts, no gaps to measure "
                  f"(<2 obs/market)")
            continue
        print(f"  {c.game_id}: {c.markets} mkts, median={c.median_s:.3f}s "
              f"p99={c.p99_s:.3f}s max={c.max_s:.3f}s "
              f"violations={c.n_violations}/{c.n_gaps}")
    print(f"  -> total {tot_viol} gap(s) over spec across all games\n")

    print("CHECK 3 cross-clock validity (observed_at vs source_captured_at, "
          "declared skew [0,%.1fs]):" % SKEW_BOUND_S)
    xc = check_cross_clock(df)
    xc_alarm = any(c.alarm for c in xc)
    for c in xc:
        tag = "ALARM" if c.alarm else "ok"
        print(f"  {c.game_id}: n={c.n} median_skew={c.median_skew_s:.3f}s "
              f"p99={c.p99_skew_s:.3f}s all_zero={c.all_zero} "
              f"inversions={c.n_inversion} missing={c.n_missing} [{tag}]")
        for r in c.reasons:
            print(f"      - {r}")
    print(f"  -> {'PASS (two clocks have the right shape)' if not xc_alarm else 'ALARM (wrong-clock / inversion / out-of-band)'}")
    return 0 if (not mm and not xc_alarm) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--db", action="store_true")
    ap.add_argument("--csv", metavar="PATH",
                    help="score a CSV export of quote_v2_observations "
                         "(offline, when the DB isn't reachable here)")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.db:
        return run_db()
    if args.csv:
        return run_csv(args.csv)
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
