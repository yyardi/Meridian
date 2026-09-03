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
from core.leagues import league_of_slug
from core.quote.engine import (
    INGAME,
    MAX_OBSERVATION_AGE_SECONDS,
    CycleResult,
    ShadowQuoter,
    require_engine_commit,
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

#: Queue-ahead depth sampling (manager 2026-09-03: option 1, scope-a, cadence-b;
#: constants + gate design D's convention, 2026-09-03).
#:
#: The PRIMARY validity gate is PRICE IDENTITY, not elapsed time (D's measurement:
#: WNBA in-play touch survival is median 2s, p90 17s — no single time threshold
#: separates fresh from dead when survival is that skewed). Queue-ahead is a claim
#: about the queue AT price P; it is exactly valid while the market still quotes P
#: (1s or 5min) and meaningless the instant the touch moves, at any age. So each
#: row carries the touch AT the sample's fetch (`depth_best_bid`/`depth_best_ask`)
#: beside the touch at observation (`best_bid`/`best_ask`): SAME touch -> the queue
#: number is exactly valid; DIFFERENT -> unusable regardless of age. That is
#: "lying vs lagging" as an exact predicate rather than a threshold.
#:
#: REFRESH is touch-change-triggered (refetch when the touch has moved since the
#: sample) with a FLOOR so the rate stays bounded: naive touch-change on a 2s
#: median would hit ~10 req/s across 20 markets, over the ~5 req/s throttle and
#: onto a gateway already 155% cap-oversubscribed (manager count 2026-09-03). The
#: floor caps refetch at (quoted markets)/interval = 4 req/s at 20 markets / 5s.
DEPTH_REFRESH_INTERVAL_SECONDS = 5.0     # floor between touch-triggered refetches
#: Hard backstop: refetch at least this often even if the touch never moves (to
#: catch same-price SIZE drift — rare, D: 3/54 pregame side-intervals), and the
#: consumer's SECONDARY gate — the touch coincidentally returning to the same
#: price after moving away would pass price-identity wrongly, so a sample older
#: than this is unusable even on a price match. Not enforced at write time (the
#: writer records the stamp; the consumer judges — coverage counted, never hidden).
DEPTH_QUEUE_STALENESS_MAX_SECONDS = 60.0
#: CAVEAT (D): the survival numbers above are WNBA in-play. NFL in-play touch
#: survival is unmeasured until the first slate — but the price-identity gate needs
#: no constant to be right, so it is robust to that gap; only the refresh cadence's
#: efficiency (not its correctness) depends on the number holding for NFL.


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
        #: Bounded-cadence queue-ahead depth cache (manager 2026-09-03): per
        #: market -> ({(side, price4dp): qty}, fetched_at). Refreshed at most once
        #: per DEPTH_REFRESH_INTERVAL_SECONDS, for QUOTED markets only. v2-only
        #: state — NOT _standing and NOT fills, so replay equivalence (proof 1)
        #: and off-decision-path (proof 3) are untouched.
        self._book_cache: dict[str, tuple[dict, dt.datetime]] = {}

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
        # The QUOTER'S OWN receive stamp for this batch — one instant, taken
        # when the read returns. NOT market_snapshots.captured_at: that is the
        # recorder's cross-process clock, which the schema forbids
        # (docs/math/quote-v2-observation-schema.md: observed_at is "the
        # QUOTER'S OWN stamp — never recorder stamps"; B's congestion-detector
        # registration forbids a cross-process recorder-timestamp join). det_*
        # stamped in the recorder clock would later join to fills in the quoter
        # clock — the exact skew the design exists to prevent. One stamp per
        # cycle gives a uniform <=1s cadence, and within a cycle the detector's
        # (t, ladder, rung) tie discipline reduces to market_slug order.
        read_at = dt.datetime.now(UTC)
        out = []
        for r in rows:
            lg = league_of_slug(r.market_slug)
            if lg is None or lg.slug != self._league:
                continue              # league filter (amendment 12), RECORD path
            bid, ask = float(r.best_bid), float(r.best_ask)
            if ask <= bid:
                continue
            out.append(dict(
                market_slug=r.market_slug, game_id=str(r.game_id),
                event_slug=r.event_slug or "",
                sports_market_type=r.sports_market_type or "",
                observed_at=read_at, source_captured_at=r.captured_at,
                bid=bid, ask=ask,
                is_live=bool(r.is_live),
                event_period=r.event_period, event_score=r.event_score))
        # Canonical input order (observed_at, market_slug) — the c78432d tie
        # discipline the congestion detector registers as its input contract.
        # record_cycle feeds the per-game detector in this order, so the
        # offline recording-integrity replay reconciles exactly. With the
        # per-cycle read stamp above this reduces to market_slug within a cycle;
        # kept explicit so it stays correct if observed_at ever becomes
        # per-observation, and so an equal-instant divergence is a real
        # out-of-contract signal (the scorer's should-never-fire assertion).
        out.sort(key=lambda o: (o["observed_at"], o["market_slug"]))
        return out

    def _detector_for(self, game_id: str):
        det = self._detectors.get(game_id)
        if det is None:
            from analysis.congestion_detector import CongestionDetector
            det = CongestionDetector()
            self._detectors[game_id] = det
            self._confirms_seen[game_id] = 0
        return det

    def _fetch_book_levels(self, market_slug: str):
        """One venue book read -> ({(side, price@4dp): total_qty}, (best_bid,
        best_ask)). The touch (best_bid = highest bid px, best_ask = lowest offer
        px) rides along so the row can carry the touch AT fetch for the price-
        identity gate. READ-ONLY gateway client (no order/auth/credential import —
        proof 2; the client v1 uses for settlement). Fail-open: any error ->
        None, never a crash or a stall of the record loop."""
        from collections import defaultdict

        from core.polymarket.client import PolymarketGatewayClient
        try:
            with PolymarketGatewayClient() as gw:
                book, _raw = gw.get_book(market_slug)
        except Exception as exc:            # a read failure must never break recording
            log.warning("qv2_book_fetch_failed", market=market_slug,
                        error=str(exc)[:150])
            return None
        md = getattr(book, "market_data", None)
        if md is None:
            return None
        out: dict = defaultdict(float)
        bids, offers = [], []
        for side, entries, prices in (("bid", md.bids, bids),
                                      ("offer", md.offers, offers)):
            for be in entries:
                if be.px is None or be.px.value is None or be.qty is None:
                    continue
                px = round(float(be.px.value), 4)
                out[(side, px)] += float(be.qty)
                prices.append(px)
        touch = (max(bids) if bids else None, min(offers) if offers else None)
        return dict(out), touch

    def _queue_ahead(self, market_slug: str, bid_price, ask_price,
                     obs_bid: float, obs_ask: float, now: dt.datetime):
        """Queue-ahead qty at OUR quote price each side (manager 2026-09-03,
        option 1) + the touch AT fetch for the price-identity gate (D's
        convention 2026-09-03).

        REFRESH is touch-change-triggered with a floor: refetch when no cache, OR
        the observation's touch has moved off the cached sample's touch AND at
        least DEPTH_REFRESH_INTERVAL_SECONDS have passed (the floor that bounds
        the rate — naive touch-change on a 2s in-play median would be ~10 req/s),
        OR the sample is older than DEPTH_QUEUE_STALENESS_MAX_SECONDS (backstop
        for same-price size drift). Between refetches the cached sample is reused
        and every row carries its fetch instant + touch, so the consumer applies
        the exact price-identity gate itself. Read-only, off the decision path,
        fail-open. Returns (our_bid_qty, our_ask_qty, depth_fetched_at,
        depth_best_bid, depth_best_ask) — any may be None."""
        cached = self._book_cache.get(market_slug)
        obs_touch = (round(float(obs_bid), 4), round(float(obs_ask), 4))
        refetch = cached is None
        if not refetch:
            _levels, ctouch, cfetched = cached
            elapsed = (now - cfetched).total_seconds()
            touch_moved = ctouch != obs_touch
            refetch = ((touch_moved and elapsed >= DEPTH_REFRESH_INTERVAL_SECONDS)
                       or elapsed >= DEPTH_QUEUE_STALENESS_MAX_SECONDS)
        if refetch:
            fetched = self._fetch_book_levels(market_slug)
            if fetched is None:
                return None, None, None, None, None
            levels, touch = fetched
            self._book_cache[market_slug] = (levels, touch, now)
        levels, touch, fetched_at = self._book_cache[market_slug]

        def at(side, price):
            if price is None:
                return None
            return levels.get((side, round(float(price), 4)), 0.0)

        return (at("bid", bid_price), at("offer", ask_price), fetched_at,
                touch[0], touch[1])

    def record_cycle(self) -> int:
        """Write one observation row per live market. Runs B's detector on the
        quoter's OWN stream. **Reads `_standing` (the quoting state) but never
        writes it** — this is the off-decision-path guarantee, asserted in the
        selftest. For markets we are QUOTING it also records the queue-ahead
        depth at our own price (bounded-cadence book sample, read-only, fail-open
        — still off the decision path). Returns rows written."""
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
                # Queue-ahead at OUR price — quoted markets only (no standing
                # quote -> no queue to be behind -> NULL). Bounded-cadence book
                # sample; off the decision path; fail-open to NULL.
                if q is None:
                    bidq = askq = depth_at = depth_bb = depth_ba = None
                else:
                    bidq, askq, depth_at, depth_bb, depth_ba = self._queue_ahead(
                        o["market_slug"], q.bid_price, q.ask_price,
                        o["bid"], o["ask"], o["observed_at"])
                rows.append(QuoteV2Observation(
                    market_slug=o["market_slug"], game_id=o["game_id"],
                    event_slug=o["event_slug"],
                    sports_market_type=o["sports_market_type"],
                    observed_at=o["observed_at"],
                    source_captured_at=o["source_captured_at"],
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
                    our_bid_qty=None if bidq is None else Decimal(str(bidq)),
                    our_ask_qty=None if askq is None else Decimal(str(askq)),
                    depth_fetched_at=depth_at,
                    depth_best_bid=None if depth_bb is None else Decimal(str(depth_bb)),
                    depth_best_ask=None if depth_ba is None else Decimal(str(depth_ba)),
                    det_version=self.detector_version, det_in_window=in_window,
                    det_confirm_t0=confirm_t0,
                    engine_commit=self._engine_commit))
            for r in rows:
                s.add(r)
            s.commit()
            return len(rows)

    # ---- lifecycle: quote at 5s (v1), record at <=1s (new), telemetry ----- #

    def _quote_and_beat(self) -> None:
        """Run one v1 quote cycle AND beat the heartbeat with v1's exact
        payload. v2's `run_forever` overrode v1's loop, and v1's loop beats
        every cycle (engine.py); the first override dropped the beat, so the
        engine ran fine but read DEAD to /api/quote, the header dot, and
        health.py — a healthy engine on a silent telemetry channel. The
        replay-equivalence proof could not catch it: it compares `_standing`
        and fills, and the beat is neither (a rule-19 blind spot of that proof,
        now declared in its docstring and covered by `_selftest_heartbeat_beat`
        instead). Beats even when `cycle()` raises, exactly as v1 does, so a bad
        cycle degrades the payload (game_live=None) but never kills the channel.
        """
        started = time.monotonic()
        try:
            result = self.cycle()
            any_live = any(q.regime == INGAME
                           for q in self._standing.values())
        except Exception as exc:   # one bad cycle must not silence telemetry
            log.error("quote_v2_cycle_failed", error=str(exc)[:300])
            result, any_live = CycleResult(), None
        self._heartbeat.beat(
            interval_seconds=self.interval_seconds,
            rows_written=result.fills,
            cycle_seconds=time.monotonic() - started,
            game_live=any_live,
        )

    def run_forever(self) -> None:
        # FAIL-CLOSED (amendment 12): no unstamped observation/fill row ever.
        self._engine_commit = require_engine_commit()
        log.info("quote_v2_started",
                 quote_interval_seconds=self.interval_seconds,
                 record_interval_seconds=self.record_interval_seconds,
                 league=self._league, engine_commit=self._engine_commit,
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
            # quoting on v1's slower cadence, unchanged — and beating the
            # heartbeat every quote cycle exactly as v1 does (payload is
            # quote-cycle-shaped, so it rides the 5s quote tick, not the <=1s
            # record tick; max heartbeat age ~= interval_seconds, matching v1).
            if record_done - last_quote >= self.interval_seconds:
                last_quote = record_done
                self._quote_and_beat()
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

    # WNBA-routable slug so the league filter (amendment 12) admits it — the
    # replay equivalence runs on the frozen binary's own league.
    SLUG = "tsc-wnba-test-qv2-replay"
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


def _selftest_heartbeat_beat(Session) -> None:
    """Amendment-11 checklist item: v2's loop MUST beat every quote cycle.

    The replay-equivalence proof is BLIND to this — it compares `_standing` and
    fills, and the beat is neither (a declared rule-19 gap of that proof). So
    the beat is asserted directly here: a stubbed heartbeat, one quote-and-beat
    on an empty board, then a raising cycle. Both must beat — the second because
    one bad cycle must not silence the telemetry channel (the exact failure the
    first override shipped: healthy engine, heartbeat age growing unbounded,
    reads DEAD to /api/quote and health.py).
    """
    from unittest import mock

    beats: list[dict] = []

    class _StubHeartbeat:
        def beat(self, **kw):
            beats.append(kw)

    q = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                       settlement_lookup=lambda s: None)
    q._heartbeat = _StubHeartbeat()

    q._quote_and_beat()   # normal quote cycle (empty board)
    assert len(beats) == 1, "no heartbeat beat on a normal quote cycle"
    assert set(beats[0]) == {"interval_seconds", "rows_written",
                             "cycle_seconds", "game_live"}, \
        f"beat payload shape != v1: {sorted(beats[0])}"
    assert beats[0]["interval_seconds"] == q.interval_seconds

    with mock.patch.object(q, "cycle", side_effect=RuntimeError("boom")):
        q._quote_and_beat()
    assert len(beats) == 2, "a failed cycle did not beat — telemetry would die"
    assert beats[1]["game_live"] is None, \
        "failed-cycle beat must carry game_live=None (v1 semantics)"

    print("proof (heartbeat, rule-19 gap of equivalence): v2 beats every quote "
          "cycle with v1's payload, and beats even when cycle() raises")


def _selftest_league_filter_and_identity(Session) -> None:
    """Amendment-12 compensators. (1) fail-closed: the engine refuses to start
    without MERIDIAN_ENGINE_COMMIT. (2) the league-filter PLANT PAIR: the replay pin has no
    NFL rows, so replay proves the filter byte-identical by construction but
    CANNOT exercise its reject branch — a declared blind spot. So a plant pair
    asserts the filter ADMITS a wnba slug and REJECTS an nfl slug, on the read
    path (`_observations`) AND the write path (`_fill`). A no-op proven only
    where the operand is absent proves nothing about the operand."""
    import os

    from core.quote.engine import (
        BID, Observation, StandingQuote, require_engine_commit,
    )

    # (1) fail-closed on missing MERIDIAN_ENGINE_COMMIT
    saved = os.environ.pop("MERIDIAN_ENGINE_COMMIT", None)
    try:
        raised = False
        try:
            require_engine_commit()
        except RuntimeError:
            raised = True
        assert raised, "engine did not fail-closed on missing MERIDIAN_ENGINE_COMMIT"
        os.environ["MERIDIAN_ENGINE_COMMIT"] = "deadbeefcafe"
        assert require_engine_commit() == "deadbeefcafe"
    finally:
        if saved is None:
            os.environ.pop("MERIDIAN_ENGINE_COMMIT", None)
        else:
            os.environ["MERIDIAN_ENGINE_COMMIT"] = saved
    print("proof (fail-closed): engine refuses to start without MERIDIAN_ENGINE_COMMIT")

    q = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                       settlement_lookup=lambda s: None)   # league defaults wnba
    assert q._league == "wnba"
    SLUG_W, SLUG_N, GAME = "tsc-wnba-flt-a", "aec-nfl-flt-b", "flt-game"

    def _clean():
        with Session() as s:
            s.execute(text("delete from market_snapshots where market_slug in "
                           "(:w,:n)"), {"w": SLUG_W, "n": SLUG_N})
            s.commit()

    # (2a) READ path: a wnba slug admitted, an nfl slug rejected
    _clean()
    try:
        base = dt.datetime.now(UTC) - dt.timedelta(seconds=20)
        with Session() as s:
            for slug in (SLUG_W, SLUG_N):
                s.execute(text("""
                    insert into market_snapshots
                        (market_slug, game_id, event_slug, sports_market_type,
                         captured_at, best_bid, best_ask, is_live, event_period,
                         event_score)
                    values (:m,:g,'e','basketball_team_full_game_spread',:t,
                            0.40,0.44,true,'Q3','55-50')
                """), {"m": slug, "g": GAME, "t": base})
            s.commit()
        with Session() as s:
            slugs = {o.market_slug for o in q._observations(s)}
        assert SLUG_W in slugs, "READ filter dropped a wnba slug (admit failed)"
        assert SLUG_N not in slugs, "READ filter admitted an nfl slug (reject failed)"
        print("proof (league filter, READ): admits wnba, rejects nfl")
    finally:
        _clean()

    # (2b) WRITE path: _fill admits a wnba standing, refuses an nfl standing
    def _standing(slug):
        return StandingQuote(market_slug=slug, game_id=GAME, regime="ingame",
                             bid_price=0.40, ask_price=0.44, mid=0.42,
                             spread=0.04, quoted_at=dt.datetime.now(UTC))

    def _ob(slug):
        return Observation(market_slug=slug, game_id=GAME,
                           captured_at=dt.datetime.now(UTC), bid=0.40, ask=0.44,
                           is_live=True)

    q._fill(_standing(SLUG_W), _ob(SLUG_W), BID)   # must not raise
    refused = False
    try:
        q._fill(_standing(SLUG_N), _ob(SLUG_N), BID)
    except RuntimeError:
        refused = True
    assert refused, "WRITE filter did not refuse an nfl fill"
    print("proof (league filter, WRITE): fills wnba, refuses nfl")

    # (3) engine-identity: with MERIDIAN_ENGINE_COMMIT set, a written row carries the stamp
    saved2 = os.environ.get("MERIDIAN_ENGINE_COMMIT")
    os.environ["MERIDIAN_ENGINE_COMMIT"] = "stamptest99cafe"
    try:
        qs = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                            settlement_lookup=lambda s: None)
        assert qs._engine_commit == "stamptest99cafe"
        row = qs._fill(_standing(SLUG_W), _ob(SLUG_W), BID)
        assert row.engine_commit == "stamptest99cafe", "fill row not stamped"
    finally:
        if saved2 is None:
            os.environ.pop("MERIDIAN_ENGINE_COMMIT", None)
        else:
            os.environ["MERIDIAN_ENGINE_COMMIT"] = saved2
    print("proof (engine-identity stamp): a written row carries the binary commit")


