"""Scorer for the variance-aware Kelly gate (docs/math/variance-aware-kelly.md).

    .venv/bin/python analysis/variance_kelly_scorer.py [--tape CSV]
                                                       [--exports DIR]
    .venv/bin/python analysis/variance_kelly_scorer.py --selftest

Reads a forward decision-tape export, keeps entries decided AFTER the
registration's cohort epoch (read from git — the epoch of the commit that
ADDED the registration file, never from prose), scores both arms and
prints the registered verdict skeleton:

* **arms** — incumbent flat fraction ``F0`` vs the pinned variance arm
  (``analysis/ride_model_pin.py``: frozen P(ride), inverse-variance map,
  equal mean exposure over the cohort);
* **primary** — paired per-game realized log-growth (entries compound
  sequentially in decided_at order within a game; concurrency ignored —
  stated simplification; both arms score the SAME realized per-$ outcomes,
  so fill-rule optimism largely cancels in the pair);
* **secondary** — per-game max drawdown of each arm's within-game path;
* **floors** — ≥100 sizing-divergent entries (|f_var − F0| > pinned eps)
  across ≥15 games with at least one; below either: NO DATA, counts only.
  At ≥2× floors with the primary CI still straddling zero:
  FAIL-BY-EXHAUSTION;
* **the mandatory printed check, verbatim** — "q5 − q1 realized mean ≈ 0
  in-cohort" (quintiles by the PINNED edges; per-game paired contrast on
  games carrying both quintiles, game-clustered); and the tripwire: if the
  arm's gain is dominated by mean-selection — the first-order selection
  term ``Sel_g = Σ (f_i − F0)·r_i`` has a clustered CI above zero AND
  carries > 50% of a positive total gain — or the q5−q1 contrast breaks
  negative (CI fully below zero: the flat-quintile premise failed in the
  direction the arm tilts), the output prints **"rebuilt a filter"**
  regardless of the primary;
* **exit-policy assertion** — the cohort REQUIRES the incumbent exit
  policy; any exit row in-cohort whose reason is not in
  {profit_target, ev_stop} raises hard, naming the registration's
  split-at-that-instant rule. Enforced by code, not memory.

``--selftest`` runs the two registered mutations through the same scoring
core: a fat-left-tail / zero-mean-difference tape (the variance arm must
win the primary, no tripwire), and a mean-driven tape (the tripwire MUST
print "rebuilt a filter") — proving the check can fire.

No in-sample result justifies capital. The forward test is the evidence.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.quote.adverse_selection import clustered_mean  # noqa: E402
import ride_model_pin as pin                              # noqa: E402

REGISTRATION = "docs/math/variance-aware-kelly.md"
DEFAULT_TAPE = "pulse_decisions_full_20260901T195202Z.csv"
INCUMBENT_EXIT_REASONS = {"profit_target", "ev_stop"}
FLOOR_DIVERGENT = 100
FLOOR_GAMES = 15


def cohort_epoch() -> int:
    """Epoch of the commit that ADDED the registration file. From git,
    never from prose (the registration's own rule)."""
    out = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%at", "--",
         REGISTRATION],
        cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    if not out:
        raise SystemExit(f"cannot read cohort epoch: no commit adds "
                         f"{REGISTRATION} in this checkout")
    return int(out[-1])


def load_cohort(tape_path: Path, epoch: int) -> pd.DataFrame:
    """Entry ledger for rows decided after the epoch, with the exit-policy
    assertion applied to the same window."""
    from pulse_loss_map import build_ledger
    raw = pd.read_csv(tape_path)
    decided = pd.to_datetime(raw.decided_at, utc=True, format="ISO8601")
    in_cohort = decided > pd.Timestamp(epoch, unit="s", tz="UTC")

    exits = raw[(raw.action == "exit") & in_cohort]
    bad = set(exits.reason.dropna()) - INCUMBENT_EXIT_REASONS
    if bad:
        raise SystemExit(
            f"EXIT-POLICY CHANGE DETECTED in cohort: reasons {sorted(bad)} "
            f"are not the incumbent policy {sorted(INCUMBENT_EXIT_REASONS)}. "
            f"The registration splits the cohort at the change instant — "
            f"score each era separately; this scorer refuses to pool them.")

    m = build_ledger(raw)
    m["decided_ts"] = pd.to_datetime(m.decided_at, utc=True,
                                     format="ISO8601")
    m = m[m.decided_ts > pd.Timestamp(epoch, unit="s", tz="UTC")].copy()
    return m.reset_index(drop=True)


