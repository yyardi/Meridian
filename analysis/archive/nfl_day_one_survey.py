"""GRIDIRON day-one market-quality survey — the NFL board (maker program).

    .venv/bin/python analysis/nfl_day_one_survey.py --snapshots CSV[.gz]
        [--resolved CSV] [--out DIR] [--selftest]

Port of the NBA day-one survey (analysis/nba_day_one_survey.py — the
league-agnostic machinery is IMPORTED from it, never duplicated: probit_fit,
parse_book_raw, coherence_violations, the census wiring). The operator's
directive: the algo pays for itself or the project ends; NFL is maker-only
under GRIDIRON. This survey's spread/depth/two-sidedness read is the first
real input to the $100/month memo.

CONVENTIONS, MEASURED AGAINST THE VENUE (2026-09-02, direct read of
api.polymarket.us via the public gateway, 16 listed events — the V29
pattern; never assumed from other leagues):
- slug families: asc- (spreads, 852), tsc- (totals, 920), aec- (winner, 16)
- 18 market types, `football_*` naming: full_game winner/spread/total,
  per-quarter totals+spreads (1q..4q), first/second-half spreads+totals,
  and team totals (football_team_points_full_game_total)
- totals slugs carry a SEGMENT token before ptX (…-total-24pt5, …-1q-1pt5)
  — unlike WNBA's bare -158pt5; the parser here is segment-aware
- all sampled lines half-point; feeCoefficient 0.06 on every scanned NFL
  market (V9 transfers); gameStartTime present per market; tick/min-qty
  live under orderPriceMinTickSize / minimumTradeQty in the raw payload
- cadence: pregame board sweeps + 0.5s live (recorder deployed 2026-09-02;
  live tape starts with the first game, Thursday)

The convention GATE is module zero exactly as on NBA — it is what licenses
reading a new league's data at all (rule 16's spirit: the known answers
below are venue-probed, and the gate verifies the recorded stream against
them before anything else quotes a number). No NFL fitted constants exist:
the sigma module fits and REPORTS ONLY, comparison gated until a GRIDIRON
R-series registers. Shadow only; maker-only is GRIDIRON's charter.

**No in-sample result justifies capital. The forward test is the evidence.**
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.quote.adverse_selection import clustered_mean  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "nba_day_one_survey", Path(__file__).with_name("nba_day_one_survey.py"))
nba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nba)

hr = nba.hr
probit_fit = nba.probit_fit
coherence_violations = nba.coherence_violations
parse_book_raw = nba.parse_book_raw

#: Venue-probed inventory (2026-09-02, 16 events). A type observed in data
#: but absent here is NEW and prints loudly — inventory drift is survey
#: output, not silence.
PROBED_MARKET_TYPES = {
    "football_team_full_game_winner", "football_team_full_game_spread",
    "football_team_full_game_total", "football_team_points_full_game_total",
    "football_game_first_quarter_total", "football_game_second_quarter_total",
    "football_game_third_quarter_total", "football_game_fourth_quarter_total",
    "football_game_first_half_total", "football_game_second_half_total",
    "football_team_first_quarter_spread", "football_team_second_quarter_spread",
    "football_team_third_quarter_spread", "football_team_fourth_quarter_spread",
    "football_team_first_half_spread", "football_team_second_half_spread",
    "football_team_first_half_total", "football_team_second_half_total",
}
PROBED_PREFIXES = {"asc", "tsc", "aec"}
CADENCE_LIVE_MS = 500          # recorder spec: 0.5s live; pregame sweeps
                               # are slower by design — reported, not gated
KICKOFF_BUCKETS_H = [("<0.5h", 0, 0.5), ("0.5-2h", 0.5, 2), ("2-6h", 2, 6),
                     ("6-24h", 6, 24), (">=24h", 24, 10_000)]
WNBA_INPLAY_P50_C = 4.0        # my measured whole-game in-play ladder p50
C1_LATE_CLASS_C = 12.0         # C1's late-window class, for context


def m0_gridiron_gate(df: pd.DataFrame,
                     resolved: pd.DataFrame | None) -> dict:
    """Convention gate, NFL edition. Returns {check: bool}; any False makes
    the run exit 3. Reuses the NBA gate's checks with the venue-probed NFL
    parameters; the segment-aware slug parse is the one structural delta."""
    hr("M0. COMPOSITION + GRIDIRON CONVENTION GATE (counts before ratios)")
    gate: dict[str, bool] = {}
    print(f"rows {len(df)} | markets {df.market_slug.nunique()} | events "
          f"{df.event_slug.nunique() if 'event_slug' in df else '?'} | "
          f"window {df.captured_at.min()} -> {df.captured_at.max()}")
    fam = df.market_slug.str.split("-").str[0]
    fam_counts = fam.value_counts()
    print(f"slug families: {fam_counts.to_dict()}")
    unknown_fam = set(fam_counts.index) - PROBED_PREFIXES
    gate["slug_families"] = not unknown_fam
    if unknown_fam:
        print(f"  CONVENTION GATE FAILS: unprobed slug families "
              f"{unknown_fam} — the venue changed shape since the probe")

    print("\nmarket-type inventory (venue-probed set = 18 types):")
    mt_counts = df.groupby("sports_market_type").market_slug.nunique()
    print(mt_counts.to_string())
    new_types = set(mt_counts.index.astype(str)) - PROBED_MARKET_TYPES
    if new_types:
        # inventory drift is OUTPUT, not a gate failure — a new listed type
        # is information the maker program wants, loudly
        print(f"  NEW TYPES not in the 2026-09-02 probe (loud, not fatal): "
              f"{sorted(new_types)}")

    # ptX slug/line agreement — segment-aware: the trailing NptM token is
    # the line magnitude; pos/neg only on spread (asc) slugs.
    if "line" in df.columns:
        per = df.drop_duplicates("market_slug")
        tail = per.market_slug.str.extract(r"-(\d+)pt(\d)$", expand=True)
        have = tail[0].notna() & per.line.notna()
        mag = (pd.to_numeric(tail.loc[have, 0])
               + pd.to_numeric(tail.loc[have, 1]) / 10.0)
        neg = per.loc[have, "market_slug"].str.contains("-neg-")
        parsed = mag.where(~neg.values, -mag)
        agree = (parsed.values == per.loc[have, "line"].astype(float).values)
        n_half = int((pd.to_numeric(tail.loc[have, 1]) == 5).sum())
        gate["slug_line_encoding"] = bool(agree.all()) and n_half == int(
            have.sum())
        print(f"\nptX ladder slugs: {int(have.sum())} ({n_half} half-point); "
              f"slug<->line agreement {int(agree.sum())}/{len(agree)}"
              + ("" if gate["slug_line_encoding"] else
                 "  <- CONVENTION GATE FAILS: encoding drifted from the "
                 "probe; line parsing unsafe"))

    # First-team score frame vs settlements — identical method to NBA
    # (event-level finals, truncation boundary class); full_game spreads only.
    if (resolved is not None and "event_score" in df.columns
            and "line" in df.columns):
        settle = resolved.dropna(subset=["settlement"]).drop_duplicates(
            "market_slug").set_index("market_slug").settlement
        finals = (df[df.event_score.notna()].sort_values("captured_at")
                  .groupby("event_slug").event_score.last())
        spr = df[df.sports_market_type == "football_team_full_game_spread"]
        per = spr.drop_duplicates("market_slug")[
            ["market_slug", "event_slug", "line"]].set_index("market_slug")
        per["S"] = per.index.map(settle)
        per["final"] = per.event_slug.map(finals)
        per = per[per.S.notna() & per.final.notna()]
        n_ok = n_all = n_boundary = 0
        bad = []
        for r in per.itertuples():
            try:
                a, b = str(r.final).split("-")
                margin = int(a) - int(b)
                pred = 1 if (margin + float(r.line)) > 0 else 0
            except (ValueError, TypeError):
                continue
            n_all += 1
            if pred == int(r.S):
                n_ok += 1
            elif abs(margin + float(r.line)) <= 8.5:
                # NFL: one score (TD+2) can land after a tape truncation;
                # the boundary class is wider than basketball's, stated.
                n_boundary += 1
            else:
                bad.append(r.Index)
        if n_all:
            gate["score_frame"] = len(bad) == 0
            print(f"\nfirst-team frame vs settlements: {n_ok}/{n_all} agree, "
                  f"{n_boundary} boundary rungs (tape-truncation class, "
                  f"<=8.5 pts)"
                  + ("" if gate["score_frame"] else
                     f"  <- GATE FAILS: clear flips {bad[:5]}"))
        else:
            print("\nframe check: no resolvable full-game spreads yet — "
                  "UNVERIFIED (reruns as settlements land)")
    else:
        print("\nframe check: UNVERIFIED until --resolved is provided — "
              "stated, not skipped")

    # Cadence: live rows gated at ~500ms; pregame sweeps reported only.
    if "is_live" in df.columns:
        live = df[df.is_live]
        if len(live):
            g = live.sort_values("captured_at").groupby("market_slug")
            gaps = g.captured_at.diff().dt.total_seconds().dropna() * 1000
            if len(gaps):
                gate["cadence_live"] = bool(gaps.median()
                                            <= 5 * CADENCE_LIVE_MS)
                print(f"\nlive cadence: p50 {gaps.median():.0f}ms p90 "
                      f"{gaps.quantile(.9):.0f}ms (spec ~{CADENCE_LIVE_MS}ms"
                      + ("" if gate["cadence_live"] else
                         " — GATE FAILS: >5x slower") + ")")
        pre = df[~df.is_live]
        if len(pre):
            g = pre.sort_values("captured_at").groupby("market_slug")
            gaps = g.captured_at.diff().dt.total_seconds().dropna()
            if len(gaps):
                print(f"pregame sweep cadence (reported, not gated): p50 "
                      f"{gaps.median():.0f}s per market")

    fee_cols = ["fee_coefficient", "min_tick_size", "min_trade_qty",
                "book_tier", "raw", "game_start_time"]
    avail = {c: ("yes" if c in df.columns else "MISSING") for c in fee_cols}
    print(f"\ncolumn availability: {avail}")
    return gate


def m1_spreads_nfl(df: pd.DataFrame) -> None:
    hr("M1. SPREADS x TYPE x TIME-TO-KICKOFF — the maker program's raw "
       "material ($100/month memo input)")
    if not nba.CENSUS_OK:
        print("DEGRADED: census module unavailable")
    else:
        print(nba.census.spread_distribution(df).to_string(index=False))

    two = df[df.best_bid.notna() & df.best_ask.notna()].copy()
    two["spread_c"] = (two.best_ask - two.best_bid) * 100
    if "game_start_time" in two.columns and two.game_start_time.notna().any():
        pre = two[~two.get("is_live", False)].copy()
        pre["tth"] = (pd.to_datetime(pre.game_start_time, utc=True,
                                     format="ISO8601")
                      - pre.captured_at).dt.total_seconds() / 3600
        print("\npregame spread by hours-to-kickoff (p50/p90 cents; counts "
              "first):")
        fam = pre.sports_market_type.astype(str).str.rsplit("_", n=1).str[-1]
        for name, lo, hi in KICKOFF_BUCKETS_H:
            sub = pre[(pre.tth >= lo) & (pre.tth < hi)]
            if len(sub) == 0:
                continue
            print(f"  {name:>7s}: n={len(sub):8d} "
                  f"({sub.market_slug.nunique()} mkts) "
                  f"p50 {sub.spread_c.median():.0f}c "
                  f"p90 {sub.spread_c.quantile(.9):.0f}c")
    else:
        print("\nhours-to-kickoff cut UNAVAILABLE: game_start_time missing "
              "from export — the checklist lesson, again; fix before "
              "Thursday's live tape")

    live = df[df.get("is_live", pd.Series(False, index=df.index))]
    lt = live[live.best_bid.notna() & live.best_ask.notna()
              & live.sports_market_type.isin(
                  ["football_team_full_game_spread",
                   "football_team_full_game_total"])]
    if len(lt):
        p50 = float((lt.best_ask - lt.best_bid).median()) * 100
        print(f"\nTHE NFL TOLL NUMBER (in-play full-game ladders): p50 "
              f"{p50:.1f}c on {len(lt)} rows / {lt.market_slug.nunique()} "
              f"markets — vs WNBA {WNBA_INPLAY_P50_C:.0f}c whole-game and "
              f"the {C1_LATE_CLASS_C:.0f}c late class. Tighter books with "
              f"more flow reshape the maker economics; this number goes to "
              f"c7's memo AS MEASURED, routing decisions stay theirs.")
    else:
        print("\nno in-play rows yet (live tape starts Thursday) — the toll "
              "number is pending, correctly")


def m1b_width_x_flow(df: pd.DataFrame, stats: pd.DataFrame | None) -> None:
    """THE CELL THAT DECIDES GRIDIRON: is any market type both WIDE and
    TRADED?

    Why this is the kill-line rather than one table among many. My WNBA
    placement curve (analysis/mm_control_variables.py M2) found that per
    cycle quoted, the measured-concession arm improves monotonically with
    spread width and ONLY the >10c band is non-negative — so width is where
    a maker's honest economics live. But width without flow is a desert: a
    30c book that never trades pays nothing at any placement. The manager's
    hand read at T-7 found the NFL MONEYLINE 0.5c wide (TIGHTER than WNBA's
    1c winner) with $919k traded, while 14 OF 18 MARKET TYPES HAD NEVER
    TRADED AT ALL. If that pattern holds — liquidity only where it is too
    tight to earn, width only where nothing trades — the maker program has
    no cell to stand in, and that is a finding worth having BEFORE size is
    committed rather than after.

    Consumes `market_trade_stats` (migration c3f7a91b28d4) when present.
    COVERAGE LIMIT, stated because it shapes the read: those stats accrue
    only where the DEPTH loop polls, i.e. LIVE games — so the pregame board's
    volume growth is unrecorded unless a low-frequency stats-only sweep is
    added. Day one is a pregame board; without that sweep this table can
    show width but not flow until kickoff."""
    hr("M1b. WIDTH x FLOW — is any market type both wide enough to earn and "
       "traded enough to fill? (the GRIDIRON kill-line)")
    two = df[df.best_bid.notna() & df.best_ask.notna()].copy()
    if two.empty:
        print("no two-sided rows yet")
        return
    two["spread_c"] = (two.best_ask - two.best_bid) * 100
    # PER-MARKET (per rung), never per type. A type's MEDIAN width crossed
    # with any-rung-traded would flag a type whose WIDE rungs are dead and
    # whose TRADED rungs are tight — the exact false positive this table
    # exists to avoid, and the reason the manager's market-level count
    # (56/136 traded) is not the same statistic as their type-level one
    # (4/18). The cell must be one rung that is BOTH.
    per_mkt = two.groupby("market_slug").agg(
        mtype=("sports_market_type", "first"),
        spread_c=("spread_c", "median"))
    if stats is None or stats.empty:
        print("market_trade_stats NOT SUPPLIED — width only, flow unknown. "
              "On a pregame board this is the expected state until either "
              "kickoff or the stats-only sweep's rows land; the cross-tab "
              "is the point, so a width-only run answers half the question.")
        print(per_mkt.groupby("mtype").agg(
            markets=("spread_c", "size"),
            spread_p50_c=("spread_c", "median")).round(1).to_string())
        return
    latest = (stats.sort_values("captured_at").groupby("market_slug").last())
    per_mkt["shares"] = per_mkt.index.map(latest.shares_traded).fillna(0.0)
    per_mkt["notional"] = per_mkt.index.map(
        latest.notional_traded).fillna(0.0)
    per_mkt["traded"] = per_mkt.shares > 0
    per_mkt["wide"] = per_mkt.spread_c > 10

    tab = per_mkt.groupby("mtype").agg(
        markets=("spread_c", "size"),
        spread_p50_c=("spread_c", "median"),
        traded=("traded", "sum"),
        wide=("wide", "sum"),
        WIDE_AND_TRADED=("mtype", "size"))   # placeholder, replaced below
    tab["WIDE_AND_TRADED"] = per_mkt.groupby("mtype").apply(
        lambda g: int((g.wide & g.traded).sum()), include_groups=False)
    tab["notional"] = per_mkt.groupby("mtype").notional.sum()
    print(tab.round(1).to_string())

    cells = per_mkt[per_mkt.wide & per_mkt.traded]
    print(f"\nRUNGS THAT ARE BOTH WIDE (>10c) AND TRADED: {len(cells)} of "
          f"{len(per_mkt)} markets — THE ONLY CELLS A MAKER CAN EARN IN.")
    if len(cells) == 0:
        print("  NONE. On this read the board offers no rung where a maker "
              "is both paid for width and given flow: liquidity sits where "
              "it is too tight to earn, width sits where nothing trades. "
              "That is the kill-line answer, and it is a finding, not a "
              "null.")
    else:
        print(f"  median width {cells.spread_c.median():.0f}c, total "
              f"notional ${cells.notional.sum():,.0f}; top by notional:")
        for r in cells.nlargest(min(8, len(cells)), "notional").itertuples():
            print(f"    {r.Index[:46]:46s} {r.spread_c:>5.0f}c  "
                  f"${r.notional:>12,.0f}")
        print("  These rungs — not their market TYPES — are what a GRIDIRON "
              "placement arm would stand in; the type is not the tradable "
              "object and a type-level read cannot see them.")
    print(f"\ncomposition: {int(per_mkt.traded.sum())} traded / "
          f"{int(per_mkt.wide.sum())} wide / {len(per_mkt)} markets. A maker "
          f"cannot fill where nothing trades at any width or placement, and "
          f"cannot earn where the spread is thinner than the concession.")


def m5_sigma_nfl(df: pd.DataFrame) -> None:
    hr("M5. LADDER SHAPE — fitted (mu, sigma) REPORT-ONLY: no NFL fitted "
       "constants exist; comparison gated until a GRIDIRON R-series "
       "registers (the NBA survey's R5 pattern)")
    two = df[df.best_bid.notna() & df.best_ask.notna()].copy()
    two["mid"] = (two.best_bid + two.best_ask) / 2
    tot = two[two.sports_market_type == "football_team_full_game_total"]
    fits = []
    for ev, g in tot.groupby("event_slug"):
        first = (g.sort_values("captured_at").groupby("line").first()
                 .reset_index())
        fit = probit_fit(first.line, first.mid)
        if fit is not None:
            fits.append((ev, fit))
    if not fits:
        print("no fittable full-game totals ladders yet")
        return
    mus = pd.Series([m for _, (m, s) in fits])
    sigs = pd.Series([s for _, (m, s) in fits])
    print(f"full-game totals at listing: {len(fits)} ladders; implied mu "
          f"p50 {mus.median():.1f}; implied sigma p50 {sigs.median():.2f} "
          f"(p25 {sigs.quantile(.25):.2f}, p75 {sigs.quantile(.75):.2f})")
    print("(recorded as day-one material; the fitted values become the "
          "comparison target only through a registration, never by reading "
          "them twice)")


def selftest() -> int:
    print("mutation test: GRIDIRON survey on NFL-shaped synthetic listings")
    failures = 0

    def check(name, ok):
        nonlocal failures
        print(f"  {name} -> {'ok' if ok else 'FAIL'}")
        failures += 0 if ok else 1

    base = pd.Timestamp("2026-09-09 22:00:00+00:00")
    rows = []
    from scipy import stats as st
    mu, sigma = 44.5, 13.5
    for k in range(10):
        line = 24.5 + 4 * k
        mid = 1.0 - st.norm.cdf((line - mu) / sigma)
        rows.append(dict(
            market_slug=f"tsc-nfl-ne-sea-2026-09-09-total-{line:g}".replace(
                ".5", "pt5"),
            event_slug="nfl-ne-sea-2026-09-09",
            sports_market_type="football_team_full_game_total", line=line,
            captured_at=base, best_bid=round(mid - .01, 4),
            best_ask=round(mid + .01, 4), is_live=False,
            event_score=None, fee_coefficient=0.06,
            game_start_time="2026-09-10 00:15:00+00:00"))
    rows.append(dict(
        market_slug="asc-nfl-ne-sea-2026-09-09-pos-20pt5",
        event_slug="nfl-ne-sea-2026-09-09",
        sports_market_type="football_team_full_game_spread", line=20.5,
        captured_at=base, best_bid=0.5, best_ask=0.52, is_live=False,
        event_score=None, fee_coefficient=0.06,
        game_start_time="2026-09-10 00:15:00+00:00"))
    rows.append(dict(
        market_slug="tsc-nfl-ne-sea-2026-09-09-1q-1pt5",
        event_slug="nfl-ne-sea-2026-09-09",
        sports_market_type="football_game_first_quarter_total", line=1.5,
        captured_at=base, best_bid=0.4, best_ask=0.44, is_live=False,
        event_score=None, fee_coefficient=0.06,
        game_start_time="2026-09-10 00:15:00+00:00"))
    df = pd.DataFrame(rows)
    df["captured_at"] = pd.to_datetime(df.captured_at, utc=True)

    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        gate = m0_gridiron_gate(df, None)
    check("segment-aware ptX parse (total-/1q-/pos- slugs all agree)",
          gate.get("slug_line_encoding") is True)
    check("probed slug families pass", gate.get("slug_families") is True)

    drift = df.copy()
    drift["line"] = drift.line + 1.0
    with contextlib.redirect_stdout(io.StringIO()):
        g2 = m0_gridiron_gate(drift, None)
    check("line drift fails the gate", g2.get("slug_line_encoding") is False)

    alien = df.copy()
    alien.loc[alien.index[:1], "market_slug"] = "xxc-nfl-foo-1pt5"
    with contextlib.redirect_stdout(io.StringIO()):
        g3 = m0_gridiron_gate(alien, None)
    check("unprobed slug family fails the gate",
          g3.get("slug_families") is False)

    # frame check with an NFL-width boundary: margin+line inside one score
    # classifies boundary, outside classifies flip
    res_ok = pd.DataFrame([dict(
        market_slug="asc-nfl-ne-sea-2026-09-09-pos-20pt5", settlement=1)])
    frame_df = df.copy()
    frame_df["event_score"] = "24-10"          # margin +14; +20.5 -> 1
    with contextlib.redirect_stdout(io.StringIO()):
        g4 = m0_gridiron_gate(frame_df, res_ok)
    check("frame verified on agreeing settlement",
          g4.get("score_frame") is True)
    res_flip = res_ok.assign(settlement=0)     # |14+20.5| >> 8.5 -> flip
    with contextlib.redirect_stdout(io.StringIO()):
        g5 = m0_gridiron_gate(frame_df, res_flip)
    check("clear flip caught (outside the one-score class)",
          g5.get("score_frame") is False)

    # M1b: a board with one wide-and-traded type and one wide-but-dead type
    # must name exactly the first and count the second as never-traded.
    st = pd.DataFrame([
        dict(market_slug=df.market_slug.iloc[0],   # a wide totals rung
             captured_at=base, shares_traded=100.0, notional_traded=1000.0,
             open_interest=50.0),
        dict(market_slug=df.market_slug.iloc[1],
             captured_at=base, shares_traded=0.0, notional_traded=0.0,
             open_interest=0.0)])
    wide = df.copy()
    wide["best_bid"] = 0.30
    wide["best_ask"] = 0.45          # 15c -> above the >10c bar
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m1b_width_x_flow(wide, st)
    tb = buf.getvalue()
    check("M1b names the wide+traded RUNG (1 of the two seeded)",
          "AND TRADED: 1 of" in tb)

    # THE FALSE POSITIVE THIS TABLE EXISTS TO AVOID: a type whose WIDE rung
    # is dead and whose TRADED rung is tight must yield ZERO cells, even
    # though the type has both a wide rung and a traded rung.
    mixed = df.copy()
    m_wide, m_tight = df.market_slug.iloc[0], df.market_slug.iloc[1]
    mixed.loc[mixed.market_slug == m_wide, ["best_bid", "best_ask"]] = [.30, .45]
    mixed.loc[mixed.market_slug == m_tight, ["best_bid", "best_ask"]] = [.40, .41]
    st2 = pd.DataFrame([
        dict(market_slug=m_wide, captured_at=base, shares_traded=0.0,
             notional_traded=0.0, open_interest=0.0),
        dict(market_slug=m_tight, captured_at=base, shares_traded=500.0,
             notional_traded=5000.0, open_interest=100.0)])
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        m1b_width_x_flow(mixed[mixed.market_slug.isin([m_wide, m_tight])], st2)
    check("M1b refuses the wide-rung-dead/traded-rung-tight false positive",
          "AND TRADED: 0 of" in buf3.getvalue())
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        m1b_width_x_flow(wide, None)
    check("M1b degrades honestly with no stats (width only)",
          "flow unknown" in buf2.getvalue())

    # sigma fit on the fabricated ladder recovers (44.5, 13.5)
    tot = df[df.sports_market_type == "football_team_full_game_total"]
    fit = probit_fit(tot.line, (tot.best_bid + tot.best_ask) / 2)
    check("sigma fit recovers mu=44.5 sigma=13.5",
          fit is not None and abs(fit[0] - 44.5) < 0.1
          and abs(fit[1] - 13.5) < 0.1)

    # coherence: reuse of the NBA module holds on a clean NFL board
    stretch = df.copy()
    stretch = pd.concat([stretch, stretch.assign(
        captured_at=stretch.captured_at + pd.Timedelta(seconds=30))])
    check("coherence clean on NFL ladder",
          len(coherence_violations(stretch)) == 0)

    print(f"mutation test: {'ALL OK' if failures == 0 else f'{failures} FAILURES'}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots", type=Path)
    ap.add_argument("--resolved", type=Path, default=None)
    ap.add_argument("--trade-stats", type=Path, default=None,
                    help="market_trade_stats export (migration "
                         "c3f7a91b28d4) — enables the width x flow "
                         "cross-tab, the GRIDIRON kill-line read")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.snapshots is None:
        print("need --snapshots (NFL market_snapshots-shaped export); "
              "--selftest runs without data")
        return 2

    print("GRIDIRON day-one survey (NFL board; maker-only program)")
    print(f"input: {args.snapshots}")
    if selftest() != 0:
        print("ABORT: mutation test failed")
        return 1

    df = pd.read_csv(args.snapshots)
    df["captured_at"] = pd.to_datetime(df.captured_at, utc=True,
                                       format="ISO8601")
    if "is_live" in df.columns and df.is_live.dtype != bool:
        df["is_live"] = (df.is_live.astype(str).str.lower()
                         .map({"t": True, "true": True, "1": True,
                               "f": False, "false": False, "0": False})
                         .fillna(False))
    resolved = pd.read_csv(args.resolved) if args.resolved else None

    stats = None
    if args.trade_stats is not None:
        stats = pd.read_csv(args.trade_stats)
        stats["captured_at"] = pd.to_datetime(stats.captured_at, utc=True,
                                              format="ISO8601")

    gate = m0_gridiron_gate(df, resolved)
    m1_spreads_nfl(df)
    m1b_width_x_flow(df, stats)
    nba.m2_depth(df, args.out)
    nba.m3_fees(df)          # venue-probed 0.06 on NFL; V9's gate stands
    m5_sigma_nfl(df)
    nba.m6_coherence(df)
    if args.out is not None:
        nba.m7_artifacts(df, args.out)
    else:
        print("\n(--out not given: day-one record artifacts NOT written — "
              "on listing day this is not optional)")

    hr("STANDING STATEMENTS")
    print("Shadow only; GRIDIRON is maker-only by charter. Rule 15: the "
          "first real episode of anything gets hand-verified. WNBA/NBA "
          "verdicts port as registrations, never as evidence. The frame "
          "boundary class here is one NFL score (8.5 pts) — wider than "
          "basketball's, stated.")
    print("\nNo in-sample result justifies capital. The forward test is "
          "the evidence.")
    failed = [k for k, v in gate.items() if not v]
    if failed:
        print(f"\nCONVENTION GATE FAILED: {failed} — nothing above is safe "
              f"to quote; resolve in daylight first.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
