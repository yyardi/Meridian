"""QUOTE v2 recording-integrity scorer — the two standing checks B signed off
on for the `quote_v2_observations` table (see the model docstring in
core/quote/storage.py and docs/math/quote-v2-observation-schema.md).

    .venv/bin/python analysis/quote_v2_recording_integrity.py --selftest
    .venv/bin/python analysis/quote_v2_recording_integrity.py --db   # once data exists

Two checks, per game:

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

CANONICAL FEED ORDER (a documented assumption of check 1). The detector is
order-sensitive only when a trigger and a same-ladder response share one
receive instant. This scorer replays in the detector's canonical order
(`observed_at`, then `market_slug` — the c78432d ordering discipline). For the
reconciliation to be exact, the recording engine must feed its within-cycle
observations in that same order. `record_cycle` currently iterates
`_record_observations(s)` in returned order; if two markets of one game ever
carry a bit-identical `observed_at`, that order must be market_slug-sorted or
this check will report a spurious mismatch. Flagged forward to B — the fix is a
one-line sort on the engine's feed, and until forward data exists it cannot be
exercised. This scorer does NOT paper over it: an equal-instant collision that
diverges is reported as a real mismatch, with the collision noted.

No forward rows exist until the recording binary deploys (amendment-gated,
post-7a3a217). --selftest validates the instrument now, on synthetic streams
whose `det_*` this module itself produced via the engine's recording logic, so
it is ready the moment real rows land. --db is a no-op-clean read when the
table is empty.
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

    print()
    print("SELFTEST:", "PASS — reconciliation catches a dropped and a "
          "corrupted raw observation as named mismatches, and the cadence "
          "check flags a sub-spec gap; clean passes both. The scorer can fail."
          if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
#  --db: run the checks against the real table (clean no-op while empty)
# --------------------------------------------------------------------------- #

def _load_db() -> pd.DataFrame:
    from core.storage.base import get_engine  # lazy: selftest needs no DB
    eng = get_engine()
    q = ("SELECT game_id, market_slug, sports_market_type, observed_at, "
         "best_bid, best_ask, det_in_window, det_confirm_t0, det_version "
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
            print("quote_v2_observations not present / DB unreachable — no "
                  "forward rows yet (recording binary not deployed). Nothing "
                  "to score; not a failure.")
            return 0
        raise
    if df.empty:
        print("quote_v2_observations is empty — no forward rows yet "
              "(recording binary not deployed). Nothing to score; not a "
              "failure.")
        return 0
    games = df["game_id"].nunique()
    print(f"scoring {len(df):,} rows across {games} game(s)\n")
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
        print(f"  {c.game_id}: {c.markets} mkts, median={c.median_s:.3f}s "
              f"p99={c.p99_s:.3f}s max={c.max_s:.3f}s "
              f"violations={c.n_violations}/{c.n_gaps}")
    print(f"  -> total {tot_viol} gap(s) over spec across all games")
    return 0 if not mm else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--db", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.db:
        return run_db()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