def score_frame(m: pd.DataFrame) -> dict:
    """Scoring core. Needs: event_slug, decided-order sortable column
    ``order_key``, ret (realized per-$), p_ride. Returns everything the
    report prints; used identically by real runs and mutations."""
    f_var = pin.variance_fractions(m.p_ride.to_numpy())
    f0 = pin.F0
    m = m.assign(f_var=f_var)
    divergent = np.abs(f_var - f0) > pin.DIVERGENCE_EPS
    games_div = m.loc[divergent, "event_slug"].nunique()

    diffs, sel, dd0, dd1 = {}, {}, [], []
    for slug, g in m.sort_values("order_key").groupby("event_slug"):
        r = g.ret.to_numpy()
        fv = g.f_var.to_numpy()
        lg0 = np.log1p(np.clip(f0 * r, -0.999, None))
        lg1 = np.log1p(np.clip(fv * r, -0.999, None))
        diffs[slug] = [float(lg1.sum() - lg0.sum())]
        sel[slug] = [float(((fv - f0) * r).sum())]
        for lg, acc in ((lg0, dd0), (lg1, dd1)):
            w = np.exp(np.cumsum(lg))
            peak = np.maximum.accumulate(np.concatenate([[1.0], w]))
            acc.append(float((1 - np.concatenate([[1.0], w]) / peak).max()))

    q = pin.quintile(m.p_ride.to_numpy())
    contrast = {}
    for slug, g in m.assign(q=q).groupby("event_slug"):
        r5, r1 = g.loc[g.q == 5, "ret"], g.loc[g.q == 1, "ret"]
        if len(r5) and len(r1):
            contrast[slug] = [float(r5.mean() - r1.mean())]

    return {
        "n": len(m), "games": m.event_slug.nunique(),
        "n_divergent": int(divergent.sum()), "games_divergent": games_div,
        "primary": clustered_mean(diffs),
        "selection": clustered_mean(sel),
        "sel_total": sum(v[0] for v in sel.values()),
        "gain_total": sum(v[0] for v in diffs.values()),
        "q5_q1": clustered_mean(contrast), "n_contrast_games": len(contrast),
        "dd0": float(np.mean(dd0)) if dd0 else float("nan"),
        "dd1": float(np.mean(dd1)) if dd1 else float("nan"),
    }


def report(s: dict) -> str:
    out = []
    add = out.append
    add(f"entries in cohort             : {s['n']:,} "
        f"({s['games']} games)")
    add(f"sizing-divergent entries      : {s['n_divergent']:,} "
        f"(floor {FLOOR_DIVERGENT}) across {s['games_divergent']} games "
        f"(floor {FLOOR_GAMES})")
    at_floor = (s["n_divergent"] >= FLOOR_DIVERGENT
                and s["games_divergent"] >= FLOOR_GAMES)
    exhausted = (s["n_divergent"] >= 2 * FLOOR_DIVERGENT
                 and s["games_divergent"] >= 2 * FLOOR_GAMES)
    cm = s["primary"]
    if cm is not None:
        add(f"primary: paired log-growth    : {cm.mean:+.5f} "
            f"[{cm.lo:+.5f}, {cm.hi:+.5f}]  (G={cm.n_clusters})")
        add(f"secondary: mean max drawdown  : incumbent {s['dd0']:.4f} vs "
            f"variance arm {s['dd1']:.4f}")

    tripwire = False
    cq = s["q5_q1"]
    if cq is not None:
        add(f"MANDATORY CHECK — q5 − q1 realized mean ≈ 0 in-cohort: "
            f"{cq.mean * 100:+.1f}¢/$ [{cq.lo * 100:+.1f}, "
            f"{cq.hi * 100:+.1f}] ({s['n_contrast_games']} games with both "
            f"quintiles)")
        if cq.hi < 0:
            tripwire = True
            add("  -> the flat-quintile premise BROKE in the direction the "
                "arm tilts")
    else:
        add("MANDATORY CHECK — q5 − q1 realized mean ≈ 0 in-cohort: "
            "NOT COMPUTABLE (too few games carry both quintiles)")
    cs = s["selection"]
    if cs is not None and cm is not None:
        share = (s["sel_total"] / s["gain_total"]
                 if s["gain_total"] > 0 else float("nan"))
        add(f"selection term Sel_g          : {cs.mean:+.5f} "
            f"[{cs.lo:+.5f}, {cs.hi:+.5f}]; share of gain "
            f"{share:+.2f}" if s["gain_total"] > 0 else
            f"selection term Sel_g          : {cs.mean:+.5f} "
            f"[{cs.lo:+.5f}, {cs.hi:+.5f}]; total gain ≤ 0")
        if cs.lo > 0 and s["gain_total"] > 0 and share > 0.5:
            tripwire = True
            add("  -> the arm's gain is dominated by mean-selection")
    if tripwire:
        add('VERDICT OVERRIDE: "rebuilt a filter" — the gain is '
            "mean-selection, not variance sizing, regardless of the "
            "primary.")
        add("VERDICT: rebuilt a filter")
    elif not at_floor:
        add(f"VERDICT: NO DATA — floors are {FLOOR_DIVERGENT} divergent "
            f"entries / {FLOOR_GAMES} games; counts only.")
    elif cm is not None and cm.lo > 0:
        add("VERDICT: PASS (log-growth CI excludes zero in the variance "
            "arm's favour at floor)")
    elif exhausted and cm is not None and cm.lo <= 0 <= cm.hi:
        add("VERDICT: FAIL-BY-EXHAUSTION (2x floors, still straddling)")
    else:
        add("VERDICT: FAIL" if cm is not None and cm.hi < 0
            else "VERDICT: accruing (at floor, CI straddles zero; "
                 "closure at 2x floors)")
    return "\n".join(out)


