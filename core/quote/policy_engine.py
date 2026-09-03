"""PolicyQuoterV2 — the GRIDIRON A/B engine, OUTSIDE the v1 freeze.

The amendment (docs/gridiron/policy-variants.md, 9d371e8; correction 385eae5)
runs two engines: BASE and FLATTEN(k=1c). This is the engine both deploy as; the
policy is chosen at construction (MERIDIAN_QUOTE_POLICY). It subclasses the
recording engine ShadowQuoterV2 and adds exactly two things:

  1. TOUCH-AT-FILL on every fill (best_bid/ask_at_fill), recorded from the SAME
     observation the fill was judged against and NEVER re-joined from the tape.
     BASE needs this too: the three analysis cuts and phantom classification run
     on BASE's fills.

  2. FLATTEN's inventory-conditional lean. This is the ONLY reason FLATTEN needs
     an engine rather than a cut — it changes the PRICES QUOTED, which a tape
     cannot answer after the fact.

WHY BASE STAYS == v1. BASE runs v1's cycle() unchanged (the lean is guarded off),
so its quoting DECISIONS are v1's; the only additions are recording (touch-at-
fill, the policy stamp) and an inventory counter BASE never reads. The freeze is
on the quoting policy, and BASE does not touch it. Proven BEHAVIOURALLY here
(decisions match over a seeded run) rather than structurally, because _fill and
cycle ARE overridden — to record and to lean — so the ShadowQuoterV2 "overrides
no quoting method" proof does not and should not apply to this class.

THE INVENTORY PREDICATE — the load-bearing correctness property (manager/D,
2026-09-03). FLATTEN is the program's first STATEFUL policy: inventory is a
CONTROLLER INPUT, not a scoreboard. So the P&L record and the position counter
are DIFFERENT OBJECTS with DIFFERENT truth conditions, and one _fill() call site
must not increment both:

  * The P&L record is written for EVERY mid-cross fill, phantom or real, flagged
    by its touch-at-fill. That is the study's accounting convention.
  * The position counter moves ONLY on a REAL fill — one where the touch came to
    us (a bid fill with best_ask_at_fill <= B, an ask fill with best_bid_at_fill
    >= A). A phantom is scored but does NOT move inventory.

EQUIVALENCE WITH D'S INSERTION SIMULATOR (why "scoring trades we say didn't
happen" is fine). Insertion (D): our order sits in the book, so the bid cannot
fall below B and phantoms never occur — a SMALLER fill set. Ours: phantoms still
occur and are scored (flagged), they simply do not move q. Different scored sets,
but **the set of fills where the touch came to us is identical under both**, so
the inventory path — and therefore the quote path — is identical. Strictly more
informative on scoring, exactly equivalent on control. Feeding q from the naive
mid-cross set instead (63.9% phantom on the WNBA tape) would make FLATTEN lean to
flatten a position it does not hold: a self-consistent wrong answer, invisible
in-sample because the shadow fill model and the shadow inventory agree with each
other. That is the bug this separation exists to prevent.

EXPECTATION FOR THE SLATE: q accrues at ~1/3 the rate the contaminated sim
implied (~36% of mid-cross fills are real), so FLATTEN leans LESS OFTEN than the
pre-correction sim suggested. That is correct behaviour, not underperformance —
D's insertion numbers are the right expectation.

THE k=0 KNOWN-ANSWER: at k=0 the lean is inert, so inventory (however fed) cannot
steer quotes and the fill set is v1's exactly. `_selftest_k0_and_lean` asserts
SET IDENTITY on a synthetic volatile walk (structural — catches a lean/re-quote
bug unrelated to phantoms that a numeric penny-check would sail past), and the
converse: at k=1c the fills DIVERGE, so the lever is live.
"""
from __future__ import annotations

import os
from dataclasses import replace
from decimal import Decimal

import structlog

