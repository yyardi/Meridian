"""PULSE scored on settlement, with the standards that were built after it ran.

PULSE is the DIRECTIONAL engine — the second, neglected shot at the tape. Its
loss map was measured before today's standards existed: before the estimator was
named, before the four doors, before we knew a decision rule could be
predetermined. This re-scores it.

    .venv/bin/python analysis/pulse_settlement.py --selftest
    .venv/bin/python analysis/pulse_settlement.py

Substrate: `backups/exports/pulse_decisions_full_20260901T195202Z.csv`
(19,333 decisions / 34 games / 480 markets, 2026-08-18 → 08-31, WNBA) joined to
`resolved_outcomes_20260901T195202Z.csv`. Written before computing:

**PRIMARY METRIC — settlement P&L per FILLED ENTRY, held to settlement.**
Money at price (C11), YES-frame throughout as verified in Track C (`fair_value`
and `market_bid/ask` are YES-frame whatever `side` says):
    side=yes: staked = limit_price,       returned = settlement
    side=no : staked = 1 - limit_price,   returned = 1 - settlement

**Why held-to-settlement is the right primary here, and not trip P&L.** The
round-trip is ENGINE-MEDIATED: a fixed 5¢ profit target means trip P&L pays on
price oscillation and exit availability rather than on the belief being right,
and the record already concluded trip P&L is ~decoupled from fv correctness.
Held-to-settlement is the belief's own scoreboard — it does not depend on the
exit policy at all. (It is also the only one available: `entry_id` is NULL on
every row of this export, so round-trip lineage cannot be reconstructed from it.)

**ESTIMATOR — named, because two are in circulation and differ on identical
rows.** `core.quote.adverse_selection.clustered_mean`: the POOLED mean with a
game-cluster-robust sandwich SE, df = G-1, **two-sided 95%**. The unweighted
mean-of-game-means is the other one. Never mixed, never compared across.

**COUNTS AND COMPOSITION BEFORE RATIOS.** 19,333 rows over 34 games is ~570 per
game and they are NOT 19,333 opinions: the engine re-evaluates open positions
every cycle. The report leads with how many DISTINCT opinions the tape holds
(unique market x side), how often one opinion is re-entered, and the Kish
effective game count — a game with 214 entries is not 214 independent bets.

**THE FOUR DOORS (analysis/FORCED_GRADIENTS.md), applied to PULSE's entry rule.**
Stage 1 statistic, 2 population, 3 partition, 4 decision rule. Stage four is the
one no null catches, and the stage-four check is: take the achievable outcome
range, project it onto the rule's branches, inspect the image — a single branch
is PREDETERMINED, a branch outside the image is DEAD, adverse-at-best-case is
INVERTED, too-wide is CANNOT DISCRIMINATE.

The specific question, asked of PULSE the way it was asked of QUOTE's fill rule:
**is the entry threshold reachable in both directions on the recorded sample?**

*No in-sample result justifies capital. The forward test is the evidence.*
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis.guards import (assert_age_non_negative, degenerate_extremes_warning,
                            report_composite, report_count)
from core.quote.adverse_selection import clustered_mean
from core.quote.report import PHANTOM, REAL, classify_fill
from core.quote.storage import ASK, BID

DECISIONS = "backups/exports/pulse_decisions_full_20260901T195202Z.csv"
OUTCOMES = "backups/exports/resolved_outcomes_20260901T195202Z.csv"
TICKS = "backups/exports/live_ticks_pulse_games_20260901T195202Z.csv.gz"
#: The engine's entry threshold, read off the tape's own support (see stage 2).
OBSERVED_MIN_EDGE = 0.03
CAPITAL_LINE = "No in-sample result justifies capital. The forward test is the evidence."


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_csv(DECISIONS)
    r = pd.read_csv(OUTCOMES).drop_duplicates("market_slug")
    d = d.merge(r[["market_slug", "settlement"]], on="market_slug",
                how="left", suffixes=("_row", "_res"))
    d["settle"] = d.settlement_res.fillna(d.settlement_row)
    e = d[d.action == "enter"].copy()
    filled = e[e.filled_at.notna() & e.settle.notna()].copy()
    # money at price, YES frame (Track C verified the frame on this export)
    yes = filled.side == "yes"
    filled["staked"] = np.where(yes, filled.limit_price, 1 - filled.limit_price)
    filled["returned"] = np.where(yes, filled.settle, 1 - filled.settle)
    filled["pnl_c"] = (filled.returned - filled.staked) * 100.0
    assert (filled.staked > 0).all(), "non-positive stake"
    return d, filled


def kish(counts: np.ndarray) -> float:
    return float(counts.sum() ** 2 / (counts ** 2).sum())


def classify(filled: pd.DataFrame) -> pd.DataFrame:
    """Apply QUOTE's real/phantom separation to PULSE's fills — never done before.

    PULSE fills on the same rule that made QUOTE's number meaningless (the mid
    reaching a resting limit), so its fills carry the same question and nobody
    had asked it. The classifier is IMPORTED, not re-derived. Frame mapping:
    a `yes` entry rests a BID at limit_price (reachable only if the best ASK
    came down to it); a `no` entry rests an offer to sell YES at limit_price,
    i.e. an ASK (reachable only if the best BID came up to it).
    """
    t = pd.read_csv(TICKS, usecols=["market_slug", "captured_at", "best_bid", "best_ask"])
    t["captured_at"] = pd.to_datetime(t.captured_at, utc=True, format="ISO8601")
    t = t.dropna(subset=["best_bid", "best_ask"]).sort_values("captured_at")
    filled = filled.copy()
    filled["filled_at"] = pd.to_datetime(filled.filled_at, utc=True, format="ISO8601")
    parts = []
    for slug, g in filled.groupby("market_slug"):
        tk = t[t.market_slug == slug]
        if tk.empty:
            parts.append(g.assign(bb=np.nan, ba=np.nan))
            continue
        parts.append(pd.merge_asof(
            g.sort_values("filled_at"), tk[["captured_at", "best_bid", "best_ask"]],
            left_on="filled_at", right_on="captured_at", direction="backward",
            tolerance=pd.Timedelta("5s")).rename(columns={"best_bid": "bb", "best_ask": "ba"}))
    f = pd.concat(parts, ignore_index=True)
    age = (f.filled_at - f.captured_at).dt.total_seconds().dropna()
    if len(age):
        assert_age_non_negative(float(age.min()), "PULSE fill -> book backward join")
    f["pop"] = [classify_fill(side=(BID if s == "yes" else ASK), quote_price=q,
                              best_bid=None if pd.isna(b) else b,
                              best_ask=None if pd.isna(a) else a)
                for s, q, b, a in zip(f.side, f.limit_price, f.bb, f.ba)]
    return f


def composition(d: pd.DataFrame, filled: pd.DataFrame) -> None:
    print("=== COMPOSITION — counts before ratios ===")
    e = d[d.action == "enter"]
    print(f"decisions {len(d):,} · games {d.game_id.nunique()} · markets {d.market_slug.nunique()} · "
          f"{d.decided_at.min()[:10]} to {d.decided_at.max()[:10]}")
    print(f"actions: {d.action.value_counts().to_dict()}")
    print(f"entries {len(e):,} -> filled {len(filled):,} ({len(filled) / len(e):.1%}), all settled")
    pairs = e.groupby(["market_slug", "side"]).size()
    print(f"\nDISTINCT OPINIONS vs ROWS: {len(pairs)} unique (market x side) behind {len(e):,} "
          f"entries — {(pairs > 1).sum()} of them entered more than once (max {pairs.max()}x).")
    print("The engine re-evaluates and re-enters the same opinion; rows are not bets.")
    per_game = filled.groupby("game_id").size()
    print(f"filled entries per game: median {per_game.median():.0f}, max {per_game.max()}, "
          f"min {per_game.min()} · Kish effective games {kish(per_game.to_numpy()):.2f} "
          f"of {len(per_game)} nominal ({kish(per_game.to_numpy()) / len(per_game):.0%})")
    print(f"estimates_version on filled entries: {filled.estimates_version.value_counts().to_dict()} "
          f"(three model versions share the window — confounded with dates and games)")
    bc = e.binding_constraint.value_counts()
    print(f"\nbinding_constraint on entries: {bc.head(4).to_dict()}")
    print(f"  {bc.get('max_open_per_event', 0) / len(e):.0%} of entries were size-capped by the "
          f"per-event open limit — the engine wanted more than it took, so entry SIZE is a")
    print("  policy artifact and per-dollar aggregates inherit it.")


def population_split(f: pd.DataFrame) -> None:
    """The check nobody had run on PULSE: are its fills obtainable?"""
    print("\n=== POPULATION — could these fills have happened? ===")
    matched = f.bb.notna()
    print(f"book matched within 5s: {int(matched.sum()):,}/{len(f):,} ({matched.mean():.1%})")
    print(f"classification: {f['pop'].value_counts().to_dict()} · "
          f"PHANTOM SHARE {(f['pop'] == PHANTOM).mean():.1%}")
    print(f"  (QUOTE's phantom share on the same rule was 63.9%. PULSE's is HIGHER.)")
    print("\nsettlement P&L by population, game-clustered pooled:")
    for pop in [PHANTOM, REAL]:
        s = f[f["pop"] == pop]
        cm = clustered_mean({g: v.pnl_c.tolist() for g, v in s.groupby("game_id")})
        gm = s.groupby("game_id").pnl_c.mean()
        print(f"  {pop:8s} n={len(s):5,d} G={cm.n_clusters:2d}  {cm.mean:+8.3f}c "
              f"[{cm.lo:+8.3f}, {cm.hi:+8.3f}]  games losing {int((gm < 0).sum())}/{len(gm)}")
    print("\n★ THE POPULATIONS DO NOT HAVE OPPOSITE SIGNS HERE, AND THAT IS A REAL")
    print("DIFFERENCE FROM QUOTE, WITH A MECHANISM. QUOTE scored capture/markout — SHORT-")
    print("HORIZON price motion, which is precisely what a momentary dip-and-revert")
    print("distorts, so its populations came apart (+0.951c vs -3.376c). PULSE is scored")
    print("HELD TO SETTLEMENT, and the eventual game outcome does not care whether the")
    print("fill price was momentarily reachable. So contamination does not flip the sign.")
    print("\n★ IT STILL GUTS THE EVIDENCE, FOR A DIFFERENT REASON. A phantom fill is one we")
    print("COULD NOT HAVE OBTAINED. Its P&L is real conditional on a fill that was not")
    print("available, so it is not money at any horizon. The tradable sample is the REAL")
    print("row above — and it is 361 fills, not 1,944. **81% of the apparent evidence is")
    print("unobtainable**, and what remains spans zero.")


def primary(filled: pd.DataFrame) -> None:
    print("\n=== PRIMARY — settlement P&L per filled entry, held to settlement ===")
    print("estimator: clustered_mean (POOLED mean, game-cluster-robust SE, df=G-1, two-sided 95%)")
    by_game = {g: v.pnl_c.tolist() for g, v in filled.groupby("game_id")}
    cm = clustered_mean(by_game)
    print(f"ALL filled entries (BLEND — see the population split below before quoting "
          f"this): {cm.mean:+.3f}c per entry [{cm.lo:+.3f}, {cm.hi:+.3f}] "
          f"(G={cm.n_clusters}, n={cm.n:,})")
    gm = filled.groupby("game_id").pnl_c.mean()
    print(f"  per-game sd {gm.std(ddof=1):.3f}c · games losing money: "
          f"{int((gm < 0).sum())}/{len(gm)}")
    staked, returned = filled.staked.sum(), filled.returned.sum()
    comp = report_composite("PULSE settlement", numerator=(returned - staked) * 100,
                            denominator=staked * 100, events=len(filled))
    print(f"  money at price: staked ${staked:,.2f} -> returned ${returned:,.2f} "
          f"({comp.ratio:+.4f} per dollar staked)")
    warn = degenerate_extremes_warning("PULSE settlement", comp.per_event)
    if warn:
        print(f"  rule 25: {warn}")

    # one-opinion view: the first entry per market x side, so a re-entered
    # opinion counts once. Not a better number — a differently-conditioned one.
    first = filled.sort_values("decided_at").groupby(["market_slug", "side"]).first().reset_index()
    cm1 = clustered_mean({g: v.pnl_c.tolist() for g, v in first.groupby("game_id")})
    print(f"\nONE OPINION PER (market,side), first entry only: {cm1.mean:+.3f}c "
          f"[{cm1.lo:+.3f}, {cm1.hi:+.3f}] (G={cm1.n_clusters}, n={cm1.n:,})")
    print("  Reported because re-entry is a policy choice, not extra evidence. If this")
    print("  differs materially from the all-rows figure, the aggregate is being driven by")
    print("  how often an opinion was repeated rather than by whether it was right.")

    for col, label in [("sports_market_type", "market type"), ("estimates_version", "version")]:
        print(f"\nby {label} (descriptive; the version split is confounded with dates):")
        for k, v in filled.groupby(col):
            c = clustered_mean({g: x.pnl_c.tolist() for g, x in v.groupby("game_id")})
            if c:
                print(f"  {str(k)[:44]:<44s} {c.mean:+7.3f}c [{c.lo:+7.3f}, {c.hi:+7.3f}] "
                      f"G={c.n_clusters:2d} n={c.n:,}")


def four_doors(d: pd.DataFrame, filled: pd.DataFrame) -> None:
    print("\n=== THE FOUR DOORS, applied to PULSE's ENTRY RULE ===")
    e = d[d.action == "enter"]

    print("\nSTAGE 1 — STATISTIC: settlement P&L is money, computed from limit_price and")
    print("the outcome. `edge_net` (the selection variable) appears nowhere in it. CLEAN.")

    print("\nSTAGE 2 — POPULATION: entries are selected BY edge_net, so any cut of this")
    print(f"population BY edge_net is forced in the FORCED_GRADIENTS sense. The support")
    print(f"shows it: min edge_net on the tape is {e.edge_net.min():.4f} and rows below it")
    print(f"number {int((d.edge_net < OBSERVED_MIN_EDGE).sum())}. The variable is TRUNCATED at the")
    print("threshold, so an edge-ordering result on entries speaks only about the region")
    print("above it and can say nothing about the threshold's placement.")

    print("\nSTAGE 3 — PARTITION: the cuts above are market type and version, neither of")
    print("which selected the population. Any FUTURE edge_net banding inherits stage 2.")

    print("\nSTAGE 4 — DECISION RULE. The one no null catches.")
    print("Question, as asked of QUOTE's fill rule: is the entry threshold reachable in")
    print("BOTH directions on the recorded sample?\n")
    holds = d[d.action == "hold"]
    print(f"  decisions recorded : enter {len(e):,} · hold {len(holds):,} · "
          f"exit {int((d.action == 'exit').sum()):,}")
    print(f"  hold rows carrying an edge_net at all : {int(holds.edge_net.notna().sum())}")
    print(f"  hold reasons                          : {holds.reason.value_counts().to_dict()}")
    print(f"  rows anywhere with edge_net < {OBSERVED_MIN_EDGE}    : "
          f"{int((d.edge_net < OBSERVED_MIN_EDGE).sum())}")
    print("\n  ★ FINDING — THE DECLINE BRANCH IS NOT RECORDED. `hold` does not mean")
    print('  "evaluated and declined": every hold row carries reason=position_open and no')
    print("  edge_net at all. There is not one row in 19,333 representing a market the")
    print("  engine looked at and passed on. The image of the outcome range under this")
    print("  rule, ON THIS TAPE, is a SINGLE BRANCH.")
    print("\n  What that does and does not mean, stated precisely:")
    print("   - It does NOT mean the rule never declines. It certainly does, in the engine.")
    print("   - It DOES mean the threshold is UNAUDITABLE on this tape. The population it")
    print("     excluded is invisible, so 'is 3c the right threshold' has no observable")
    print("     answer here, in either direction, and no amount of this data will produce")
    print("     one. The opportunity cost of the threshold is structurally unmeasurable.")
    print("   - It is the same SHAPE as QUOTE's fill rule booking only one half of its")
    print("     distribution: a rule whose recorded image is one-sided. QUOTE's cost was a")
    print("     wrong number; PULSE's is a number that cannot be computed at all.")
    print("   - THE FIX IS RECORDING, NOT ANALYSIS: log the declined evaluations (market,")
    print("     state, edge, threshold) and the branch becomes observable from that day on.")
    print("     Nothing in the existing tape can be reprocessed into it.")


def league_shaped_or_structural(filled: pd.DataFrame) -> None:
    """Which parts of this result port to CFB/NFL/NBA, and which are basketball?

    The decision-relevant question, given four slates in two months and one
    engine that addresses one of them. Separated because they have opposite
    consequences: a structural defect multiplies across the port, and a
    league-shaped edge does not survive it.
    """
    print("\n=== LEAGUE-SHAPED vs STRUCTURAL — what would survive a port ===")
    print("\nSTRUCTURAL (identical in any league — these travel with the engine):")
    print("  - The decline branch is unrecorded. A property of what the engine LOGS, so")
    print("    porting reproduces it exactly, in three more leagues at once.")
    print("  - The abstain branch is unproven (guards deployed after the engine stopped).")
    print("  - Rows are not opinions: re-entry inflates row counts in any sport.")
    print("  - Entry size is capped by max_open_per_event on most entries, so per-dollar")
    print("    aggregates are policy artifacts wherever the engine runs.")
    print("  - edge_net truncated at the threshold: a rule property, not a market one.")
    print("  These are the ones that MULTIPLY across a port. Fixing them is league-agnostic")
    print("  work and it is cheaper before three ports than after.")

    print("\nLEAGUE-SHAPED (basketball-specific — these do NOT travel):")
    print("  - The P&L level itself: one league, 34 games, WNBA-only.")
    print("  - Market composition: this tape is full-game totals/spread/winner. The")
    print("    football boards carry half- and quarter-derivative markets that settle on a")
    print("    DIFFERENT EVENT (~700 such fills on the quote tape), which the entry rule has")
    print("    never seen and which no part of this scoring covers.")
    print("  - ★ AND THE ONE THAT DECIDES THE PORT: the entry rule is `edge_net >= 3c`, which")
    print("    is league-agnostic arithmetic — but `edge_net` is `fair_value` minus a price,")
    print("    and PULSE's fair_value is a BASKETBALL MODEL (anchored win curve, tempo")
    print("    total, spread FV). Porting the RULE without a fair value ports an empty")
    print("    comparison. There is no football fair-value model in this repo.")

    print("\n  The strength of that objection is measurable rather than asserted, and the")
    print("  measurement already exists — the R-series, on 13,116 NBA games:")
    print("    - NBA sigma RISES through the game (Q1~2.32 -> Q4~2.71) where WNBA FALLS")
    print("      (2.98 -> 2.40): the wrong SIGN OF SLOPE, not a mis-level.")
    print("    - NBA totals banking is nearly pure (b 1.09/1.02/1.02) against WNBA's")
    print("      1.32/1.21/1.13 — the pace-persistence term is ~5x smaller.")
    print("    - The WNBA-ported constants LOST their gate against NBA-fitted ones.")
    print("  BASKETBALL-TO-BASKETBALL the constants already failed to transfer. Football is")
    print("  a larger jump than that: different clock, different scoring quanta, different")
    print("  possession structure. **The prior that PULSE's FV ports to CFB/NFL is weak,")
    print("  and it is weak on evidence we generated ourselves rather than on intuition.**")

    print("\n  WHAT THAT IMPLIES FOR THE PORT DECISION (hypothesis, not a gate):")
    print("  the cheap half of the port is the structural half — recording the decline")
    print("  branch, proving the abstain branch, fixing the row/opinion confusion. That is")
    print("  worth doing regardless of league because it is what makes ANY future answer")
    print("  auditable. The expensive half is a football fair value, which is a new model,")
    print("  not a port, and the R-series says to expect refitting rather than porting.")


def abstentions() -> None:
    print("\n=== THE ABSTAIN BRANCH (rule 22 — a zero needs provenance) ===")
    print("`pulse_abstentions` is not in any pinned export, so it cannot be read here.")
    print("But its status is determinable WITHOUT the table, from two dates:")
    print("  guards authored/landed : 2026-09-02T00:05Z (core/pulse/guards.py, 1d54565)")
    print("  PULSE's last decision  : 2026-08-31T02:30Z")
    print("The guards were deployed into an engine that had ALREADY STOPPED PRODUCING, and")
    print("PULSE has recorded nothing in the four days since. So the abstain branch has")
    print("never had the opportunity to fire on live data.")
    z = report_count("pulse_abstentions_observed", 0)
    print(f"  {z}")
    print("A zero in that table is therefore NOT evidence the guards are inert, and NOT")
    print("evidence they work. It is an UNPROVEN INSTRUMENT, and the first forward slate")
    print("PULSE actually sees is what proves or disproves it. The registered forward")
    print("check (compare forward refusal rate to the in-sample 3.71%) is still unstarted.")


def selftest() -> None:
    """The scorer must recover a known P&L before it reports an unknown one."""
    ok = True
    # a hand-computable book: one YES win, one YES loss, one NO win, one NO loss
    f = pd.DataFrame({
        "game_id": [1, 1, 2, 2], "side": ["yes", "yes", "no", "no"],
        "limit_price": [0.40, 0.40, 0.70, 0.70], "settle": [1.0, 0.0, 0.0, 1.0],
    })
    yes = f.side == "yes"
    f["staked"] = np.where(yes, f.limit_price, 1 - f.limit_price)
    f["returned"] = np.where(yes, f.settle, 1 - f.settle)
    f["pnl_c"] = (f.returned - f.staked) * 100
    # NOTE: my first hand-computed expectation here was WRONG (+30 for the NO win)
    # and the test caught it, which is the reason to write the expectation by hand
    # rather than from the code: a 30c stake that WINS returns 100c, so it earns
    # +70c, not +30c. The asymmetry (+70/-30) is the whole point of money-at-price.
    want = [60.0, -40.0, 70.0, -30.0]
    got = [round(v, 6) for v in f.pnl_c.tolist()]
    print(f"[money at price] {got} (want {want}) — YES at 40c: wins +60 / loses -40. "
          f"NO at a 70c YES-ask stakes 30c: wins +70 / loses -30.")
    ok &= got == want

    # clustering must widen relative to the naive interval on correlated games
    rng = np.random.default_rng(3)
    g = np.repeat(np.arange(12), 200)
    shock = rng.normal(0, 20, 12)[g]
    vals = pd.DataFrame({"game_id": g, "pnl_c": shock + rng.normal(0, 5, len(g))})
    cm = clustered_mean({k: v.pnl_c.tolist() for k, v in vals.groupby("game_id")})
    naive_hw = 1.96 * vals.pnl_c.std(ddof=1) / np.sqrt(len(vals))
    hw = (cm.hi - cm.lo) / 2
    print(f"[clustering] clustered half-width {hw:.2f}c vs naive {naive_hw:.2f}c "
          f"(ratio {hw / naive_hw:.1f}x; want >>1 on game-correlated data)")
    ok &= hw > 3 * naive_hw

    # Kish must fall when one game dominates
    print(f"[Kish] equal {kish(np.full(10, 100)):.2f} (want 10.00) · "
          f"dominated {kish(np.array([5000] + [10] * 9)):.2f} (want ~1)")
    ok &= abs(kish(np.full(10, 100)) - 10) < 1e-9 and kish(np.array([5000] + [10] * 9)) < 1.5

    # rule 22: an unproven zero must announce itself
    s = str(report_count("x", 0))
    print(f"[rule 22] unproven zero prints: {'UNPROVEN INSTRUMENT' in s}")
    ok &= "UNPROVEN INSTRUMENT" in s

    print("SELFTEST", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    d, filled = load()
    composition(d, filled)
    f = classify(filled)
    population_split(f)
    primary(filled)
    print("\nREAL fills only (the tradable population), by market type:")
    for k, v in f[f["pop"] == REAL].groupby("sports_market_type"):
        c = clustered_mean({g: x.pnl_c.tolist() for g, x in v.groupby("game_id")})
        if c:
            print(f"  {str(k)[:44]:<44s} {c.mean:+7.3f}c [{c.lo:+7.3f}, {c.hi:+7.3f}] "
                  f"G={c.n_clusters:2d} n={c.n:,}")
    print(f"  phantom share by type: "
          f"{f.groupby('sports_market_type')['pop'].apply(lambda s: round((s == PHANTOM).mean(), 3)).to_dict()}")
    four_doors(d, filled)
    league_shaped_or_structural(filled)
    abstentions()
    print("\n=== STANDING LANGUAGE ===")
    print("DESCRIPTIVE and HYPOTHESIS-GENERATING. In-sample, 34 games, one league, and")
    print("three model versions confounded with dates. Nothing here gates anything.")
    print(CAPITAL_LINE)


if __name__ == "__main__":
    main()
