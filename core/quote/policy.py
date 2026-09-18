"""Quoting policies for the GRIDIRON parallel A/B (registration:
docs/gridiron/policy-variants.md, c7 2026-09-03; landed 8fc58e3 + FLATTEN 550c68f).

Five engines run the SAME image on the SAME live board in the SAME second, each
with one pre-declared lever off the frozen v1 base, so variants are compared
within-second on identical markets. This module is the PURE decision logic — no
engine state, no DB, no clock, no coupling to the frozen quoting code. The engine
calls `decide(...)` at the requote point of its cycle and acts on the returned
Decision; it supplies the per-market inputs (touch bid/ask/mid, spread, the
final-period flag, seconds since the last fill, the width threshold it rolled,
and the net position it derives from its own fills).

BASE returns Decision(QUOTE) with no price override, so an engine running BASE
takes exactly v1's path — the freeze (and rule 16: "BASE must reproduce v1
byte-identically") is preserved by BASE being a no-op, NOT by trusting this
module. Four arms QUOTE LESS (HOLD/WITHDRAW); FLATTEN quotes DIFFERENTLY (it
leans the resting price by inventory). The instrument (mid-cross fill rule) pays
a bonus per quote and every quote-less lever quotes less than BASE, so the
PRIMARY metric is per-fill capture, not total P&L, and each arm reads
independently against BASE (registration).

Every registered constant (N=30s, 60th pct / 30-min window, k=1c) is pinned here
with its basis; the registration forbids tuning them after a read, so they are
policy defaults, not env knobs.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Actions at the requote point. QUOTE = rest a quote this cycle (at the touch
#: unless the Decision overrides bid/ask — FLATTEN does); HOLD = leave the
#: standing quote where it is (do not chase the touch); WITHDRAW = stand down.
QUOTE, HOLD, WITHDRAW = "quote", "hold", "withdraw"
ACTIONS = frozenset({QUOTE, HOLD, WITHDRAW})

#: Registered lever constants (docs/gridiron/policy-variants.md). Pinned, not
#: env-tunable: the registration forbids tuning them after a read (a tuned
#: constant destroys the information it carries — 3c/5c FLATTEN measured negative).
PATIENCE_N_SECONDS = 30.0
WIDTH_FLOOR_PERCENTILE = 60.0
WIDTH_FLOOR_WINDOW_MINUTES = 30.0
FLATTEN_K = 0.01


@dataclass(frozen=True)
class Decision:
    """What a policy tells the engine to do with a quotable market this cycle.
    For QUOTE, bid/ask are the prices to rest at; None means "the touch" (v1's
    requote-to-touch), so BASE and the gating arms never override the price and
    only FLATTEN sets them."""
    action: str
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class Policy:
    """BASE — the frozen v1 policy: always QUOTE at the touch, the control.
    `decide` takes every input any lever needs as keywords so the engine calls
    all policies identically."""
    name: str = "base"

    def decide(self, *, bid: float, ask: float, mid: float,
               spread: float | None = None, is_final_period: bool = False,
               seconds_since_fill: float | None = None,
               width_floor_threshold: float | None = None,
               net_position: float = 0.0) -> Decision:
        return Decision(QUOTE)


@dataclass(frozen=True)
class Patience(Policy):
    """PATIENCE(N) — after a fill, do NOT requote to the touch for N seconds; HOLD
    the resting quote (it can still fill; it just does not chase the dip). Basis:
    v1 requoted into the dip 82.2% of the time at 0.0s median gap; dips revert
    +0.76->+0.90c."""
    name: str = "patience"
    n_seconds: float = PATIENCE_N_SECONDS

    def decide(self, *, seconds_since_fill: float | None = None, **_) -> Decision:
        if seconds_since_fill is not None and seconds_since_fill < self.n_seconds:
            return Decision(HOLD)
        return Decision(QUOTE)


@dataclass(frozen=True)
class LateSuppress(Policy):
    """LATE-SUPPRESS — no quoting in the final period; WITHDRAW there. Basis: Q4
    collected the fattest half-spreads (2.2-2.3c) and the worst nets (-2.6 to
    -3.3c). A negative result is informative — football's late structure may
    differ from basketball's."""
    name: str = "late_suppress"

    def decide(self, *, is_final_period: bool = False, **_) -> Decision:
        return Decision(WITHDRAW) if is_final_period else Decision(QUOTE)


@dataclass(frozen=True)
class WidthFloor(Policy):
    """WIDTH-FLOOR — quote only when the current spread is at/above the Pth
    percentile of THIS market's own spread over the trailing window; WITHDRAW
    below. Self-calibrating (no imported constant a 5-6c NFL cell makes quote
    nothing); the engine rolls the per-market percentile and passes it as
    `width_floor_threshold`. Percentile + window pinned by registration."""
    name: str = "width_floor"
    percentile: float = WIDTH_FLOOR_PERCENTILE
    window_minutes: float = WIDTH_FLOOR_WINDOW_MINUTES

    def decide(self, *, spread: float | None = None,
               width_floor_threshold: float | None = None, **_) -> Decision:
        # Warm-up: too little history for a threshold -> behave as BASE, so the
        # arm is never silently dark while its window fills (the engine counts
        # warm-up cycles so a read can exclude them).
        if width_floor_threshold is None or spread is None:
            return Decision(QUOTE)
        return Decision(QUOTE) if spread >= width_floor_threshold else Decision(WITHDRAW)


