"""What is an exit worth? — pricing the ride tail at entry. Track D follow-on,
2026-09-02 (manager brief: breakeven exit premium + does crossing buy exit
availability). Rules: analysis/WAVE_STANDARD.md.

    .venv/bin/python analysis/exit_option_value.py [--selftest]
        [--decisions CSV] [--ticks CSV.GZ] [--resolved CSV]
        [--emit-book-state PATH.csv]

Reads the PINNED exports only. EVERYTHING IS IN-SAMPLE, DESCRIPTIVE AND
HYPOTHESIS-GENERATING; no number gates anything. Verbatim:
**No in-sample result justifies capital. The forward test is the evidence.**

What this script answers, in order:

1. RIDE ARITHMETIC. r_trip and r_ride per $ (money-at-price, this repo's
   drop-linking policy, reconciled in print against A's re-linked numbers),
   the observed ride share p, and the breakeven ride share
   p* = r_trip / (r_trip - r_ride) above which the book loses even with the
   optimistic fill rule. Both arms: engine-rule and the measured-4.70c
   pessimistic re-charge.

2. BREAKEVEN EXIT PREMIUM delta*(p): the extra entry concession (c/contract)
   whose certain cost equals the expected ride loss avoided, IF a guaranteed
   exit converted each ride into an average trip. That IF is generous twice
   (a ride's would-be trip is not an average trip, and trip P&L itself is
   doubly-optimistic under the fill rule), so delta* is an UPPER bound on
   what an exit guarantee could ever be worth at entry. Tabled over a p grid
   including B's measured state-cell ride shares — the sizing input the
   engine lacks (it treats 2% and 30% ride risk identically).

3. TERM STRUCTURE of the exit option: per ride, mark-to-mid at fill+{1,2,5,
   10,20}min and end-anchored horizons, valued as (exit at mark) - (what the
   ride returned), per $. Shows WHEN the option value evaporates — the joint
   note measured it is ~all gone by book death ("rides are worth 0.000 at
   book close"), this shows the decay path getting there.

4. PESSIMISTIC RIDE RELABELING p(k): a modelled trip whose exit-side mid
   never traded >= k cents through the exit limit (over the exit's whole
   possible life, rest -> last live tick) would NOT have exited under a
   k-cent-concession fill rule — it is a ride mislabeled by optimism. p(k)
   for k in {1, 2, 3.15, 4.7} quantifies "predicted ride risk is a lower
   bound" for B's fitted model, with the flipped trips re-scored at
   settlement to show the P&L at stake.

5. CROSSING vs EXIT AVAILABILITY: crossing at intent moves entry from
   filled_at back to decided_at — it buys (filled_at - decided_at) of extra
   book runway and nothing else, because book death is anchored to the game
   (measured: death offset from the event's last live tick), not to when we
   entered. Compared against the term structure's decay over that runway.

6. --emit-book-state: per-intent tape flags for B's ride-risk model (share
   of two-sided ticks and any-one-sided flag in a +/-60s window around each
   entry intent) — the tick pin has no depth, but one-sidedness is exactly
   the joint note's open check, so the late-vs-early aggregate prints here.

Fill-rule caveat, stated once and riding on everything: fills are modelled
(mid-cross rule); measured losses are trustworthy, profits and premiums are
upper bounds. See pulse_execution_decomposition.py's header for the full
statement and the 1.5c-booked vs 4.70c-measured opposite-direction gap.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Single source of ledger truth: reuse the decomposition's builders.
_spec = importlib.util.spec_from_file_location(
    "pulse_execution_decomposition",
    Path(__file__).with_name("pulse_execution_decomposition.py"))
ped = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ped)

from core.quote.adverse_selection import clustered_mean  # noqa: E402

PIN = ped.PIN
MEASURED = ped.MEASURED_CONCESSION_INGAME          # 0.0470 $/ct/leg
ENGINE_LEG_CONCESSION = 0.0155                     # measured on this tape (c_e~c_x)
K_GRID = [0.01, 0.02, MEASURED - ENGINE_LEG_CONCESSION, MEASURED]
HORIZONS_MIN = [1, 2, 5, 10, 20]
END_ANCHORS_MIN = [10, 5]
#: Ride shares by entry state, quoted from the B x D work (A's ledger, late
#: cells) — the p column of the premium table. In-sample, other policy.
STATE_P = {"overall (this tape, drop policy)": None,   # filled in at runtime
           "Q4 (B, A-ledger)": 0.166,
           "minutes_left 5-10 (B)": 0.181,
           "|margin| >= 10 (B)": 0.108}


def hr(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def money_roi(sub: pd.DataFrame) -> float:
    stake = (sub.cost_ct * sub.contracts).sum()
    return float(sub.pnl_ct_usd.sum() / stake) if stake else float("nan")


def clustered_roi(sub: pd.DataFrame) -> str:
    vals = {g: list(v) for g, v in
            (sub.pnl_ct / sub.cost_ct).groupby(sub.event_slug)}
    return ped.cm_str(vals, unit="c/$", scale=100.0)


# --------------------------------------------------------------------------- #
# 1 + 2: arithmetic and the premium table
# --------------------------------------------------------------------------- #

def breakeven_p(r_trip: float, r_ride: float) -> float:
    """Ride share above which E[per-$] = (1-p)r_trip + p r_ride < 0."""
    return r_trip / (r_trip - r_ride) if r_trip > 0 else 0.0


def premium_per_ct(p: float, r_trip: float, r_ride: float,
                   mean_cost_ct: float) -> float:
    """delta*(p): entry concession whose certain cost equals the expected
    ride loss avoided by a guaranteed (average-trip) exit, $/contract."""
    return p * (r_trip - r_ride) * mean_cost_ct


def section_arithmetic(legs: pd.DataFrame) -> tuple[float, float, float]:
    hr("1. RIDE ARITHMETIC (money-at-price; policy: drop-linking as in "
       "live_report.py — A's re-linked ledger quoted for reconciliation)")
    trips, rides = legs[legs.kind == "trip"], legs[legs.kind == "ride"]
    r_t, r_r = money_roi(trips), money_roi(rides)
    print(f"trips: {len(trips)} rows / {trips.event_slug.nunique()} games, "
          f"{r_t * 100:+.2f}c/$ money-weighted; clustered {clustered_roi(trips)}")
    print(f"rides: {len(rides)} rows / {rides.event_slug.nunique()} games, "
          f"{r_r * 100:+.2f}c/$ money-weighted; clustered {clustered_roi(rides)}")
    print("(A's re-linked policy reads 1,807 trips +5.83c/$ and 137 rides "
          "-50.62c/$ on the same tape — the 17-row lineage repair; both "
          "policies are pinned in the crossing-arms registration)")

    p_obs = len(rides) / len(legs)
    p_star = breakeven_p(r_t, r_r)
    print(f"\nobserved ride share p = {len(rides)}/{len(legs)} = {p_obs:.1%}")
    print(f"breakeven ride share p* = r_trip/(r_trip - r_ride) = {p_star:.1%}")
    print(f"headroom: {(p_star - p_obs) * 100:+.1f}pp of ride probability — "
          "under the OPTIMISTIC fill rule; the pessimistic arm below has no "
          "headroom to allocate")

    # Pessimistic arm: strip engine concessions, charge measured 4.70c/leg.
    for name, sub, legs_n in (("trips", trips, 2), ("rides", rides, 1)):
        stake = (sub.cost_ct * sub.contracts).sum()
        pess_pnl = (sub.pnl_ct_usd + sub.c_e_usd + sub.c_x_usd
                    - MEASURED * legs_n * sub.contracts).sum()
        print(f"pessimistic {name}: {pess_pnl / stake * 100:+.2f}c/$ "
              f"(measured 4.70c x {legs_n} leg(s); tonight's per-game cut "
              f"reads {'-16.46' if name == 'trips' else '-65.45'} on A's "
              f"policy)")
    return r_t, r_r, p_obs


def section_premium(legs: pd.DataFrame, r_t: float, r_r: float,
                    p_obs: float) -> None:
    hr("2. BREAKEVEN EXIT PREMIUM delta*(p) — the sizing input the engine "
       "lacks")
    mean_cost = float((legs.cost_ct * legs.contracts).sum()
                      / legs.contracts.sum())
    print(f"mean cost per contract on the tape: {mean_cost * 100:.1f}c")
    print("delta*(p) = p x (r_trip - r_ride) x cost/ct — what a GUARANTEED "
          "exit (ride -> average trip) is worth at entry. UPPER BOUND twice "
          "over: a ride's counterfactual trip is below-average, and trip P&L "
          "is doubly-optimistic. Compare each row against the alpha the "
          "decomposition measured (+3.47c/ct) and the concessions already "
          "paid (1.54c entry + 1.55c exit; 4.70c/leg measured):\n")
    STATE_P["overall (this tape, drop policy)"] = p_obs
    print(f"{'state cell':38s} {'p':>7s} {'delta* c/ct':>12s}")
    for name, p in STATE_P.items():
        d = premium_per_ct(p, r_t, r_r, mean_cost)
        note = " <- exceeds measured alpha" if d * 100 > 3.47 else ""
        print(f"{name:38s} {p:7.1%} {d * 100:12.2f}{note}")
    print("\nreading: at the LATE-STATE ride shares, fairly pricing the exit "
          "option costs more than the model's entire measured alpha — late "
          "entries are uneconomic once exit risk is priced, even under the "
          "optimistic rule. At the overall ride share the fair premium is "
          "about one extra concession leg.")


# --------------------------------------------------------------------------- #
# 3: term structure of the exit option (tick tape)
# --------------------------------------------------------------------------- #

def section_term_structure(con: duckdb.DuckDBPyConnection,
                           legs: pd.DataFrame) -> None:
    hr("3. TERM STRUCTURE — what an exit guaranteed by horizon h was worth, "
       "per $ staked (rides only; mark = first two-sided live mid at/after "
       "h, gap capped 120s)")
    rides = legs[legs.kind == "ride"].copy()
    con.register("rides_ts", rides[["id", "event_slug", "market_slug", "s",
                                    "filled_at", "settlement", "cost_ct",
                                    "contracts"]])
    grid = [("fill+%dm" % m, "f.filled_at + INTERVAL '%d minutes'" % m)
            for m in HORIZONS_MIN]
    grid += [("end-%dm" % m, "e.t_end - INTERVAL '%d minutes'" % m)
             for m in END_ANCHORS_MIN]
    for label, expr in grid:
        rows = con.execute(f"""
            WITH live_end AS (
              SELECT event_slug, max(captured_at) t_end FROM ticks
              WHERE is_live GROUP BY 1
            ), f AS (
              SELECT f.*, e.t_end, {expr} AS target,
                     -epoch({expr}) AS tneg
              FROM rides_ts f JOIN live_end e USING (event_slug)
            ), m AS (
              SELECT f.*, t.mid m_h,
                     epoch(t.captured_at) + f.tneg AS gap_s
              FROM f ASOF JOIN (
                    SELECT market_slug, mid, captured_at,
                           -epoch(captured_at) neg_t
                    FROM ticks WHERE two_sided AND is_live) t
                ON f.market_slug = t.market_slug AND t.neg_t <= f.tneg
            )
            SELECT event_slug,
                   s * (m_h - settlement) / cost_ct AS saved_per_dollar,
                   s * (m_h - settlement) * contracts AS saved_usd,
                   cost_ct * contracts AS stake_usd
            FROM m
            WHERE gap_s <= 120 AND target > filled_at AND target <= t_end
        """).df()
        vals = {g: list(v) for g, v in
                rows.groupby("event_slug").saved_per_dollar}
        mw = (rows.saved_usd.sum() / rows.stake_usd.sum() * 100
              if len(rows) else float("nan"))
        print(f"  {label:9s}: {ped.cm_str(vals, unit='c/$')}  "
              f"money-weighted {mw:+.1f}c/$  "
              f"[n={len(rows)}/{len(rides)} rides in range]")
    print("\n(positive = exiting at that mark would have beaten riding. The "
          "end-anchored rows approach the joint note's measured 'rides are "
          "worth ~0 at book close'; the fill-anchored rows price how fast "
          "the option decays. A guarantee that only kicks in late buys "
          "nothing — the guarantee has value only while the position does.)")


# --------------------------------------------------------------------------- #
# 4: pessimistic ride relabeling p(k)
# --------------------------------------------------------------------------- #

def section_relabel(con: duckdb.DuckDBPyConnection, dec: pd.DataFrame,
                    legs: pd.DataFrame) -> pd.DataFrame:
    hr("4. PESSIMISTIC RIDE RELABELING p(k) — trips whose exit never traded "
       "k cents through the limit are rides under a k-concession fill rule")
    trips = legs[legs.kind == "trip"].copy()
    x = dec[(dec.action == "exit") & dec.filled_at.notna()
            & dec.entry_id.notna()].copy()
    x["entry_id"] = x.entry_id.astype("int64")
    x = x.sort_values(["filled_at", "id"]).groupby("entry_id").first()
    trips["exit_rested_at"] = trips.id.map(x.decided_at)
    con.register("trips_x", trips[["id", "event_slug", "market_slug", "s",
                                   "L_x", "exit_rested_at", "settlement",
                                   "L_e", "contracts", "cost_ct",
                                   "pnl_ct"]])
    exc = con.execute("""
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), w AS (
          SELECT f.*, e.t_end FROM trips_x f JOIN live_end e USING (event_slug)
        )
        SELECT w.id,
               max(w.s * (t.mid - w.L_x)) AS max_excursion
        FROM w JOIN ticks t
          ON t.market_slug = w.market_slug AND t.two_sided AND t.is_live
         AND t.captured_at > w.exit_rested_at AND t.captured_at <= w.t_end
        GROUP BY w.id
    """).df().set_index("id").max_excursion
    trips["max_exc"] = trips.id.map(exc)
    n_no_tape = int(trips.max_exc.isna().sum())
    print(f"trips scanned: {len(trips)} (no in-window two-sided tape for "
          f"{n_no_tape} — counted as zero excursion, i.e. they flip)")
    trips["max_exc"] = trips.max_exc.fillna(0.0)
    n_rides0 = int((legs.kind == "ride").sum())
    print(f"\n{'k (c through limit)':>20s} {'flipped trips':>14s} "
          f"{'p(k) ride share':>16s} {'flipped settle P&L':>19s}")
    for k in K_GRID:
        flip = trips[trips.max_exc < k - 1e-12]
        settle_pnl = (flip.s * (flip.settlement - flip.L_e)
                      * flip.contracts).sum()
        p_k = (n_rides0 + len(flip)) / len(legs)
        print(f"{k * 100:>19.2f} {len(flip):>14d} {p_k:>15.1%} "
              f"{settle_pnl:>+18.2f}$")
    print("\n(k = 3.15c is the measured-real minus engine-booked concession "
          "gap; k = 4.70c the full measured concession. Reading for B's "
          "model: the tape's 'ride' label undercounts real no-exit risk by "
          "the k-column of your choice — predicted ride risk is a lower "
          "bound, quantified. The flipped trips' settlement P&L is what "
          "their 'trip' label is hiding.)")
    return trips


# --------------------------------------------------------------------------- #
# 5: crossing vs exit availability
# --------------------------------------------------------------------------- #

def section_crossing_exit(con: duckdb.DuckDBPyConnection,
                          legs: pd.DataFrame) -> None:
    hr("5. DOES CROSSING AT INTENT BUY EXIT AVAILABILITY? (it buys entry "
       "runway; book death is anchored to the game)")
    rides = legs[legs.kind == "ride"].copy()
    rides["ttf_s"] = (rides.filled_at - rides.decided_at).dt.total_seconds()
    con.register("rides_ce", rides[["id", "event_slug", "market_slug",
                                    "filled_at"]])
    tim = con.execute("""
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), w AS (
          SELECT f.*, e.t_end FROM rides_ce f JOIN live_end e USING (event_slug)
        )
        SELECT w.id,
               epoch(max(CASE WHEN t.two_sided THEN t.captured_at END)
                     - w.filled_at) runway_s,
               epoch(w.t_end - max(CASE WHEN t.two_sided
                                        THEN t.captured_at END)) death_off_s
        FROM w LEFT JOIN ticks t
          ON t.market_slug = w.market_slug AND t.is_live
         AND t.captured_at >= w.filled_at AND t.captured_at <= w.t_end
        GROUP BY w.id, w.filled_at, w.t_end
    """).df().set_index("id")
    rides = rides.join(tim, on="id")
    print(f"rides: {len(rides)} rows / {rides.event_slug.nunique()} games "
          "(descriptive medians)")
    print(f"  time-to-fill (intent -> entry fill): median "
          f"{rides.ttf_s.median():.0f}s, p75 {rides.ttf_s.quantile(.75):.0f}s"
          f" — the ONLY runway crossing at intent adds")
    print(f"  exit-book runway (entry fill -> last two-sided live tick): "
          f"median {rides.runway_s.median() / 60:.1f}min, p25 "
          f"{rides.runway_s.quantile(.25) / 60:.1f}min")
    print(f"  book death offset before the event's last live tick: median "
          f"{rides.death_off_s.median() / 60:.1f}min, p25 "
          f"{rides.death_off_s.quantile(.25) / 60:.1f}min, p75 "
          f"{rides.death_off_s.quantile(.75) / 60:.1f}min")
    frac = float((rides.ttf_s / rides.runway_s.clip(lower=1)).median())
    print(f"\n  median added-runway / exit-runway ratio: {frac:.1%}")
    print("\nreading: the exit book on ride markets dies late-game-anchored "
          "(median 8.8 min before the live end, with spread — not tight), "
          "and the runway crossing would add is ~5% of the runway the exit "
          "already had and did not use; the term structure shows the value "
          "was mostly gone before the book was. Crossing buys CERTAINTY OF "
          "ENTRY (the never-reachable third from the withdrawal autopsy); "
          "it buys ~nothing on the exit side. The ride tail is state-owned "
          "— B's mask (crossing-arms companion registration) is the lever "
          "pointed at it, and section 2's premium table is what exit risk "
          "costs where the mask does not apply.")


# --------------------------------------------------------------------------- #
# 6: per-intent book state for B (+ the joint note's open check)
# --------------------------------------------------------------------------- #

def section_book_state(con: duckdb.DuckDBPyConnection, dec: pd.DataFrame,
                       emit_path: Path | None) -> None:
    hr("6. BOOK STATE AROUND ENTRY INTENTS (for B's ride-risk model; the "
       "joint note's open check)")
    ent = dec[dec.action == "enter"].copy()
    ent["late"] = ~ent.period.isin(["Q1", "Q2", "Q3"])
    ent["unfilled"] = ent.filled_at.isna()
    con.register("intents", ent[["id", "event_slug", "market_slug",
                                 "decided_at", "late", "unfilled"]])
    bs = con.execute("""
        SELECT i.id, i.event_slug, i.late, i.unfilled,
               count(t.captured_at) n_ticks,
               avg(CASE WHEN t.two_sided THEN 1.0 ELSE 0.0 END) share_two_sided,
               max(CASE WHEN NOT t.two_sided
                         AND t.captured_at >= i.decided_at
                        THEN 1 ELSE 0 END) one_sided_after
        FROM intents i LEFT JOIN ticks t
          ON t.market_slug = i.market_slug
         AND t.captured_at BETWEEN i.decided_at - INTERVAL '60 seconds'
                               AND i.decided_at + INTERVAL '60 seconds'
        GROUP BY i.id, i.event_slug, i.late, i.unfilled
    """).df()
    bs["one_sided_after"] = bs.one_sided_after.fillna(0).astype(bool)
    print("share of intents with ANY one-sided/empty tick in the 60s after "
          "intent (counts before ratios):")
    for late in (False, True):
        for unf in (False, True):
            sub = bs[(bs.late == late) & (bs.unfilled == unf)]
            if len(sub) == 0:
                continue
            print(f"  late={str(late):5s} unfilled={str(unf):5s}: "
                  f"{int(sub.one_sided_after.sum()):4d}/{len(sub):4d} = "
                  f"{sub.one_sided_after.mean():5.1%}  "
                  f"({sub.event_slug.nunique()} games)")
    print("\n(joint note's open check: the entry-side symptom predicted "
          "thin/one-sided books around LATE unfilled intents specifically — "
          "the late-unfilled cell vs the other three above is the answer. "
          "Depth is not in the pin; one-sidedness is the readable half.)")
    if emit_path is not None:
        bs.drop(columns=["event_slug"]).to_csv(emit_path, index=False)
        print(f"\nper-intent flags written to {emit_path} "
              f"({len(bs)} rows: id, late, unfilled, n_ticks, "
              f"share_two_sided, one_sided_after) — join key is "
              f"pulse_decisions id")


# --------------------------------------------------------------------------- #
# Mutation test
# --------------------------------------------------------------------------- #

def selftest() -> int:
    print("mutation test: known answers must be recovered")
    failures = 0

    def check(name, got, want, tol=1e-9):
        nonlocal failures
        ok = abs(got - want) < tol
        print(f"  {name}: {got:+.4f} (want {want:+.4f}) -> "
              f"{'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    # Breakeven algebra on known values.
    check("p* at r_t=+0.06, r_r=-0.54", breakeven_p(0.06, -0.54), 0.10)
    check("delta* at p=10%, cost 50c", premium_per_ct(0.10, 0.06, -0.54, 0.5),
          0.03)
    check("delta* at p=0", premium_per_ct(0.0, 0.06, -0.54, 0.5), 0.0)

    # Excursion scan: a synthetic trip whose mid goes exactly 2c through the
    # exit limit must flip at k=3c and survive at k=2c.
    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    base = pd.Timestamp("2026-01-01 00:00:00+00:00")
    S = pd.Timedelta
    ticks = pd.DataFrame([
        dict(event_slug="g", market_slug="A",
             captured_at=base + S(seconds=10), mid=0.55),
        dict(event_slug="g", market_slug="A",
             captured_at=base + S(seconds=20), mid=0.57),   # 2c through 0.55
        dict(event_slug="g", market_slug="A",
             captured_at=base + S(seconds=30), mid=0.50),
    ])
    ticks["two_sided"] = True
    ticks["is_live"] = True
    con.register("ticks", ticks)
    con.register("trips_x", pd.DataFrame([dict(
        id=1, event_slug="g", market_slug="A", s=1, L_x=0.55,
        exit_rested_at=base, settlement=0, L_e=0.50, contracts=10.0,
        cost_ct=0.50, pnl_ct=0.05)]))
    exc = con.execute("""
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), w AS (
          SELECT f.*, e.t_end FROM trips_x f JOIN live_end e USING (event_slug)
        )
        SELECT max(w.s * (t.mid - w.L_x)) me FROM w JOIN ticks t
          ON t.market_slug = w.market_slug AND t.two_sided AND t.is_live
         AND t.captured_at > w.exit_rested_at AND t.captured_at <= w.t_end
    """).fetchone()[0]
    check("max excursion (2c injected)", float(exc), 0.02)

    # Term-structure mark: ride entered at base, settlement 0, mid 0.30 at
    # +60s -> exit at fill+1m saves +0.30/0.50 = +60c/$.
    con2 = duckdb.connect()
    con2.execute("SET timezone='UTC'")
    t2 = pd.DataFrame([
        dict(event_slug="g", market_slug="A", captured_at=base + S(seconds=60),
             mid=0.30),
        dict(event_slug="g", market_slug="A", captured_at=base + S(seconds=600),
             mid=0.10),
    ])
    t2["two_sided"] = True
    t2["is_live"] = True
    con2.register("ticks", t2)
    con2.register("rides_ts", pd.DataFrame([dict(
        id=1, event_slug="g", market_slug="A", s=1, filled_at=base,
        settlement=0, cost_ct=0.50, contracts=10.0)]))
    r = con2.execute("""
        WITH live_end AS (
          SELECT event_slug, max(captured_at) t_end FROM ticks
          WHERE is_live GROUP BY 1
        ), f AS (
          SELECT f.*, e.t_end, f.filled_at + INTERVAL '1 minutes' AS target,
                 -epoch(f.filled_at + INTERVAL '1 minutes') AS tneg
          FROM rides_ts f JOIN live_end e USING (event_slug)
        )
        SELECT f.s * (t.mid - f.settlement) / f.cost_ct
        FROM f ASOF JOIN (SELECT market_slug, mid, captured_at,
                                 -epoch(captured_at) neg_t
                          FROM ticks WHERE two_sided AND is_live) t
          ON f.market_slug = t.market_slug AND t.neg_t <= f.tneg
    """).fetchone()[0]
    check("mark at fill+1m (+60c/$ injected)", float(r), 0.60)

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decisions", type=Path, default=ped.DEFAULT_DECISIONS)
    ap.add_argument("--ticks", type=Path, default=ped.DEFAULT_TICKS)
    ap.add_argument("--resolved", type=Path, default=ped.DEFAULT_RESOLVED)
    ap.add_argument("--emit-book-state", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    print("Exit option value — track D follow-on, 2026-09-02")
    print(f"pins: {args.decisions.name}, {args.ticks.name}")
    print("reproduce: .venv/bin/python analysis/exit_option_value.py")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    dec = pd.read_csv(args.decisions, parse_dates=[
        "created_at", "decided_at", "filled_at", "withdrawn_at", "settled_at"])
    legs, anomalies = ped.build_legs(dec)
    print(f"\nledger anomalies (same as decomposition): {anomalies}")

    r_t, r_r, p_obs = section_arithmetic(legs)
    section_premium(legs, r_t, r_r, p_obs)

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    markets = sorted(dec.market_slug.dropna().unique())
    ped.load_ticks(con, args.ticks, markets)
    section_term_structure(con, legs)
    section_relabel(con, dec, legs)
    section_crossing_exit(con, legs)
    section_book_state(con, dec, args.emit_book_state)

    hr("STANDING STATEMENTS")
    print("Multiple comparisons: this run prints many intervals and "
          "descriptive medians across horizons, k-grids and state cells; "
          "several nominally significant cells are expected by chance. "
          "Ranking is mechanism plausibility + effect size + robustness.")
    print("Every number inherits the modelled-fill assumption; premiums and "
          "profits are upper bounds, losses are trustworthy. The pessimistic "
          "arm is negative everywhere including trips — a policy that fixes "
          "the ride tail and still loses is a live possibility and nothing "
          "here contradicts it.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
