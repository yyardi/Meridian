"""The dynamic-exit-repricing shadow arm — the pure state machine.

Built AGAINST `docs/math/dynamic-exit-repricing.md` (registration, rule 11).
The exact repricing rule is pinned HERE, in committed code, before the first
forward read (rule 12) — this module IS the pin.

What the arm is
---------------
The incumbent PULSE exit rests a FIXED profit-target limit the moment an
entry fills (`entry ± profit_target`, YES frame) and only ever moves it to
cut at the touch on an ev/adverse stop. The registration's hypothesis: that
fixed target is STALE — as fair value moves during the game, the price at
which we should be willing to close moves with it, and a target frozen at
entry leaves money on the table (or fails to fill) when FV has travelled.

This arm is a SHADOW annotation that rests, per filled entry, a second exit
whose profit-target limit is **recomputed each cycle at current fair value**,
and records what it would have done. **No order exists behind it** — like
every PULSE row, it is bookkeeping. The incumbent's behaviour is untouched;
this never changes what the engine actually rests (design constraint 2).

The pinned repricing rule (YES frame, every price in this repo — V14)
---------------------------------------------------------------------
    static_target  = entry_price + profit_target   (YES position)
                   = entry_price - profit_target   (NO position)
    dynamic_target = static_target + (fv_now - fv_open)

`fv_open` is the fair value at the cycle the position opened (anchored on the
first usable FV if the open cycle had none). The target is the static target
shifted by how far FV has travelled since open. Two consequences that matter:

* **Flat FV reproduces the static target exactly** — `fv_now == fv_open`
  gives `dynamic == static`, so a game whose FV never moves produces ZERO
  divergence. This is the mutation-test invariant, and it is why the rule is
  a shift of the static target rather than a function of FV alone (which
  would diverge even when nothing moved).
* When FV rises the YES target rises (hold out for the better exit); when FV
  falls the YES target falls (close nearer the new fair value rather than
  resting above a market that has left). The downside repricing is the
  arm's own stop-equivalent — see "one changed variable" below.

Everything else mirrors the incumbent EXACTLY: the ev/adverse stop
(`docs/math/pulse-ev-stop.md`), the endpoint fill rule (mid crosses the
resting limit; never filled by the tick it was born from), the YES/NO frame
and fill sign. **The only changed variable is the profit-target limit**, so
a divergence between the two arms is attributable to repricing and nothing
else. The arm keeps the incumbent's ev stop so that below entry both arms
behave identically and the comparison isolates the profit-taking side.

Staleness bound — per v3a's fallback pattern (registration)
-----------------------------------------------------------
Repricing may only trust a FRESH FV. `core/pulse/live.py` already produces a
fair value only when the estimate's clock is usable (v3/v4:
`VENUE_CLOCK_STALENESS_SECONDS = 60s`). Mirroring that bound here: when this
cycle's estimate is usable the target reprices; when it is not, the target
HOLDS its last usable value while that value is within
`REPRICE_STALENESS_SECONDS`, and beyond the bound FALLS BACK to the static
target — the honest degrade (v3a): without a fresh estimate the arm cannot
claim to be repricing, so it reverts to the incumbent's fixed target rather
than repricing off a stale number. Holds and fallbacks are counted so the
bound is observable — and provably fires — in the tape.

Two limitations, stated not buried
----------------------------------
* **F8 caveat (registration, mandatory):** repricing fixes staleness of the
  TARGET, not adverse selection of the RESTING order. A repriced exit still
  rests against flow ~37s ahead, and in reality repricing a resting limit is
  a cancel+replace that surrenders queue position — neither cost is modelled
  here; both make this arm, like every fill-dependent PULSE number,
  optimistic by construction. It is an instrument, never evidence.
* **In-memory, like the incumbent position.** An arm lives in process memory
  from entry fill until it fills or the market rides to settlement; a restart
  mid-game abandons in-flight arms exactly as it abandons in-flight
  incumbent positions (neither is reconstructed from the DB). Continuous
  per-game operation is the assumption for both.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

#: Position direction (YES frame), restated to avoid importing the ORM here —
#: this module is pure and unit-tested without a database.
YES = "yes"
NO = "no"

STOP_RULE_EV = "ev"
STOP_RULE_ADVERSE = "adverse"

#: Repricing staleness bound — the same 60s v3 uses for the venue clock
#: (`VENUE_CLOCK_STALENESS_SECONDS`). A held FV older than this stops being
#: trusted and the target falls back to static.
REPRICE_STALENESS_SECONDS = 60.0

_PRICE_FLOOR = 0.01
_PRICE_CEIL = 0.99


def _clamp(p: float) -> float:
    return min(max(p, _PRICE_FLOOR), _PRICE_CEIL)


def static_target(side: str, entry_price: float, profit_target: float) -> float:
    """The incumbent's fixed profit-target limit (YES frame), clamped."""
    raw = (entry_price + profit_target if side == YES
           else entry_price - profit_target)
    return _clamp(raw)


