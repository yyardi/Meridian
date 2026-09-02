"""Registered proof-1 (amendment 10): QUOTE v2 on the pinned Aug tape is
byte-identical to the frozen v1 (7a3a217), AND the pin is the complete
substrate that produced the 17,032-fill ledger.

Two parts, deliberately separated because they answer different questions and
one is cadence-independent while the other looked cadence-dependent until it
was reframed:

1. EQUIVALENCE (the rebind's core). Replay BOTH engines over the pin and assert
   `_standing` + fills byte-identical, every cycle. Both run v1's `cycle()`
   UNCHANGED (v2 inherits it — proven structurally in engine_v2); the replay
   replaces only the observation SOURCE and the session, identically for both,
   so a divergence could come only from v2 overriding a quoting method, which
   it does not. This holds on ANY faithful grid — it is cadence-independent.

2. SUBSTRATE COMPLETENESS (the integrity companion). The original prescribed
   form — "the replay reproduces the ledger fill population" — has a flaw found
   while building it: v1's EXACT cycle grid is unrecorded (only the fills'
   quoted_at/filled_at survive, a sparse subset of v1's continuous ~5s
   cadence), so any from-substrate replay reproduces the population only up to
   cadence, and a "trigger fell between cycles → grid artifact" attributor
   rubber-stamps ANYTHING (a deliberately-too-sparse instant grid "passed" at
   7% reproduction with 100% of misses labelled grid artifacts — proof the
   attributor is vacuous). The SOUND, cadence-independent integrity check is
   direct: does the pin CONTAIN, for every one of the 17,032 ledgered fills,
   the producing observations — the quote observation at `quoted_at` and the
   trigger observation at `filled_at`, the latter with mid == the ledger's
   `mid_at_fill` and crossing the quote? Present for all ⇒ the pin is the
   complete producing substrate (integrity confirmed), fill by fill, exactly,
   with no cadence dependence. ANY absent ⇒ a substrate hole ⇒ stop and look.

Pin (manager decision (a), cut from prod): md5 asserted before a byte is read.
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import os
import sys
from pathlib import Path

from core.quote.engine import (
    MAX_OBSERVATION_AGE_SECONDS,
    Observation,
    ShadowQuoter,
)
from core.quote.engine_v2 import ShadowQuoterV2

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = Path(os.environ.get("MERIDIAN_EXPORTS_DIR", ROOT / "backups" / "exports"))
PIN = EXPORTS / "market_snapshots_quote_replay_20260902T173700Z.csv.gz"
PIN_MD5 = "b740d2fb6dcd5f325877cf8281a97c42"
FILLS_PIN = EXPORTS / "quote_fills_v1_20260902T161223Z.csv"
CYCLE_S = 5.0                       # v1's DEFAULT_INTERVAL_SECONDS (equivalence grid)
FRESH_S = MAX_OBSERVATION_AGE_SECONDS


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("+00", "+00:00"))


def _verify_pin() -> None:
    h = hashlib.md5()
    with open(PIN, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == PIN_MD5, f"pin md5 mismatch — refuse to replay"
    print(f"pin md5 verified: {h.hexdigest()}")


# ---- replay shims (equivalence) — DATA SOURCE only, no quoting method ------ #

class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def add(self, obj):
        self._sink.append(obj)

    def commit(self):
        pass

    def execute(self, *a, **k):
        class _R:
            def all(self_inner):
                return []
        return _R()


class _ReplayMixin:
    def _install_replay(self):
        import time
        self._pending = []
        self._committed = []
        self._Session = lambda: _FakeSession(self._committed)
        self._last_settle = time.monotonic()   # keep the settle path disabled

    def _observations(self, session):
        return self._pending

    def run_cycle(self, obs):
        self._pending = obs
        sink = []
        self._committed = sink
        self._Session = lambda: _FakeSession(sink)
        self.cycle()
        return list(sink)


class ReplayV1(_ReplayMixin, ShadowQuoter):
    pass


class ReplayV2(_ReplayMixin, ShadowQuoterV2):
    pass


def _make(cls):
    q = cls(sessionmaker=None, settle_every_seconds=10 ** 12,
            settlement_lookup=lambda s: None)
    q._install_replay()
    return q


def _standing(q):
    return {k: (v.bid_price, v.ask_price, v.regime, v.quoted_at)
            for k, v in q._standing.items()}


def _fill_key(f):
    return (f.market_slug, f.side, float(f.quote_price), float(f.mid_at_fill),
            f.quoted_at, f.filled_at)


# --------------------------------------------------------------------------- #

def load_ledger_ingame():
    """(market, side, quoted_at, filled_at, quote_price, mid_at_fill) per fill."""
    out = []
    with open(FILLS_PIN) as fh:
        for row in csv.DictReader(fh):
            if row["regime"] != "ingame":
                continue
            out.append((row["market_slug"], row["side"],
                        _parse(row["quoted_at"]), _parse(row["filled_at"]),
                        float(row["quote_price"]), float(row["mid_at_fill"])))
    return out


def one_pass(target_events):
    """Single chronological pass over the pin: build the 5s equivalence grid AND
    collect the (bid,ask,mid) of every target (market, captured_at) event."""
    last: dict[str, Observation] = {}
    cycles = []
    last_cycle_t = None
    obs_at: dict = {}
    n = 0
    with gzip.open(PIN, "rt") as fh:
        for row in csv.DictReader(fh):
            n += 1
            bb, ba, gid = row["best_bid"], row["best_ask"], row["game_id"]
            if not bb or not ba or not gid:
                continue
            t = _parse(row["captured_at"])
            bid, ask = float(bb), float(ba)
            key = (row["market_slug"], t)
            if key in target_events:
                obs_at[key] = (bid, ask, (bid + ask) / 2.0)
            last[row["market_slug"]] = Observation(
                market_slug=row["market_slug"], game_id=str(gid),
                captured_at=t, bid=bid, ask=ask, is_live=(row["is_live"] == "t"))
            if last_cycle_t is None or (t - last_cycle_t).total_seconds() >= CYCLE_S:
                fresh = [o for o in last.values()
                         if 0 <= (t - o.captured_at).total_seconds() <= FRESH_S
                         and o.ask > o.bid]
                cycles.append(fresh)
                last_cycle_t = t
    print(f"pin rows read: {n:,}; equivalence cycles: {len(cycles):,}")
    return cycles, obs_at


def main() -> int:
    import logging
    import structlog
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    _verify_pin()

    ledger = load_ledger_ingame()
    targets = {(m, q) for (m, s, q, f, qp, mf) in ledger} \
        | {(m, f) for (m, s, q, f, qp, mf) in ledger}
    print(f"ledger in-game fills: {len(ledger):,}")
    cycles, obs_at = one_pass(targets)

    # --- part 1: EQUIVALENCE (byte-identical, cadence-independent) --------- #
    v1, v2 = _make(ReplayV1), _make(ReplayV2)
    diverged = 0
    for i, obs in enumerate(cycles):
        f1 = v1.run_cycle(obs)
        f2 = v2.run_cycle(obs)
        if sorted(_fill_key(f) for f in f1) != sorted(_fill_key(f) for f in f2) \
                or _standing(v1) != _standing(v2):
            diverged += 1
            if diverged <= 3:
                print(f"  DIVERGENCE at cycle {i}")

    # --- part 2: SUBSTRATE COMPLETENESS (per fill, exact, cadence-free) ---- #
    q_missing = t_missing = t_midmismatch = t_nocross = 0
    holes = []
    for (m, side, q, f, qp, mf) in ledger:
        if (m, q) not in obs_at:
            q_missing += 1
            holes.append((m, side, "quote_obs_absent", q))
            continue
        to = obs_at.get((m, f))
        if to is None:
            t_missing += 1
            holes.append((m, side, "trigger_obs_absent", f))
            continue
        _, _, mid = to
        if abs(mid - mf) > 1e-9:
            t_midmismatch += 1
            holes.append((m, side, "trigger_mid!=ledger", f))
            continue
        crosses = (mid <= qp) if side == "bid" else (mid >= qp)
        if not crosses:
            t_nocross += 1
            holes.append((m, side, "trigger_no_cross", f))
    confirmed = len(ledger) - len(holes)

    print("\n=== registered proof-1 result ===")
    print("PART 1 — EQUIVALENCE (rebind core):")
    print(f"  cycles replayed       : {len(cycles):,}")
    print(f"  v1==v2 byte-identical : "
          f"{'YES (all cycles)' if diverged == 0 else f'NO ({diverged} diverged)'}")
    print("PART 2 — SUBSTRATE COMPLETENESS (integrity companion, per fill):")
    print(f"  ledgered in-game fills             : {len(ledger):,}")
    print(f"  producing obs present & matching    : {confirmed:,}")
    print(f"  quote-obs absent (hole)            : {q_missing:,}")
    print(f"  trigger-obs absent (hole)          : {t_missing:,}")
    print(f"  trigger mid != ledger mid_at_fill  : {t_midmismatch:,}")
    print(f"  trigger present but no cross       : {t_nocross:,}")

    ok = True
    if diverged != 0:
        print("\nEQUIVALENCE FAILED — v2 diverged from v1. Do NOT rebind.")
        ok = False
    else:
        print("\nEQUIVALENCE: PASS — v2 quoting == v1, all cycles, on the pin.")
    if holes:
        print(f"SUBSTRATE FINDING: {len(holes)} ledgered fills whose producing "
              "observation is absent/mismatched in the pin — the pin is NOT the "
              "complete producing substrate. STOP AND LOOK. Sample:")
        for h in holes[:10]:
            print(f"    {h}")
        ok = False
    else:
        print("SUBSTRATE COMPLETENESS: PASS — for ALL 17,032 fills the pin "
              "contains the quote observation AND the trigger observation, the "
              "trigger's mid equals the ledger's mid_at_fill and crosses the "
              "quote. Zero holes, exact, fill-by-fill, cadence-independent. The "
              "pin IS the complete producing substrate.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