def run(tape: Path, exports: Path) -> int:
    pin.verify(exports)  # the pin is checked at read time, every read
    epoch = cohort_epoch()
    add_iso = pd.Timestamp(epoch, unit="s", tz="UTC").isoformat()
    print(f"# Variance-aware Kelly — scorer\n")
    print(f"Registration: `{REGISTRATION}` · cohort epoch (git, commit "
          f"that added the file): {epoch} = {add_iso}")
    print(f"Tape: `{tape.name}` · arms: flat F0={pin.F0} vs pinned "
          f"inverse-variance (cap {pin.F_CAP:.4f}, eps "
          f"{pin.DIVERGENCE_EPS:.4f})\n")
    m = load_cohort(tape, epoch)
    if len(m) == 0:
        print("entries in cohort             : 0")
        print("VERDICT: NO DATA — no decisions after the cohort epoch. "
              "The gate reads the moment forward games exist.")
        return 0
    m["p_ride"] = pin.predict(m)
    m["order_key"] = m.decided_ts
    print(report(score_frame(m)))
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    return 0


# ---------------------------------------------------------------------------
# Mutations (the registration's rule: prove the pipeline can both find the
# effect and fire the tripwire, before anything real is read).
# ---------------------------------------------------------------------------

def _mutation_tape(rng, *, mean_driven: bool) -> pd.DataFrame:
    """Mutation A: returns drawn from the pin's own two-point tail model at
    each entry's p (mean EXACTLY zero, fat left tail at high p) — the
    variance arm's edge is pure volatility drag, ~½·F0·σ per divergent
    entry, so detecting it needs the large N below (t ∝ sqrt(N)·F0·σ).
    Mutation B: high-p entries carry a worse MEAN instead — the gain
    becomes selection and the tripwire must fire."""
    games, n_hi, n_lo = 60, 80, 80
    p_hi, p_lo = 0.45, 0.02
    win_hi = p_hi * pin.L_RIDE / (1 - p_hi)
    # exactly-balanced within-game composition (36 losses / 44 wins at
    # p=0.45): per-game mean is zero BY CONSTRUCTION, so the paired diff
    # isolates the volatility-drag channel instead of drowning it in
    # selection noise — the effect under test is variance, and this makes
    # the null (mean) exactly true rather than true-in-expectation
    hi_rets = np.array([-pin.L_RIDE] * int(n_hi * p_hi)
                       + [win_hi] * (n_hi - int(n_hi * p_hi)))
    rows = []
    for gi in range(games):
        rets_hi = rng.permutation(hi_rets)
        for ei in range(n_hi + n_lo):
            hi = ei % 2 == 1
            if mean_driven:
                r = (rng.normal(-0.10, 0.05) if hi
                     else 0.02 + (0.05 if rng.random() < 0.5 else -0.05))
            else:
                r = (rets_hi[ei // 2] if hi
                     else (0.05 if rng.random() < 0.5 else -0.05))
            rows.append({"event_slug": f"g{gi}", "order_key": ei,
                         "ret": r, "p_ride": p_hi if hi else p_lo})
    return pd.DataFrame(rows)


def selftest() -> int:
    rng = np.random.default_rng(20260902)
    ok = True

    s = score_frame(_mutation_tape(rng, mean_driven=False))
    r = report(s)
    win = s["primary"].lo > 0
    fired = "rebuilt a filter" in r
    print(f"mutation A (fat tail, zero mean diff): arm wins primary "
          f"{s['primary'].mean:+.5f} [{s['primary'].lo:+.5f}, "
          f"{s['primary'].hi:+.5f}] -> {'OK' if win else 'FAIL'}; "
          f"tripwire fired: {fired} -> {'FAIL' if fired else 'OK'}")
    ok &= win and not fired

    s = score_frame(_mutation_tape(rng, mean_driven=True))
    r = report(s)
    fired = "rebuilt a filter" in r
    print(f"mutation B (mean-driven gain): tripwire fired: {fired} "
          f"-> {'OK (the check can fire)' if fired else 'FAIL'}")
    ok &= fired
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape", type=Path, default=None)
    ap.add_argument("--exports", type=Path,
                    default=REPO / "backups/exports")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    tape = args.tape or (args.exports / DEFAULT_TAPE)
    return run(tape, args.exports)


if __name__ == "__main__":
    raise SystemExit(main())