def dynamic_target(side: str, entry_price: float, profit_target: float,
                   fv_now: float | None, fv_open: float | None) -> float:
    """The pinned repriced limit (YES frame), clamped.

    Falls back to the static target whenever FV is unavailable — the caller's
    staleness logic decides which ``fv_now`` to pass (fresh, held, or None
    for a beyond-bound fallback).
    """
    stat = static_target(side, entry_price, profit_target)
    if fv_now is None or fv_open is None:
        return stat
    return _clamp(stat + (fv_now - fv_open))


@dataclass
class RepriceOutcome:
    """What one cycle's observation did to the arm — for logging and tests."""

    filled: bool = False
    fill_price: float | None = None
    staleness: str = "fresh"          # 'fresh' | 'held' | 'fallback' | 'n/a'
    repriced: bool = False


@dataclass
class RepriceArm:
    """One filled entry's shadow dynamic exit. Independent of the incumbent
    position's life: it lives until it fills or the market settles, so it can
    hold past the incumbent's exit (the whole point of the hypothesis).
    """

    entry_decision_id: int
    event_slug: str
    market_slug: str
    side: str
    strategy: str
    entry_price: float
    contracts: float
    profit_target: float
    opened_at: dt.datetime
    stop_rule: str = STOP_RULE_EV
    stop_adverse: float = 0.10
    #: The estimates version that priced the entry, recorded at open so two
    #: model generations never blend in a paired read (the era-separation
    #: lesson). Set by the engine; the pure arm defaults it.
    estimates_version: str = "v1"

    # ---- evolving state -------------------------------------------------- #
    fv_open: float | None = None
    limit: float = 0.0
    is_stop: bool = False
    fv_last: float | None = None
    fv_last_at: dt.datetime | None = None
    reprice_cycles: int = 0
    target_diverged: bool = False
    staleness_holds: int = 0
    staleness_fallbacks: int = 0
    filled_at: dt.datetime | None = None
    fill_price: float | None = None

    def __post_init__(self) -> None:
        # Born resting at the static target — identical to the incumbent at
        # t0; the first usable FV anchors fv_open and repricing begins.
        self.limit = static_target(self.side, self.entry_price, self.profit_target)

    @property
    def buys_yes(self) -> bool:
        # A NO position exits by buying YES back (mirror the incumbent).
        return self.side == NO

    @property
    def done(self) -> bool:
        return self.filled_at is not None

    def _crosses(self, mid: float) -> bool:
        # Endpoint fill rule, identical to RestingOrder.fills_at.
        return mid <= self.limit if self.buys_yes else mid >= self.limit

    def observe(self, *, mid: float, ask: float, bid: float,
                at: dt.datetime, fv: float | None,
                clock_usable: bool) -> RepriceOutcome:
        """Advance the arm one observation. Order mirrors the engine cycle:
        fill first (against the limit resting since last cycle), then stop,
        then reprice for next cycle. Never filled by the tick it was born
        from (``at > opened_at``)."""
        out = RepriceOutcome()
        if self.done:
            return out

        # 1. Fill against the ALREADY-resting limit (as the incumbent does in
        #    _check_exit_fill, before _manage_position reprices anything).
        if at > self.opened_at and self._crosses(mid):
            self.filled_at = at
            self.fill_price = self.limit
            out.filled = True
            out.fill_price = self.limit
            return out

        # 2. Stop — mirror _manage_position exactly. Once stopped, the limit
        #    rests at the touch and never reprices again.
        usable = clock_usable and fv is not None
        if not self.is_stop and usable:
            adverse = (self.entry_price - fv if self.side == YES
                       else fv - self.entry_price)
            fire = (adverse >= 0.0 if self.stop_rule == STOP_RULE_EV
                    else adverse >= self.stop_adverse)
            if fire:
                self.is_stop = True
                self.limit = _clamp(ask if self.side == YES else bid)
                out.staleness = "n/a"
                return out
        if self.is_stop:
            out.staleness = "n/a"
            return out

        # 3. Reprice the profit-target limit at current FV, staleness-bounded.
        if usable:
            fv_used, out.staleness = fv, "fresh"
            self.fv_last, self.fv_last_at = fv, at
        elif (self.fv_last is not None and self.fv_last_at is not None
              and (at - self.fv_last_at).total_seconds() <= REPRICE_STALENESS_SECONDS):
            fv_used, out.staleness = self.fv_last, "held"
            self.staleness_holds += 1
        else:
            fv_used, out.staleness = None, "fallback"
            self.staleness_fallbacks += 1

        if self.fv_open is None and fv_used is not None:
            self.fv_open = fv_used     # anchor on the first usable FV
        self.limit = dynamic_target(self.side, self.entry_price,
                                    self.profit_target, fv_used, self.fv_open)
        self.reprice_cycles += 1
        out.repriced = True
        if self.limit != static_target(self.side, self.entry_price,
                                       self.profit_target):
            self.target_diverged = True
        return out