from core import heartbeat as hb
from core.quote.engine import ASK, BID, service_quote_for
from core.quote.engine_v2 import ShadowQuoterV2
from core.quote.policy import DEFAULT_TICK, Flatten, resolve_policy

log = structlog.get_logger(__name__)


class PolicyQuoterV2(ShadowQuoterV2):
    """v2 recording engine + touch-at-fill + FLATTEN's inventory lean. BASE
    (policy='base') is v1's quoting plus recording; FLATTEN leans."""

    def __init__(self, sessionmaker, *, policy: str = "base",
                 tick: float = DEFAULT_TICK, **kw) -> None:
        super().__init__(sessionmaker, **kw)
        self._policy_name = (policy or "base").strip().lower()
        #: fail-closed on an unknown policy (mislabelling a cohort as BASE is the
        #: same class of hole as an unstamped row).
        self._policy = resolve_policy(self._policy_name)
        #: BASE is a pure no-op on quoting — do not even run the lean pass, so
        #: BASE's cycle is v1's cycle byte-for-byte on the decision path.
        self._leans = self._policy_name != "base"
        self._tick = tick
        #: per-market PHANTOM-TESTED net position (real fills only): +1 per real
        #: bid fill (long YES), -1 per real ask fill (short YES). This is the
        #: controller input; it is NOT the P&L record. See the module docstring.
        self._net_position: dict[str, int] = {}
        #: policy-specific heartbeat key so BASE and FLATTEN never overwrite each
        #: other's row (base -> quote_engine_<league>; flatten -> ..._flatten).
        self._heartbeat = hb.Heartbeat(
            self._Session, service_quote_for(self._league, self._policy_name))

    # ---- fills: record touch-at-fill, and move inventory on REAL fills only -- #

    def _fill(self, standing, ob, side):
        # (1) THE P&L RECORD — always written for a mid-cross fill (v1's row),
        #     now carrying the TOUCH of the filling observation and the arm that
        #     produced it. Recorded from `ob`, never re-joined from the tape:
        #     for FLATTEN this is a correctness precondition, not provenance.
        fill = super()._fill(standing, ob, side)
        fill.best_bid_at_fill = Decimal(str(round(ob.bid, 4)))
        fill.best_ask_at_fill = Decimal(str(round(ob.ask, 4)))
        fill.policy = self._policy_name

        # (2) THE POSITION COUNTER — a DIFFERENT object with a DIFFERENT
        #     predicate (the phantom test), so a fill can be SCORED above while
        #     failing to MOVE INVENTORY here. A bid fill is real iff the ask
        #     came to us (ob.ask <= our bid); an ask fill iff the bid came to us
        #     (ob.bid >= our ask). Phantoms — the recorded touch never reached
        #     our price — are the 63.9% of the WNBA tape that must not steer the
        #     lean. This is the set on which our engine and D's insertion sim
        #     agree exactly; our scored set (1) is the larger one.
        real = (ob.ask <= standing.bid_price if side == BID
                else ob.bid >= standing.ask_price)
        if real:
            self._net_position[standing.market_slug] = (
                self._net_position.get(standing.market_slug, 0)
                + (1 if side == BID else -1))
        return fill

    # ---- quoting: v1's cycle, then (FLATTEN only) lean by real inventory ----- #

    def cycle(self):
        """v1's cycle (fills + requote-to-touch, inherited) then, for a leaning
        policy, re-price the standing quotes by the phantom-tested inventory.
        BASE takes the `if` false and is therefore v1 exactly on the decision
        path."""
        result = super().cycle()
        if self._leans:
            self._apply_policy_lean()
        return result

    def _apply_policy_lean(self) -> None:
        """Re-price each standing quote by its phantom-tested net position.

        Runs AFTER v1's requote-to-touch, so it always leans FROM the current
        touch — no lean accumulates across cycles — and the leaned quote is what
        the NEXT cycle's fill-check judges against (equivalent to leaning at the
        requote point, but v1's cycle() stays inherited verbatim: the freeze).
        Flat markets are left at the touch (= BASE). At k=0 `decide` returns the
        touch unchanged, so this whole pass is a no-op and the fill set is v1's."""
        for slug, q in list(self._standing.items()):
            net = self._net_position.get(slug, 0)
            if net == 0:
                continue                      # flat -> the touch (= BASE)
            d = self._policy.decide(bid=q.bid_price, ask=q.ask_price,
                                    net_position=net, tick=self._tick)
            if d.bid != q.bid_price or d.ask != q.ask_price:
                # only bid_price/ask_price change; mid/spread/quoted_at/regime
                # stay the touch's (the lean moves OUR price, not the market's).
                self._standing[slug] = replace(q, bid_price=d.bid, ask_price=d.ask)


