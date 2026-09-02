"""Registered proof-1 (amendment 10): QUOTE v2 replayed on the pinned Aug tape
produces byte-identical quoting decisions to the frozen v1 commit (7a3a217).

The rule-11 form (docs/math/quote-v2-program.md): NOT the synthetic selftest in
engine_v2 (that is the fast regression guard) but a replay of BOTH engines over
the pinned market_snapshots substrate that produced the 17,032-fill ledger,
comparing `_standing` + fills byte-for-byte, WITH the fill-population
reproduction as the substrate-integrity check. If the replay does not reproduce
the ledgered in-game fill population from this substrate, that is a finding
about the pin or the shim — stop and look, do not proceed.

Substrate (manager decision (a), cut from prod): the pin whose md5 this asserts
before reading a byte — the exact `market_snapshots` table the running quoter
read, window 2026-08-17 12:00 → 2026-08-23 00:00 UTC, game_id on every row.

How the replay stays faithful WITHOUT modifying v1's quoting:
* both engines run v1's `cycle()` UNCHANGED (v2 inherits it — proven
  structurally in engine_v2). The replay only replaces the observation SOURCE
  (a shim overriding `_observations` to return the as-of fresh set) and the
  session (a capture-only fake) — identically for both engines, so any
  divergence could come only from v2 overriding a quoting method, which it does
  not. The shim is the definition of "replay"; it changes no decision logic.
* the as-of fresh set at cycle time t = newest snapshot per market with
  captured_at in (t-MAX_OBSERVATION_AGE_SECONDS, t] and ask>bid — exactly what
  the live `_observations` query returns, minus the now()-coupling.
* cycles step at the engine's 5s interval across the observation stream.
"""

from __future__ import annotations

import gzip
import hashlib
import sys
from pathlib import Path

from core.quote.engine import (
    MAX_OBSERVATION_AGE_SECONDS,
    Observation,
    ShadowQuoter,
)
from core.quote.engine_v2 import ShadowQuoterV2

ROOT = Path(__file__).resolve().parent.parent
import os
EXPORTS = Path(os.environ.get("MERIDIAN_EXPORTS_DIR", ROOT / "backups" / "exports"))
PIN = EXPORTS / "market_snapshots_quote_replay_20260902T173700Z.csv.gz"
PIN_MD5 = "b740d2fb6dcd5f325877cf8281a97c42"
CYCLE_S = 5.0                      # v1's DEFAULT_INTERVAL_SECONDS
FRESH_S = MAX_OBSERVATION_AGE_SECONDS


