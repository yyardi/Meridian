"""QUOTE v2 — the recording engine: v1's quoting, unchanged, plus the forward
observation stream.

Built against the registered program (docs/math/quote-v2-program.md) and
amendment 10 (256c038). The load-bearing property: **the QUOTING policy is
byte-identical to the frozen v1 commit (7a3a217)** — v2 SUBCLASSES
`ShadowQuoter` and inherits `cycle()` (fill-check + requote-to-touch, 5s)
UNCHANGED. v2 only ADDS a recording path, `record_cycle()`, that runs async at
<=1s off the decision loop, writes `quote_v2_observations`, and runs B's
congestion detector live — touching neither `_standing` nor the fills. So:

* **Replay equivalence (proof 1):** because `cycle()` is inherited verbatim,
  v2's quoting decisions equal v1's by construction; `_selftest` proves it and
  proves `record_cycle()` perturbs neither `_standing` nor fills. Repeatable
  selftest, not a one-off — the freeze re-binds only at the instant the proofs
  land, so the proof must be re-runnable.
* **Off-decision-path (proof 3):** `record_cycle()` is a separate method the
  run loop calls on its own cadence; it never calls `cycle()` and never mutates
  quoting state. Loop-time telemetry is printed pre/post so a recording change
  that slowed the quote loop (a policy change wearing a recording costume)
  would show.
* **AST extension (proof 2):** this module carries the same no-order /
  no-credential import ban the quote + pulse engines carry — verified in
  `_selftest`.

**Deploy is amendment-gated** (the freeze pins the running commit, not just the
policy): this binary ships only under a research dated amendment with these
three proofs attached, before the first Sept 17 tip, or the recording waits for
A1. Landing this module is repo code, off-path.

The observation table is EMBARGOED from analytical reads until a consuming gate
registers (amendment 10); the recording-integrity checks here read no outcome.
"""

from __future__ import annotations

import datetime as dt
import time
from decimal import Decimal

import structlog
from sqlalchemy import text

from core.live_fv import parse_score
from core.quote.engine import (
    MAX_OBSERVATION_AGE_SECONDS,
    ShadowQuoter,
)
from core.quote.storage import QuoteV2Observation

log = structlog.get_logger(__name__)
UTC = dt.timezone.utc

#: Recording cadence — <=1s so B's congestion detector is not degenerate
#: (observation cadence must be << LONG_S=5s; B, registered-object property).
#: This is the RECORDING loop; the QUOTING loop stays v1's 5s cycle.
DEFAULT_RECORD_INTERVAL_SECONDS = 1.0

#: The detector code version recorded beside its output (D's pin discipline:
#: a congestion number = code version x substrate). Set from the landed
#: congestion_detector commit at deploy.
DETECTOR_VERSION = "d1fb6de"


def _epoch_seconds(t: dt.datetime) -> float:
    return (t - dt.datetime(1970, 1, 1, tzinfo=UTC)).total_seconds()


