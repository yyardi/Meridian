"""The PULSE round-trip ledger: one row per ENTRY intent, joined to its outcome.

Substrate for the 2026-09-01 edge-hunt wave (Wave Standard v1, this
directory). Reads the pinned exports ONLY — never a database:

    backups/exports/pulse_decisions_full_20260901T195202Z.csv
    backups/exports/resolved_outcomes_20260901T195202Z.csv

Reproduce:

    python3 analysis/roundtrip_ledger.py

which self-tests FIRST (synthetic null reads $0.00, synthetic injected tape
recovers every hand-computed cell — Wave Standard rule 4), then writes

    backups/exports/roundtrip_ledger_20260901T195202Z.csv
    analysis/roundtrip_ledger_report.md

THE P&L POLICY — one definition, labelled (Wave Standard rule 4)
----------------------------------------------------------------
**Round-trip, YES frame, maker fills at recorded limit prices, fees $0.**

* Prices are the YES frame everywhere (V14, `core/pulse/storage.py`): a
  ``side='no'`` position costs ``1 − limit_price`` and its exit rests in the
  same frame, so entry and exit prices subtract directly. ``side`` on THIS
  tape is the position's economic direction — written by the engine itself,
  the single writer — not the venue book mechanics that V28 warns about on
  activities rows. The V28 hazard does not arise here because no order and
  no venue row exists behind any decision (AST-pinned).
* Per contract: ``pnl = (close_yes_value − entry_yes_price) × (+1 if yes
  else −1)`` where ``close_yes_value`` is the filled exit's limit price
  (trip) or the 0/1 settlement (ride).
* Fees are $0 NOT by omission but by the venue's schedule: both legs rest as
  maker limits (never a cross — `core/pulse/live.py`), θ_maker = 0 (V9/C7,
  `core/backtest/fills.py`), and settlement is not a trade. The taker
  coefficient 0.06 is real (V9) and appears only in the labelled sensitivity
  column below — applying it to these fills would charge a fee the venue
  does not charge makers.
* Scope: positions are single-lot and non-overlapping (one per market at a
  time), so per-row round-trip P&L coincides with the venue's per-position
  average-cost ex-fee scope (V27). A literal to-the-cent reconciliation
  against the venue-pinned intent-rule ledger (`core/audit/wnba_trade_sheet
  .py`, 26/26) is IMPOSSIBLE for shadow rows — the venue has no record of
  them, by construction. What is matched is the policy (book from economic
  direction; label the accounting scope; fees explicit) and the instrument
  is mutation-tested instead.

Labelled sensitivity columns (arms, not the policy):

* ``pnl_*_taker``  — θ_taker = 0.06 charged on every FILLED leg,
  fee = 0.06·p·(1−p)·contracts at that leg's price (frame-symmetric).
  Settlement legs uncharged.
* ``pnl_*_pess``   — the measured in-game fill concession 4.70¢/contract
  (C13; all PULSE rows are in_play) charged on every FILLED leg: entries
  fill worse, exits fill worse. Settlement unchanged.

Outcome classification — explicit, never a default (trap 2):

* ``exit_fill``        entry filled, a linked exit row filled. Closed at the
                       exit's limit price.
* ``settlement``       entry filled, no exit fill, ``settlement`` stamped.
* ``still_open``       entry filled, no exit fill, no settlement. (Zero in
                       this export; the category exists so a future export
                       cannot silently misfile one.)
* ``withdrawn``        entry never filled, stood down (``withdrawn_at``).
* ``expired_unfilled`` entry never filled, never withdrawn — still resting
                       when the export was cut or the process died.

Lineage (trap: early-era orphan exits): 20 exit rows from 2026-08-18/19
predate the ``entry_id`` wiring. Filled orphans are re-linked by a stated
rule — in fill-time order, each orphan exit closes the LATEST still-open
filled entry in its market (the engine holds one position per market) —
and carry ``lineage_source='reconstructed'``; recorded links carry
``'recorded'``. Booking those 17 fills as rides would misprice real trips.

Cap semantics (trap 4): ``stake_usd``/``contracts`` are the model's FULL
desired size on every row; live-faithful size is ``capped_stake_usd`` where
non-null (0 = live would not have entered at all). Rows decided before the
2026-08-21 operator decision carry ``cap_semantics='enforced'`` — there the
caps actually shrank the recorded size and the desired size was never
written. ``live_stake_usd = coalesce(capped_stake_usd, stake_usd)`` is
correct in BOTH eras; full-intent sums are correct only in the annotate era.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PIN = "20260901T195202Z"
DECISIONS = ROOT / "backups" / "exports" / f"pulse_decisions_full_{PIN}.csv"
OUTCOMES = ROOT / "backups" / "exports" / f"resolved_outcomes_{PIN}.csv"
OUT_LEDGER = ROOT / "backups" / "exports" / f"roundtrip_ledger_{PIN}.csv"
OUT_REPORT = ROOT / "analysis" / "roundtrip_ledger_report.md"

THETA_TAKER = 0.06            # V9, venue-published, measured on 874,267 rows
CONCESSION_IN_GAME = 0.047    # C13, measured in-game maker-fill concession
EXPOSURE_CAPS = {"max_game_exposure_pct", "max_daily_exposure_pct",
                 "max_position_size_pct"}

DATE_COLS = ["decided_at", "filled_at", "withdrawn_at", "settled_at"]

#: Columns carried through from the entry decision row unchanged, so B/C/D
#: slice without re-joining the raw tape.
CARRY = ["event_slug", "market_slug", "game_id", "sports_market_type", "line",
         "strategy", "phase", "side", "estimates_version", "decided_at",
         "score", "margin", "period", "minutes_left",
         "minutes_left_is_estimate", "total_so_far", "projected_total",
         "total_sigma", "market_bid", "market_ask", "fair_value", "edge_net",
         "binding_constraint", "stake_usd", "contracts", "capped_stake_usd",
         "capped_contracts", "bankroll_usd"]


def _fee_taker(price: float, contracts: float) -> float:
    """0.06·p·(1−p) per contract (V9). Symmetric in p vs 1−p, so the YES
    frame price is usable for either side."""
    return THETA_TAKER * price * (1.0 - price) * contracts


def build_ledger(decisions: pd.DataFrame,
                 outcomes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per entry intent. Pure — no I/O, no interpretation."""
    d = decisions
    entries = d[d.action == "enter"].copy()
    exits = d[d.action == "exit"].copy()

    # ---- lineage: recorded links, then the stated reconstruction rule ---- #
    filled_exits = exits[exits.filled_at.notna()]
    recorded = filled_exits[filled_exits.entry_id.notna()]
    if recorded.entry_id.duplicated().any():
        raise AssertionError("an entry has two recorded filled exits")
    link = {int(r.entry_id): (r, "recorded") for r in recorded.itertuples()}

    orphans = filled_exits[filled_exits.entry_id.isna()].sort_values("filled_at")
    fe = entries[entries.filled_at.notna()]
    n_reconstructed = n_unlinked_orphans = 0
    closed: set[int] = set(link)
    for o in orphans.itertuples():
        cand = fe[(fe.market_slug == o.market_slug)
                  & (fe.filled_at < o.filled_at)
                  & (~fe.id.isin(closed))]
        if len(cand):
            eid = int(cand.sort_values("filled_at").iloc[-1].id)
            link[eid] = (o, "reconstructed")
            closed.add(eid)
            n_reconstructed += 1
        else:
            n_unlinked_orphans += 1

    osett = outcomes.drop_duplicates("market_slug").set_index("market_slug")[
        "settlement"]

    rows = []
    for e in entries.itertuples():
        r = {"entry_decision_id": e.id}
        for c in CARRY:
            r[c] = getattr(e, c)

        # cap semantics: annotate era writes capped_* (or 'kelly'); before
        # 2026-08-21 exposure caps silently bound the recorded size.
        if pd.notna(e.capped_stake_usd):
            r["cap_semantics"] = "annotate"
        elif e.binding_constraint in EXPOSURE_CAPS:
            r["cap_semantics"] = "enforced"
        else:
            r["cap_semantics"] = "agree"
        r["live_stake_usd"] = (e.capped_stake_usd
                               if pd.notna(e.capped_stake_usd) else e.stake_usd)
        r["live_contracts"] = (e.capped_contracts
                               if pd.notna(e.capped_contracts) else e.contracts)
        r["live_blocked"] = r["live_stake_usd"] == 0

        is_yes = e.side == "yes"
        entry_cost = e.limit_price if is_yes else 1.0 - e.limit_price
        r["entry_limit_price"] = e.limit_price
        r["entry_cost_per_contract"] = entry_cost
        r["entry_filled"] = pd.notna(e.filled_at)
        r["filled_at"] = e.filled_at
        r["mid_at_fill"] = e.mid_at_fill
        r["time_to_fill_s"] = ((e.filled_at - e.decided_at).total_seconds()
                               if pd.notna(e.filled_at) else np.nan)
        r["settlement"] = e.settlement
        r["settled_at"] = e.settled_at
        r["settlement_source"] = ("decision_row" if pd.notna(e.settlement)
                                  else ("outcomes_csv"
                                        if e.market_slug in osett.index
                                        else None))
        if pd.isna(e.settlement) and e.market_slug in osett.index:
            r["settlement"] = osett[e.market_slug]

        ex, src = link.get(e.id, (None, None))
        r["lineage_source"] = src
        close_yes = np.nan
        legs = 0
        if not r["entry_filled"]:
            r["outcome"] = ("withdrawn" if pd.notna(e.withdrawn_at)
                            else "expired_unfilled")
            r["close_at"] = e.withdrawn_at
        elif ex is not None:
            r["outcome"] = "exit_fill"
            r["exit_decision_id"] = ex.id
            r["exit_reason"] = ex.reason
            r["exit_limit_price"] = ex.limit_price
            r["exit_filled_at"] = ex.filled_at
            r["exit_mid_at_fill"] = ex.mid_at_fill
            r["close_at"] = ex.filled_at
            close_yes = ex.limit_price
            legs = 2
        elif pd.notna(r["settlement"]):
            r["outcome"] = "settlement"
            r["exit_reason"] = "rode_to_settlement"
            r["close_at"] = e.settled_at
            close_yes = float(r["settlement"])
            legs = 1
        else:
            r["outcome"] = "still_open"
            r["close_at"] = pd.NaT

        if legs:
            sign = 1.0 if is_yes else -1.0
            per = sign * (close_yes - e.limit_price)
            r["close_yes_value"] = close_yes
            r["pnl_per_contract"] = per
            r["pnl_per_dollar"] = per / entry_cost
            r["pnl_usd"] = per * e.contracts
            r["pnl_usd_live"] = per * r["live_contracts"]
            r["holding_s"] = ((r["close_at"] - e.filled_at).total_seconds()
                              if pd.notna(r["close_at"]) else np.nan)
            fee = _fee_taker(e.limit_price, 1.0)
            if legs == 2:
                fee += _fee_taker(close_yes, 1.0)
            r["fee_per_contract_taker"] = fee
            r["pnl_per_dollar_taker"] = (per - fee) / entry_cost
            r["pnl_usd_taker"] = (per - fee) * e.contracts
            pess = per - legs * CONCESSION_IN_GAME
            r["pnl_per_contract_pess"] = pess
            r["pnl_per_dollar_pess"] = pess / entry_cost
            r["pnl_usd_pess"] = pess * e.contracts
        rows.append(r)

    ledger = pd.DataFrame(rows)

    oc = ledger.outcome.value_counts()
    funnel = {
        "entry_intents": len(entries),
        "filled": int(ledger.entry_filled.sum()),
        "withdrawn_unfilled": int(oc.get("withdrawn", 0)),
        "expired_unfilled": int(oc.get("expired_unfilled", 0)),
        "closed_by_exit_fill": int(oc.get("exit_fill", 0)),
        "rode_to_settlement": int(oc.get("settlement", 0)),
        "still_open": int(oc.get("still_open", 0)),
        "scored": int(ledger.pnl_usd.notna().sum()),
        "lineage_reconstructed": n_reconstructed,
        "orphan_exits_unlinked": n_unlinked_orphans,
        "live_blocked_intents": int(ledger.live_blocked.sum()),
        "cap_enforced_era_rows": int((ledger.cap_semantics == "enforced").sum()),
        "games": int(ledger.event_slug.nunique()),
    }
    # Wave Standard rule 1: the funnel must partition — a row that fell out
    # of every category is exactly the silent default trap 2 forbids.
    assert (funnel["filled"] + funnel["withdrawn_unfilled"]
            + funnel["expired_unfilled"] == funnel["entry_intents"])
    assert (funnel["closed_by_exit_fill"] + funnel["rode_to_settlement"]
            + funnel["still_open"] == funnel["filled"])
    assert funnel["scored"] == funnel["filled"] - funnel["still_open"]
    return ledger, funnel