@dataclass(frozen=True)
class Flatten(Policy):
    """FLATTEN(k) — inventory-conditional PLACEMENT (not gating): when net LONG a
    market lean the ASK k toward the mid (sell the inventory down), when net SHORT
    lean the BID k toward the mid (buy it back); flat -> the touch (= BASE). The
    only arm that quotes DIFFERENTLY rather than less, and the only one testing
    the program's headline finding (v1 never closes a round trip). Basis: round
    trips available 27-42% within 30s, +1.44c on the flattened subset, +$76
    whole-book at k=1c, negative by 5c — so k=1c carries information and is pinned.
    Leaning is clamped at the mid: it tightens the exit side, never crosses."""
    name: str = "flatten"
    k: float = FLATTEN_K

    def decide(self, *, bid: float, ask: float, mid: float,
               net_position: float = 0.0, **_) -> Decision:
        if net_position > 0:            # long -> lean the ASK toward mid
            ask = round(max(mid, ask - self.k), 4)
        elif net_position < 0:          # short -> lean the BID toward mid
            bid = round(min(mid, bid + self.k), 4)
        return Decision(QUOTE, bid=bid, ask=ask)


#: name -> policy factory. Extend here AND the registration to add a lever.
_REGISTRY = {
    "base": Policy,
    "patience": Patience,
    "late_suppress": LateSuppress,
    "width_floor": WidthFloor,
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

    touch = dict(bid=0.48, ask=0.52, mid=0.50)

    b = resolve_policy("base")
    d = b.decide(**touch, is_final_period=True, seconds_since_fill=0.0,
                 width_floor_threshold=0.99, net_position=5)
    chk("BASE always QUOTE at the touch (control is a no-op)",
        d == Decision(QUOTE, None, None))

    p = resolve_policy("patience")
    chk("PATIENCE default N=30 (registered)", p.n_seconds == 30.0)
    chk("PATIENCE HOLDs within N", p.decide(**touch, seconds_since_fill=5.0).action == HOLD)
    chk("PATIENCE QUOTEs at exactly N", p.decide(**touch, seconds_since_fill=30.0).action == QUOTE)
    chk("PATIENCE QUOTEs with no recent fill", p.decide(**touch, seconds_since_fill=None).action == QUOTE)

    la = resolve_policy("late_suppress")
    chk("LATE WITHDRAWs in final period", la.decide(**touch, is_final_period=True).action == WITHDRAW)
    chk("LATE QUOTEs otherwise", la.decide(**touch, is_final_period=False).action == QUOTE)

    w = resolve_policy("width_floor")
    chk("WIDTH pinned 60pct/30min", w.percentile == 60.0 and w.window_minutes == 30.0)
    chk("WIDTH QUOTEs at/above threshold",
        w.decide(**touch, spread=0.06, width_floor_threshold=0.05).action == QUOTE)
    chk("WIDTH WITHDRAWs below threshold",
        w.decide(**touch, spread=0.04, width_floor_threshold=0.05).action == WITHDRAW)
    chk("WIDTH QUOTEs during warm-up",
        w.decide(**touch, spread=0.04, width_floor_threshold=None).action == QUOTE)

    f = resolve_policy("flatten")
    chk("FLATTEN pinned k=1c", f.k == 0.01)
    chk("FLATTEN flat -> touch (= BASE)",
        f.decide(**touch, net_position=0).__eq__(Decision(QUOTE, 0.48, 0.52)))
    long_d = f.decide(**touch, net_position=3)
    chk("FLATTEN long -> ask leaned 1c toward mid, bid untouched",
        long_d.action == QUOTE and long_d.ask == 0.51 and long_d.bid == 0.48)
    short_d = f.decide(**touch, net_position=-3)
    chk("FLATTEN short -> bid leaned 1c toward mid, ask untouched",
        short_d.bid == 0.49 and short_d.ask == 0.52)
    tight = f.decide(bid=0.495, ask=0.505, mid=0.50, net_position=3)
    chk("FLATTEN clamps at mid (never crosses)", tight.ask == 0.50)

    raised = False
    try:
        resolve_policy("moonshot")
    except ValueError:
        raised = True
    chk("unknown policy FAILS CLOSED (not silent BASE)", raised)
    chk("every registered arm returns a valid action",
        all(p().decide(**touch).action in ACTIONS for p in _REGISTRY.values()))

    print("\nPOLICY SELFTEST:", "PASS — BASE is a no-op (freeze preserved), each "
          "lever returns its registered Decision, constants pinned, unknown names "
          "fail closed." if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