# --------------------------------------------------------------------------- #
# Proofs / selftest — repeatable, the freeze re-binds at proof-pass.
# --------------------------------------------------------------------------- #

def _selftest_ast_policy() -> None:
    """Proof 2 extended to this module and core.quote.policy: no order /
    credential / venue-client import on the policy engine path either."""
    import ast
    import inspect

    from core.quote import policy as pol
    from core.quote import policy_engine as pe
    for module in (pe, pol):
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
    print("proof 2 (AST no-order on policy engine path): PASS")


def _snap(Session, slug, game, at, bid, ask):
    from sqlalchemy import text
    with Session() as s:
        s.execute(text("""
            insert into market_snapshots
                (market_slug, game_id, event_slug, sports_market_type,
                 captured_at, best_bid, best_ask, is_live, event_period,
                 event_score)
            values (:m,:g,'e','basketball_team_full_game_spread',:t,:b,:a,
                    true,'Q3','55-50')
        """), {"m": slug, "g": game, "t": at, "b": bid, "a": ask})
        s.commit()


def _fill_decisions(Session, slug_prefix):
    """The quoting DECISION fields of every fill (NOT id/created_at/policy/
    touch-at-fill) — the surface the freeze is defined on, normalised for
    set-identity comparison."""
    from sqlalchemy import text
    with Session() as s:
        rows = s.execute(text("""
            select market_slug, side, quote_price, mid_at_quote, spread_at_quote,
                   mid_at_fill, quoted_at, filled_at
            from shadow_quote_fills where market_slug like :m
            order by market_slug, filled_at, side
        """), {"m": slug_prefix + "%"}).all()
    return [tuple(r) for r in rows]


def _clean(Session, prefix):
    from sqlalchemy import text
    with Session() as s:
        for tbl in ("shadow_quote_fills", "quote_v2_observations",
                    "market_snapshots"):
            s.execute(text(f"delete from {tbl} where market_slug like :m"),
                      {"m": prefix + "%"})
        s.commit()


def _drive(engine, Session, seq, slug, game, base):
    """Seed one obs per step (at `base + i*6s`) and run one cycle each; return
    fill decisions. `base` is passed in so two engines compared for set-identity
    seed IDENTICAL observation timestamps — otherwise quoted_at/filled_at differ
    by the wall-clock gap between runs and the decisions look (spuriously)
    divergent though every price field matches."""
    import datetime as dt
    for i, (b, a) in enumerate(seq):
        _snap(Session, slug, game, base + dt.timedelta(seconds=i * 6), b, a)
        engine.cycle()
    return _fill_decisions(Session, slug)


def _base_time(seq):
    import datetime as dt
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(seconds=len(seq) * 6 + 10))