def game_clustered_ci(ledger: pd.DataFrame, pnl_col: str, stake_col: str,
                      n_boot: int = 10_000,
                      seed: int = 20260901) -> tuple[float, float, float]:
    """Return on stake with a 95% CI, clustered by GAME (trap 3): resample
    the 34 games with replacement and recompute Σpnl/Σstake each draw."""
    scored = ledger[ledger[pnl_col].notna() & (ledger[stake_col] > 0)]
    by_game = scored.groupby("event_slug")[[pnl_col, stake_col]].sum()
    point = by_game[pnl_col].sum() / by_game[stake_col].sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(by_game), size=(n_boot, len(by_game)))
    pnl = by_game[pnl_col].to_numpy()[idx].sum(axis=1)
    stk = by_game[stake_col].to_numpy()[idx].sum(axis=1)
    ratios = pnl / stk
    lo, hi = np.percentile(ratios, [2.5, 97.5])
    return point, lo, hi


# --------------------------------------------------------------------------- #
# Mutation tests — run FIRST, always (Wave Standard rule 4). The pipeline
# must read ~zero on a synthetic null and recover a hand-computed injected
# tape cell-by-cell before it may touch real rows. Expected values below are
# written as literals on purpose: the test must not share arithmetic with
# the code under test (the two-ledgers-agreeing-and-both-wrong scar).
# --------------------------------------------------------------------------- #

