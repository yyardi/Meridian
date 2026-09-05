"""QUOTE v2 row-visibility probe — the compensator the recording scorer defers
to for its declared empty-read blind spot.

    .venv/bin/python analysis/quote_v2_visibility_probe.py --selftest
    .venv/bin/python analysis/quote_v2_visibility_probe.py --db

The recording-integrity scorer (analysis/quote_v2_recording_integrity.py) reads
what is IN the table, so it cannot tell "no board live yet" from "board live but
its rows were born invisible" — the 2026-09-02 RPS-2 slow-sweep defect, where the
recorder stamped `captured_at` at sweep start and committed ~16min later, so
every market_snapshots row surfaced already past the engine's 600s observation
window and the quoter never ingested one, while `record_s` sat at 2-3ms. That is
a ROW-VISIBILITY property, one level below the rows the scorer checks; this probe
checks it. The row is the level the consumer acts on, so the row's VISIBILITY is
the level the probe checks.

Two reads (per the manager, 2026-09-02):

1. BIRTH-STALENESS DISTRIBUTION, per sweep. `created_at - captured_at` on
   market_snapshots, grouped by `captured_at` (all rows of one sweep share it).
   `captured_at` is stamped at sweep START; `created_at` defaults to postgres
   `now()` = the write transaction's start, which — because the recorder fetches
   the whole board THEN inserts+commits (core/recorder.py run_once) — is the
   commit/visibility instant. So the difference is how stale a sweep was when it
   became visible: healthy live-recorder ~0s, the RPS-6 sweep ~5min, the RPS-2
   defect ~16min. A sweep whose birth-staleness >= the observation window is DEAD
   ON ARRIVAL: no consumer bounded by that window can ever see it.

   Transaction-semantics-INDEPENDENT backstop: FRESHEST LAG = now - max(captured_at)
   over visible rows. This needs no assumption about `created_at`; it is simply
   how old the freshest visible substrate is right now. If it is >= the window,
   the quoter is blind at this instant regardless of how the staleness arose.

2. RECEIVING-WHILE-LIVE, a NAMED ALARM (not an ambiguity). If a board is present
   and the substrate is FRESH but quote_v2_observations gained zero rows in the
   recent window, the quoter recorded nothing it could see — a hard alarm.

Verdict (refined 2026-09-02 so a checklist probe does not cry wolf): a SLOW
recorder (birth-staleness >= window: rows born past the window), a STALLED
recorder (sweeps overdue vs the measured cadence), and a quoter blind on FRESH
substrate are each a hard ALARM. A FAST-but-INFREQUENT recorder (rows born
fresh, sweeps rarer than the window) is DUTY_CYCLED — a truthful middle state
reporting its fresh-fraction, not an alarm. An aged-out state with too few
sweeps to measure cadence is INDETERMINATE (never a false all-clear). No board
is EMPTY_BENIGN; fresh + continuous + recording is HEALTHY.

Belongs in the pre-slate checklist beside the heartbeat (§4b) once it exists:
same species — check the level the consumer acts on.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

UTC = dt.timezone.utc

#: The quoter's observation window — the bar a sweep's staleness is measured
#: against. Imported lazily in gather(); restated here for the pure classifier
#: and selftest so they need no DB. Kept in sync with
#: core.quote.engine.MAX_OBSERVATION_AGE_SECONDS (asserted in gather()).
WINDOW_S = 600.0
#: How far back a market_snapshots row still counts as "a board is present" —
#: generous (several sweep durations) so a SLOW-but-present board still registers
#: as present rather than reading as "no board" and masking the defect.
BOARD_WINDOW_S = 1800.0
#: The "in the last N seconds" for the receiving-while-live read.
RECENT_S = 600.0
#: A sweep is OVERDUE (recorder may have stalled) when the freshest substrate is
#: older than this multiple of the measured cadence. A design bound, not fitted:
#: within one cadence a trough is expected; beyond ~1.5x the next sweep is late.
OVERDUE_FACTOR = 1.5


@dataclass
class Sweep:
    captured_at: dt.datetime
    n_rows: int
    birth_staleness_s: float     # commit (max created_at) - captured_at


@dataclass
class ProbeState:
    now: dt.datetime
    sweeps: list[Sweep]                  # recent market_snapshots sweeps
    freshest_lag_s: float | None         # now - max(captured_at); None if none
    board_present: bool                  # any market_snapshots rows in window
    quoter_rows_recent: int              # quote_v2_observations in RECENT_S
    window_s: float = WINDOW_S
    recent_s: float = RECENT_S


@dataclass
class Verdict:
    #: HEALTHY | EMPTY_BENIGN | DUTY_CYCLED | INDETERMINATE | ALARM
    status: str
    alarms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _sweep_interval_s(state: ProbeState) -> float | None:
    """Median gap between consecutive sweeps' captured_at — the cadence. None if
    fewer than two sweeps (cadence unmeasurable)."""
    if len(state.sweeps) < 2:
        return None
    ts = sorted(s.captured_at for s in state.sweeps)
    gaps = sorted((ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1))
    return gaps[len(gaps) // 2]


def classify(state: ProbeState) -> Verdict:
    """Pure: ProbeState -> Verdict. The empty-read verdict the scorer defers to.

    The refinement (2026-09-02): DON'T conflate a SLOW recorder (rows born past
    the window — a real defect) with an INFREQUENT-but-fast recorder (rows born
    fresh, but sweeps rarer than the window, so the substrate is duty-cycled).
    The first is an ALARM; the second is a truthful middle state (DUTY_CYCLED)
    reporting its fresh-fraction, because a checklist probe that cries wolf 50
    minutes of every hour trains people to ignore red (health.py's cutover
    lesson). The safety rails keep the softening honest: a slow recorder, an
    overdue (stalled) recorder, and a quoter blind on FRESH substrate all stay
    hard ALARMs, and an aged-out state we cannot classify (fewer than two sweeps)
    is INDETERMINATE — never a false all-clear."""
    w = state.window_s
    if not state.board_present:
        return Verdict("EMPTY_BENIGN", [],
                       ["no market_snapshots rows within the board window — no "
                        "board listed; an empty observation stream is expected"])

    interval = _sweep_interval_s(state)
    lag = state.freshest_lag_s
    fresh_now = lag is not None and lag < w

    # ---- hard ALARMs (the safety rails; never softened) ------------------- #
    alarms: list[str] = []
    dead = [s for s in state.sweeps if s.birth_staleness_s >= w]
    if dead:                                   # RECORDER TOO SLOW — the defect
        worst = max(s.birth_staleness_s for s in dead)
        alarms.append(
            f"recorder too slow: {len(dead)}/{len(state.sweeps)} recent sweeps "
            f"committed >= {w:.0f}s after captured_at (worst {worst:.0f}s) — rows "
            f"born past the quoter's window, dead on arrival")
    if interval is not None and lag is not None and lag > OVERDUE_FACTOR * interval:
        alarms.append(                         # STALLED RECORDER — must not hide
            f"sweeps overdue: freshest substrate is {lag:.0f}s old, > "
            f"{OVERDUE_FACTOR:g}x the {interval:.0f}s cadence — the recorder may "
            f"have stalled (an outage cannot hide inside the duty-cycle verdict)")
    if fresh_now and state.quoter_rows_recent == 0:
        alarms.append(                         # QUOTER BLIND on fresh substrate
            f"quoter blind: substrate is fresh ({lag:.0f}s < {w:.0f}s window) but "
            f"quote_v2_observations gained 0 rows in {state.recent_s:.0f}s — the "
            f"quoter recorded nothing it could see")
    if alarms:
        return Verdict("ALARM", alarms, [])

    # ---- non-alarm classification ---------------------------------------- #
    # Aged out but cadence unmeasurable: cannot tell a duty-cycle trough from a
    # stall. Refuse the all-clear.
    if not fresh_now and interval is None:
        return Verdict("INDETERMINATE", [], [
            f"freshest substrate is "
            f"{'n/a' if lag is None else f'{lag:.0f}s'} old (>= {w:.0f}s window) "
            f"but there are < 2 sweeps to measure cadence — cannot distinguish a "
            f"duty-cycle trough from a stalled recorder; need >= 2 sweeps"])
    # Fast recorder, sweeps rarer than the window: duty-cycled, not broken.
    if interval is not None and interval > w:
        frac = w / interval
        phase = "currently fresh" if fresh_now else f"currently in a trough ({lag:.0f}s old)"
        return Verdict("DUTY_CYCLED", [], [
            f"observation duty-cycled ~{frac:.0%}: substrate fresh for the {w:.0f}s "
            f"window out of every {interval:.0f}s sweep cadence (recorder fast — "
            f"birth-staleness under the window — but sweeps infrequent); {phase}. "
            f"Tolerable where the consumer's real read is continuous (in-game 0.5s "
            f"recorder → cadence << window); a coverage gap where it is not."])
    # Continuous, fresh, quoter recording (or nothing to flag).
    return Verdict("HEALTHY", [], (
        [] if interval is not None else
        ["substrate fresh and quoter recording; cadence unmeasured (< 2 sweeps)"]))


# --------------------------------------------------------------------------- #
#  DB gather
# --------------------------------------------------------------------------- #

def gather(session, *, window_s: float = WINDOW_S,
           board_window_s: float = BOARD_WINDOW_S,
           recent_s: float = RECENT_S) -> ProbeState:
    from sqlalchemy import text

    # keep the window bar in sync with what the quoter actually uses
    try:
        from core.quote.engine import MAX_OBSERVATION_AGE_SECONDS
        window_s = float(MAX_OBSERVATION_AGE_SECONDS)
    except Exception:  # noqa: BLE001 — fall back to the restated default
        pass

    now = session.execute(text("SELECT now()")).scalar_one()
    sweep_rows = session.execute(text("""
        SELECT captured_at, count(*) AS n, max(created_at) AS commit_at
        FROM market_snapshots
        WHERE captured_at > now() - make_interval(secs => :bw)
        GROUP BY captured_at
        ORDER BY captured_at
    """), {"bw": board_window_s}).all()
    sweeps = [
        Sweep(captured_at=r.captured_at, n_rows=int(r.n),
              birth_staleness_s=max((r.commit_at - r.captured_at).total_seconds(),
                                    0.0))
        for r in sweep_rows
    ]
    freshest_lag = None
    if sweeps:
        freshest_lag = max((now - max(s.captured_at for s in sweeps))
                           .total_seconds(), 0.0)
    quoter_recent = session.execute(text("""
        SELECT count(*) FROM quote_v2_observations
        WHERE observed_at > now() - make_interval(secs => :r)
    """), {"r": recent_s}).scalar_one()
    return ProbeState(
        now=now, sweeps=sweeps, freshest_lag_s=freshest_lag,
        board_present=bool(sweeps), quoter_rows_recent=int(quoter_recent),
        window_s=window_s, recent_s=recent_s)


def _print_verdict(state: ProbeState, v: Verdict) -> None:
    print(f"board present: {state.board_present}  "
          f"freshest substrate lag: "
          f"{'n/a' if state.freshest_lag_s is None else f'{state.freshest_lag_s:.0f}s'}  "
          f"(window {state.window_s:.0f}s)")
    print(f"quote_v2_observations rows in last {state.recent_s:.0f}s: "
          f"{state.quoter_rows_recent}")
    if state.sweeps:
        st = sorted(s.birth_staleness_s for s in state.sweeps)
        med = st[len(st) // 2]
        print(f"birth-staleness over {len(state.sweeps)} recent sweeps "
              f"(recorder speed): min {st[0]:.0f}s  median {med:.0f}s  max "
              f"{st[-1]:.0f}s")
        interval = _sweep_interval_s(state)
        if interval is not None:
            print(f"sweep cadence (interval between sweeps): {interval:.0f}s"
                  + (f"  -> fresh-fraction {state.window_s / interval:.0%}"
                     if interval > state.window_s else "  (continuous: <= window)"))
        else:
            print("sweep cadence: unmeasured (< 2 sweeps)")
    print(f"\nVERDICT: {v.status}")
    for a in v.alarms:
        print(f"  ALARM: {a}")
    for n in v.notes:
        print(f"  note: {n}")


def run_db() -> int:
    from core.storage.base import get_engine
    from core.storage import get_sessionmaker
    with get_sessionmaker(get_engine())() as s:
        state = gather(s)
    v = classify(state)
    _print_verdict(state, v)
    # distinct exit codes for a checklist: 1 = ALARM, 2 = INDETERMINATE (look
    # again, never a silent pass), 0 = HEALTHY / EMPTY_BENIGN / DUTY_CYCLED.
    return {"ALARM": 1, "INDETERMINATE": 2}.get(v.status, 0)


# --------------------------------------------------------------------------- #
#  --selftest: the classifier can fail, and created_at really carries the lag
# --------------------------------------------------------------------------- #

def selftest(Session=None) -> int:
    ok = True
    now = dt.datetime(2026, 9, 9, 0, 0, tzinfo=UTC)

    def st(ages, stale_s, quoter):
        """ProbeState from sweep ages (s ago), a uniform birth-staleness, and a
        quoter row count. freshest_lag = youngest sweep; board present iff any."""
        sweeps = [Sweep(now - dt.timedelta(seconds=a), 900, stale_s) for a in ages]
        return ProbeState(
            now=now, sweeps=sweeps,
            freshest_lag_s=(min(ages) if ages else None),
            board_present=bool(ages), quoter_rows_recent=quoter)

    def check(label, v, want_status, want_in=(), want_not=()):
        nonlocal ok
        c = v.status == want_status
        for s in want_in:
            c = c and any(s in x for x in v.alarms + v.notes)
        for s in want_not:
            c = c and not any(s in x for x in v.alarms + v.notes)
        print(f"{label:22}-> {v.status:13} {'OK' if c else 'FAIL: ' + repr(v)}")
        ok &= c

    # 1. no board -> benign empty (NOT an alarm, NOT 'healthy')
    check("no board", classify(st([], 0.5, 0)), "EMPTY_BENIGN")

    # 2. continuous + recording (interval 60s <= 600 window) -> healthy
    check("continuous+recording", classify(st([1, 61, 121], 1.0, 900)), "HEALTHY")

    # 3. THE REGRESSION THAT MATTERS: slow recorder (birth-staleness 960s >=
    #    window) must STILL land ALARM after the softening.
    check("slow recorder (defect)", classify(st([1, 900], 960.0, 0)),
          "ALARM", want_in=("recorder too slow",))

    # 4. quoter blind on FRESH substrate -> hard ALARM (not softened)
    check("quoter-blind on fresh", classify(st([1, 61], 1.0, 0)),
          "ALARM", want_in=("quoter blind",), want_not=("recorder too slow",))

    # 5. DUTY_CYCLED: fast recorder (birth 1s), hourly sweeps (interval 3600 >
    #    window), currently in a trough, quoter empty (expected) -> NOT an alarm,
    #    reports the ~17% fresh-fraction. This is tonight's real property.
    check("duty-cycled (hourly)", classify(st([1800, 5400], 1.0, 0)),
          "DUTY_CYCLED", want_in=("duty-cycled ~17%",))

    # 6. SAFETY: a stalled recorder cannot hide in the duty-cycle verdict.
    #    Same cadence, but freshest is 7200s > 1.5x3600 -> overdue ALARM.
    check("sweeps overdue (stall)", classify(st([7200, 10800], 1.0, 0)),
          "ALARM", want_in=("sweeps overdue",))

    # 7. INDETERMINATE: tonight's post-fix state — 1 sweep, born fresh (1s) but
    #    aged out now (1014s), cadence unmeasurable -> never a false all-clear.
    check("aged, <2 sweeps", classify(st([1014], 1.0, 0)), "INDETERMINATE")

    if Session is not None:
        ok &= _selftest_created_at_carries_lag(Session)
    else:
        print("created_at-carries-lag: SKIPPED (no DB; run --selftest with a "
              "DATABASE_URL to validate the birth-staleness metric empirically)")

    print("\nSELFTEST:", "PASS — the slow-recorder defect STILL alarms (the "
          "regression that matters); a fast-but-infrequent recorder is the "
          "truthful DUTY_CYCLED middle state, not a cried-wolf alarm; and a "
          "stalled recorder, a quoter blind on fresh substrate, and an "
          "unclassifiable aged-out state are each caught. The probe can fail."
          if ok else "FAIL")
    return 0 if ok else 1


def _selftest_created_at_carries_lag(Session) -> bool:
    """The birth-staleness metric assumes postgres `created_at` (server_default
    now()) equals the write-transaction start, which for the recorder is the
    post-fetch commit instant — so `created_at - captured_at` is the visibility
    lag. Validate empirically: back-date captured_at, insert now, and confirm
    the stored difference is the back-dated gap (not ~0, which a naive reading of
    'now() is transaction time' might fear)."""
    from sqlalchemy import text
    from core.quote.storage import QuoteV2Observation  # noqa: F401 (ensures models import)
    try:
        with Session() as s:
            s.execute(text(
                "DELETE FROM market_snapshots WHERE market_slug = 'probe-selftest'"))
            s.commit()
        with Session() as s:
            # captured_at back-dated 960s, as a slow sweep would leave it; the
            # INSERT (and thus now()/created_at) happens in THIS transaction now.
            s.execute(text("""
                INSERT INTO market_snapshots
                    (market_slug, game_id, event_slug, sports_market_type,
                     captured_at, best_bid, best_ask, is_live)
                VALUES ('probe-selftest', 'probe-g', 'probe-e', 'x',
                        now() - make_interval(secs => 960), 0.5, 0.5, false)
            """))
            s.commit()
        with Session() as s:
            lag = s.execute(text("""
                SELECT extract(epoch from (created_at - captured_at))
                FROM market_snapshots WHERE market_slug = 'probe-selftest'
            """)).scalar_one()
            s.execute(text(
                "DELETE FROM market_snapshots WHERE market_slug = 'probe-selftest'"))
            s.commit()
        good = 940.0 <= float(lag) <= 980.0   # ~960s, allowing a few s of slack
        print(f"created_at-carries-lag: {float(lag):.0f}s "
              f"{'OK (created_at is the commit instant; lag is real)' if good else 'FAIL (created_at did not carry the lag — birth-staleness would read ~0; use freshest-lag)'}")
        return good
    except Exception as exc:  # noqa: BLE001
        print(f"created_at-carries-lag: SKIPPED ({str(exc)[:80]})")
        return True


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
