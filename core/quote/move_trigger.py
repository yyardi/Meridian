"""H1c live trigger: quote ONLY in the minute after a >=1c one-minute move, on
the move's side. Places nothing; emits intents.

The rule, exactly as measured
-----------------------------
`cfb/run_making_touch.py` with MOVE_STRATUM=1 (registered as H1c in
docs/math/e8-nfl-preregistration.md) buckets the winner market's mid into
one-minute closes. If the close of minute k differs from the close of minute
k-1 by at least 0.01, it posts ONE contract at the touch on the FIRST snapshot
of minute k+1 -- a bid after an up-move, an ask after a down-move -- rests it
120 seconds, and marks the fill out against the mid 2 and 5 minutes later.
Nothing else is quoted: at-plays quoting lost -0.82c/fill on CFB and dead
windows were flat.

STATUS 2026-09-10 14:14Z: this stratum was reported positive (+3.58c, 15/17 games) and
that report is RETRACTED. This class was written as the independent
implementation for the live probe; the replay (`cfb/run_trigger_replay.py`)
counted 862 moves against the harness's 865, and the difference was a
one-minute LOOK-AHEAD in the harness's post instant. Corrected, the rule
LOSES: -1.21c [-2.15, -0.27] at +2 min, 8/22 games positive. Nothing should be
armed on it. The class is kept because it is the second implementation that
caught the first, and the reconciliation is now exact (862 / 850 both ways).

What it does NOT do
-------------------
* No order. It returns a `MoveSignal`; turning that into a resting order is
  `core.quote.probe.plan()` + `execute(armed=True, submit_fn=...)`, which is
  inert until an operator's own script arms it. Nothing here imports a venue
  client or reads a credential.
* No opinion about fair value. Arm A of the harness is the naive maker; the
  shield arms did not beat it on markout and are not reproduced here.
* No sizing. One contract. The bounded probe is one contract with a hard loss
  cap the operator sets in their arming script.

Minute phase
------------
The harness anchored minute 0 on the first play (`phase="kickoff"`). A live
process has no reason to prefer that phase over wall-clock minutes, and a
result that holds only for one phase is an artifact of the phase. Both are
supported here; the pre-registration addendum for 2026-09-10 records the
result under both. Live use is `phase="utc"`.

    python -m core.quote.move_trigger      # selftest, with mutants
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

MIN_MOVE = 0.01           # MOVE_MIN_C in the harness
REST_S = 120              # MOVE_REST_S
GAME_WINDOW_S = 3 * 3600 + 40 * 60   # the harness's `end = ko + 3h40`


@dataclass(frozen=True)
class MoveSignal:
    """One posting instruction. `at` is the observation we post ON."""
    at: dt.datetime
    side: str            # "bid" after an up-move, "ask" after a down-move
    price: float         # the touch on that side at `at`: join, never improve
    minute_k: int        # the minute whose close moved (harness's k)
    mid_prev: float      # close of minute k-1
    mid_now: float       # close of minute k
    dm: float            # mid_now - mid_prev
    rest_until: dt.datetime


class MoveTrigger:
    """Feed every winner-market observation for ONE game, in time order."""

    def __init__(self, anchor: dt.datetime, *, phase: str = "utc",
                 min_move: float = MIN_MOVE, rest_s: int = REST_S,
                 window_s: int = GAME_WINDOW_S) -> None:
        if phase not in ("utc", "kickoff"):
            raise ValueError(f"phase must be utc|kickoff, got {phase!r}")
        self.anchor = anchor
        self.phase = phase
        self.min_move = min_move
        self.rest_s = rest_s
        self._end = anchor + dt.timedelta(seconds=window_s)
        self._close: dict[int, float] = {}     # minute -> closing mid so far
        self._opened: set[int] = set()         # minutes whose first obs is done
        self.n_observed = 0

    def _minute(self, t: dt.datetime) -> int:
        if self.phase == "utc":
            return int(t.timestamp() // 60)
        return int((t - self.anchor).total_seconds() // 60)

    def observe(self, t: dt.datetime, bid: float, ask: float) -> MoveSignal | None:
        # the harness keeps snapshots in (ko, ko + 3h40] only
        if not (self.anchor < t <= self._end):
            return None
        self.n_observed += 1
        k = self._minute(t)
        sig = None
        if k not in self._opened:
            self._opened.add(k)
            # first observation of minute k: minutes k-1 and k-2 are closed.
            # The harness posts on first[k'+1] for a move between k'-1 and k'.
            prev, now = self._close.get(k - 2), self._close.get(k - 1)
            if prev is not None and now is not None:
                dm = now - prev
                # SAME comparison as the harness (no epsilon) so replay can agree
                # with it exactly; boundary cases are counted by the replay.
                if not abs(dm) < self.min_move:
                    side = "bid" if dm > 0 else "ask"
                    sig = MoveSignal(at=t, side=side,
                                     price=bid if side == "bid" else ask,
                                     minute_k=k - 1, mid_prev=prev, mid_now=now,
                                     dm=dm,
                                     rest_until=t + dt.timedelta(seconds=self.rest_s))
        self._close[k] = (bid + ask) / 2.0     # last observation wins = the close
        return sig


def replay(observations, anchor: dt.datetime, **kw) -> list[MoveSignal]:
    """Run the trigger over an iterable of (t, bid, ask) in time order."""
    trig = MoveTrigger(anchor, **kw)
    out = []
    for t, b, a in observations:
        s = trig.observe(t, b, a)
        if s is not None:
            out.append(s)
    return out


# ------------------------------------------------------------------ selftest
def _selftest() -> None:
    T0 = dt.datetime(2026, 9, 13, 17, 0, tzinfo=dt.timezone.utc)   # a :00 minute
    m = lambda mins, secs=0: T0 + dt.timedelta(minutes=mins, seconds=secs)

    # * one +1c move: minute 1 closes 0.50, minute 2 closes 0.51 -> ONE signal,
    #   a BID, on the FIRST observation of minute 3, at that observation's bid
    obs = [(m(1, 5), 0.49, 0.51), (m(2, 5), 0.50, 0.52), (m(2, 40), 0.50, 0.52),
           (m(3, 2), 0.505, 0.525), (m(3, 30), 0.505, 0.525)]
    sig = replay(obs, T0)
    assert len(sig) == 1, sig
    s = sig[0]
    assert s.side == "bid" and s.at == m(3, 2) and s.price == 0.505, s
    assert abs(s.dm - 0.01) < 1e-9 and s.minute_k == int(m(2).timestamp() // 60)
    assert s.rest_until == m(3, 2) + dt.timedelta(seconds=120)

    # * a -1c move is an ASK at the ask
    obs = [(m(1, 5), 0.50, 0.52), (m(2, 5), 0.49, 0.51), (m(3, 2), 0.485, 0.505)]
    sig = replay(obs, T0)
    assert len(sig) == 1 and sig[0].side == "ask" and sig[0].price == 0.505, sig

    # * a 0.5c move is NOT a signal
    obs = [(m(1, 5), 0.50, 0.52), (m(2, 5), 0.505, 0.525), (m(3, 2), 0.505, 0.525)]
    assert replay(obs, T0) == []

    # * MUTANT: the close is the LAST observation of the minute, not the first.
    #   Minute 2 opens +2c up and closes back flat -> no move.
    obs = [(m(1, 5), 0.50, 0.52), (m(2, 5), 0.52, 0.54), (m(2, 50), 0.50, 0.52),
           (m(3, 2), 0.50, 0.52)]
    assert replay(obs, T0) == [], "close must be the last observation"

    # * a missing minute k-1 (no observation) -> no signal, never interpolated
    obs = [(m(1, 5), 0.50, 0.52), (m(3, 2), 0.52, 0.54), (m(4, 1), 0.52, 0.54)]
    assert replay(obs, T0) == []

    # * the post is on the FIRST observation of the next minute only: a second
    #   observation in minute 3 must not re-fire
    obs = [(m(1, 5), 0.49, 0.51), (m(2, 5), 0.50, 0.52), (m(3, 2), 0.50, 0.52),
           (m(3, 40), 0.50, 0.52), (m(3, 59), 0.50, 0.52)]
    assert len(replay(obs, T0)) == 1

    # * observations before the anchor or after 3h40 are ignored (harness window)
    obs = [(m(-2), 0.40, 0.42), (m(-1), 0.50, 0.52), (m(0, 30), 0.50, 0.52),
           (m(221), 0.60, 0.62), (m(222), 0.70, 0.72), (m(223), 0.70, 0.72)]
    assert replay(obs, T0) == []

    # * phase matters exactly when the move straddles a bucket boundary:
    #   kickoff at :00:30 shifts every bucket by 30s. Two observations 40s apart
    #   across a UTC minute boundary land in different UTC minutes but the same
    #   kickoff-anchored minute.
    ko = T0 + dt.timedelta(seconds=30)
    obs = [(m(1, 5), 0.50, 0.52), (m(1, 50), 0.50, 0.52), (m(2, 5), 0.52, 0.54),
           (m(2, 45), 0.52, 0.54), (m(3, 2), 0.52, 0.54), (m(3, 45), 0.52, 0.54),
           (m(4, 2), 0.52, 0.54)]
    utc_sig = replay(obs, ko, phase="utc")
    ko_sig = replay(obs, ko, phase="kickoff")
    # UTC: minute 1 closes 0.51 (m1:50), minute 2 closes 0.53 (m2:45) -> post at m3:02.
    # kickoff-anchored (buckets start at :30): minute 0 = [0:30,1:30) closes 0.51,
    # minute 1 = [1:30,2:30) closes 0.53 at m2:05 -> post on the first obs of
    # minute 2 = m2:45. Same tape, different post instant, 17 seconds apart.
    assert len(utc_sig) == 1 and utc_sig[0].at == m(3, 2), utc_sig
    assert len(ko_sig) == 1 and ko_sig[0].at == m(2, 45), ko_sig
    assert utc_sig[0].at != ko_sig[0].at

    # * MUTANT: an epsilon in the comparison would admit 0.00999...; the
    #   harness admits it too only if float arithmetic lands >= 0.01. Pin the
    #   comparison to the harness's: (0.505+0.525)/2 - (0.50+0.52)/2 in floats.
    dm = (0.505 + 0.525) / 2 - (0.50 + 0.52) / 2
    obs = [(m(1, 5), 0.50, 0.52), (m(2, 5), 0.505, 0.525), (m(3, 2), 0.505, 0.525)]
    assert (len(replay(obs, T0)) == 1) == (not abs(dm) < MIN_MOVE), \
        "trigger and harness must agree on the boundary case"

    print("selftest OK -- one signal per >=1c close-to-close move, posted on the first "
          "observation of the next minute at the touch on the move's side; last-obs close; "
          "no interpolation; window (anchor, +3h40]; phase changes the post instant.")


if __name__ == "__main__":
    _selftest()