_TEMPLATE = dict(created_at=None, phase="in_play", strategy="total",
                 sports_market_type="t", line=100.0, game_id="g",
                 bankroll_usd=20.0, binding_constraint="kelly", reason=None,
                 score=None, margin=None, period=None, minutes_left=None,
                 minutes_left_is_estimate=False, total_so_far=None,
                 projected_total=None, total_sigma=None, market_bid=None,
                 market_ask=None, fair_value=None, edge_net=None,
                 mid_at_fill=None, estimates_version="v4",
                 capped_stake_usd=None, capped_contracts=None)


def _mk(rows: list[dict]) -> pd.DataFrame:
    out = []
    for i, r in enumerate(rows):
        full = {**_TEMPLATE, "id": i + 1, "entry_id": None,
                "settlement": None, **r}
        out.append(full)
    df = pd.DataFrame(out)
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df.get(c), utc=True)
    return df


def _t(minute: int) -> str:
    return f"2026-08-30 01:{minute:02d}:00+00:00"


def _selftest() -> None:
    no_outcomes = pd.DataFrame(columns=["market_slug", "settlement"])

    # ---- null tape: every trade carries its exact mirror; truth = $0 ----- #
    null_rows = []
    for g, (p, s) in enumerate([(0.30, 1), (0.62, 0), (0.45, 1)]):
        ev, mk = f"game{g}", f"game{g}-m"
        for side in ("yes", "no"):
            null_rows += [
                dict(event_slug=ev, market_slug=mk, action="enter", side=side,
                     limit_price=p, contracts=2.0,
                     stake_usd=2 * (p if side == "yes" else 1 - p),
                     decided_at=_t(1), filled_at=_t(2),
                     settlement=s, settled_at=_t(50)),
            ]
    null_ledger, nf = build_ledger(_mk(null_rows), no_outcomes)
    assert abs(null_ledger.pnl_usd.sum()) < 1e-9, "null tape must read $0"
    assert abs(null_ledger.pnl_usd_pess.sum() -
               (-0.047 * 2 * 6)) < 1e-9   # concession survives the mirror
    assert nf["scored"] == 6 and nf["games"] == 3

    # ---- injected tape: every cell hand-computed ------------------------- #
    inj = [
        # 1: yes trip 0.30 -> 0.40, 2c. pnl = +0.20; per$ = .10/.30
        dict(event_slug="gA", market_slug="gA-m1", action="enter", side="yes",
             limit_price=0.30, contracts=2.0, stake_usd=0.60,
             decided_at=_t(1), filled_at=_t(2), settlement=0, settled_at=_t(50)),
        dict(event_slug="gA", market_slug="gA-m1", action="exit", side="yes",
             limit_price=0.40, contracts=2.0, stake_usd=0.0, entry_id=1,
             reason="profit_target", decided_at=_t(3), filled_at=_t(4)),
        # 3: no trip, YES 0.70 -> 0.60, 3c. pnl/ct = +0.10 -> +0.30 total
        dict(event_slug="gA", market_slug="gA-m2", action="enter", side="no",
             limit_price=0.70, contracts=3.0, stake_usd=0.90,
             decided_at=_t(1), filled_at=_t(2), settlement=1, settled_at=_t(50)),
        dict(event_slug="gA", market_slug="gA-m2", action="exit", side="no",
             limit_price=0.60, contracts=3.0, stake_usd=0.0, entry_id=3,
             reason="ev_stop", decided_at=_t(3), filled_at=_t(5)),
        # 5: yes ride, 0.25, settles 0. pnl = -0.25
        dict(event_slug="gB", market_slug="gB-m1", action="enter", side="yes",
             limit_price=0.25, contracts=1.0, stake_usd=0.25,
             decided_at=_t(1), filled_at=_t(2), settlement=0, settled_at=_t(50)),
        # 6: no ride, YES 0.80 (cost .20), settles 0. pnl = +0.80
        dict(event_slug="gB", market_slug="gB-m1", action="enter", side="no",
             limit_price=0.80, contracts=1.0, stake_usd=0.20,
             decided_at=_t(5), filled_at=_t(6), settlement=0, settled_at=_t(50)),
        # 7: withdrawn, never filled — must carry NO pnl (trap 2)
        dict(event_slug="gB", market_slug="gB-m2", action="enter", side="yes",
             limit_price=0.40, contracts=1.0, stake_usd=0.40,
             decided_at=_t(1), withdrawn_at=_t(9)),
        # 8: expired unfilled — NO pnl
        dict(event_slug="gB", market_slug="gB-m3", action="enter", side="no",
             limit_price=0.50, contracts=1.0, stake_usd=0.50, decided_at=_t(1)),
        # 9+10: orphan-exit reconstruction: entry_id NULL, same market,
        # exit fills after — books as a trip 0.55 -> 0.65, +0.10
        dict(event_slug="gC", market_slug="gC-m1", action="enter", side="yes",
             limit_price=0.55, contracts=1.0, stake_usd=0.55,
             decided_at=_t(1), filled_at=_t(2), settlement=1, settled_at=_t(50)),
        dict(event_slug="gC", market_slug="gC-m1", action="exit", side="yes",
             limit_price=0.65, contracts=1.0, stake_usd=0.0,
             reason="profit_target", decided_at=_t(3), filled_at=_t(7)),
        # 11: cap-annotated blocked intent (capped 0): scored, flagged
        dict(event_slug="gC", market_slug="gC-m2", action="enter", side="yes",
             limit_price=0.10, contracts=5.0, stake_usd=0.50,
             capped_stake_usd=0.0, capped_contracts=0.0,
             binding_constraint="max_open_per_event",
             decided_at=_t(1), filled_at=_t(2), settlement=1, settled_at=_t(50)),
    ]
    led, f = build_ledger(_mk(inj), no_outcomes)
    led = led.set_index("entry_decision_id")

    def cell(i, col):
        return led.loc[i, col]

    assert f == {"entry_intents": 8, "filled": 6, "withdrawn_unfilled": 1,
                 "expired_unfilled": 1, "closed_by_exit_fill": 3,
                 "rode_to_settlement": 3, "still_open": 0, "scored": 6,
                 "lineage_reconstructed": 1, "orphan_exits_unlinked": 0,
                 "live_blocked_intents": 1, "cap_enforced_era_rows": 0,
                 "games": 3}, f
    exp = {1: (0.20, "exit_fill"), 3: (0.30, "exit_fill"),
           5: (-0.25, "settlement"), 6: (0.80, "settlement"),
           9: (0.10, "exit_fill"), 11: (4.50, "settlement")}
    for i, (pnl, out) in exp.items():
        assert abs(cell(i, "pnl_usd") - pnl) < 1e-9, (i, cell(i, "pnl_usd"))
        assert cell(i, "outcome") == out, (i, cell(i, "outcome"))
    for i in (7, 8):
        assert pd.isna(cell(i, "pnl_usd")), "unfilled row leaked into P&L"
    assert cell(7, "outcome") == "withdrawn"
    assert cell(8, "outcome") == "expired_unfilled"
    assert cell(9, "lineage_source") == "reconstructed"
    assert bool(cell(11, "live_blocked")) and cell(11, "pnl_usd_live") == 0.0
    # per-$ and sensitivity arms, hand-computed on row 1:
    #   per$ = .10/.30; taker fee = .06(.3·.7 + .4·.6) = .0270/ct
    #   pess = .10 − 2×.047 = .006/ct
    assert abs(cell(1, "pnl_per_dollar") - 1 / 3) < 1e-9
    assert abs(cell(1, "fee_per_contract_taker") - 0.0270) < 1e-9
    assert abs(cell(1, "pnl_usd_taker") - (0.10 - 0.0270) * 2) < 1e-9
    assert abs(cell(1, "pnl_usd_pess") - 0.006 * 2) < 1e-9
    # ride pays one concession leg, not two: 6: +0.80 − 1×.047
    assert abs(cell(6, "pnl_usd_pess") - (0.80 - 0.047)) < 1e-9
    # holding time: row 3 filled :02, exit filled :05
    assert cell(3, "holding_s") == 180.0

    # ---- the settlement column must actually decide the sign ------------- #
    flipped = [dict(r, settlement=1 - r["settlement"])
               if "settlement" in r and r.get("action") == "enter" else dict(r)
               for r in inj]
    led2, _ = build_ledger(_mk(flipped), no_outcomes)
    led2 = led2.set_index("entry_decision_id")
    assert abs(led2.loc[5, "pnl_usd"] - 0.75) < 1e-9   # −0.25 became +0.75
    assert abs(led2.loc[6, "pnl_usd"] + 0.20) < 1e-9   # +0.80 became −0.20
    assert abs(led2.loc[1, "pnl_usd"] - 0.20) < 1e-9   # trips must NOT move