def _selftest_base_equals_v1(Session) -> None:
    """BASE's quoting decisions == v1's over a seeded run (behavioural — _fill
    and cycle are legitimately overridden to record and lean, so the structural
    'overrides nothing' proof is v2's, not this class's)."""
    from core.quote.engine import ShadowQuoter

    P = "tsc-wnba-pol-base"
    seq = [(0.40, 0.43), (0.42, 0.44), (0.38, 0.41), (0.45, 0.47), (0.30, 0.34)]
    t0 = _base_time(seq)
    _clean(Session, P)
    try:
        v1 = ShadowQuoter(Session, settle_every_seconds=10 ** 9,
                          settlement_lookup=lambda s: None)
        d_v1 = _drive(v1, Session, seq, P + "-a", "pol-base-g", t0)
        _clean(Session, P)
        base = PolicyQuoterV2(Session, policy="base", settle_every_seconds=10 ** 9,
                              settlement_lookup=lambda s: None)
        d_base = _drive(base, Session, seq, P + "-a", "pol-base-g", t0)
        assert d_v1 == d_base, (
            f"BASE diverged from v1:\n v1 ={d_v1}\n base={d_base}")
        assert len(d_v1) > 0, "seeded run produced no fills — test proves nothing"
        print(f"proof (BASE == v1, behavioural): {len(d_v1)} fills identical "
              f"in every decision field")
    finally:
        _clean(Session, P)


def _selftest_touch_and_phantom(Session) -> None:
    """A controlled sequence with a KNOWN real bid fill, a KNOWN phantom bid
    fill, and a KNOWN real ask fill. Asserts: (1) touch-at-fill is recorded from
    the filling observation on every fill; (2) all three are SCORED; (3) the
    phantom is identifiable (best_ask_at_fill > quote_price on a bid fill);
    (4) inventory moved only on the two real fills (net back to 0), never the
    phantom. BASE is used so the standing quote is the touch (no lean) and the
    fill prices are known exactly."""
    from sqlalchemy import text

    P = "tsc-wnba-pol-phan"
    slug, game = P + "-m", "pol-phan-g"
    _clean(Session, P)
    try:
        q = PolicyQuoterV2(Session, policy="base", settle_every_seconds=10 ** 9,
                           settlement_lookup=lambda s: None)
        # 0: seed a quote at (0.40, 0.44)
        # 1: (0.38,0.40) mid .39<=.40 -> BID fill; ask .40<=.40 REAL   -> +1
        # 2: (0.36,0.39) mid .375<=.38 -> BID fill; ask .39<=.38? no PHANTOM -> +0
        # 3: (0.42,0.50) mid .46>=.39(A) -> ASK fill; bid .42>=.39 REAL -> -1
        seq = [(0.40, 0.44), (0.38, 0.40), (0.36, 0.39), (0.42, 0.50)]
        _drive(q, Session, seq, slug, game, _base_time(seq))

        with Session() as s:
            rows = s.execute(text("""
                select side, quote_price, best_bid_at_fill, best_ask_at_fill,
                       mid_at_fill
                from shadow_quote_fills where market_slug = :m
                order by filled_at, side
            """), {"m": slug}).all()
        assert len(rows) == 3, f"expected 3 scored fills, got {len(rows)}"
        # every fill carries the touch of its filling observation
        assert all(r.best_bid_at_fill is not None and r.best_ask_at_fill is not None
                   for r in rows), "a fill is missing touch-at-fill"
        # fill 1: real bid at 0.40, touch (0.38, 0.40) -> ask .40 <= .40 real
        r1 = rows[0]
        assert r1.side == BID and float(r1.best_ask_at_fill) <= float(r1.quote_price), \
            "fill 1 should be a REAL bid (ask came to us)"
        # fill 2: phantom bid at 0.38, touch (0.36, 0.39) -> ask .39 > .38
        r2 = rows[1]
        assert r2.side == BID and float(r2.best_ask_at_fill) > float(r2.quote_price), \
            "fill 2 should be a PHANTOM bid (ask never reached us)"
        # fill 3: real ask at 0.39, touch (0.42, 0.50) -> bid .42 >= .39 real
        r3 = rows[2]
        assert r3.side == ASK and float(r3.best_bid_at_fill) >= float(r3.quote_price), \
            "fill 3 should be a REAL ask (bid came to us)"
        # inventory: +1 (real bid), +0 (phantom), -1 (real ask) -> 0
        assert q._net_position.get(slug, 0) == 0, (
            f"inventory should be 0 (real bid + phantom(0) + real ask), "
            f"got {q._net_position.get(slug)} — phantom must not move q")
        print("proof (touch-at-fill + phantom-gated inventory): 3 fills scored, "
              "phantom flagged and EXCLUDED from q, two real fills net to 0")
    finally:
        _clean(Session, P)


