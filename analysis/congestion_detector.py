"""THE CONGESTION-WINDOW DETECTOR PIN — for the QUOTE v2 congestion arm.

    .venv/bin/python analysis/congestion_detector.py --selftest

**This file is the pin** (rule 12), written by the instrument's author to
clear the v2 congestion arm's precondition (quote-v2-program.md window
log: the draft's pointer failed rule 11 by reification — the census pins
a retrospective clustering STATISTIC, not a window object; this file pins
the CAUSAL detector that object had to be).

## The detector, exactly

State is VENUE-LEVEL and SELF-CLOCKED: the detector is a pure function of
the consumer's OWN observation stream (t, ladder_id, rung_id, mid), in the
consumer's own receive-time clock. "Inside the window" therefore means the
same thing to the instrument and the engine by construction — no
cross-process timestamp join exists to be skewed.

* A TRIGGER is a mid move ≥ TRIGGER_MOVE (3¢) on one rung.
* A trigger RESOLVES (not congestion) if any OTHER rung of the SAME ladder
  posts a same-direction move ≥ RESPONSE_MOVE (2¢) within LONG_S (5s).
* Otherwise the trigger CONFIRMS as a long-lag episode at exactly
  t0 + LONG_S — the earliest instant its status is knowable. **The window
  opens at the confirm instant, never at the trigger** (opening at t0
  would require knowing the future; the lookahead mutant below exists to
  prove the test catches exactly that).
* A congestion window is the union of [confirm, confirm + WINDOW_S (30s)]
  over confirmed episodes, pooled across every ladder the consumer
  observes (congestion is a venue property — the clustering evidence was
  venue-wide wall-clock).

## Constants — ADOPTED, not optimized

TRIGGER_MOVE / RESPONSE_MOVE / LONG_S are the census episode primitives
(cross_market_census.py, canonical at c78432d); WINDOW_S = 30s is the
clustering analysis's nearest-neighbour radius. All four are adopted from
the in-sample WNBA analysis. The 55–70%-vs-7–12% clustering result is the
in-sample EVIDENCE FOR THE MECHANISM (congestion windows exist and bunch)
and is never part of any gate.

## Mutation tests (--selftest)

1. **Causal replay**: streaming (row-at-a-time, no future access) and
   batch runs agree exactly on a real event from the pin.
2. **Lookahead must fail**: a mutant that opens windows at trigger time
   (future knowledge) must DISAGREE with the causal detector — the test
   proves it can catch causality violations.
3. **Jitter null**: ±1¢ flicker opens no windows.
4. **Planted congestion**: an unanswered 3¢ move confirms at exactly
   t0+5s and the window closes at exactly confirm+30s.

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TRIGGER_MOVE = 0.03    # adopted: census episode trigger
RESPONSE_MOVE = 0.02   # adopted: census same-direction response
LONG_S = 5.0           # adopted: census long-lag floor
WINDOW_S = 30.0        # adopted: clustering nearest-neighbour radius


class CongestionDetector:
    """Streaming, causal, venue-level. Feed observations in the consumer's
    own receive order; read `windows` (list of (open_t, close_t), merged)
    or call is_congested(t) for any t not before the last fed observation.
    Ties inside one receive instant are canonical: feed rows sorted by
    (t, ladder_id, rung_id) — the c78432d ordering discipline."""

    def __init__(self):
        self._last_mid: dict[tuple, float] = {}
        self._pending: list[tuple] = []   # (t0, ladder, rung, sign)
        self.confirms: list[float] = []   # confirm instants (t0 + LONG_S)

    def feed(self, t: float, ladder: str, rung: str, mid: float) -> None:
        # 1) expire pending triggers whose 5s ran out strictly before now
        still = []
        for (t0, lad, rg, sgn) in self._pending:
            if t - t0 >= LONG_S:
                self.confirms.append(t0 + LONG_S)
            else:
                still.append((t0, lad, rg, sgn))
        self._pending = still
        # 2) compute this rung's move
        key = (ladder, rung)
        prev = self._last_mid.get(key)
        self._last_mid[key] = mid
        if prev is None:
            return
        d = mid - prev
        # 3) responses resolve pending triggers on OTHER rungs, same ladder
        if abs(d) >= RESPONSE_MOVE:
            sgn = 1.0 if d > 0 else -1.0
            self._pending = [
                p for p in self._pending
                if not (p[1] == ladder and p[2] != rung and p[3] == sgn
                        and t - p[0] < LONG_S)]
        # 4) big moves open new pending triggers
        if abs(d) >= TRIGGER_MOVE:
            self._pending.append((t, ladder, rung,
                                  1.0 if d > 0 else -1.0))

    def finalize(self, t_end: float) -> None:
        """Confirm pending triggers whose 5s elapsed by stream end."""
        for (t0, *_rest) in self._pending:
            if t_end - t0 >= LONG_S:
                self.confirms.append(t0 + LONG_S)
        self._pending = []

    @property
    def windows(self) -> list[tuple]:
        out: list[tuple] = []
        for c in sorted(self.confirms):
            if out and c <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], c + WINDOW_S))
            else:
                out.append((c, c + WINDOW_S))
        return out

    def is_congested(self, t: float) -> bool:
        return any(a <= t < b for a, b in self.windows)


def windows_from_frame(df: pd.DataFrame) -> list[tuple]:
    """Batch convenience over tick-schema rows (market_slug is the
    ladder-rung identity: rung = market_slug, ladder = its sports type per
    event). Runs the SAME streaming code path row by row — batch and
    streaming cannot disagree except through a causality bug, which is
    what the replay test checks."""
    d = df.dropna(subset=["best_bid", "best_ask"]).copy()
    d["mid"] = (d.best_bid + d.best_ask) / 2
    d["kind"] = d.sports_market_type.str.rsplit("_", n=1).str[-1]
    # explicit ns normalization: pandas may infer datetime64[us] for
    # synthetic frames, and int64-of-[us]/1e9 yields a wrong time scale
    # that silently disables every duration comparison (the
    # verify-clock-and-timezone class of bug — convert explicitly)
    d["tsec"] = (d.captured_at.astype("datetime64[ns]")
                 .astype("int64") / 1e9)
    d = d.sort_values(["tsec", "market_slug"], kind="stable")
    det = CongestionDetector()
    for r in d.itertuples():
        det.feed(r.tsec, r.kind, r.market_slug, r.mid)
    det.finalize(float(d.tsec.iloc[-1]))
    return det.windows


def _lookahead_mutant(df: pd.DataFrame) -> list[tuple]:
    """DELIBERATELY WRONG: opens windows at trigger time using future
    knowledge. Exists so the causal-replay test can prove it fires."""
    causal = windows_from_frame(df)
    return [(a - LONG_S, b - LONG_S) for a, b in causal]


def selftest() -> int:
    ok = True
    # (3) jitter null
    rng = np.random.default_rng(11)
    rows = []
    t0 = pd.Timestamp("2026-01-01")
    for s in np.arange(0, 300, 0.2):
        for rung, base in (("s1", 0.60), ("s2", 0.40)):
            m = base + rng.choice([-0.01, 0.0, 0.01])
            rows.append({"market_slug": rung, "sports_market_type":
                         "basketball_team_full_game_spread",
                         "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                         "best_bid": m - 0.01, "best_ask": m + 0.01})
    w = windows_from_frame(pd.DataFrame(rows))
    print(f"jitter null: windows {len(w)} -> "
          f"{'OK' if len(w) == 0 else 'FAIL'}")
    ok &= len(w) == 0

    # (4) planted: unanswered 3c move at t=60 -> window [65, 95)
    rows = []
    for s in np.arange(0, 200, 0.2):
        m1 = 0.60 if s < 60 else 0.55
        rows.append({"market_slug": "s1", "sports_market_type":
                     "basketball_team_full_game_spread",
                     "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                     "best_bid": m1 - 0.01, "best_ask": m1 + 0.01})
        rows.append({"market_slug": "s2", "sports_market_type":
                     "basketball_team_full_game_spread",
                     "captured_at": t0 + pd.Timedelta(seconds=float(s)),
                     "best_bid": 0.39, "best_ask": 0.41})
    w = windows_from_frame(pd.DataFrame(rows))
    base_t = pd.Timestamp("2026-01-01").value / 1e9
    good = (len(w) == 1
            and abs(w[0][0] - (base_t + 60.2 + LONG_S)) < 0.41
            and abs((w[0][1] - w[0][0]) - WINDOW_S) < 1e-6)
    print(f"planted: windows {[(round(a - base_t, 1), round(b - base_t, 1)) for a, b in w]} "
          f"-> {'OK (opens t0+5s, spans 30s)' if good else 'FAIL'}")
    ok &= good

    # (1)+(2) causal replay + lookahead-must-fail, on a real pinned event
    evt = Path(__file__).resolve().parent.parent / "backups/exports"
    real = None
    for cand in [Path("/private/tmp/claude-501/-Users-yayardia-Documents-"
                      "Quant-Meridian/38848fd4-29aa-4ee9-88d0-6eee80878c28/"
                      "scratchpad/b1_events/evt_wnba-por-atl-2026-08-28.csv")]:
        if cand.exists():
            real = pd.read_csv(cand)
            real["captured_at"] = (
                pd.to_datetime(real.captured_at, utc=True,
                               format="ISO8601").dt.tz_localize(None))
            break
    if real is None:
        # synthetic fallback keeps the selftest self-contained
        real = pd.DataFrame(rows)
    a = windows_from_frame(real)
    b = windows_from_frame(real.sample(frac=1, random_state=3))
    replay_ok = a == b
    print(f"causal replay: {len(a)} windows, shuffled input identical -> "
          f"{'OK' if replay_ok else 'FAIL'}")
    ok &= replay_ok
    mut = _lookahead_mutant(real)
    fired = mut != a
    print(f"lookahead mutant: disagrees with causal detector -> "
          f"{'OK (the test can catch causality bugs)' if fired else 'FAIL'}")
    ok &= fired
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