# --------------------------------------------------------------------------- #

def main() -> None:
    _selftest()
    print("selftest: PASSED (null reads $0; injected tape recovered "
          "cell-by-cell; settlement flip moves rides only)")

    decisions = pd.read_csv(DECISIONS, parse_dates=DATE_COLS + ["created_at"])
    outcomes = pd.read_csv(OUTCOMES)
    ledger, funnel = build_ledger(decisions, outcomes)
    ledger.to_csv(OUT_LEDGER, index=False)
    print(f"ledger: {len(ledger)} rows -> {OUT_LEDGER}")
    print("funnel:", funnel)

    scored = ledger[ledger.pnl_usd.notna()]
    lines = []
    lines.append(f"total pnl_usd (full intent):  {scored.pnl_usd.sum():+.2f} "
                 f"on {scored.stake_usd.sum():.2f} staked")
    lines.append(f"total pnl_usd_live:           {scored.pnl_usd_live.sum():+.2f} "
                 f"on {scored.live_stake_usd.sum():.2f} staked")
    for pnl_col, stake_col, label in [
            ("pnl_usd", "stake_usd", "full-intent, policy (maker, $0 fees)"),
            ("pnl_usd_taker", "stake_usd", "full-intent, taker-fee arm"),
            ("pnl_usd_pess", "stake_usd", "full-intent, pessimistic 4.70c arm"),
            ("pnl_usd_live", "live_stake_usd", "live-faithful, policy")]:
        pt, lo, hi = game_clustered_ci(ledger, pnl_col, stake_col)
        sub = ledger[ledger[pnl_col].notna() & (ledger[stake_col] > 0)]
        lines.append(f"{label}: {pt:+.1%} [{lo:+.1%}, {hi:+.1%}] "
                     f"(n={sub.event_slug.nunique()} games, {len(sub)} rows)")
    print(*lines, sep="\n")


if __name__ == "__main__":
    sys.exit(main())
