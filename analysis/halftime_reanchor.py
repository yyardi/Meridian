"""D2 — the halftime re-anchor, descriptive pass (speed-1 item 3).

    .venv/bin/python analysis/halftime_reanchor.py [--selftest] [--ticks GZ]

One script on the pinned tape (34 games), per the round-3 disposition:
scored against BOTH targets — the state-FV and the venue's own Q3
self-consistency — so the candidate can die honestly against wall 6 rather
than surviving on a target choice. F8-free window (the break: nothing races
our feed). IN-SAMPLE, DESCRIPTIVE, HYPOTHESIS-GENERATING; the kill condition
is printed with the results. Verbatim:
**No in-sample result justifies capital. The forward test is the evidence.**

Tape fact that reshapes the candidate, found before designing (counts before
ratios): THE BOOKS QUOTE STRAIGHT THROUGH HALFTIME — 1,522,505 HT rows in
the pin, 99.3% two-sided. There is no closed-book "reopen". So the
measurable objects are:

  J   = mid(first two-sided live Q3 tick) − mid(last two-sided live Q2 tick)
        — the venue's own break-window repricing, done with ~15 minutes and
        zero clock pressure;
  D_h = mid(Q3open + h) − mid(Q3open), h ∈ {1, 2, 5, 10} min
        — the post-break drift the candidate says is predictable.

Instruments (each a game-clustered mean; sign conventions pinned here):

  TARGET B (venue self-consistency, model-free): D_h · sign(J).
    positive  = the break move CONTINUES into Q3 — the break repricing was
                an under-anchored partial step (the re-anchor signature);
    negative  = the break move REVERTS — overshoot;
    ≈ 0       = the break repricing was complete; no re-anchor.
    Rows with |J| < 0.005 (half a tick) carry no usable sign and are
    excluded from THIS instrument only, counted.

  TARGET A (state-FV): D_h · sign(G), G = FV_half − mid(Q3open), with
    FV_half computed by the repo's own verified functions at the halftime
    state (minutes_left = 20): core.live_fv.fair_value (winner),
    the engine's spread_fair_value (spread), core.live_totals_fv
    project_total → over_probability (totals, sigma = remaining_sigma(20)).
    positive = the market drifts toward our FV after the break.

  ANCHOR PROXIES, labelled (the pin has no pregame rows): the winner/spread
  pregame_price anchor is the event's EARLIEST live two-sided winner mid
  (Q1 open); the totals pregame_mu is the at-the-money rung (line whose
  earliest live mid is nearest 0.50). Both are stated wherever used; markets
  without a proxy are skipped and counted.

THE HARVEST BAR, printed beside every instrument: a drift is only a
candidate if it exceeds the crossing toll at the reopen — the median Q3-open
spread plus the 0.06·p(1−p) taker fee. Mid-drift below the toll is
spectator sport.

KILL CONDITION (the candidate's own round-1 text): if both instruments read
≈ 0 — or nonzero but below the toll — at every horizon, the reopen is
already fully state-priced and D2 DIES BY MEASUREMENT. Wall 6 asymmetry
carried: target A positive while target B is flat is NOT a pass for our FV —
it must survive the wall-6 reading (our FV is uninformative where it
disagrees) and would need target B's mechanism to corroborate.
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

from core.live_fv import DEFAULT_SIGMA, fair_value, parse_score  # noqa: E402
from core.live_totals_fv import (  # noqa: E402
    over_probability,
    project_total,
    remaining_sigma,
)
from core.pulse.live import spread_fair_value  # noqa: E402
from core.quote.adverse_selection import clustered_mean  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "pulse_execution_decomposition",
    Path(__file__).with_name("pulse_execution_decomposition.py"))
ped = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ped)

HORIZONS_MIN = [1, 2, 5, 10]
HALF_MINUTES_LEFT = 20.0     # WNBA regulation half remaining
HALF_ELAPSED = 20.0
J_MIN = 0.005                # below half a tick the break move has no sign
GAP_CAP_S = 120
MARKET_WINNER = "basketball_team_full_game_winner"
MARKET_TOTAL = "basketball_team_full_game_total"
MARKET_SPREAD = "basketball_team_full_game_spread"


def hr(t: str) -> None:
    print(f"\n{'=' * 78}\n{t}\n{'=' * 78}")


def cm_str(vals_by_game: dict[str, list[float]]) -> str:
    cm = clustered_mean(vals_by_game)
    if cm is None:
        return "n/a (<2 games)"
    return (f"{cm.mean * 100:+.2f} [{cm.lo * 100:+.2f}, {cm.hi * 100:+.2f}] "
            f"c (n={cm.n}, {cm.n_clusters} games)")


# --------------------------------------------------------------------------- #
# Extraction (SQL) — boundary points, marks, anchors
# --------------------------------------------------------------------------- #

def load(con: duckdb.DuckDBPyConnection, ticks_path: Path) -> None:
    con.execute(f"""
        CREATE TEMP TABLE tk AS
        SELECT event_slug, market_slug, sports_market_type, line,
               captured_at, event_period, event_score,
               best_ask - best_bid AS spread,
               (best_bid + best_ask) / 2.0 AS mid
        FROM read_csv('{ticks_path}')
        WHERE is_live AND best_bid IS NOT NULL AND best_ask IS NOT NULL
    """)
    con.execute("CREATE INDEX ix_tk ON tk(market_slug, captured_at)")


def extract(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per market with Q2-close and Q3-open points and forward marks."""
    base = con.execute("""
        WITH q2 AS (
          SELECT market_slug, arg_max(mid, captured_at) mid_q2close,
                 max(captured_at) t_q2close
          FROM tk WHERE event_period = 'Q2' GROUP BY 1
        ), q3 AS (
          SELECT market_slug, arg_min(mid, captured_at) mid_q3open,
                 arg_min(spread, captured_at) spread_q3open,
                 min(captured_at) t_q3open
          FROM tk WHERE event_period = 'Q3' GROUP BY 1
        ), ht AS (
          SELECT market_slug, count(*) n_ht FROM tk
          WHERE event_period = 'HT' GROUP BY 1
        ), meta AS (
          SELECT market_slug, any_value(event_slug) event_slug,
                 any_value(sports_market_type) mtype, any_value(line) line
          FROM tk GROUP BY 1
        )
        SELECT m.*, q2.mid_q2close, q2.t_q2close,
               q3.mid_q3open, q3.spread_q3open, q3.t_q3open,
               coalesce(ht.n_ht, 0) n_ht
        FROM meta m JOIN q2 USING (market_slug) JOIN q3 USING (market_slug)
        LEFT JOIN ht USING (market_slug)
    """).df()
    for h in HORIZONS_MIN:
        marks = con.execute(f"""
            WITH q3 AS (
              SELECT market_slug, min(captured_at) t0 FROM tk
              WHERE event_period = 'Q3' GROUP BY 1
            ), tgt AS (
              SELECT market_slug, t0 + INTERVAL '{h} minutes' AS target,
                     -epoch(t0 + INTERVAL '{h} minutes') AS tneg
              FROM q3
            )
            SELECT g.market_slug, t.mid AS mark,
                   epoch(t.captured_at) + g.tneg AS gap_s
            FROM tgt g ASOF JOIN (
                 SELECT market_slug, mid, captured_at,
                        -epoch(captured_at) AS neg_t FROM tk) t
              ON g.market_slug = t.market_slug AND t.neg_t <= g.tneg
        """).df()
        marks = marks[marks.gap_s <= GAP_CAP_S].set_index("market_slug").mark
        base[f"mark_{h}m"] = base.market_slug.map(marks)
    return base


