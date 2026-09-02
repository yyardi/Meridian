"""Forward scorer for the crossing-arms registrations. Built AGAINST the
landed texts (read from main per wave rule 11, never a relay):

  parent    docs/math/intent-crossing-arms.md      (arms a, b; gate on b)
  companion docs/math/crossing-arms-state-mask.md  (arm b''; paired b''-b)

    .venv/bin/python analysis/crossing_arms_scorer.py [--selftest]
        [--decisions CSV] [--resolved CSV] [--renet LEGS.csv]
        [--skip-cutoff-verify]

NOTHING HERE IS A RESULT until floors are met; until then every run prints
composition and "accruing", never verdict language. Verbatim, always:
**No in-sample result justifies capital. The forward test is the evidence.**

Cohort cutoffs — pinned as EPOCH INTEGERS (findings' %cI trap: ISO strings
carry offsets that get misread; epochs do not). Verified at runtime against:

  TZ=UTC git log --format=%ct --follow origin/main -- docs/math/intent-crossing-arms.md | tail -1
  TZ=UTC git log --format=%ct --follow origin/main -- docs/math/crossing-arms-state-mask.md | tail -1

A mismatch ABORTS the run (a scorer reading the wrong cohort is worse than no
scorer); git being unavailable warns and continues on the pinned values.

The arms (registration text is authoritative; this file implements it):

  (a) CROSS-ALWAYS — every forward entry intent scored as a unit-size taker
      fill at the intent-time FAR touch. Context arm: NEVER gates.
  (b) CROSS-SELECTIVE — same scoring; eligible only where the intent row's
      own decision-time fields show fair_value clearing the far touch plus
      the taker fee. THE ELIGIBILITY FORMULA IS PINNED HERE, per the
      registration's "pinned in the harness before the first read":

          yes intent:  fair_value - market_ask         > 0.06*ask*(1-ask)
          no  intent:  market_bid - fair_value         > 0.06*bid*(1-bid)

      Strict inequality. Rows with NULL fair_value or NULL far touch are
      INELIGIBLE and counted. No other condition; no post-hoc slicing.
  (b'') COMPANION — (b) eligibility AND NOT in the masked region
      (Q4-or-later OR |margin| >= 10, state at decision time). PINNED here:
      "Q4" includes overtime (period not in Q1/Q2/Q3 — a lateness mask that
      excluded OT would be perverse); a row with NULL period AND NULL margin
      cannot be shown to be in the region and stays eligible, counted.

Score, per contract, YES frame, unit size (registration: "unit size"):

      yes: (S - ask) - 0.06*ask*(1-ask)        cost = ask
      no : (bid - S) - 0.06*bid*(1-bid)        cost = 1 - bid

S is settlement from the resolved-outcomes export ONLY (registration:
"settlement from resolved outcomes"). Unresolved markets are PENDING —
counted, never scored, never dropped silently. Per-$ = score / cost.
Clustering is by game via the blessed clustered_mean (C4).

Linking policy — the sign-flipping sensitivity (+1.2c/$ re-linked vs
-10.0c/$ dropped on the live-faithful subset, #147/#158):
THE ARM SCORES ARE LINKING-FREE BY CONSTRUCTION (unit-size intents scored to
settlement; no exit, no lineage anywhere in the formula). Lineage enters only
the incumbent-context block, and there this scorer refuses the choice: it
computes and prints BOTH policies side by side, labelled, every run —
  drop:     filled exits with NULL entry_id are dropped (live_report rule)
  repaired: A's stated reconstruction — orphans in fill-time order each
            close the LATEST still-open earlier-filled entry in the SAME
            market (lineage_source='reconstructed')
NOTICE, flagged for the research agent and unresolved by this file: the
parent registration's prose pins "D's ... orphan-join rule from #126" (the
drop side) while the companion pins "the lineage_source-REPAIRED rule" (the
re-linked side). Since no gated number here depends on linking, this scorer
prints both and adjudicates neither; the discrepancy needs c7's written
resolution before any linked context number is quoted in a verdict.

Re-netting hook (mandatory clause, docs/math/dynamic-exit-repricing.md):
``renet_premium_table(legs, label)`` recomputes the breakeven/premium table
under ANY exit policy from a legs frame scored under that policy — the
committed interface the clause requires. See its docstring for the input
contract; ``--renet PATH`` runs it from a CSV.

Fill-realism caveats carried (they are this file's author's own): the arms
assume a taker fill AT the recorded far touch for the full unit — top-of-book
depth is not in the tape, so thin-touch slippage is unmodelled and the arm
scores are OPTIMISTIC for size > touch depth. The confounds section of the
parent registration rides with any late cell.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "exit_option_value", Path(__file__).with_name("exit_option_value.py"))
eov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eov)
ped = eov.ped                       # pulse_execution_decomposition, transitively

# ---- pinned cutoffs (epoch seconds; see module docstring for the commands) --
PARENT_CUTOFF_EPOCH = 1788302576        # 2026-09-01T22:42:56Z
COMPANION_CUTOFF_EPOCH = 1788324836     # 2026-09-02T04:53:56Z
CUTOFF_DOCS = {
    "docs/math/intent-crossing-arms.md": PARENT_CUTOFF_EPOCH,
    "docs/math/crossing-arms-state-mask.md": COMPANION_CUTOFF_EPOCH,
}

# ---- registration floors, quoted -------------------------------------------
PARENT_FLOOR_GAMES = 15        # games containing >=1 arm-(b)-eligible intent
PARENT_FLOOR_INTENTS = 200     # arm-(b) intents
COMPANION_FLOOR_DIFF_GAMES = 10   # games where (b) and (b'') differ
COMPANION_FLOOR_B_INTENTS = 100   # parent-arm-(b) intents within those games

THETA = 0.06
LINKING_SENSITIVITY = ("linking sensitivity (#147/#158, live-faithful "
                       "subset): +1.2c/$ re-linked vs -10.0c/$ dropped — "
                       "the sign flips on the join rule")


def fee(p: float) -> float:
    return THETA * p * (1.0 - p)


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


# --------------------------------------------------------------------------- #
# Cutoff verification
# --------------------------------------------------------------------------- #

def verify_cutoffs() -> bool:
    """Compare pinned epochs against git's own %ct for each doc. Mismatch is
    fatal (wrong cohort); git unavailable is a loud warning, not fatal."""
    ok = True
    for doc, pinned in CUTOFF_DOCS.items():
        try:
            out = subprocess.run(
                ["git", "log", "--format=%ct", "--follow", "origin/main",
                 "--", doc],
                capture_output=True, text=True, cwd=REPO, timeout=30,
                env={"TZ": "UTC", "PATH": "/usr/bin:/bin:/usr/local/bin"},
            )
            lines = [l for l in out.stdout.strip().splitlines() if l]
            if out.returncode != 0 or not lines:
                print(f"WARNING: could not read cutoff for {doc} from git "
                      f"— proceeding on the pinned epoch {pinned}")
                continue
            got = int(lines[-1])
            if got != pinned:
                print(f"FATAL: cutoff mismatch for {doc}: git says {got}, "
                      f"pinned {pinned}. A scorer on the wrong cohort is "
                      f"worse than no scorer — fix the pin or the checkout.")
                ok = False
        except Exception as exc:
            print(f"WARNING: cutoff verification unavailable ({exc}); "
                  f"proceeding on pinned epochs")
    return ok


# --------------------------------------------------------------------------- #
# Pinned formulas
# --------------------------------------------------------------------------- #

def far_touch(row) -> float | None:
    t = row.market_ask if row.side == "yes" else row.market_bid
    return None if pd.isna(t) else float(t)


def cost_ct(row) -> float | None:
    t = far_touch(row)
    if t is None:
        return None
    return t if row.side == "yes" else 1.0 - t


def score_ct(row, settlement: float) -> float | None:
    """Pinned score: s*(S - touch) - fee(touch), per contract, unit size."""
    t = far_touch(row)
    if t is None:
        return None
    if row.side == "yes":
        return (settlement - t) - fee(t)
    return (t - settlement) - fee(t)


def eligible_b(row) -> bool:
    """Pinned arm-(b) eligibility. NULL fair_value or NULL touch: ineligible."""
    t = far_touch(row)
    if t is None or pd.isna(row.fair_value):
        return False
    fv = float(row.fair_value)
    if row.side == "yes":
        return fv - t > fee(t)
    return t - fv > fee(t)


def in_masked_region(row) -> bool:
    """Pinned companion mask region: Q4-or-later OR |margin| >= 10, state at
    decision. NULL state cannot prove membership -> not in region (counted by
    the caller)."""
    late = (not pd.isna(row.period)) and row.period not in ("Q1", "Q2", "Q3")
    big = (not pd.isna(row.margin)) and abs(float(row.margin)) >= 10.0
    return late or big


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def build_scored(dec: pd.DataFrame, resolved: pd.DataFrame,
                 cutoff_epoch: int) -> tuple[pd.DataFrame, dict]:
    """All forward entry intents with scores and eligibility flags."""
    ent = dec[dec.action == "enter"].copy()
    epoch = ent.decided_at.map(pd.Timestamp.timestamp)
    fwd = ent[epoch > cutoff_epoch].copy()          # strictly after landing
    settle = resolved.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug").settlement
    fwd["S"] = fwd.market_slug.map(settle)

    rows = []
    counts = dict(intents=len(fwd), games=fwd.event_slug.nunique(),
                  no_touch=0, pending=0, null_state=0)
    for r in fwd.itertuples():
        t = far_touch(r)
        if t is None:
            counts["no_touch"] += 1
            continue
        if pd.isna(r.S):
            counts["pending"] += 1
            continue
        if pd.isna(r.period) and pd.isna(r.margin):
            counts["null_state"] += 1
        elig = eligible_b(r)
        rows.append(dict(
            id=r.id, event_slug=r.event_slug, decided_at=r.decided_at,
            side=r.side, cost=cost_ct(r), score=score_ct(r, float(r.S)),
            eligible_b=elig,
            eligible_bpp=elig and not in_masked_region(r),
        ))
    scored = pd.DataFrame(rows)
    return scored, counts


def arm_report(scored: pd.DataFrame, mask, label: str, gates: bool) -> None:
    sub = scored[mask] if len(scored) else scored
    if len(sub) == 0:
        print(f"  {label}: 0 intents — accruing")
        return
    per_d = sub.score / sub.cost
    vals = {g: list(v) for g, v in per_d.groupby(sub.event_slug)}
    cm = clustered_mean(vals)
    mw = sub.score.sum() / sub.cost.sum()
    line = (f"  {label}: {len(sub)} intents / {sub.event_slug.nunique()} "
            f"games; money-weighted {mw * 100:+.2f}c/$")
    if cm is not None:
        line += (f"; clustered {cm.mean * 100:+.2f} "
                 f"[{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}] c/$")
    print(line)
    if not gates:
        print("    (context arm — never gates, per the registration)")


def parent_gate(scored: pd.DataFrame) -> None:
    elig = scored[scored.eligible_b] if len(scored) else scored
    n_games = elig.event_slug.nunique() if len(elig) else 0
    n = len(elig)
    print(f"\nparent floors: {n_games}/{PARENT_FLOOR_GAMES} games with a "
          f"(b)-eligible intent; {n}/{PARENT_FLOOR_INTENTS} (b) intents")
    if n_games < PARENT_FLOOR_GAMES or n < PARENT_FLOOR_INTENTS:
        print("parent gate: FLOORS UNMET — accruing; no verdict language "
              "attaches to any number above")
        return
    per_d = elig.score / elig.cost
    cm = clustered_mean({g: list(v)
                         for g, v in per_d.groupby(elig.event_slug)})
    verdict = ("PASS" if cm.lo > 0 else "FAIL" if cm.hi < 0 else "straddling")
    print(f"parent gate at floor: CI [{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}]"
          f" -> {verdict}")
    if (verdict == "straddling"
            and n_games >= 2 * PARENT_FLOOR_GAMES
            and n >= 2 * PARENT_FLOOR_INTENTS):
        print("closure clause: 2x floors reached with CI straddling zero -> "
              "FAIL-BY-EXHAUSTION; the gate CLOSES, it does not ride")


def companion_gate(scored: pd.DataFrame) -> None:
    if len(scored) == 0:
        print("  companion: 0 intents — accruing")
        return
    b = scored[scored.eligible_b]
    diffs = []
    n_b_in_diff = 0
    for g, sub in b.groupby("event_slug"):
        bpp = sub[sub.eligible_bpp]
        if len(bpp) == len(sub):
            print(f"  {g}: arms do not differ — game uninformative")
            continue
        if len(bpp) == 0:
            # the mask removed every eligible intent: the b'' side of this
            # game is empty; per-$ of an empty book is 0 by money-at-price
            d = 0.0 - sub.score.sum() / sub.cost.sum()
        else:
            d = (bpp.score.sum() / bpp.cost.sum()
                 - sub.score.sum() / sub.cost.sum())
        diffs.append((g, d))
        n_b_in_diff += len(sub)
    print(f"\ncompanion floors: {len(diffs)}/{COMPANION_FLOOR_DIFF_GAMES} "
          f"differing games; {n_b_in_diff}/{COMPANION_FLOOR_B_INTENTS} "
          f"parent-(b) intents within them")
    if (len(diffs) < COMPANION_FLOOR_DIFF_GAMES
            or n_b_in_diff < COMPANION_FLOOR_B_INTENTS):
        print("companion gate: FLOORS UNMET — accruing")
        return
    cm = clustered_mean({g: [d] for g, d in diffs})
    verdict = ("PASS" if cm.lo > 0 else "FAIL" if cm.hi < 0 else "straddling")
    print(f"companion gate at floor: paired (b''-b) CI "
          f"[{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}] c/$ -> {verdict}")
    if (verdict == "straddling"
            and len(diffs) >= 2 * COMPANION_FLOOR_DIFF_GAMES
            and n_b_in_diff >= 2 * COMPANION_FLOOR_B_INTENTS):
        print("closure clause: 2x floors, still straddling -> "
              "FAIL-BY-EXHAUSTION; the mask is not adopted, the gate closes")


# --------------------------------------------------------------------------- #
# Incumbent context — BOTH linking policies, every run
# --------------------------------------------------------------------------- #

def relink_repaired(dec: pd.DataFrame) -> pd.DataFrame:
    """A's stated reconstruction rule, reimplemented exactly: filled orphan
    exits in fill-time order each close the LATEST still-open earlier-filled
    entry in the SAME market. Returns dec with orphan entry_id filled in."""
    d = dec.copy()
    exits = d[(d.action == "exit") & d.filled_at.notna()]
    linked = set(exits.entry_id.dropna().astype("int64"))
    fe = d[(d.action == "enter") & d.filled_at.notna()]
    for o in exits[exits.entry_id.isna()].sort_values("filled_at").itertuples():
        cand = fe[(fe.market_slug == o.market_slug)
                  & (fe.filled_at < o.filled_at)
                  & (~fe.id.isin(linked))]
        if len(cand):
            eid = int(cand.sort_values("filled_at").iloc[-1].id)
            d.loc[d.id == o.id, "entry_id"] = eid
            linked.add(eid)
    return d


def incumbent_context(dec: pd.DataFrame, cutoff_epoch: int) -> None:
    hr("INCUMBENT CONTEXT — the resting book on the same forward cohort, "
       "BOTH linking policies (this block never gates)")
    print(LINKING_SENSITIVITY)
    print("NOTICE for c7: parent prose pins the drop rule, companion prose "
          "pins the repaired rule — unresolved; both printed, neither "
          "chosen. Arm scores above are linking-free by construction.")
    epoch = dec.decided_at.map(pd.Timestamp.timestamp)
    fwd = dec[(epoch > cutoff_epoch) | (dec.action != "enter")]
    for label, frame in (("drop (live_report rule)", dec),
                         ("repaired (A's reconstruction)",
                          relink_repaired(dec))):
        legs, _ = ped.build_legs(frame)
        lepoch = legs.decided_at.map(pd.Timestamp.timestamp)
        legs = legs[lepoch > cutoff_epoch]
        if len(legs) == 0:
            print(f"  {label}: 0 forward filled entries — accruing")
            continue
        stake = (legs.cost_ct * legs.contracts).sum()
        print(f"  {label}: {len(legs)} filled entries "
              f"({int((legs.kind == 'ride').sum())} rides), "
              f"{legs.pnl_ct_usd.sum() / stake * 100:+.2f}c/$")


# --------------------------------------------------------------------------- #
# Re-netting hook — the committed interface (dynamic-exit-repricing.md clause)
# --------------------------------------------------------------------------- #

def renet_premium_table(legs: pd.DataFrame, label: str) -> pd.DataFrame:
    """Recompute the breakeven/premium table under a NEW exit policy.

    Input contract (pinned): one row per filled entry SCORED UNDER THE POLICY
    BEING NETTED, columns: kind ('trip'|'ride'), pnl_ct, cost_ct, contracts,
    event_slug. The caller is responsible for the scoring policy; this
    function only does the netting arithmetic (eov.breakeven_p /
    eov.premium_per_ct — the same pinned formulas as exit_option_value.py).

    Returns a frame [p, delta_star_ct] over the p grid, and prints r_trip,
    r_ride, p_obs, p* with the label. Per the mandatory clause, no
    incumbent-era netting may be cited for a changed exit policy — call this
    with the new policy's legs instead.
    """
    trips = legs[legs.kind == "trip"]
    rides = legs[legs.kind == "ride"]
    stake_t = (trips.cost_ct * trips.contracts).sum()
    stake_r = (rides.cost_ct * rides.contracts).sum()
    r_t = float((trips.pnl_ct * trips.contracts).sum() / stake_t) if stake_t else 0.0
    r_r = float((rides.pnl_ct * rides.contracts).sum() / stake_r) if stake_r else 0.0
    p_obs = len(rides) / len(legs) if len(legs) else 0.0
    mean_cost = float((legs.cost_ct * legs.contracts).sum()
                      / legs.contracts.sum()) if len(legs) else 0.0
    print(f"re-netted under '{label}': r_trip {r_t * 100:+.2f}c/$, r_ride "
          f"{r_r * 100:+.2f}c/$, p_obs {p_obs:.1%}, "
          f"p* {eov.breakeven_p(r_t, r_r):.1%}")
    grid = sorted({p_obs, 0.02, 0.05, 0.10, 0.20, 0.30})
    out = pd.DataFrame([
        dict(p=p, delta_star_ct=eov.premium_per_ct(p, r_t, r_r, mean_cost))
        for p in grid])
    print(out.assign(delta_star_ct=lambda d: (d.delta_star_ct * 100).round(2))
          .to_string(index=False))
    return out


# --------------------------------------------------------------------------- #
# Mutation tests
# --------------------------------------------------------------------------- #

def _intent(id, game, side, bid, ask, fv, S, period="Q2", margin=0,
            when="2026-10-01 00:00:00+00:00"):
    return dict(id=id, event_slug=game, market_slug=f"m{id}", action="enter",
                side=side, market_bid=bid, market_ask=ask, fair_value=fv,
                period=period, margin=margin,
                decided_at=pd.Timestamp(when), S=S)


def selftest() -> int:
    print("mutation test: the scorer must not manufacture edge")
    failures = 0

    def check(name, got, want, tol=1e-12):
        nonlocal failures
        ok = abs(got - want) < tol
        print(f"  {name}: {got:+.6f} (want {want:+.6f}) -> "
              f"{'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    def score_rows(rows):
        df = pd.DataFrame(rows)
        return [score_ct(r, r.S) for r in df.itertuples()]

    # Balanced null: side x settlement fully crossed at touch 0.50 — the only
    # systematic term left is the taker fee.
    null_rows = [
        _intent(1, "g1", "yes", 0.48, 0.50, None, 1),
        _intent(2, "g1", "yes", 0.48, 0.50, None, 0),
        _intent(3, "g2", "no", 0.50, 0.52, None, 1),
        _intent(4, "g2", "no", 0.50, 0.52, None, 0),
    ]
    s = score_rows(null_rows)
    check("balanced null mean (= -fee)", sum(s) / 4, -fee(0.50))

    # Injected edge: touches moved 5c favourable -> mean = +0.05 - fee(0.45).
    edge_rows = [
        _intent(1, "g1", "yes", 0.43, 0.45, None, 1),
        _intent(2, "g1", "yes", 0.43, 0.45, None, 0),
    ]
    s = score_rows(edge_rows)
    check("injected +5c edge recovered",
          sum(s) / 2 - (-fee(0.45)), 0.05)

    # The shuffled-settlement read. The raw mean of s*(S - touch) is
    # PERMUTATION-INVARIANT in S by linearity (sum S and sum touch are both
    # unchanged), so the shuffle can only bite through arm (b)'s eligibility
    # selection: on a tape where fair_value predicts S, (b) picks winners;
    # shuffling S must destroy (b)'s edge while leaving (a) exactly fixed.
    sel_rows = [
        _intent(1, "g1", "yes", 0.48, 0.50, 0.60, 1),   # eligible, wins
        _intent(2, "g1", "yes", 0.48, 0.50, 0.40, 0),   # ineligible, loses
        _intent(3, "g2", "yes", 0.48, 0.50, 0.60, 1),
        _intent(4, "g2", "yes", 0.48, 0.50, 0.40, 0),
    ]
    df = pd.DataFrame(sel_rows)
    elig = [eligible_b(r) for r in df.itertuples()]
    s_all = score_rows(sel_rows)
    b_mean = sum(x for x, e in zip(s_all, elig) if e) / 2
    check("arm (b) aligned (+50c per pick)", b_mean, 0.50 - fee(0.50))
    rot = [dict(r, S=1 - r["S"]) for r in sel_rows]     # shuffle settlements
    s_rot = score_rows(rot)
    b_rot = sum(x for x, e in zip(s_rot, elig) if e) / 2
    check("arm (b) shuffled (edge destroyed)", b_rot, -0.50 - fee(0.50))
    check("arm (a) invariant under shuffle (reads -fee)",
          sum(s_rot) / 4, -fee(0.50))

    # Eligibility pin: fv must clear touch + fee strictly.
    r = pd.DataFrame([_intent(1, "g", "yes", 0.43, 0.45, 0.45 + fee(0.45),
                              1)]).itertuples().__next__()
    ok = not eligible_b(r)
    r2 = pd.DataFrame([_intent(1, "g", "yes", 0.43, 0.45,
                               0.45 + fee(0.45) + 1e-6, 1)]
                      ).itertuples().__next__()
    ok = ok and eligible_b(r2)
    print(f"  eligibility strict at touch+fee boundary -> "
          f"{'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    # Companion: a game where b == b'' must print "arms do not differ", and
    # a differing game must be counted — never a degenerate zero.
    dec = pd.DataFrame([
        _intent(1, "gsame", "yes", 0.30, 0.32, 0.40, 1, period="Q1"),
        _intent(2, "gdiff", "yes", 0.30, 0.32, 0.40, 1, period="Q4"),
        _intent(3, "gdiff", "yes", 0.30, 0.32, 0.40, 1, period="Q1"),
    ])
    scored = pd.DataFrame([dict(
        id=r.id, event_slug=r.event_slug, side=r.side, cost=cost_ct(r),
        score=score_ct(r, r.S), eligible_b=eligible_b(r),
        eligible_bpp=eligible_b(r) and not in_masked_region(r))
        for r in dec.itertuples()])
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        companion_gate(scored)
    out = buf.getvalue()
    ok = ("arms do not differ — game uninformative" in out
          and "1/10 differing games" in out)
    print(f"  companion differ/no-differ handling -> {'ok' if ok else 'FAIL'}")
    if not ok:
        print(out)
    failures += 0 if ok else 1

    # Empty forward cohort: everything predates the cutoff -> accruing lines.
    old = pd.DataFrame([_intent(1, "g", "yes", 0.4, 0.5, 0.9, 1,
                                when="2026-08-01 00:00:00+00:00")])
    old["filled_at"] = pd.NaT
    scored0, counts = build_scored(
        old, pd.DataFrame({"market_slug": ["m1"], "settlement": [1]}),
        PARENT_CUTOFF_EPOCH)
    ok = len(scored0) == 0 and counts["intents"] == 0
    print(f"  pre-cutoff tape -> empty cohort -> {'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    # Re-netting interface on synthetic legs with a known answer:
    # r_t=+0.06, r_r=-0.54, cost 0.50 -> delta*(10%) = 3c.
    legs = pd.DataFrame([
        dict(kind="trip", pnl_ct=0.03, cost_ct=0.50, contracts=10.0,
             event_slug="g1"),
        dict(kind="ride", pnl_ct=-0.27, cost_ct=0.50, contracts=10.0,
             event_slug="g2"),
    ])
    tab = renet_premium_table(legs, "selftest policy")
    got = float(tab.loc[(tab.p - 0.10).abs() < 1e-9, "delta_star_ct"].iloc[0])
    check("renet delta*(10%) on known legs", got, 0.03)

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=Path, default=ped.DEFAULT_DECISIONS)
    ap.add_argument("--resolved", type=Path, default=ped.DEFAULT_RESOLVED)
    ap.add_argument("--renet", type=Path, default=None,
                    help="legs CSV (kind,pnl_ct,cost_ct,contracts,event_slug)"
                         " scored under a NEW exit policy; prints the "
                         "re-netted premium table and exits")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--skip-cutoff-verify", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.renet is not None:
        renet_premium_table(pd.read_csv(args.renet), str(args.renet))
        return 0

    print("Crossing-arms forward scorer")
    print(f"decisions: {args.decisions.name}; resolved: {args.resolved.name}")
    print("reproduce: .venv/bin/python analysis/crossing_arms_scorer.py")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1
    if not args.skip_cutoff_verify and not verify_cutoffs():
        return 1

    dec = pd.read_csv(args.decisions, parse_dates=[
        "created_at", "decided_at", "filled_at", "withdrawn_at", "settled_at"])
    resolved = pd.read_csv(args.resolved)

    hr("PARENT — intent-crossing arms (cutoff 2026-09-01T22:42:56Z, epoch "
       f"{PARENT_CUTOFF_EPOCH})")
    scored, counts = build_scored(dec, resolved, PARENT_CUTOFF_EPOCH)
    print(f"forward cohort: {counts['intents']} intents / {counts['games']} "
          f"games; excluded: {counts['no_touch']} without a far touch, "
          f"{counts['pending']} unresolved (pending); "
          f"{counts['null_state']} with null state (kept, flagged)")
    if len(scored) == 0:
        print("cohort empty — the registrations accrue; nothing to score yet")
    else:
        arm_report(scored, scored.index >= 0, "arm (a) cross-always",
                   gates=False)
        arm_report(scored, scored.eligible_b, "arm (b) cross-selective",
                   gates=True)
        parent_gate(scored)

    hr("COMPANION — state mask (cutoff 2026-09-02T04:53:56Z, epoch "
       f"{COMPANION_CUTOFF_EPOCH})")
    scored_c, counts_c = build_scored(dec, resolved, COMPANION_CUTOFF_EPOCH)
    print(f"forward cohort: {counts_c['intents']} intents / "
          f"{counts_c['games']} games")
    if len(scored_c) == 0:
        print("cohort empty — accruing")
    else:
        arm_report(scored_c, scored_c.eligible_bpp, "arm (b'') masked",
                   gates=True)
        companion_gate(scored_c)

    incumbent_context(dec, PARENT_CUTOFF_EPOCH)

    hr("STANDING STATEMENTS")
    print("Unit size at the recorded far touch; top-of-book depth is not in "
          "the tape, so arm scores are optimistic for size beyond the touch. "
          "The parent registration's confounds (shorter late windows; "
          "spread-conditional eligibility) ride with every cell above.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