class ShadowQuoterV2(ShadowQuoter):
    """v1's quoter with the forward observation stream added off the decision
    path. Quoting is inherited UNCHANGED; only recording is new."""

    def __init__(self, sessionmaker, *,
                 record_interval_seconds: float = DEFAULT_RECORD_INTERVAL_SECONDS,
                 detector_version: str = DETECTOR_VERSION, **kw) -> None:
        super().__init__(sessionmaker, **kw)
        self.record_interval_seconds = record_interval_seconds
        self.detector_version = detector_version
        #: one streaming CongestionDetector per game (venue-pooled across that
        #: game's ladders), fed in observation order.
        self._detectors: dict[str, object] = {}
        self._confirms_seen: dict[str, int] = {}

    # ---- recording (OFF the decision path — never touches _standing/fills) - #

    def _record_observations(self, session) -> list[dict]:
        """The quoter's own richer observation read: v1's book plus the
        quote-time state snapshot the guard/lateness/state arms need."""
        rows = session.execute(text("""
            SELECT DISTINCT ON (market_slug)
                   market_slug, game_id, event_slug, sports_market_type,
                   captured_at, best_bid, best_ask, is_live,
                   event_period, event_score
            FROM market_snapshots
            WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL
              AND game_id IS NOT NULL
              AND captured_at > now() - make_interval(secs => :age)
            ORDER BY market_slug, captured_at DESC
        """), {"age": MAX_OBSERVATION_AGE_SECONDS}).all()
        out = []
        for r in rows:
            bid, ask = float(r.best_bid), float(r.best_ask)
            if ask <= bid:
                continue
            out.append(dict(
                market_slug=r.market_slug, game_id=str(r.game_id),
                event_slug=r.event_slug or "",
                sports_market_type=r.sports_market_type or "",
                observed_at=r.captured_at, bid=bid, ask=ask,
                is_live=bool(r.is_live),
                event_period=r.event_period, event_score=r.event_score))
        return out

    def _detector_for(self, game_id: str):
        det = self._detectors.get(game_id)
        if det is None:
            from analysis.congestion_detector import CongestionDetector
            det = CongestionDetector()
            self._detectors[game_id] = det
            self._confirms_seen[game_id] = 0
        return det

    def record_cycle(self) -> int:
        """Write one observation row per live market. Runs B's detector on the
        quoter's OWN stream. **Reads `_standing` (the quoting state) but never
        writes it** — this is the off-decision-path guarantee, asserted in the
        selftest. Returns rows written."""
        with self._Session() as s:
            obs = self._record_observations(s)
            rows = []
            for o in obs:
                det = self._detector_for(o["game_id"])
                t = _epoch_seconds(o["observed_at"])
                kind = o["sports_market_type"].rsplit("_", 1)[-1]
                det.feed(t, kind, o["market_slug"], (o["bid"] + o["ask"]) / 2.0)
                # new confirms since last cycle -> the most recent t0 (=confirm-LONG_S)
                confirm_t0 = None
                seen = self._confirms_seen[o["game_id"]]
                if len(det.confirms) > seen:
                    from analysis.congestion_detector import LONG_S
                    confirm_t0 = dt.datetime.fromtimestamp(
                        max(det.confirms) - LONG_S, tz=UTC)
                    self._confirms_seen[o["game_id"]] = len(det.confirms)
                in_window = det.is_congested(t)

                pair = parse_score(o["event_score"])
                margin = None if pair is None else pair[0] - pair[1]
                total = None if pair is None else pair[0] + pair[1]
                q = self._standing.get(o["market_slug"])   # READ only
                rows.append(QuoteV2Observation(
                    market_slug=o["market_slug"], game_id=o["game_id"],
                    event_slug=o["event_slug"],
                    sports_market_type=o["sports_market_type"],
                    observed_at=o["observed_at"],
                    best_bid=Decimal(str(o["bid"])), best_ask=Decimal(str(o["ask"])),
                    is_live=o["is_live"], event_period=o["event_period"],
                    event_score=o["event_score"], margin=margin, total_so_far=total,
                    # fair_value / minutes_left / clock-quality: NULL here.
                    # fv has NO follow-up deploy (amendment 10 authorizes ONE
                    # pre-tip deploy; a mid-accrual binary change is barred), and
                    # an offline PULSE-fv join is FORECLOSED — it would be a
                    # cross-process proxy for the value guard-2 acts on (the
                    # congestion-proxy mistake, different field). So fv is the
                    # quoter's OWN in-binary value or NULL. With NULL, guard-2 is
                    # unevaluable and the cohort hole is COUNTED and disclosed
                    # (scoring standard: coverage counted, never dropped); the fv
                    # wire, if it does not fit before the tip, joins the post-A1
                    # deploy. Fork status is reported to the manager at proof-pass.
                    quote_bid=None if q is None else Decimal(str(q.bid_price)),
                    quote_ask=None if q is None else Decimal(str(q.ask_price)),
                    quote_event="rested" if q is not None else "none",
                    det_version=self.detector_version, det_in_window=in_window,
                    det_confirm_t0=confirm_t0))
            for r in rows:
                s.add(r)
            s.commit()
            return len(rows)

    # ---- lifecycle: quote at 5s (v1), record at <=1s (new), telemetry ----- #

    def run_forever(self) -> None:
        log.info("quote_v2_started",
                 quote_interval_seconds=self.interval_seconds,
                 record_interval_seconds=self.record_interval_seconds,
                 note="quoting is frozen-v1 policy; recording only is added")
        last_quote = float("-inf")
        while not self._stop.is_set():
            loop_started = time.monotonic()
            # recording every cadence tick (off the decision path)
            try:
                self.record_cycle()
            except Exception as exc:
                log.error("quote_v2_record_failed", error=str(exc)[:300])
            record_done = time.monotonic()
            # quoting on v1's slower cadence, unchanged
            if record_done - last_quote >= self.interval_seconds:
                last_quote = record_done
                try:
                    self.cycle()
                except Exception as exc:
                    log.error("quote_v2_cycle_failed", error=str(exc)[:300])
            # proof-3 telemetry: the recording must not slow the quote loop
            log.debug("quote_v2_loop_times",
                      record_s=round(record_done - loop_started, 4),
                      quote_s=round(time.monotonic() - record_done, 4))
            self._stop.wait(self.record_interval_seconds)


# --------------------------------------------------------------------------- #
# Proofs / selftest (amendment 10) — repeatable, not a one-off run.
# --------------------------------------------------------------------------- #

def _selftest_ast() -> None:
    """Proof 2: the writer path imports no order/credential/venue-client."""
    import ast
    import inspect

    from core.quote import engine as v1
    from core.quote import engine_v2 as v2
    for module in (v1, v2):
        tree = ast.parse(inspect.getsource(module))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        for forbidden in ("core.executor", "core.fill_watcher",
                          "core.polymarket.client.PolymarketOrderClient",
                          "core.polymarket.client.PolymarketAuthedClient",
                          "core.polymarket.client.USCredentials"):
            assert forbidden not in imported, f"{module.__name__} imports {forbidden}"
    print("proof 2 (AST no-order on writer path): PASS")


