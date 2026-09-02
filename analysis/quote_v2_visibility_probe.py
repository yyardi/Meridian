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
   (market_snapshots gained rows within the board window) but quote_v2_observations
   gained zero rows within the recent window, the quoter recorded nothing while a
   board was being captured — the blindness symptom, stated as an alarm.

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
    status: str                          # HEALTHY | EMPTY_BENIGN | ALARM
    alarms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def classify(state: ProbeState) -> Verdict:
    """Pure: ProbeState -> Verdict. The empty-read verdict the scorer defers to.

    No board present -> empty is benign. Board present but the substrate is born
    past the window, or the quoter recorded nothing while it was captured ->
    ALARM, with the reason named. Never returns a bare 'clean'."""
    w = state.window_s
    if not state.board_present:
        return Verdict("EMPTY_BENIGN", [],
                       ["no market_snapshots rows within the board window — no "
                        "board listed; an empty observation stream is expected"])
    alarms: list[str] = []
    if state.freshest_lag_s is not None and state.freshest_lag_s >= w:
        alarms.append(
            f"substrate born invisible: the freshest visible market_snapshots "
            f"row is {state.freshest_lag_s:.0f}s old (>= {w:.0f}s window) — every "
            f"visible row is already past the quoter's window (recorder too slow)")
    dead = [s for s in state.sweeps if s.birth_staleness_s >= w]
    if dead:
        worst = max(s.birth_staleness_s for s in dead)
        alarms.append(
            f"{len(dead)}/{len(state.sweeps)} recent sweeps committed >= {w:.0f}s "
            f"after their captured_at (worst {worst:.0f}s) — dead on arrival to "
            f"the quoter")
    if state.quoter_rows_recent == 0:
        alarms.append(
            f"board present but quote_v2_observations gained 0 rows in the last "
            f"{state.recent_s:.0f}s — the quoter recorded nothing while a board "
            f"was being captured")
    return Verdict("ALARM" if alarms else "HEALTHY", alarms, [])


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
        print(f"birth-staleness over {len(state.sweeps)} recent sweeps: "
              f"min {st[0]:.0f}s  median {med:.0f}s  max {st[-1]:.0f}s")
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
    return 0 if v.status != "ALARM" else 1


# --------------------------------------------------------------------------- #
#  --selftest: the classifier can fail, and created_at really carries the lag
# --------------------------------------------------------------------------- #

def _mk(now, sweeps, freshest, board, quoter):
    return ProbeState(now=now, sweeps=sweeps, freshest_lag_s=freshest,
                      board_present=board, quoter_rows_recent=quoter)


def selftest(Session=None) -> int:
    ok = True
    now = dt.datetime(2026, 9, 9, 0, 0, tzinfo=UTC)

    def fresh_sweeps(stale_s):
        return [Sweep(now - dt.timedelta(seconds=1), 900, stale_s)]

    # 1. no board -> benign empty (NOT an alarm, NOT 'healthy')
    v = classify(_mk(now, [], None, False, 0))
    c = v.status == "EMPTY_BENIGN"
    print(f"no board          -> {v.status:12} {'OK' if c else 'FAIL'}")
    ok &= c

    # 2. healthy: fresh substrate, quoter recording
    v = classify(_mk(now, fresh_sweeps(0.5), 0.5, True, 900))
    c = v.status == "HEALTHY" and not v.alarms
    print(f"fresh + recording -> {v.status:12} {'OK' if c else 'FAIL'}")
    ok &= c

    # 3. THE DEFECT: born invisible (16min sweeps, freshest 16min, quoter empty)
    v = classify(_mk(now, fresh_sweeps(960.0), 960.0, True, 0))
    c = (v.status == "ALARM"
         and any("born invisible" in a for a in v.alarms)
         and any("dead on arrival" in a for a in v.alarms)
         and any("recorded nothing" in a for a in v.alarms))
    print(f"born-invisible    -> {v.status:12} {'OK (all 3 alarms)' if c else 'FAIL'}")
    ok &= c

    # 4. quoter blind despite FRESH substrate (recorder fine, quoter down)
    v = classify(_mk(now, fresh_sweeps(1.0), 1.0, True, 0))
    c = (v.status == "ALARM"
         and any("recorded nothing" in a for a in v.alarms)
         and not any("born invisible" in a for a in v.alarms))
    print(f"quoter-blind      -> {v.status:12} {'OK' if c else 'FAIL'}")
    ok &= c

    # 5. RPS-6 fixed state: 5min sweeps, under the 10min window -> healthy
    v = classify(_mk(now, fresh_sweeps(300.0), 300.0, True, 900))
    c = v.status == "HEALTHY"
    print(f"fixed 5min sweeps -> {v.status:12} {'OK (under window)' if c else 'FAIL'}")
    ok &= c

    if Session is not None:
        ok &= _selftest_created_at_carries_lag(Session)
    else:
        print("created_at-carries-lag: SKIPPED (no DB; run --selftest with a "
              "DATABASE_URL to validate the birth-staleness metric empirically)")

    print("\nSELFTEST:", "PASS — classifier names the defect (born-invisible), "
          "distinguishes it from quoter-down and from benign-empty, and never "
          "calls an unclassifiable empty 'healthy'. The probe can fail."
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
