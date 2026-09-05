"""PULSE execution decomposition — how much of the loss is execution, how much
is prediction. Track D of the 2026-09-01 edge-hunt wave (analysis/README.md,
rules in analysis/WAVE_STANDARD.md).

    .venv/bin/python analysis/pulse_execution_decomposition.py [--selftest]
        [--decisions CSV] [--ticks CSV.GZ] [--resolved CSV]

Reads the PINNED exports (never a live database):

    backups/exports/pulse_decisions_full_20260901T195202Z.csv
    backups/exports/live_ticks_pulse_games_20260901T195202Z.csv.gz
    backups/exports/resolved_outcomes_20260901T195202Z.csv

EVERYTHING HERE IS IN-SAMPLE, DESCRIPTIVE AND HYPOTHESIS-GENERATING. No number
below gates anything or justifies anything. Verbatim, per the wave standard:
**No in-sample result justifies capital. The forward test is the evidence.**

The assumption that bounds every number in this file
----------------------------------------------------
A PULSE fill is a MODELLED fill. The engine's rule (core/pulse/live.py,
``RestingOrder.fills_at``): a resting limit fills when a NEWER observation's
MID crosses it — buy fills when mid <= limit, sell when mid >= limit; an order
is never filled by the tick it was born from; observations are the newest
two-sided tick per market per ~1s cycle. Consequences, stated so a reader can
size everything below:

1. Real maker fills happen when an aggressor crosses at the touch, i.e. at or
   before mid-cross. The rule therefore records a fill only after the market
   has already moved through the price, so every recorded fill carries a
   non-negative "concession vs mid at fill" BY CONSTRUCTION (verified: 0 rule
   violations in 3,751 filled rows). What this file calls the execution
   concession is exactly that quantity — half the spread plus however far
   through the limit the mid had moved at the declaring tick. It is an
   assumption-laden stand-in for real slippage, not an observation of it.
2. Transient touches between observations that would really have filled are
   invisible, and the invisible fills skew favourable-at-entry (the docstring's
   own words): measured losses are trustworthy, measured profits are upper
   bounds.
3. Fills the rule denies are not fills the venue would have denied: a resting
   bid can fill from an aggressive seller without the mid ever crossing. The
   "unfilled entries" section is therefore about the RULE's selection, an
   upper bound on the direction of real fill selection, not its size.

Accounting policy (one labelled definition, per wave rule 1/4)
--------------------------------------------------------------
Legs are scored exactly as ``core/pulse/live_report.py`` scores them (money at
price, C11/V14): a round trip is entry joined to its FIRST filled exit by
filled_at; a ride is a filled entry with no filled exit, scored at settlement.
GROSS = NET here: theta_maker = 0 (findings C7/V24) and every modelled fill is
a resting maker limit, so the shadow ledger books ZERO fees, correctly. The
taker fee 0.06*p*(1-p) (V9) appears only as an explicit counterfactual.
Population: FULL-INTENT (shadow dollars at the model's desired size) — nearly
every fill on this tape is a cap-annotated intent; the registered
live-faithful subset (~60 fills) is printed separately for reconciliation
with track A's ledger and never sliced.

The identity that makes the headline number
-------------------------------------------
Per contract, YES frame, s = +1 for a yes position, -1 for no. m_e, m_x are
the engine's mid at entry/exit fill; L_e, L_x the fill (limit) prices.

  round trip:  pnl = s*(L_x - L_e) = s*(m_x - m_e) - c_e - c_x
  ride:        pnl = s*(S - L_e)   = s*(S - m_e)   - c_e        (S = 0/1)

with c_e = s*(L_e - m_e) >= 0 and c_x = s*(m_x - L_x) >= 0 the entry/exit
execution concessions. Summing: total P&L = [mid-basis prediction alpha]
minus [execution concessions] minus [fees = 0]. The script verifies the
identity to a tenth of a cent on the real tape and mutation-tests it on
synthetic worlds where the split is known (--selftest).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402  (blessed)

PIN = "20260901T195202Z"
DEFAULT_DECISIONS = REPO / f"backups/exports/pulse_decisions_full_{PIN}.csv"
DEFAULT_TICKS = REPO / f"backups/exports/live_ticks_pulse_games_{PIN}.csv.gz"
DEFAULT_RESOLVED = REPO / f"backups/exports/resolved_outcomes_{PIN}.csv"

THETA_TAKER = 0.06          # V9: venue-published, 874,267 rows / 241 markets
MEASURED_CONCESSION_INGAME = 0.0470   # $/contract, quote study (feed-lag mechanism)
MEASURED_CONCESSION_PREGAME = 0.0211  # $/contract [1.83, 2.39] — for reference

AS_HORIZONS_S = [10, 30, 60, 120, 300]
AS_MAX_GAP_S = 120          # a "mid at t+H" found more than this late is dropped
ENDGAME_WINDOW_S = 300      # "book present at end" = two-sided live tick in the
                            # last 5:00 of WALLCLOCK before the event's last
                            # live tick (proxy; the bookless-endgames doc uses
                            # the venue box clock — different unit, stated)

PRICE_BANDS = [(0.0, 0.10), (0.10, 0.35), (0.35, 0.65), (0.65, 0.90), (0.90, 1.0)]


# --------------------------------------------------------------------------- #
# Ledger reconstruction (live_report.py conventions, verbatim)
# --------------------------------------------------------------------------- #

def sgn(side: str) -> int:
    return 1 if side == "yes" else -1


def build_legs(dec: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per FILLED entry with its outcome leg, live_report semantics.

    Returns (legs, anomalies). Columns: kind ('trip'|'ride'), side, s,
    contracts, L_e, m_e, L_x, m_x (trip only), settlement (ride only),
    pnl_ct (per contract), plus the decomposition terms c_e, c_x, alpha_ct.
    """
    entries = dec[(dec.action == "enter") & dec.filled_at.notna()].copy()
    exits = dec[(dec.action == "exit") & dec.filled_at.notna()].copy()
    exits = exits.sort_values(["filled_at", "id"])
    first_exit = exits.dropna(subset=["entry_id"]).groupby("entry_id").first().reset_index()
    first_exit["entry_id"] = first_exit.entry_id.astype("int64")
    multi = exits.dropna(subset=["entry_id"]).groupby("entry_id").size()
    anomalies = {
        # Filled exit rows with NULL entry_id: no lineage, excluded from BOTH
        # this ledger and live_report's (its LATERAL join can't match NULL).
        "orphan_filled_exit_rows": int(exits.entry_id.isna().sum()),
        "entries_with_multiple_filled_exits": int((multi > 1).sum()),
    }

    legs = entries.merge(
        first_exit[["entry_id", "limit_price", "mid_at_fill", "filled_at",
                    "contracts"]].rename(columns={
            "entry_id": "id", "limit_price": "L_x", "mid_at_fill": "m_x",
            "filled_at": "exit_filled_at", "contracts": "exit_contracts"}),
        on="id", how="left")
    legs["s"] = legs["side"].map(sgn)
    legs = legs.rename(columns={"limit_price": "L_e", "mid_at_fill": "m_e"})

    is_trip = legs.exit_filled_at.notna()
    legs["kind"] = is_trip.map({True: "trip", False: "ride"})
    unsettled = legs[(legs.kind == "ride") & legs.settlement.isna()]
    anomalies["unsettled_rides_excluded"] = int(len(unsettled))
    legs = legs[(legs.kind == "trip") | legs.settlement.notna()].copy()

    s, Le, me = legs.s, legs.L_e, legs.m_e
    legs["c_e"] = s * (Le - me)                              # >= 0 by rule
    legs["c_x"] = (s * (legs.m_x - legs.L_x)).where(is_trip, 0.0)
    legs["alpha_ct"] = (s * (legs.m_x - me)).where(
        is_trip, s * (legs.settlement - me))
    legs["pnl_ct"] = (s * (legs.L_x - Le)).where(
        is_trip, s * (legs.settlement - Le))
    # live_report stake basis: cost per contract of the position
    legs["cost_ct"] = Le.where(legs.side == "yes", 1.0 - Le)
    for c in ("c_e", "c_x", "alpha_ct", "pnl_ct"):
        legs[c + "_usd"] = legs[c] * legs.contracts
    return legs, anomalies