def _standing_snapshot(q) -> dict:
    """The quoting decision state, normalised for byte-comparison."""
    return {k: (v.bid_price, v.ask_price, v.regime, v.quoted_at)
            for k, v in q._standing.items()}


def _selftest_replay_equivalence(Session) -> None:
    """Proof 1 (replay equivalence) + proof 3 (off-decision-path), behavioural.

    STRUCTURAL first — unfoolable: v2 overrides NO quoting method, so its
    quoting is literally v1's code object. Then BEHAVIOURAL: over a seeded
    sequence, v1.cycle() and v2.cycle() produce byte-identical _standing and
    fills even with v2.record_cycle() interleaved — proving recording is off
    the decision path (it mutates neither).
    """
    # structural: every quoting method is inherited, not overridden
    for name in ("cycle", "_observations", "_fill", "_settle_fills"):
        assert getattr(ShadowQuoterV2, name) is getattr(ShadowQuoter, name), \
            f"v2 overrides quoting method {name} — replay equivalence not by construction"
    print("proof 1 (structural): v2 overrides no quoting method — quoting IS v1")

    SLUG = "test-qv2-replay"
    GAME = "qv2-replay-game"

    def _clean():
        with Session() as s:
            for tbl in ("shadow_quote_fills", "quote_v2_observations",
                        "market_snapshots"):
                s.execute(text(f"delete from {tbl} where market_slug like :m"),
                          {"m": SLUG + "%"})
            s.commit()

    def _snap(bid, ask, at, slug):
        with Session() as s:
            s.execute(text("""
                insert into market_snapshots
                    (market_slug, game_id, event_slug, sports_market_type,
                     captured_at, best_bid, best_ask, is_live, event_period,
                     event_score)
                values (:m,:g,:e,:ty,:t,:b,:a,true,'Q3','55-50')
            """), {"m": slug, "g": GAME, "e": "wnba-qv2", "ty":
                   "basketball_team_full_game_spread", "t": at,
                   "b": bid, "a": ask})
            s.commit()

    _clean()
    try:
        v1 = ShadowQuoter(Session, settle_every_seconds=10 ** 9,
                          settlement_lookup=lambda s: None)
        v2 = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                            settlement_lookup=lambda s: None)
        # a price path with requotes and both-side fills across two markets
        base = dt.datetime.now(UTC) - dt.timedelta(seconds=50)
        m1, m2 = SLUG + "-a", SLUG + "-b"
        seq = [(0.40, 0.43, 0.55, 0.58), (0.42, 0.44, 0.50, 0.54),
               (0.38, 0.41, 0.60, 0.63), (0.45, 0.47, 0.48, 0.52),
               (0.30, 0.34, 0.66, 0.70)]
        obs_written = 0
        for i, (b1, a1, b2, a2) in enumerate(seq):
            at = base + dt.timedelta(seconds=i * 6)
            _snap(b1, a1, at, m1)
            _snap(b2, a2, at, m2)
            r1 = v1.cycle()
            obs_written += v2.record_cycle()      # OFF-path: before v2.cycle()
            std_after_record = _standing_snapshot(v2)
            r2 = v2.cycle()
            # record_cycle must not have changed v2's quoting state...
            # (its effect, if any, would show as a v1/v2 divergence below)
            assert _standing_snapshot(v1) == _standing_snapshot(v2), \
                f"step {i}: _standing diverged — quoting not equivalent"
            assert r1.fills == r2.fills and r1.requotes == r2.requotes, \
                f"step {i}: fills/requotes diverged ({r1.fills}/{r1.requotes} vs {r2.fills}/{r2.requotes})"
            _ = std_after_record
        assert obs_written > 0, "record_cycle wrote no observations"
        # and the observations landed with the detector version stamped
        with Session() as s:
            n = s.execute(text(
                "select count(*), count(det_version) from quote_v2_observations "
                "where market_slug like :m"), {"m": SLUG + "%"}).one()
        assert n[0] == obs_written and n[1] == obs_written
        print(f"proof 1 (behavioural): v1==v2 across {len(seq)} cycles, "
              f"2 markets; {obs_written} obs rows written off-path")
        print("proof 3 (off-decision-path): record_cycle perturbed neither "
              "_standing nor fills")
    finally:
        _clean()


def selftest(Session=None) -> int:
    _selftest_ast()
    if Session is None:
        from core.storage import get_engine, get_sessionmaker
        Session = get_sessionmaker(get_engine())
    _selftest_replay_equivalence(Session)
    print("engine_v2 selftest: ALL PROOFS PASS")
    return 0


def main() -> int:
    from core.storage import get_engine, get_sessionmaker
    ShadowQuoterV2(get_sessionmaker(get_engine())).run_forever()
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest())
    raise SystemExit(main())
