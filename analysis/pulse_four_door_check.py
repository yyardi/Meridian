"""The four-door check on PULSE's entry rule, and its settlement re-score.

QUOTE's fill rule could only book the losing half of its distribution. This
asks the same question of PULSE's entry rule, on the 34 games recorded before
the engine went dark (last decision 2026-08-31T02:31Z, WNBA season over).

FINDINGS, in the order the doors were opened.

★ POPULATION — 97% of the recorded tape is intent that live would have refused.
`core/pulse/live.py:1188-1194` and `:1268-1275`: in LIVE mode the per-event
count cap (`DEFAULT_MAX_OPEN_PER_EVENT = 3`) blocks an entry outright before
sizing. In SHADOW mode the entry is still WRITTEN, at full desired size, with
`binding_label = "max_open_per_event"` and `capped_stake/contracts = 0`. That
is a deliberate, documented choice (operator follow-up 2026-08-22) and the
columns are honestly labelled — the hazard is which column downstream reads.

    recorded entries                    2,974
      capped_contracts == 0             2,947   99.1%   live would NOT have entered
      live-faithful                        27

    settled filled entries              1,944   <- the population every PULSE number uses
      capped_stake_usd == 0             1,884
      capped_stake_usd NULL                40   pre-2026-08-22 regime: refusals were
                                                not written, so a recorded entry IS real
      capped_stake_usd  > 0                20
      => live-faithful                     60   3.1%

★ AND THE TWO POPULATIONS HAVE OPPOSITE SIGNS, exactly as QUOTE's did:

    population          n      games   per-contract settlement P&L (game-clustered)
    full-intent-only  1,884      28    +5.16c [ -1.29, +11.62]
    live-faithful        60      13    -7.83c [-20.63,  +4.96]
    ALL as recorded   1,944      34    +4.76c [ -1.46, +10.98]

The headline aggregate is the counterfactual half wearing the whole tape's
name. Both intervals span zero, so nothing here is established either way —
but a +4.76c that is 97% composed of trades live would have refused should
never have travelled as PULSE's number.

★ DECISION RULE — the estimator never sizes anything. Every one of the 2,974
entries carries a binding constraint; `kelly`, the estimator's own sizing,
binds on 45 (1.5%). A position counter decides 92.8%.

★ POPULATION, second door — the estimator's output is recorded ONLY when it
acted. `edge_net` is NULL on all 13,680 holds and all 2,679 exits. So the
entry threshold's discriminating power CANNOT be evaluated from this table:
there is no record of the edges we saw and declined. Entries span
edge_net [+0.0300, +0.9596] against `min_edge_threshold = 0.03`
(strategies/wnba_totals/config.py:143), so the floor binds exactly — and how
often it was reached and refused is unrecorded.

★ COMPOSITION — the live-faithful subset is a different strategy mix from the
tape. Live-faithful: 54 spread / 4 winner / 2 total. The decision tape overall:
10,613 total / 7,435 spread / 1,285 winner. So the 3% that would really have
traded is 90% spread, while the tape is majority total.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from core.quote.adverse_selection import clustered_mean  # noqa: E402


def _exports_dir():
    for base in [REPO, *Path(__file__).resolve().parents]:
        if (base / "backups/exports").is_dir():
            return base / "backups/exports"
    raise FileNotFoundError("backups/exports not found — run from the main "
                            "checkout, where the pinned exports live.")


DECISIONS = "pulse_decisions_full_20260901T195202Z.csv"


def live_faithful(capped_stake: pd.Series) -> pd.Series:
    """NULL or >0 is live-faithful; ==0 is intent live would have refused.

    NULL means the pre-2026-08-22 regime, where a capped-out tick was simply
    not written — so a recorded entry with NULL capping WAS a real entry.
    Folding NULL in with zero would discard the only genuine early data.
    """
    return capped_stake.isna() | (capped_stake > 0)


def _selftest() -> int:
    fails = 0

    def check(name, ok):
        nonlocal fails
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        fails += 0 if ok else 1

    s = pd.Series([np.nan, 0.0, 1.5, 0.0])
    lf = live_faithful(s)
    check("NULL counts as live-faithful (old regime wrote only real entries)",
          bool(lf.iloc[0]))
    check("zero is NOT live-faithful", not bool(lf.iloc[1]))
    check("positive is live-faithful", bool(lf.iloc[2]))

    # THE CONFUSION THIS EXISTS TO PREVENT: an aggregate dominated by the
    # refused population can carry the opposite sign to the real one.
    df = pd.DataFrame({"game_id": ["g1"] * 3 + ["g2"] * 3,
                       "capped_stake_usd": [0.0, 0.0, 1.0] * 2,
                       "pnl": [0.10, 0.10, -0.05] * 2})   # aggregate +0.05
    allm = df.pnl.mean()
    real = df[live_faithful(df.capped_stake_usd)].pnl.mean()
    check(f"aggregate ({allm:+.3f}) and live-faithful ({real:+.3f}) can differ "
          "in SIGN", allm > 0 > real)
    return fails


def main() -> None:
    d = pd.read_csv(_exports_dir() / DECISIONS,
                    parse_dates=["decided_at", "filled_at"], low_memory=False)
    print(f"decisions {len(d):,}  games {d.game_id.nunique()}  "
          f"last {d.decided_at.max()}")
    print(f"  actions: {d.action.value_counts().to_dict()}")

    e = d[d.action == "enter"]
    print(f"\n=== DECISION RULE: what actually sizes an entry ===")
    vc = e.binding_constraint.value_counts(dropna=False)
    for k, v in vc.items():
        print(f"  {str(k):26s} {v:>6,}  {v/len(e):>6.1%}")
    print(f"  entries with NO binding constraint: "
          f"{int(e.binding_constraint.isna().sum())}")

    print(f"\n=== POPULATION: what live would have done ===")
    z = e.capped_contracts.fillna(0) == 0
    print(f"  recorded entries {len(e):,}; capped_contracts==0 on {int(z.sum()):,}"
          f" ({z.mean():.1%}) — live would not have entered")

    f = d[(d.action == "enter") & d.filled_at.notna() & d.settlement.notna()].copy()
    f["pnl"] = np.where(f.side.str.upper().str.startswith("Y"),
                        f.settlement - f.limit_price,
                        f.limit_price - f.settlement)
    f["pop"] = np.where(live_faithful(f.capped_stake_usd),
                        "live-faithful", "full-intent-only")
    print(f"\n=== SETTLEMENT RE-SCORE (game-clustered) ===")
    print(f"{'population':18s} {'n':>6s} {'games':>6s} {'per-contract P&L':>30s}")
    for p, g in list(f.groupby("pop")) + [("ALL (as recorded)", f)]:
        cm = clustered_mean({k: list(v) for k, v in g.groupby("game_id").pnl})
        ci = f"{cm.mean*100:+.2f}c [{cm.lo*100:+.2f}, {cm.hi*100:+.2f}]"
        print(f"{p:18s} {len(g):>6,} {g.game_id.nunique():>6d} {ci:>30s}")

    print(f"\n=== THE OTHER POPULATION DOOR: declined decisions are unrecorded ===")
    for act in ("enter", "hold", "exit"):
        g = d[d.action == act]
        print(f"  {act:6s} n={len(g):>6,}  edge_net NULL on "
              f"{int(g.edge_net.isna().sum()):>6,} ({g.edge_net.isna().mean():.0%})")
    print("  -> the entry threshold's discriminating power is not evaluable:")
    print("     there is no record of the edges seen and declined.")

    lf = f[f["pop"] == "live-faithful"]
    print(f"\n=== COMPOSITION ===")
    print(f"  live-faithful strategy mix: {lf.strategy.value_counts().to_dict()}")
    print(f"  whole decision tape:        {d.strategy.value_counts().to_dict()}")

    print("\nNo in-sample result justifies capital. The forward test is the")
    print("evidence.")


if __name__ == "__main__":
    if _selftest():
        sys.exit("selftest failed")
    main()