def identity_check(legs: pd.DataFrame) -> float:
    """Max abs violation of pnl = alpha - c_e - c_x across legs, in $."""
    resid = legs.pnl_ct_usd - (legs.alpha_ct_usd - legs.c_e_usd - legs.c_x_usd)
    return float(resid.abs().max()) if len(legs) else 0.0


def taker_fee_ct(p: pd.Series) -> pd.Series:
    return THETA_TAKER * p * (1.0 - p)


# --------------------------------------------------------------------------- #
# Reporting helpers
# --------------------------------------------------------------------------- #

def cm_str(values_by_game: dict[str, list[float]], unit: str = "c/ct",
           scale: float = 100.0) -> str:
    cm = clustered_mean(values_by_game)
    if cm is None:
        return "n/a (<2 games)"
    return (f"{cm.mean * scale:+.2f} [{cm.lo * scale:+.2f}, {cm.hi * scale:+.2f}] {unit} "
            f"(n={cm.n} rows, {cm.n_clusters} games)")


def by_game(legs: pd.DataFrame, col: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for g, v in legs.groupby("event_slug")[col]:
        out[g] = list(v)
    return out


def hr(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

def section_composition(dec: pd.DataFrame) -> None:
    hr("0. COUNTS AND COMPOSITION (before any ratio — wave rule 1)")
    games = dec.event_slug.nunique()
    print(f"window: {dec.decided_at.min()} -> {dec.decided_at.max()}  "
          f"| {len(dec)} rows | {games} games | pins {PIN}")
    t = dec.groupby(["action"]).agg(
        rows=("id", "size"), filled=("filled_at", lambda x: x.notna().sum()),
        withdrawn=("withdrawn_at", lambda x: x.notna().sum()),
        games=("event_slug", "nunique"))
    print(t.to_string())
    ent = dec[dec.action == "enter"]
    unfilled = ent.filled_at.isna()
    print(f"\nentry intents never filled UNDER THE ENGINE'S RULE: "
          f"{int(unfilled.sum())}/{len(ent)} rows = {unfilled.mean():.1%} "
          f"({ent[unfilled].contracts.sum():.0f} of {ent.contracts.sum():.0f} contracts; "
          f"{ent[unfilled].event_slug.nunique()} of {ent.event_slug.nunique()} games)")
    print("(the wave standard's 46% is the QUOTE study's historical number — "
          "different instrument, same direction)")
    print("\nfilled entries by estimates_version x population "
          "(cap=0 rows are cap-annotated intents; FULL-INTENT includes them):")
    f = ent[ent.filled_at.notna()].copy()
    f["pop"] = "live_faithful"
    f.loc[f.capped_stake_usd.fillna(-1) == 0, "pop"] = "full_intent_only"
    print(f.groupby(["estimates_version", "pop"]).agg(
        rows=("id", "size"), games=("event_slug", "nunique")).to_string())


def section_ledger(legs: pd.DataFrame) -> pd.DataFrame:
    hr("1. THE LEDGER (live_report.py conventions; policy: money at price, "
       "gross=net, $0 fees booked — theta_maker=0, C7/V24)")
    for pop_name, sub in (("FULL-INTENT (all filled entries; shadow $ at model's "
                           "desired size)", legs),
                          ("live-faithful (capped_stake_usd NULL or >0; the "
                           "registered population — tiny, unsliced)",
                           legs[legs.capped_stake_usd.isna()
                                | (legs.capped_stake_usd > 0)])):
        trips, rides = sub[sub.kind == "trip"], sub[sub.kind == "ride"]
        print(f"\n[{pop_name}]")
        print(f"  round trips: {len(trips)} rows / {trips.event_slug.nunique()} games"
              f"  staked ${ (trips.cost_ct * trips.contracts).sum():,.2f}"
              f"  pnl ${trips.pnl_ct_usd.sum():+,.2f}")
        print(f"  rides:       {len(rides)} rows / {rides.event_slug.nunique()} games"
              f"  staked ${ (rides.cost_ct * rides.contracts).sum():,.2f}"
              f"  pnl ${rides.pnl_ct_usd.sum():+,.2f}")
        print(f"  TOTAL realized shadow P&L: ${sub.pnl_ct_usd.sum():+,.2f}"
              f"  ({len(sub)} legs / {sub.event_slug.nunique()} games)")
    print("\n(the FULL-INTENT total is the number to reconcile with track A's "
          "ledger before anything downstream of it is quoted)")
    return legs


def section_decomposition(legs: pd.DataFrame) -> None:
    hr("2. THE DECOMPOSITION (FULL-INTENT; identity pnl = alpha - c_e - c_x, "
       "verified per leg)")
    resid = identity_check(legs)
    print(f"identity residual, max abs over {len(legs)} legs: ${resid:.6f}")

    total = legs.pnl_ct_usd.sum()
    a_trip = legs.loc[legs.kind == "trip", "alpha_ct_usd"].sum()
    a_ride = legs.loc[legs.kind == "ride", "alpha_ct_usd"].sum()
    ce, cx = legs.c_e_usd.sum(), legs.c_x_usd.sum()
    print(f"""
  mid-basis prediction alpha, round trips (s*(m_x-m_e))   ${a_trip:+10,.2f}
  mid-basis prediction alpha, rides      (s*(S-m_e))      ${a_ride:+10,.2f}
  entry execution concession  (s*(L_e-m_e), >=0 by rule)  ${-ce:+10,.2f}
  exit  execution concession  (s*(m_x-L_x), >=0 by rule)  ${-cx:+10,.2f}
  fees booked (maker-only shadow, theta_maker=0)          ${0.0:+10,.2f}
  ------------------------------------------------------------------
  TOTAL realized shadow P&L                               ${total:+10,.2f}
""")
    print("per-contract concessions vs the QUOTE study's measured in-game "
          f"concession ({MEASURED_CONCESSION_INGAME * 100:.2f}c/ct):")
    print(f"  entry c_e: {cm_str(by_game(legs, 'c_e'))}")
    trips = legs[legs.kind == "trip"]
    print(f"  exit  c_x: {cm_str(by_game(trips, 'c_x'))}")

    # Wave rule 2: anything fill-dependent also scores under the pessimistic
    # rule with the MEASURED concession. Same fills, same alpha, but every
    # filled contract-leg charged the measured in-game 4.70c instead of the
    # engine's own (smaller) concession.
    contract_legs = legs.contracts.sum() + trips.contracts.sum()
    pess_exec = MEASURED_CONCESSION_INGAME * contract_legs
    alpha_total = legs.alpha_ct_usd.sum()
    print(f"\nPESSIMISTIC-RULE RE-SCORE (wave rule 2; measured "
          f"{MEASURED_CONCESSION_INGAME * 100:.2f}c/ct/leg on "
          f"{contract_legs:,.0f} contract-legs):")
    print(f"  execution charge ${-pess_exec:+,.2f} vs the engine's "
          f"${-(ce + cx):+,.2f}; re-scored total = alpha - charge = "
          f"${alpha_total - pess_exec:+,.2f} (engine-rule total "
          f"${legs.pnl_ct_usd.sum():+,.2f})")
    print("  (the engine's own concession is the SMALLER of the two — its "
          "fill rule books less slippage than the venue measurably charges "
          "resting orders in-game; the re-score is the honest floor)")
    print(f"  alpha/ct : {cm_str(by_game(legs, 'alpha_ct'))}")
    print(f"  pnl/ct   : {cm_str(by_game(legs, 'pnl_ct'))}")

    print("\nby market type ($ sums; c_e+c_x = execution):")
    g = legs.groupby("sports_market_type").agg(
        legs_=("id", "size"), games=("event_slug", "nunique"),
        pnl=("pnl_ct_usd", "sum"), alpha=("alpha_ct_usd", "sum"),
        exec_=("c_e_usd", "sum"), exec_x=("c_x_usd", "sum"))
    g["exec_total"] = g.exec_ + g.exec_x
    print(g[["legs_", "games", "pnl", "alpha", "exec_total"]]
          .round(2).to_string())

    print("\nby entry price band of L_e (35-65c is where size exists — "
          "wave priority hint):")
    legs2 = legs.copy()
    legs2["band"] = pd.cut(legs2.L_e, [b for b, _ in PRICE_BANDS] + [1.0],
                           right=False)
    g = legs2.groupby("band", observed=True).agg(
        legs_=("id", "size"), games=("event_slug", "nunique"),
        pnl=("pnl_ct_usd", "sum"), alpha=("alpha_ct_usd", "sum"),
        c_e_usd=("c_e_usd", "sum"), c_x_usd=("c_x_usd", "sum"))
    print(g.round(2).to_string())

    print("\nby estimates_version (never blended — live_report rule):")
    g = legs.groupby("estimates_version").agg(
        legs_=("id", "size"), games=("event_slug", "nunique"),
        pnl=("pnl_ct_usd", "sum"), alpha=("alpha_ct_usd", "sum"),
        exec_e=("c_e_usd", "sum"), exec_x=("c_x_usd", "sum"))
    print(g.round(2).to_string())


def section_fees(legs: pd.DataFrame) -> None:
    hr("3. FEE LOAD (explicit, counterfactual)")
    print("booked in the shadow ledger: $0.00 — every modelled fill is a "
          "resting maker limit; theta_maker = 0 (C7, V24: the maker rebate "
          "has never been observed; the taker-fee promo ended 2026-05-10).")
    fee_e = taker_fee_ct(legs.L_e) * legs.contracts
    trips = legs.kind == "trip"
    fee_x = (taker_fee_ct(legs.L_x.fillna(0.0)) * legs.contracts).where(trips, 0.0)
    total = fee_e.sum() + fee_x.sum()
    print(f"IF every leg had crossed as a taker (deployment worst case, V9 "
          f"theta=0.06): ${total:,.2f} on {int(trips.sum())} trips + "
          f"{int((~trips).sum())} rides "
          f"(entry legs ${fee_e.sum():,.2f}, exit legs ${fee_x.sum():,.2f})")
    legs2 = legs.assign(fee_e=fee_e)
    legs2["band"] = pd.cut(legs2.L_e, [b for b, _ in PRICE_BANDS] + [1.0],
                           right=False)
    print("\nhypothetical taker fee by entry price band (entry leg only):")
    print(legs2.groupby("band", observed=True)
          .agg(legs_=("id", "size"), fee_usd=("fee_e", "sum"))
          .round(2).to_string())
    print("\nanswer to 'how much of the loss is fees': $0.00 of the shadow "
          "loss is fees, by construction. Fees matter only under a deployment "
          "that crosses; the counterfactual above is that price tag.")


# --------------------------------------------------------------------------- #
# Tick-tape sections (duckdb)
# --------------------------------------------------------------------------- #

def load_ticks(con: duckdb.DuckDBPyConnection, ticks_path: Path,
               markets: list[str]) -> None:
    con.execute("CREATE TEMP TABLE wanted(market_slug VARCHAR)")
    con.executemany("INSERT INTO wanted VALUES (?)", [(m,) for m in markets])
    con.execute(f"""
        CREATE TEMP TABLE ticks AS
        SELECT event_slug, market_slug, captured_at,
               best_bid, best_ask, is_live,
               (best_bid IS NOT NULL AND best_ask IS NOT NULL) AS two_sided,
               CASE WHEN best_bid IS NOT NULL AND best_ask IS NOT NULL
                    THEN (best_bid + best_ask) / 2.0 END AS mid
        FROM read_csv('{ticks_path}')
        WHERE market_slug IN (SELECT market_slug FROM wanted)
    """)
    con.execute("CREATE INDEX ix_ticks ON ticks(market_slug, captured_at)")


def section_mid_sanity(con: duckdb.DuckDBPyConnection, legs: pd.DataFrame,
                       exits: pd.DataFrame) -> None:
    hr("4. mid_at_fill vs THE TAPE (trap: our record, not the venue's)")
    fills = pd.concat([
        legs[["market_slug", "filled_at", "m_e"]].rename(columns={"m_e": "mid_rec"}),
        exits[["market_slug", "filled_at", "mid_at_fill"]]
        .rename(columns={"mid_at_fill": "mid_rec"})],
        ignore_index=True)
    con.register("fills_df", fills)
    r = con.execute("""
        SELECT count(*) n,
               sum(CASE WHEN abs(t.mid - f.mid_rec) <= 0.005 THEN 1 ELSE 0 END) n_close,
               max(abs(t.mid - f.mid_rec)) worst,
               avg(abs(t.mid - f.mid_rec)) mean_abs
        FROM fills_df f ASOF JOIN (SELECT * FROM ticks WHERE two_sided) t
          ON f.market_slug = t.market_slug AND t.captured_at <= f.filled_at
    """).fetchone()
    n, close, worst, mean_abs = r
    print(f"{n} filled legs joined to latest two-sided tape tick at/before "
          f"filled_at: {close}/{n} within 0.5c "
          f"(mean |diff| {mean_abs:.4f}, worst {worst:.4f})")
    if n and close / n < 0.95:
        print("WARNING: >5% of recorded mids disagree with the tape — "
              "everything mid-based above inherits that error.")


def section_adverse_selection(con: duckdb.DuckDBPyConnection,
                              legs: pd.DataFrame, exits: pd.DataFrame) -> None:
    hr("5. ADVERSE SELECTION — post-fill drift from the tape "
       "(signed: + = market kept moving through the fill against the leg)")
    ent = legs[["event_slug", "market_slug", "filled_at", "m_e", "s"]].copy()
    ent["role"] = "entry"
    ext = exits[["event_slug", "market_slug", "filled_at", "mid_at_fill",
                 "side"]].copy()
    ext = ext.rename(columns={"mid_at_fill": "m_e"})
    # For an exit leg the trade is the REVERSE of the position: the leg is
    # picked off if the mid keeps moving in the position's direction after we
    # sold, so its drift-against-the-leg sign is -s of the position...
    ext["s"] = -ext.side.map(sgn)
    ext["role"] = "exit"
    both = pd.concat([ent, ext], ignore_index=True)
    con.register("as_fills", both)
    con.execute("""CREATE OR REPLACE TEMP VIEW fwd_ticks AS
        SELECT market_slug, mid, captured_at, -epoch(captured_at) AS neg_t
        FROM ticks WHERE two_sided""")
    for horizon in AS_HORIZONS_S:
        rows = con.execute(f"""
            WITH f AS (
              SELECT *, -(epoch(filled_at) + {horizon}) AS tneg FROM as_fills
            ), fwd AS (
              SELECT f.event_slug, f.role, f.s, f.m_e,
                     t.mid AS m_fwd,
                     epoch(t.captured_at - f.filled_at) - {horizon} AS gap_s
              FROM f ASOF JOIN fwd_ticks t
                ON f.market_slug = t.market_slug AND t.neg_t <= f.tneg
            )
            SELECT event_slug, role, -s * (m_fwd - m_e) AS against
            FROM fwd WHERE gap_s <= {AS_MAX_GAP_S}
        """).df()
        for role in ("entry", "exit"):
            sub = rows[rows.role == role]
            vals: dict[str, list[float]] = {
                g: list(v) for g, v in sub.groupby("event_slug")["against"]}
            n_all = len(both[both.role == role])
            print(f"  {role:5s} +{horizon:>3d}s: {cm_str(vals)}  "
                  f"[coverage {len(sub)}/{n_all}]")
    print("\n(positive = the market keeps moving through the fill — picked "
          "off; NEGATIVE = post-fill REVERSION: the mid snaps back after the "
          "fill. The mid-cross rule triggers at local extremes of mid noise, "
          "so reversion here is partly mechanical to the fill model — and it "
          "is the OPPOSITE sign of the +4.70c adverse drift measured on real "
          "resting orders in-game. That gap is the size of the fill-rule "
          "optimism, and it bounds every execution number in this file.)")


def section_unfilled(dec: pd.DataFrame, legs: pd.DataFrame,
                     resolved: pd.DataFrame) -> None:
    hr("6. UNFILLED ENTRIES — is the fill rule a selection filter running "
       "backwards?")
    ent = dec[dec.action == "enter"].copy()
    settle = resolved.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug").settlement
    ent["settle_join"] = ent.market_slug.map(settle)
    unf = ent[ent.filled_at.isna() & ent.settle_join.notna()].copy()
    unresolved = int((ent.filled_at.isna() & ent.settle_join.isna()).sum())
    unf["s"] = unf.side.map(sgn)
    unf["cf_pnl_ct"] = unf.s * (unf.settle_join - unf.limit_price)

    filled = legs.copy()
    filled["settle_basis_ct"] = filled.s * (
        filled.settlement.fillna(filled.market_slug.map(settle)) - filled.L_e)
    n_no_settle = int(filled.settle_basis_ct.isna().sum())
    filled = filled[filled.settle_basis_ct.notna()]

    print("measure: settle-basis P&L per contract AT THE LIMIT PRICE, "
          "s*(S - L_e) — same yardstick for both groups; counterfactual for "
          "the unfilled (assumes the fill, ignores why it didn't happen)")
    print(f"  FILLED   entries: {cm_str(by_game(filled, 'settle_basis_ct'))}")
    print(f"  UNFILLED entries: {cm_str(by_game(unf.rename(columns={'cf_pnl_ct': 'settle_basis_ct'}), 'settle_basis_ct'))}")
    print(f"  (unfilled with no settlement resolution: {unresolved} rows "
          f"excluded; filled without: {n_no_settle})")
    d_filled = {g: list(v) for g, v in filled.groupby("event_slug").settle_basis_ct}
    d_unf = {g: list(v) for g, v in unf.groupby("event_slug").cf_pnl_ct}
    diffs = {g: [sum(d_unf[g]) / len(d_unf[g]) - sum(d_filled[g]) / len(d_filled[g])]
             for g in d_unf if g in d_filled}
    print(f"  per-game (mean unfilled - mean filled): "
          f"{cm_str(diffs)}")
    print("\nCAVEAT THAT BOUNDS THIS SECTION: 'unfilled' means unfilled UNDER "
          "THE MID-CROSS RULE. A real resting bid fills from an aggressive "
          "seller without the mid crossing, so the real venue would have "
          "filled some of these. Direction is informative; magnitude is not.")

    # State profile of unfilled intents, in track B's exact cells, to test the
    # manager's one-mechanism hypothesis: B's ride tail concentrates in Q4 /
    # minutes_left 5-10 / |margin|>=10 — do unfilled intents live in the same
    # cells (shared venue-liquidity mechanism) or elsewhere (different one)?
    print("\nunfilled share by state at DECISION time (track B's cells; "
          "counts before ratios):")
    ent2 = ent.copy()
    ent2["unfilled"] = ent2.filled_at.isna()
    cells = [
        ("period Q1-Q3", ent2.period.isin(["Q1", "Q2", "Q3"])),
        ("period Q4+", ~ent2.period.isin(["Q1", "Q2", "Q3"])),
        ("minutes_left > 10", ent2.minutes_left > 10),
        ("minutes_left 5-10", (ent2.minutes_left >= 5) & (ent2.minutes_left <= 10)),
        ("minutes_left < 5", ent2.minutes_left < 5),
        ("|margin| < 10", ent2.margin.abs() < 10),
        ("|margin| >= 10", ent2.margin.abs() >= 10),
    ]
    for name, mask in cells:
        sub = ent2[mask]
        if len(sub) == 0:
            print(f"  {name:18s}: no intents")
            continue
        print(f"  {name:18s}: {int(sub.unfilled.sum()):4d}/{len(sub):4d} unfilled "
              f"= {sub.unfilled.mean():5.1%}  ({sub.event_slug.nunique()} games)")


#: The 6b scan, shared verbatim with the selftest so the tested query IS the
#: production query. Needs `ticks` (market_slug, captured_at, mid, two_sided,
#: is_live, event_slug) and `unf_df` (id, event_slug, market_slug, side,
#: limit_price, decided_at, withdrawn_at) in scope.
WITHDRAWAL_SCAN_SQL = """
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), u AS (
          SELECT f.*, e.t_end FROM unf_df f JOIN live_end e USING (event_slug)
        ), scan AS (
          SELECT u.id,
            max(CASE WHEN t.captured_at > u.decided_at
                      AND t.captured_at <= u.withdrawn_at
                      AND ((u.side='yes' AND t.mid <= u.limit_price) OR
                           (u.side='no'  AND t.mid >= u.limit_price))
                     THEN 1 ELSE 0 END) crossed_while_resting,
            max(CASE WHEN t.captured_at > u.withdrawn_at
                      AND t.captured_at <= u.t_end
                      AND ((u.side='yes' AND t.mid <= u.limit_price) OR
                           (u.side='no'  AND t.mid >= u.limit_price))
                     THEN 1 ELSE 0 END) would_fill_later,
            min(CASE WHEN t.captured_at > u.withdrawn_at
                      AND t.captured_at <= u.t_end
                      AND ((u.side='yes' AND t.mid <= u.limit_price) OR
                           (u.side='no'  AND t.mid >= u.limit_price))
                     THEN epoch(t.captured_at - u.withdrawn_at) END) s_to_fill
          FROM u LEFT JOIN ticks t
            ON t.market_slug = u.market_slug AND t.two_sided AND t.is_live
           AND t.captured_at > u.decided_at AND t.captured_at <= u.t_end
          GROUP BY u.id
        )
        SELECT u.*, coalesce(s.crossed_while_resting, 0) crossed_while_resting,
               coalesce(s.would_fill_later, 0) would_fill_later, s.s_to_fill
        FROM u LEFT JOIN scan s ON u.id = s.id
"""


def section_withdrawal_autopsy(con: duckdb.DuckDBPyConnection,
                               dec: pd.DataFrame,
                               resolved: pd.DataFrame) -> None:
    """6b. Whose fault is an unfilled entry — the market's or our own policy?

    Every unfilled entry on this tape was WITHDRAWN by the engine (the rule:
    stood down the moment the CURRENT estimate stops clearing zero at the
    resting price — core/pulse/live.py _manage_entry — or the stream left the
    live set for 120s). So "unfilled" is withdrawal-censored, not
    expiry-censored, and the +11c unfilled-outperformance result has two
    candidate mechanisms with different remedies:

      (a) LIMIT NEVER REACHABLE: the mid ran away and never came back — a
          placement problem; no cancellation policy changes it.
      (b) PULLED TOO EARLY: after we withdrew, the mid DID cross the resting
          price — a patient order would have filled under the same rule; the
          withdrawal policy, not the market, discarded the trade.

    This section splits the withdrawn population by "would the order have
    filled later" (any two-sided live tick after withdrawn_at, up to the
    event's last live tick, with mid at-or-through the limit) and scores each
    half on the same settle-basis counterfactual as section 6.

    Built-in control: the same query counts mid-crossings BETWEEN decided_at
    and withdrawn_at. Under the engine's own rule that count should be ~0
    (it fills on the newest tick per ~1s cycle, two-sided, <=60s fresh); a
    large number here means this join and the engine disagree about the tape
    and the split above is untrustworthy.
    """
    hr("6b. WITHDRAWAL AUTOPSY — pulled too early, or never reachable?")
    ent = dec[dec.action == "enter"].copy()
    settle = resolved.dropna(subset=["settlement"]).drop_duplicates(
        "market_slug").set_index("market_slug").settlement
    unf = ent[ent.filled_at.isna() & ent.withdrawn_at.notna()].copy()
    n_open = int((ent.filled_at.isna() & ent.withdrawn_at.isna()).sum())
    unf["s"] = unf.side.map(sgn)
    unf["settle_join"] = unf.market_slug.map(settle)
    unf["rest_s"] = (unf.withdrawn_at - unf.decided_at).dt.total_seconds()
    unf["late"] = ~unf.period.isin(["Q1", "Q2", "Q3"])
    print(f"unfilled entries: {len(unf)} withdrawn + {n_open} still open at "
          f"export (open rows excluded below)")
    print(f"rest time before withdrawal: median {unf.rest_s.median():.0f}s, "
          f"p25 {unf.rest_s.quantile(.25):.0f}s, p75 "
          f"{unf.rest_s.quantile(.75):.0f}s (descriptive)")

    con.register("unf_df", unf[["id", "event_slug", "market_slug", "side",
                                "limit_price", "decided_at", "withdrawn_at",
                                "late"]])
    per = con.execute(WITHDRAWAL_SCAN_SQL).df()
    per = per.merge(unf[["id", "s", "settle_join"]], on="id")
    per["cf_pnl_ct"] = per.s * (per.settle_join - per.limit_price)

    cross = per.crossed_while_resting.astype(bool)
    n_cross = int(cross.sum())
    print(f"\ncontrol: mid crossed the limit WHILE the order rested yet the "
          f"engine recorded no fill: {n_cross}/{len(per)} = "
          f"{n_cross / len(per):.1%}. Expected small but nonzero: the engine "
          f"reads only the NEWEST tick per ~1s cycle (plus a 60s staleness "
          f"gate) on a 200ms tape, so sub-cycle crossings are invisible to "
          f"it and visible to this scan — this line QUANTIFIES that stated "
          f"fill-rule blindness. A large fraction would mean scan and engine "
          f"disagree about the tape itself; treat >10% as disqualifying.")
    wf = per.would_fill_later.astype(bool) & ~cross
    never = ~per.would_fill_later.astype(bool) & ~cross
    print(f"\nthree-way split of withdrawn entries (settle-basis cf at limit, "
          f"same yardstick as section 6):")
    print(f"  limit reached AFTER withdrawal: {int(wf.sum())}/{len(per)} = "
          f"{wf.mean():.1%} ({per[wf].event_slug.nunique()} games); "
          f"median wait {per.loc[wf, 's_to_fill'].median():.0f}s")
    for name, mask in (
            ("PULLED TOO EARLY (reached after pull)", wf),
            ("NEVER REACHABLE (mid never came)", never),
            ("SUB-CYCLE CROSS while resting", cross)):
        sub = per[mask & per.settle_join.notna()]
        vals = {g: list(v) for g, v in sub.groupby("event_slug").cf_pnl_ct}
        print(f"  {name:38s}: {cm_str(vals)}")
    print("\nby the late cell (B x D joint note; late = Q4+):")
    for latev in (True, False):
        sub = per[per.late == latev]
        if len(sub) == 0:
            continue
        print(f"  late={latev}: {int(sub.would_fill_later.sum())}/{len(sub)} "
              f"= {sub.would_fill_later.mean():.1%} would have filled later "
              f"({sub.event_slug.nunique()} games)")
    print("\n(withdrawal trigger in code: the model's OWN fair value crossing "
          "back through the resting price — 'edge gone' — or estimate/stream "
          "loss. 'Would fill later' therefore means: the model gave up, and "
          "the market subsequently came to the original price anyway.)")


def section_exit_availability(con: duckdb.DuckDBPyConnection,
                              dec: pd.DataFrame, legs: pd.DataFrame) -> None:
    hr("7. EXIT AVAILABILITY — rides and the bookless endgame "
       "(docs/math/bookless-endgames.md; FT rows carry NULL books, so all "
       "windows end at the event's LAST LIVE tick, never at FT)")
    rides = legs[legs.kind == "ride"].copy()
    if rides.empty:
        print("no rides")
        return
    x_all = dec[dec.action == "exit"]
    first_rest = x_all.groupby("entry_id").decided_at.min()
    rides["exit_rested_at"] = rides.id.map(first_rest)
    n_no_exit_row = int(rides.exit_rested_at.isna().sum())
    rides = rides[rides.exit_rested_at.notna()].copy()

    con.register("rides_df", rides[[
        "id", "event_slug", "market_slug", "exit_rested_at", "s", "m_e",
        "settlement", "contracts", "pnl_ct_usd", "sports_market_type"]])
    per = con.execute(f"""
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), w AS (
          SELECT r.*, e.t_end FROM rides_df r JOIN live_end e USING (event_slug)
        ), tick_stats AS (
          SELECT w.id,
                 count(t.captured_at) n_ticks,
                 sum(CASE WHEN t.two_sided THEN 1 ELSE 0 END) n_two_sided,
                 max(CASE WHEN t.two_sided THEN t.captured_at END) last_two_sided,
                 max(CASE WHEN t.two_sided
                          AND t.captured_at >= w.t_end - INTERVAL '{ENDGAME_WINDOW_S} seconds'
                          THEN 1 ELSE 0 END) book_at_end,
                 arg_max(t.mid, CASE WHEN t.two_sided THEN t.captured_at END) m_last
          FROM w LEFT JOIN ticks t
            ON t.market_slug = w.market_slug AND t.is_live
           AND t.captured_at BETWEEN w.exit_rested_at AND w.t_end
          GROUP BY w.id
        )
        SELECT w.*, s.n_ticks, s.n_two_sided, s.book_at_end, s.m_last,
               epoch(w.t_end - s.last_two_sided) dead_seconds
        FROM w JOIN tick_stats s ON w.id = s.id
    """).df()

    per["book_at_end"] = per.book_at_end.fillna(0).astype(bool)
    # A market bookless for the WHOLE resting window has no in-window mid to
    # price the stranded exit at; fall back to the mid at entry fill (a book
    # existed then by definition of the fill). Counted and printed.
    n_fallback = int(per.m_last.isna().sum())
    per["m_last"] = per.m_last.fillna(per.m_e)
    per["stranded_ct"] = per.s * (per.m_last - per.settlement)
    per["stranded_usd"] = per.stranded_ct * per.contracts
    if n_fallback:
        print(f"({n_fallback} rides had NO two-sided tick in the whole resting "
              f"window; their stranded cost uses the entry-fill mid)")

    print(f"rides analysed: {len(per)} rows / {per.event_slug.nunique()} games "
          f"({n_no_exit_row} rides had no exit row at all — anomaly, listed "
          f"out of scope)")
    print("\nsplit by whether ANY two-sided live tick existed in the market's "
          f"final {ENDGAME_WINDOW_S // 60}:00 (wallclock proxy) while the exit rested:")
    g = per.groupby(["sports_market_type", "book_at_end"]).agg(
        rides=("id", "size"), games=("event_slug", "nunique"),
        pnl_usd=("pnl_ct_usd", "sum"),
        stranded_usd=("stranded_usd", "sum"))
    print(g.round(2).to_string())
    dead = per[~per.book_at_end]
    print(f"\nrides whose market had NO two-sided book at the end: "
          f"{len(dead)}/{len(per)} rows "
          f"({dead.event_slug.nunique()} games), P&L ${dead.pnl_ct_usd.sum():+,.2f}")
    print(f"'stranded cost' = s*(last two-sided mid - settlement)*contracts — "
          f"what exiting at the last available mid would have returned vs "
          f"riding: ${per.stranded_usd.sum():+,.2f} over all rides, "
          f"${dead.stranded_usd.sum():+,.2f} over the bookless ones "
          f"(positive = the ride cost money relative to that exit)")
    print("(per bookless-endgames: availability is per-market-type-per-game "
          "with NO safe-harbour type; the split above is the evidence here)")


# --------------------------------------------------------------------------- #
# Mutation test (wave rule 4): known splits must be recovered
# --------------------------------------------------------------------------- #

def _mk_leg(kind, side, L_e, m_e, L_x=None, m_x=None, settlement=None,
            contracts=10.0, game="g1", version="v1"):
    return dict(id=0, event_slug=game, market_slug="m", action="enter",
                side=side, kind=kind, L_e=L_e, m_e=m_e, L_x=L_x, m_x=m_x,
                settlement=settlement, contracts=contracts,
                capped_stake_usd=None, estimates_version=version,
                sports_market_type="t")


def selftest() -> int:
    print("mutation test: synthetic worlds with KNOWN spread/prediction splits")
    failures = 0

    def finish(df: pd.DataFrame) -> pd.DataFrame:
        df["s"] = df.side.map(sgn)
        trips = df.kind == "trip"
        df["c_e"] = df.s * (df.L_e - df.m_e)
        df["c_x"] = (df.s * (df.m_x - df.L_x)).where(trips, 0.0)
        df["alpha_ct"] = (df.s * (df.m_x - df.m_e)).where(
            trips, df.s * (df.settlement - df.m_e))
        df["pnl_ct"] = (df.s * (df.L_x - df.L_e)).where(
            trips, df.s * (df.settlement - df.L_e))
        for c in ("c_e", "c_x", "alpha_ct", "pnl_ct"):
            df[c + "_usd"] = df[c] * df.contracts
        return df

    def check(name, df, want_exec, want_alpha, tol=1e-9):
        nonlocal failures
        got_exec = -(df.c_e_usd.sum() + df.c_x_usd.sum())
        got_alpha = df.alpha_ct_usd.sum()
        total = df.pnl_ct_usd.sum()
        ok = (abs(got_exec - want_exec) < tol and abs(got_alpha - want_alpha) < tol
              and abs(total - (got_alpha + got_exec)) < tol)
        print(f"  {name}: exec {got_exec:+.4f} (want {want_exec:+.4f}), "
              f"alpha {got_alpha:+.4f} (want {want_alpha:+.4f}), "
              f"total {total:+.4f} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    # World S: pure execution loss. Flat mid 0.50; entry pays 2c through,
    # exit gives 2c through. Known: exec -8c/ct * 10ct * 2 legs... exec is
    # per-leg-pair: c_e=0.02, c_x=0.02 -> pnl = -0.04/ct, alpha = 0.
    ws = finish(pd.DataFrame([
        _mk_leg("trip", "yes", L_e=0.52, m_e=0.50, L_x=0.48, m_x=0.50),
        _mk_leg("trip", "no", L_e=0.48, m_e=0.50, L_x=0.52, m_x=0.50, game="g2"),
    ]))
    check("world S (spread only) ", ws, want_exec=-0.80, want_alpha=0.0)

    # World P: pure prediction loss. Zero concession; yes ride from mid 0.60
    # settles 0 -> alpha -6.0, exec 0.
    wp = finish(pd.DataFrame([
        _mk_leg("ride", "yes", L_e=0.60, m_e=0.60, settlement=0),
        _mk_leg("trip", "no", L_e=0.40, m_e=0.40, L_x=0.50, m_x=0.50, game="g2"),
    ]))
    check("world P (prediction only)", wp, want_exec=0.0, want_alpha=-7.0)

    # World M: mixed, both causes injected with known sizes.
    #   trip yes: c_e=0.01, c_x=0.02, mid drift +0.05 -> pnl/ct=+0.02
    #   ride no : c_e=0.03, settlement 1 vs m_e 0.30 -> alpha/ct=-0.70
    wm = finish(pd.DataFrame([
        _mk_leg("trip", "yes", L_e=0.41, m_e=0.40, L_x=0.43, m_x=0.45),
        _mk_leg("ride", "no", L_e=0.27, m_e=0.30, settlement=1, game="g2"),
    ]))
    check("world M (mixed, known)  ", wm, want_exec=-0.60, want_alpha=-6.50)

    # Null world: one winning and one losing drift of equal size, zero
    # concession everywhere; every component must read exactly 0.
    wn = finish(pd.DataFrame([
        _mk_leg("trip", "yes", L_e=0.50, m_e=0.50, L_x=0.55, m_x=0.55),
        _mk_leg("trip", "yes", L_e=0.50, m_e=0.50, L_x=0.45, m_x=0.45, game="g2"),
    ]))
    check("world 0 (null)          ", wn, want_exec=0.0, want_alpha=0.0)

    # AS instrument on a synthetic tape: inject +2c drift against an entry at
    # +60s and 0 drift on a control; the measured drift must read them back.
    con = duckdb.connect()
    base = pd.Timestamp("2026-01-01 00:00:00+00:00")
    ticks = pd.DataFrame([
        dict(event_slug="g1", market_slug="A", captured_at=base, best_bid=0.49,
             best_ask=0.51, is_live=True),
        dict(event_slug="g1", market_slug="A",
             captured_at=base + pd.Timedelta(seconds=60), best_bid=0.47,
             best_ask=0.49, is_live=True),
        dict(event_slug="g2", market_slug="B", captured_at=base, best_bid=0.49,
             best_ask=0.51, is_live=True),
        dict(event_slug="g2", market_slug="B",
             captured_at=base + pd.Timedelta(seconds=60), best_bid=0.49,
             best_ask=0.51, is_live=True),
    ])
    ticks["two_sided"] = True
    ticks["mid"] = (ticks.best_bid + ticks.best_ask) / 2
    con.register("ticks", ticks)
    fills = pd.DataFrame([
        dict(event_slug="g1", market_slug="A", filled_at=base, m_e=0.50, s=1,
             role="entry"),
        dict(event_slug="g2", market_slug="B", filled_at=base, m_e=0.50, s=1,
             role="entry"),
    ])
    fills["tneg"] = -(fills.filled_at.map(pd.Timestamp.timestamp) + 60)
    con.register("as_fills", fills)
    r = con.execute("""
        SELECT f.event_slug, -f.s * (t.mid - f.m_e) against
        FROM as_fills f ASOF JOIN
             (SELECT market_slug, mid, captured_at, -epoch(captured_at) neg_t
              FROM ticks WHERE two_sided) t
          ON f.market_slug = t.market_slug AND t.neg_t <= f.tneg
    """).df().set_index("event_slug").against
    ok = abs(r["g1"] - 0.02) < 1e-9 and abs(r["g2"]) < 1e-9
    print(f"  AS instrument: injected +2c read {r['g1']:+.4f}, null read "
          f"{r['g2']:+.4f} -> {'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    # Withdrawal-autopsy scan (6b) on a synthetic tape, running the SAME SQL
    # the real section runs: one order whose limit is reached only AFTER
    # withdrawal, one never reached, one crossed while resting (the control
    # the real run expects to read ~0).
    wd = duckdb.connect()
    S = pd.Timedelta
    wticks = pd.DataFrame([
        dict(event_slug="g1", market_slug="A", captured_at=base + S(seconds=10), mid=0.45),
        dict(event_slug="g1", market_slug="A", captured_at=base + S(seconds=90), mid=0.39),
        dict(event_slug="g1", market_slug="B", captured_at=base + S(seconds=10), mid=0.45),
        dict(event_slug="g1", market_slug="B", captured_at=base + S(seconds=90), mid=0.45),
        dict(event_slug="g1", market_slug="C", captured_at=base + S(seconds=20), mid=0.61),
        dict(event_slug="g1", market_slug="C", captured_at=base + S(seconds=90), mid=0.55),
    ])
    wticks["two_sided"] = True
    wticks["is_live"] = True
    wunf = pd.DataFrame([
        dict(id=1, event_slug="g1", market_slug="A", side="yes",
             limit_price=0.40, decided_at=base, withdrawn_at=base + S(seconds=30)),
        dict(id=2, event_slug="g1", market_slug="B", side="yes",
             limit_price=0.40, decided_at=base, withdrawn_at=base + S(seconds=30)),
        dict(id=3, event_slug="g1", market_slug="C", side="no",
             limit_price=0.60, decided_at=base, withdrawn_at=base + S(seconds=30)),
    ])
    wd.register("ticks", wticks)
    wd.register("unf_df", wunf)
    scan = wd.execute(WITHDRAWAL_SCAN_SQL).df().set_index("id")
    ok = (scan.loc[1, "crossed_while_resting"] == 0
          and scan.loc[1, "would_fill_later"] == 1
          and abs(scan.loc[1, "s_to_fill"] - 60) < 1e-9
          and scan.loc[2, "crossed_while_resting"] == 0
          and scan.loc[2, "would_fill_later"] == 0
          and scan.loc[3, "crossed_while_resting"] == 1
          and scan.loc[3, "would_fill_later"] == 0)
    print(f"  withdrawal scan: fill-after-pull read "
          f"{int(scan.loc[1, 'would_fill_later'])} (want 1), never-reached "
          f"read {int(scan.loc[2, 'would_fill_later'])} (want 0), "
          f"resting-cross control read "
          f"{int(scan.loc[3, 'crossed_while_resting'])} (want 1) -> "
          f"{'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    ap.add_argument("--ticks", type=Path, default=DEFAULT_TICKS)
    ap.add_argument("--resolved", type=Path, default=DEFAULT_RESOLVED)
    ap.add_argument("--selftest", action="store_true",
                    help="run the mutation test only (no real data touched)")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    print("PULSE execution decomposition — track D, 2026-09-01 wave")
    print(f"pins: {args.decisions.name}, {args.ticks.name}, {args.resolved.name}")
    print("reproduce: .venv/bin/python analysis/pulse_execution_decomposition.py")
    print("\nRun --selftest first if you are editing this file. Everything "
          "below is IN-SAMPLE and DESCRIPTIVE.")

    if selftest() != 0:      # never print real numbers off a broken instrument
        print("ABORT: mutation test failed; numbers would be untrustworthy")
        return 1

    dec = pd.read_csv(args.decisions, parse_dates=[
        "created_at", "decided_at", "filled_at", "withdrawn_at", "settled_at"])
    resolved = pd.read_csv(args.resolved)

    legs, anomalies = build_legs(dec)
    exits_filled = dec[(dec.action == "exit") & dec.filled_at.notna()]

    section_composition(dec)
    print(f"\nanomalies: {anomalies}")

    section_ledger(legs)
    section_decomposition(legs)
    section_fees(legs)

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    markets = sorted(dec.market_slug.dropna().unique())
    load_ticks(con, args.ticks, markets)
    section_mid_sanity(con, legs, exits_filled)
    section_adverse_selection(con, legs, exits_filled)
    section_unfilled(dec, legs, resolved)
    section_withdrawal_autopsy(con, dec, resolved)
    section_exit_availability(con, dec, legs)

    hr("STANDING STATEMENTS")
    print("Multiple comparisons: this run prints dozens of intervals across "
          "market types, price bands, versions and horizons; at 95%, several "
          "nominally significant cells are expected by chance. Ranking is "
          "mechanism plausibility + effect size + robustness, never p-value.")
    print("Fill-rule bound: every number above inherits the mid-cross fill "
          "assumption stated at the top of this file. Losses are trustworthy; "
          "profits are upper bounds; unfilled-entry counterfactuals are "
          "directional only.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