def event_context(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per event: halftime score, winner anchor proxy, totals mu proxy."""
    score = con.execute("""
        SELECT event_slug, arg_max(event_score, captured_at) score_half
        FROM tk WHERE event_period = 'Q2' GROUP BY 1
    """).df().set_index("event_slug")
    anchor = con.execute(f"""
        SELECT event_slug, arg_min(mid, captured_at) winner_anchor
        FROM tk WHERE sports_market_type = '{MARKET_WINNER}' GROUP BY 1
    """).df().set_index("event_slug")
    mu = con.execute(f"""
        WITH first_mid AS (
          SELECT event_slug, line, arg_min(mid, captured_at) mid0
          FROM tk WHERE sports_market_type = '{MARKET_TOTAL}' GROUP BY 1, 2
        )
        SELECT event_slug, arg_min(line, abs(mid0 - 0.5)) mu_proxy
        FROM first_mid GROUP BY 1
    """).df().set_index("event_slug")
    ev = score.join(anchor, how="left").join(mu, how="left")
    parsed = ev.score_half.map(parse_score)
    ev["margin_half"] = parsed.map(lambda t: t[0] - t[1] if t else None)
    ev["total_half"] = parsed.map(lambda t: t[0] + t[1] if t else None)
    return ev


# --------------------------------------------------------------------------- #
# FV at the half (repo's own functions; proxies labelled)
# --------------------------------------------------------------------------- #

def fv_half(row, ev) -> float | None:
    e = ev.loc[row.event_slug] if row.event_slug in ev.index else None
    if e is None or pd.isna(e.margin_half):
        return None
    m = int(e.margin_half)
    if row.mtype == MARKET_WINNER:
        if pd.isna(e.winner_anchor):
            return None
        return fair_value(margin=m, minutes_left=HALF_MINUTES_LEFT,
                          pregame_price=float(e.winner_anchor),
                          sigma=DEFAULT_SIGMA)
    if row.mtype == MARKET_SPREAD:
        if pd.isna(e.winner_anchor) or pd.isna(row.line):
            return None
        return spread_fair_value(margin=m, minutes_left=HALF_MINUTES_LEFT,
                                 line=float(row.line),
                                 pregame_price=float(e.winner_anchor),
                                 sigma=DEFAULT_SIGMA)
    if row.mtype == MARKET_TOTAL:
        if pd.isna(e.mu_proxy) or pd.isna(row.line) or pd.isna(e.total_half):
            return None
        proj = project_total(pregame_mu=float(e.mu_proxy),
                             total_so_far=int(e.total_half),
                             elapsed_minutes=HALF_ELAPSED)
        return over_probability(projected_total=proj, line=float(row.line),
                                sigma=remaining_sigma(HALF_ELAPSED))
    return None


# --------------------------------------------------------------------------- #
# The instruments (pure python — mutation-tested)
# --------------------------------------------------------------------------- #

def instrument_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Per market: J, G, and D_h·sign columns for both targets."""
    out = df.copy()
    out["J"] = out.mid_q3open - out.mid_q2close
    out["G"] = out.fv_half - out.mid_q3open
    for h in HORIZONS_MIN:
        d = out[f"mark_{h}m"] - out.mid_q3open
        out[f"D_{h}m"] = d
        sj = out.J.map(lambda j: 0.0 if pd.isna(j) or abs(j) < J_MIN
                       else (1.0 if j > 0 else -1.0))
        out[f"B_{h}m"] = (d * sj).where(sj != 0.0)
        sg = out.G.map(lambda g: None if pd.isna(g)
                       else (1.0 if g > 0 else (-1.0 if g < 0 else 0.0)))
        out[f"A_{h}m"] = d * sg
    return out


def report_instrument(rows: pd.DataFrame, col_prefix: str, label: str) -> None:
    print(f"\n{label}")
    for h in HORIZONS_MIN:
        c = f"{col_prefix}_{h}m"
        sub = rows[rows[c].notna()]
        vals = {g: list(v) for g, v in sub.groupby("event_slug")[c]}
        print(f"  +{h:>2d}m: {cm_str(vals)}")


# --------------------------------------------------------------------------- #
# Mutation test
# --------------------------------------------------------------------------- #

def _mkt(id, game, q2, q3, marks, fv=None, mtype=MARKET_SPREAD, line=-4.5):
    r = dict(market_slug=f"m{id}", event_slug=game, mtype=mtype, line=line,
             mid_q2close=q2, mid_q3open=q3, spread_q3open=0.02, n_ht=10,
             fv_half=fv)
    for h, v in zip(HORIZONS_MIN, marks):
        r[f"mark_{h}m"] = v
    return r


def selftest() -> int:
    print("mutation test: known worlds must be read back")
    failures = 0

    def check(name, got, want, tol=1e-9):
        nonlocal failures
        ok = (got is None and want is None) or (
            got is not None and want is not None and abs(got - want) < tol)
        print(f"  {name}: {got} (want {want}) -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    # Efficient world: no break move, no drift -> every instrument 0/absent.
    eff = instrument_rows(pd.DataFrame([
        _mkt(1, "g1", 0.50, 0.50, [0.50] * 4, fv=0.55)]))
    check("efficient: B excluded (|J|<tick)",
          None if pd.isna(eff.B_1m.iloc[0]) else float(eff.B_1m.iloc[0]), None)
    check("efficient: A reads 0", float(eff.A_1m.iloc[0]), 0.0)

    # Re-anchor world: break did nothing (J=0), price then walks +5c toward
    # an FV 5c above the reopen -> A reads +5c at 5m; B stays excluded.
    rea = instrument_rows(pd.DataFrame([
        _mkt(1, "g1", 0.50, 0.50, [0.51, 0.52, 0.55, 0.55], fv=0.55)]))
    check("re-anchor: A at +5m", float(rea.A_5m.iloc[0]), 0.05)
    check("re-anchor: B excluded",
          None if pd.isna(rea.B_5m.iloc[0]) else float(rea.B_5m.iloc[0]), None)

    # Momentum world: break moved +2c and the move CONTINUES +3c -> B +3c.
    mom = instrument_rows(pd.DataFrame([
        _mkt(1, "g1", 0.50, 0.52, [0.53, 0.54, 0.55, 0.55], fv=None)]))
    check("momentum: B at +5m", float(mom.B_5m.iloc[0]), 0.03)

    # Overshoot world: break moved +2c and REVERTS -3c -> B -3c; and with
    # FV below the reopen, A reads the same reversion as +3c toward FV.
    ove = instrument_rows(pd.DataFrame([
        _mkt(1, "g1", 0.50, 0.52, [0.51, 0.50, 0.49, 0.49], fv=0.45)]))
    check("overshoot: B at +5m", float(ove.B_5m.iloc[0]), -0.03)
    check("overshoot: A at +5m (toward FV)", float(ove.A_5m.iloc[0]), 0.03)

    # FV dispatch wiring: a +10 halftime lead must price the winner above
    # its anchor; a big first half must price the over above 0.5.
    fvw = fair_value(margin=10, minutes_left=20.0, pregame_price=0.50)
    ok = fvw is not None and fvw > 0.75
    print(f"  fv wiring: winner up 10 at half -> {fvw:.3f} > 0.75 -> "
          f"{'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1
    proj = project_total(pregame_mu=160.0, total_so_far=95, elapsed_minutes=20.0)
    pov = over_probability(projected_total=proj, line=160.5,
                           sigma=remaining_sigma(20.0))
    ok = proj > 160.0 and pov > 0.5
    print(f"  fv wiring: hot half (95 pts) -> proj {proj:.1f} > 160, "
          f"P(over 160.5) {pov:.3f} > 0.5 -> {'ok' if ok else 'FAIL'}")
    failures += 0 if ok else 1

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=Path, default=ped.DEFAULT_TICKS)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    print("D2 halftime re-anchor — descriptive pass (speed-1 item 3)")
    print(f"pin: {args.ticks.name}")
    print("reproduce: .venv/bin/python analysis/halftime_reanchor.py")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    con = duckdb.connect()
    con.execute("SET timezone='UTC'")
    load(con, args.ticks)
    df = extract(con)
    ev = event_context(con)
    df["mtype"] = df.mtype.astype(str)
    df["fv_half"] = [fv_half(r, ev) for r in df.itertuples()]
    rows = instrument_rows(df)

    hr("0. COUNTS AND COMPOSITION (before any ratio)")
    print(f"markets with a Q2-close AND Q3-open two-sided live point: "
          f"{len(rows)} across {rows.event_slug.nunique()} games")
    comp = rows.groupby("mtype").agg(
        markets=("market_slug", "size"), games=("event_slug", "nunique"),
        ht_ticks_median=("n_ht", "median"),
        fv_ok=("fv_half", lambda s: s.notna().sum()),
        spread_q3_median=("spread_q3open", "median"))
    print(comp.to_string())
    print(f"(anchor proxies per module docstring; markets without one are the "
          f"fv_ok gap; HT is QUOTED — median HT ticks per market above)")
    med_spread = rows.spread_q3open.median()
    toll = med_spread + 0.06 * 0.5 * 0.5
    print(f"\nTHE HARVEST BAR: median Q3-open spread {med_spread * 100:.1f}c "
          f"+ taker fee at p=0.5 ({1.5:.1f}c) = ~{toll * 100:.1f}c of toll a "
          f"crossing capture must clear")

    hr("1. THE BREAK MOVE J = Q3 open - Q2 close (did the venue reprice "
       "during the break?)")
    for mtype, sub in rows.groupby("mtype"):
        vals = {g: list(v) for g, v in sub.groupby("event_slug").J}
        print(f"  {mtype.split('_')[-1]:7s}: median |J| "
              f"{sub.J.abs().median() * 100:.2f}c; clustered J {cm_str(vals)}")
    n_flat = int((rows.J.abs() < J_MIN).sum())
    print(f"  markets with |J| < half a tick (excluded from target B): "
          f"{n_flat}/{len(rows)}")

    hr("2. RAW POST-BREAK DRIFT (unconditional; ~0 expected)")
    report_instrument(rows, "D", "D_h = mark(Q3open+h) - mid(Q3open):")

    hr("3. TARGET B — VENUE SELF-CONSISTENCY (D_h · sign(J); + = the break "
       "move continues = re-anchor signature; - = overshoot)")
    report_instrument(rows, "B", "pooled:")
    for mtype, sub in rows.groupby("mtype"):
        report_instrument(sub, "B", f"{mtype.split('_')[-1]}:")

    hr("4. TARGET A — STATE-FV (D_h · sign(G), G = FV_half - Q3 open; "
       "+ = drifts toward our FV)")
    report_instrument(rows, "A", "pooled:")
    big = rows[rows.G.abs() > rows.spread_q3open]
    print(f"\nmeaningful disagreements only (|G| > the market's own Q3-open "
          f"spread; {len(big)} markets / {big.event_slug.nunique()} games):")
    report_instrument(big, "A", "  ")

    hr("KILL CONDITION AND STANDING STATEMENTS")
    print("Per the candidate's own registration-of-intent: if both targets "
          "read ~0 — or below the harvest bar — at every horizon, the break "
          "pricing is already complete and D2 DIES BY MEASUREMENT. Wall-6 "
          "asymmetry: target A alone cannot carry the candidate (our FV is "
          "uninformative where it disagrees with the mid); a live candidate "
          "needs target B's mechanism or a corroborated A. Anchor proxies "
          "are labelled substitutes for pregame quotes the pin does not "
          "hold. Drift is MID drift; capturing any of it pays the toll.")
    print("Multiple comparisons: 2 instruments x 4 horizons x market types; "
          "several nominal hits expected by chance; mechanism + robustness "
          "rank, never p-value.")
    print("\nNo in-sample result justifies capital. The forward test is the "
          "evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