def _selftest_k0_and_lean(Session) -> None:
    """The k=0 known-answer and its converse, on a synthetic volatile walk that
    builds real inventory: FLATTEN(k=0) selects the IDENTICAL fill set to v1 (the
    lean is inert, structural set-identity — catches a lean/requote bug a numeric
    check would miss), and FLATTEN(k=1c) selects a DIFFERENT set (the lever is
    live). If k=0 diverged, the lean path is buggy; if k=1c did not diverge, the
    lean is dead."""
    from core.quote.engine import ShadowQuoter

    P = "tsc-wnba-pol-k0"
    # a walk with early real bid fills (build long) then a region where a leaned
    # ask (touch_ask - 1c) fills while the touch ask would not.
    seq = [(0.40, 0.44), (0.38, 0.40), (0.39, 0.41), (0.40, 0.42),
           (0.41, 0.43), (0.37, 0.39), (0.43, 0.47), (0.35, 0.39)]
    t0 = _base_time(seq)
    _clean(Session, P)
    try:
        v1 = ShadowQuoter(Session, settle_every_seconds=10 ** 9,
                          settlement_lookup=lambda s: None)
        d_v1 = _drive(v1, Session, seq, P + "-a", "pol-k0-g", t0)
        _clean(Session, P)

        k0 = PolicyQuoterV2(Session, policy="flatten", settle_every_seconds=10 ** 9,
                            settlement_lookup=lambda s: None)
        k0._policy = Flatten(k=0.0)          # k=0: lean inert
        d_k0 = _drive(k0, Session, seq, P + "-a", "pol-k0-g", t0)
        _clean(Session, P)

        k1 = PolicyQuoterV2(Session, policy="flatten", settle_every_seconds=10 ** 9,
                            settlement_lookup=lambda s: None)   # k=1c (pinned)
        d_k1 = _drive(k1, Session, seq, P + "-a", "pol-k0-g", t0)

        assert d_k0 == d_v1, (
            f"k=0 FLATTEN diverged from v1 — the lean/requote path is not inert "
            f"at k=0:\n v1={d_v1}\n k0={d_k0}")
        assert d_k1 != d_v1, (
            "k=1c FLATTEN did not diverge from v1 on a walk that builds "
            "inventory — the lever is dead")
        assert len(d_v1) > 0, "walk produced no fills — test proves nothing"
        print(f"proof (k=0 known-answer): FLATTEN(k=0) == v1 to the fill "
              f"({len(d_v1)} fills, set-identical); FLATTEN(k=1c) diverges "
              f"(lever live)")
    finally:
        _clean(Session, P)


def selftest(Session=None) -> int:
    _selftest_ast_policy()
    if Session is None:
        from core.storage import get_engine, get_sessionmaker
        Session = get_sessionmaker(get_engine())
    _selftest_base_equals_v1(Session)
    _selftest_touch_and_phantom(Session)
    _selftest_k0_and_lean(Session)
    print("policy_engine selftest: ALL PROOFS PASS")
    return 0


def main() -> int:
    from core.storage import get_engine, get_sessionmaker
    policy = os.environ.get("MERIDIAN_QUOTE_POLICY", "base")
    PolicyQuoterV2(get_sessionmaker(get_engine()), policy=policy).run_forever()
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        raise SystemExit(selftest())
    raise SystemExit(main())
