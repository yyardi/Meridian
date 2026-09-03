"""Quoting policies for the GRIDIRON parallel A/B.

Registration: docs/gridiron/policy-variants.md — the five-arm design was
SUPERSEDED by the amendment "TWO ENGINES, THREE CUTS" (9d371e8, correction
385eae5). The structural ruling: **engines for PRICES, cuts for SELECTIONS.**
Per-fill capture is a market fact at the fill instant; it does not depend on the
engine's inventory or history. So a policy that only changes WHICH observed fills
you keep (WIDTH, LATE-SUPPRESS, PATIENCE) is recoverable as a *cut on BASE's own
fills* — no engine, no slot, read on all of BASE's fills. A policy that changes
the PRICES QUOTED (FLATTEN) is NOT recoverable from a tape and needs an engine.

This module is therefore the two ENGINE policies only — BASE and FLATTEN. The
three cuts live in the scorer (analysis on BASE's fills), not here.

It is the PURE decision logic: no engine state, no DB, no clock, no coupling to
the frozen quoting code. The engine calls `decide(...)` at the requote point and
acts on the returned Decision; it supplies the per-market inputs (touch bid/ask,
the tick, and the net position it derives from its OWN fills UNDER THE PHANTOM
TEST — see the FLATTEN note; this module never sees a phantom, it only consumes
the already-tested count).

BASE returns Decision(QUOTE) with no price override, so an engine running BASE
takes exactly v1's path — the freeze (rule 16: "BASE must reproduce v1") is
preserved by BASE being a no-op, NOT by trusting this module. FLATTEN quotes
DIFFERENTLY (it leans the resting price by inventory); it is the only arm that
leaves the losing family rather than partitioning it.

The registered constant (k=1c) is pinned here with its basis; the registration
forbids tuning it after a read, so it is a policy default, not an env knob.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The only action either engine takes: rest a quote this cycle (at the touch
#: unless the Decision overrides bid/ask — FLATTEN does). The gating actions
#: (HOLD/WITHDRAW) of the superseded five-arm design are gone: their arms became
#: cuts, and neither surviving engine ever quotes less than BASE.
QUOTE = "quote"
ACTIONS = frozenset({QUOTE})

#: Registered FLATTEN constant (docs/gridiron/policy-variants.md, correction
#: 385eae5). k=1c re-derived by BOOK INSERTION and RETAINED: under insertion all
#: of {1c,2c,3c} beat k=0 and the curve is a clean monotone decay from a peak at
#: 1c, crossing zero between 3c and 5c (+$30.43 over k=0). Pinned, not env-tunable
#: — the registration forbids tuning after a read.
FLATTEN_K = 0.01
#: The venue price increment. min(k, s-tick) is the effective lean: it keeps the
#: leaned side at least one tick off the other side (post-only — never crosses
#: the book), so nominal k and effective k differ in tight books.
DEFAULT_TICK = 0.01


@dataclass(frozen=True)
class Decision:
    """What a policy tells the engine to do with a quotable market this cycle.
    For QUOTE, bid/ask are the prices to rest at; None means "the touch" (v1's
    requote-to-touch), so BASE never overrides the price and only FLATTEN sets
    them."""
    action: str
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class Policy:
    """BASE — the frozen v1 policy: always QUOTE at the touch, the control.
    `decide` takes every input either engine needs as keywords so both policies
    are called identically."""
    name: str = "base"

    def decide(self, *, bid: float, ask: float,
               net_position: float = 0.0,
               tick: float = DEFAULT_TICK) -> Decision:
        return Decision(QUOTE)


@dataclass(frozen=True)
class Flatten(Policy):
    """FLATTEN(k) — inventory-conditional PLACEMENT (not gating): when net LONG a
    market lean the ASK toward the mid (sell the inventory down), when net SHORT
    lean the BID toward the mid (buy it back); flat -> the touch (= BASE). The
    only arm that quotes DIFFERENTLY rather than less, and the only one testing
    the program's headline finding (v1 never closes a round trip).

    Effective lean is `min(k, s - tick)` where s = ask - bid: the POST-ONLY
    clamp. It keeps the leaned side at least a tick off the other side, so it
    never crosses the book to become a taker; in a one-tick book the effective
    lean is 0. (Note: this is a post-only clamp, NOT a clamp at the mid — at
    k=1c the lean reaches the mid only in a two-tick book and never passes it,
    but the invariant we enforce is "don't cross", not "don't reach the mid".)

    THE INVENTORY INPUT IS PHANTOM-TESTED, and that is a correctness precondition,
    not a nicety. `net_position` MUST be the engine's count of its own REAL fills
    (those where the touch came to us: a bid fill with best_ask_at_fill <= B, an
    ask fill with best_bid_at_fill >= A) — never the naive mid-cross count. If
    phantoms feed the counter, FLATTEN leans to flatten positions it does not
    hold, and the error is invisible in-sample because the shadow fill model and
    the shadow inventory agree with each other (a self-consistent wrong answer).
    This module cannot enforce that — it only consumes `net_position` — so the
    engine owns the predicate. See core/quote/engine_v2.py.

    Basis (correction 385eae5): under book insertion k=1c is the best value on
    the board and CARRIES INFORMATION, but the caveat outranks the parameter —
    every cell is negative at every k; flattening improves a losing book, it does
    not make a winning one. k=1c stands as an empirical regularity (it improves
    per-fill P&L in all three spread bands), not as a mechanism; two proposed
    mechanisms were refuted by their own predictions."""
    name: str = "flatten"
    k: float = FLATTEN_K

    def decide(self, *, bid: float, ask: float,
               net_position: float = 0.0,
               tick: float = DEFAULT_TICK) -> Decision:
        lean = min(self.k, max(0.0, round(ask - bid, 10) - tick))
        if net_position > 0:            # long -> lean the ASK toward mid
            ask = round(ask - lean, 4)
        elif net_position < 0:          # short -> lean the BID toward mid
            bid = round(bid + lean, 4)
        return Decision(QUOTE, bid=bid, ask=ask)


#: name -> policy factory. Two engines only (amendment). Extend here AND the
#: registration to add an engine — but the ruling is that most policies are cuts.
_REGISTRY = {
    "base": Policy,
    "flatten": Flatten,
}


def resolve_policy(name: str | None) -> Policy:
    """The policy for a MERIDIAN_QUOTE_POLICY value. Fail-closed on an unknown
    name (as league resolution does) — a variant that silently fell back to BASE
    would corrupt the cohort by mislabelling its fills. None/empty -> BASE."""
    key = (name or "base").strip().lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise ValueError(
            f"unknown quote policy {name!r}; registered: {sorted(_REGISTRY)} "
            f"(docs/gridiron/policy-variants.md). The engine refuses to start "
            f"rather than mislabel a cohort as BASE.")
    return factory()


def _selftest() -> int:
    ok = True

    def chk(label, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  {label:58} {'OK' if cond else 'FAIL'}")

    touch = dict(bid=0.48, ask=0.52)  # spread 4c, tick 1c

    b = resolve_policy("base")
    chk("BASE always QUOTE at the touch (control is a no-op)",
        b.decide(**touch, net_position=5) == Decision(QUOTE, None, None))
    chk("BASE ignores inventory entirely (stateless w.r.t. fills)",
        b.decide(**touch, net_position=-99) == Decision(QUOTE, None, None))

    f = resolve_policy("flatten")
    chk("FLATTEN pinned k=1c", f.k == 0.01)
    chk("FLATTEN flat -> touch (= BASE)",
        f.decide(**touch, net_position=0) == Decision(QUOTE, 0.48, 0.52))
    long_d = f.decide(**touch, net_position=3)
    chk("FLATTEN long -> ask leaned 1c toward mid, bid untouched",
        long_d.action == QUOTE and long_d.ask == 0.51 and long_d.bid == 0.48)
    short_d = f.decide(**touch, net_position=-3)
    chk("FLATTEN short -> bid leaned 1c toward mid, ask untouched",
        short_d.bid == 0.49 and short_d.ask == 0.52)

    # post-only clamp: min(k, s-tick). A one-tick book cannot lean at all.
    onetick = f.decide(bid=0.50, ask=0.51, net_position=3)
    chk("FLATTEN one-tick book -> effective lean 0 (post-only, no cross)",
        onetick.ask == 0.51 and onetick.bid == 0.50)
    # a two-tick book: lean reaches the mid exactly, never past it.
    twotick = f.decide(bid=0.49, ask=0.51, net_position=3)
    chk("FLATTEN two-tick book long -> ask lands on mid (0.50), not past",
        twotick.ask == 0.50)
    twotick_s = f.decide(bid=0.49, ask=0.51, net_position=-3)
    chk("FLATTEN two-tick book short -> bid lands on mid (0.50), not past",
        twotick_s.bid == 0.50)
    # invariant: leaned quote never crosses the book (ask' >= bid' + tick).
    crossing_ok = True
    for bp, ap in [(0.48, 0.52), (0.49, 0.51), (0.50, 0.51), (0.40, 0.60), (0.495, 0.505)]:
        for q in (3, -3):
            d = f.decide(bid=bp, ask=ap, net_position=q)
            if round(d.ask - d.bid, 10) < 0.01 - 1e-9:
                crossing_ok = False
    chk("FLATTEN never crosses the book (post-only holds across books)", crossing_ok)

    raised = False
    try:
        resolve_policy("width_floor")   # a dropped arm is now unknown -> fail
    except ValueError:
        raised = True
    chk("a DROPPED arm (width_floor) now FAILS CLOSED, not silent BASE", raised)
    chk("only two engines registered (amendment)", sorted(_REGISTRY) == ["base", "flatten"])
    chk("every registered engine returns a valid action",
        all(p().decide(**touch).action in ACTIONS for p in _REGISTRY.values()))

    print("\nPOLICY SELFTEST:", "PASS — two engines: BASE is a no-op (freeze "
          "preserved), FLATTEN leans min(k,s-tick) post-only, k pinned, dropped "
          "arms fail closed." if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