def _verify_pin() -> None:
    h = hashlib.md5()
    with open(PIN, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    got = h.hexdigest()
    assert got == PIN_MD5, f"pin md5 mismatch: {got} != {PIN_MD5} — refuse to replay"
    print(f"pin md5 verified: {got}")


# --------------------------------------------------------------------------- #
# Replay shims — observation source + capture-only session, identical for both.
# --------------------------------------------------------------------------- #

class _FakeSession:
    """Captures the fills cycle() would have written; no DB."""

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

    def execute(self, *a, **k):      # settle path is disabled; backstop only
        class _R:
            def all(self_inner):
                return []
        return _R()


class _ReplayMixin:
    """Feeds a pre-set observation batch and captures fills. Overrides only the
    DATA SOURCE, never a quoting method (cycle/_fill/requote stay v1's)."""

    def _install_replay(self):
        import time
        self._pending: list[Observation] = []
        self._committed: list = []
        self._Session = lambda: _FakeSession(self._committed)
        # keep the settle path disabled (settle_every is huge, but _last_settle
        # starts at -inf so the first cycle would still fire it).
        self._last_settle = time.monotonic()

    def _observations(self, session):
        return self._pending

    def run_cycle(self, obs: list[Observation]):
        self._pending = obs
        self._committed = []
        # keep the fake session pointing at the fresh sink each cycle
        sink = self._committed
        self._Session = lambda: _FakeSession(sink)
        self.cycle()
        return list(self._committed)


class ReplayV1(_ReplayMixin, ShadowQuoter):
    pass


class ReplayV2(_ReplayMixin, ShadowQuoterV2):
    pass


def _make(cls):
    q = cls(sessionmaker=None, settle_every_seconds=10 ** 12,
            settlement_lookup=lambda s: None)
    q._install_replay()
    return q


# --------------------------------------------------------------------------- #
# Build the cycle sequence from the pin (single chronological pass).
# --------------------------------------------------------------------------- #

def build_cycles():
    import csv
    import datetime as dt

    def parse(ts):
        # '2026-08-17 12:30:26.331171+00' -> aware datetime
        return dt.datetime.fromisoformat(ts.replace("+00", "+00:00"))

    last: dict[str, Observation] = {}
    cycles = []
    last_cycle_t = None
    n = 0
    with gzip.open(PIN, "rt") as fh:
        r = csv.DictReader(fh)
        for row in r:
            n += 1
            bb, ba = row["best_bid"], row["best_ask"]
            gid = row["game_id"]
            if not bb or not ba or not gid:
                continue
            t = parse(row["captured_at"])
            last[row["market_slug"]] = Observation(
                market_slug=row["market_slug"], game_id=str(gid),
                captured_at=t, bid=float(bb), ask=float(ba),
                is_live=(row["is_live"] == "t"))
            if last_cycle_t is None or (t - last_cycle_t).total_seconds() >= CYCLE_S:
                fresh = [o for o in last.values()
                         if 0 <= (t - o.captured_at).total_seconds() <= FRESH_S
                         and o.ask > o.bid]
                cycles.append(fresh)
                last_cycle_t = t
    print(f"pin rows read: {n:,}; cycles built: {len(cycles):,}")
    return cycles


def _standing(q):
    return {k: (v.bid_price, v.ask_price, v.regime, v.quoted_at)
            for k, v in q._standing.items()}


def _fill_key(f):
    # a fill's identity for byte-comparison
    return (f.market_slug, f.side, float(f.quote_price), float(f.mid_at_fill),
            f.quoted_at, f.filled_at)


def main() -> int:
    import logging
    import structlog
    structlog.configure(          # the fill INFO log per fill would flood; quiet it
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    _verify_pin()
    cycles = build_cycles()

    v1, v2 = _make(ReplayV1), _make(ReplayV2)
    total_fills = ingame_fills = 0
    diverged = 0
    for i, obs in enumerate(cycles):
        f1 = v1.run_cycle(obs)
        f2 = v2.run_cycle(obs)
        s1, s2 = _standing(v1), _standing(v2)
        k1 = sorted(_fill_key(f) for f in f1)
        k2 = sorted(_fill_key(f) for f in f2)
        if s1 != s2 or k1 != k2:
            diverged += 1
            if diverged <= 3:
                print(f"  DIVERGENCE at cycle {i}: standing_eq={s1==s2} fills_eq={k1==k2}")
        total_fills += len(f1)
        ingame_fills += sum(1 for f in f1 if f.regime == "ingame")

    print("\n=== registered proof-1 result ===")
    print(f"cycles replayed        : {len(cycles):,}")
    print(f"v1==v2 byte-identical  : {'YES (all cycles)' if diverged == 0 else f'NO ({diverged} diverged)'}")
    print(f"fills reproduced       : {total_fills:,} total / {ingame_fills:,} in-game")
    print(f"ledger substrate check : ledger in-game = 17,032 (from this substrate)")
    ok_equiv = diverged == 0
    # substrate-integrity: in-game reproduction within a tolerance band of the
    # ledger (exact match is not expected — the live cycle timing drifted vs a
    # regular 5s grid; a gross miss is the finding).
    ratio = ingame_fills / 17032 if ingame_fills else 0
    print(f"in-game reproduction ratio: {ratio:.2f} (1.0 = exact; band flags a pin/shim finding)")
    if not ok_equiv:
        print("PROOF-1 FAILED: v2 diverged from v1 — do not rebind the freeze.")
        return 1
    print("PROOF-1 (equivalence): PASS — v2 quoting == v1 on the pinned substrate.")
    if not (0.7 <= ratio <= 1.3):
        print("SUBSTRATE-INTEGRITY FLAG: in-game reproduction outside [0.7,1.3] — "
              "stop and look (pin coverage or shim cadence), per the manager's rule.")
        return 2
    print("SUBSTRATE-INTEGRITY: in-game fill population reproduced within band.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