def _selftest_queue_ahead(Session) -> None:
    """Queue-ahead recording (manager 2026-09-03; gate design D 2026-09-03). Part
    A (via record_cycle): a QUOTED market's row carries our_bid_qty/our_ask_qty at
    our price + depth_fetched_at + the TOUCH at fetch (depth_best_bid/ask, the
    price-identity gate); an UNQUOTED row is NULL. Part B (direct, controlled
    time): the refresh logic — touch-change-triggered with a floor that bounds the
    rate, plus the staleness backstop."""
    import os

    from core.quote.engine import StandingQuote

    saved = os.environ.get("MERIDIAN_ENGINE_COMMIT")
    os.environ["MERIDIAN_ENGINE_COMMIT"] = "qa-selftest01"
    SLUG_Q, SLUG_U, GAME = "tsc-wnba-qa-quoted", "tsc-wnba-qa-unquoted", "qa-game"

    def _clean():
        with Session() as s:
            s.execute(text("delete from market_snapshots where market_slug in (:q,:u)"),
                      {"q": SLUG_Q, "u": SLUG_U})
            s.execute(text("delete from quote_v2_observations where market_slug in (:q,:u)"),
                      {"q": SLUG_Q, "u": SLUG_U})
            s.commit()

    _clean()
    try:
        q = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                           settlement_lookup=lambda s: None)
        # a KNOWN book (levels + touch), and a counter to prove the cache bounds fetches
        calls = {"n": 0}
        known = {("bid", 0.4000): 500.0, ("offer", 0.4400): 300.0}

        def fake_fetch(slug):
            calls["n"] += 1
            return known, (0.4000, 0.4400)         # (levels, touch)
        q._fetch_book_levels = fake_fetch          # monkeypatch the venue read

        # we ARE quoting SLUG_Q at bid 0.40 / ask 0.44; NOT quoting SLUG_U
        q._standing[SLUG_Q] = StandingQuote(
            market_slug=SLUG_Q, game_id=GAME, regime="ingame",
            bid_price=0.40, ask_price=0.44, mid=0.42, spread=0.04,
            quoted_at=dt.datetime.now(UTC))

        base = dt.datetime.now(UTC) - dt.timedelta(seconds=5)
        with Session() as s:
            for slug in (SLUG_Q, SLUG_U):
                s.execute(text("""
                    insert into market_snapshots
                        (market_slug, game_id, event_slug, sports_market_type,
                         captured_at, best_bid, best_ask, is_live)
                    values (:m,:g,'e','basketball_team_full_game_spread',:t,
                            0.40,0.44,true)
                """), {"m": slug, "g": GAME, "t": base})
            s.commit()

        q.record_cycle()
        q.record_cycle()          # second cycle, same window, touch unchanged

        with Session() as s:
            rows = {r.market_slug: r for r in s.execute(text(
                "select distinct on (market_slug) market_slug, our_bid_qty, "
                "our_ask_qty, depth_fetched_at, depth_best_bid, depth_best_ask "
                "from quote_v2_observations where market_slug in (:q,:u) "
                "order by market_slug, id desc"),
                {"q": SLUG_Q, "u": SLUG_U}).all()}

        rq = rows[SLUG_Q]
        assert float(rq.our_bid_qty) == 500.0, f"our_bid_qty {rq.our_bid_qty} != 500"
        assert float(rq.our_ask_qty) == 300.0, f"our_ask_qty {rq.our_ask_qty} != 300"
        assert rq.depth_fetched_at is not None, "depth_fetched_at not stamped"
        assert float(rq.depth_best_bid) == 0.40 and float(rq.depth_best_ask) == 0.44, \
            "touch at fetch not recorded (price-identity gate would be blind)"
        ru = rows[SLUG_U]
        assert ru.our_bid_qty is None and ru.our_ask_qty is None, \
            "unquoted market carried a queue-ahead (should be NULL — no queue)"
        assert calls["n"] == 1, \
            f"cache did not bound the fetch: {calls['n']} fetches in one window"
        print("proof (queue-ahead A): quoted row carries our-price depth + touch@fetch "
              "+ stamp; unquoted is NULL; unchanged touch reuses the sample")

        # Part B: refresh logic, direct with controlled time + a moving touch.
        q2 = ShadowQuoterV2(Session, settle_every_seconds=10 ** 9,
                            settlement_lookup=lambda s: None)
        c2 = {"n": 0}
        cur = {"touch": (0.4000, 0.4400)}

        def fake2(slug):
            c2["n"] += 1
            lv = {("bid", cur["touch"][0]): 500.0, ("offer", cur["touch"][1]): 300.0}
            return lv, cur["touch"]
        q2._fetch_book_levels = fake2
        M = "tsc-wnba-qa-refresh"
        t0 = dt.datetime(2026, 9, 17, 19, 0, 0, tzinfo=UTC)

        def call(dsec, obs):
            q2._queue_ahead(M, obs[0], obs[1], obs[0], obs[1],
                            t0 + dt.timedelta(seconds=dsec))

        call(0, (0.40, 0.44))                       # no cache -> fetch
        assert c2["n"] == 1, "first call did not fetch"
        call(2, (0.40, 0.44))                       # same touch, +2s -> reuse
        assert c2["n"] == 1, "reused-window fetched again"
        call(3, (0.41, 0.45))                       # touch MOVED but +3s (<5s floor) -> no refetch
        assert c2["n"] == 1, f"floor breached: refetched at 3s ({c2['n']})"
        cur["touch"] = (0.41, 0.45)
        call(6, (0.41, 0.45))                       # touch moved AND +6s (>=5s) -> refetch
        assert c2["n"] == 2, f"touch-change refresh did not fire at 6s ({c2['n']})"
        call(70, (0.41, 0.45))                      # same touch, +64s since fetch (>=60 backstop) -> refetch
        assert c2["n"] == 3, f"staleness backstop did not fire ({c2['n']})"
        print("proof (queue-ahead B): touch-change refresh fires past the floor, the "
              "floor bounds the rate, and the staleness backstop catches a quiet market")
    finally:
        _clean()
        if saved is None:
            os.environ.pop("MERIDIAN_ENGINE_COMMIT", None)
        else:
            os.environ["MERIDIAN_ENGINE_COMMIT"] = saved


def selftest(Session=None) -> int:
    _selftest_ast()
    if Session is None:
        from core.storage import get_engine, get_sessionmaker
        Session = get_sessionmaker(get_engine())
    _selftest_replay_equivalence(Session)
    _selftest_heartbeat_beat(Session)
    _selftest_league_filter_and_identity(Session)
    _selftest_queue_ahead(Session)
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
