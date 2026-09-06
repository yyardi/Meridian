"""Shared scoring for the two halves of `pulse_decisions`.

Written so builder-D and I run identical code on the entered and declined
branches rather than agreeing about method in prose. Import `score_branch` and
pass a frame; the dedupe policy is a parameter so both conventions can be shown
side by side.

## Answers to D's four questions, and one concession

1. **Dedupe.** My original number did **not** dedupe — it scored all rows, so
   markets with more decision rows carried more weight. **D's default (one row
   per market, earliest) is better than what I did**, and for a reason I found
   yesterday and then failed to apply here: a later mid has drifted toward the
   outcome and imports part of the answer. `dedupe="earliest"` is the default
   below; `dedupe="all"` reproduces my original.
2. **Market probability.** `mid = (market_bid + market_ask) / 2`, no other
   handling — both legs are 100% present on this table.
3. **Model probability.** `fair_value` directly, untransformed.
4. **Clustering.** `core.quote.adverse_selection.clustered_mean`: a
   cluster-robust sandwich on the per-row differences with a t critical value
   at df = G−1, clusters being games. **Not** "one mean per game then a
   t-interval" — those differ when games have unequal row counts, which they
   badly do here, so this is worth pinning rather than assuming.

## The outcome source, validated independently

`resolved_outcomes_20260901T195202Z.csv` joined on `market_slug`: **100.0%
coverage on all three actions** (enter 2,974/2,974, exit 2,679/2,679, hold
13,680/13,680) and **1.0000 agreement, zero disagreements** on the 1,944 rows
carrying a native `settlement`. D's validation reproduces exactly.

My first attempt at this check reported 10.1% coverage — a merge-suffix bug of
mine, where the joined column landed in `settlement_r` and I read the original
`settlement`. Recorded because the failure mode is silent: the join looked
selective when it was complete.

## ★ THE COMPARISON HAZARD, which is D's and which I endorse

The entered branch is selected **twice** — the model chose to enter and the book
chose to fill — while the declined branch is selected **once**. A difference
between the halves therefore confounds *what the gate declined* with *what the
book let us have*. The natural reading is that the difference is about the
model's judgement, and that reading is not available from this comparison
alone. It should be stated wherever the two halves are reported together.

**And my original entered-branch figure was selected a third time**, which D
caught: it used the 1,944 rows with a native settlement, 65.4% of enters. That
subset is not neutral — spread markets are 40.7% of it against 31.4% of the
rest, and mean `minutes_left` differs by 1.9. The join removes that layer, so
the number below supersedes the one I sent ce.
"""

from __future__ import annotations

import pandas as pd

from core.quote.adverse_selection import clustered_mean

DECISIONS = "backups/exports/pulse_decisions_full_20260901T195202Z.csv"
OUTCOMES = "backups/exports/resolved_outcomes_20260901T195202Z.csv"


def load_joined() -> pd.DataFrame:
    """Decisions with the venue outcome joined on market_slug."""
    d = pd.read_csv(DECISIONS)
    r = (pd.read_csv(OUTCOMES)[["market_slug", "settlement", "actual_total"]]
         .rename(columns={"settlement": "y"})
         .drop_duplicates("market_slug"))
    d = d.merge(r, on="market_slug", how="left")
    d["mid"] = (d.market_bid + d.market_ask) / 2.0
    # 't'/'f' STRING — third substrate carrying this trap (is_live on the QUOTE
    # tape, is_actionable on predictions, this one here).
    d["est"] = d.minutes_left_is_estimate.astype(str).str.lower().isin(
        ("t", "true", "1"))
    d["decided_at"] = pd.to_datetime(d.decided_at, utc=True, format="ISO8601",
                                     errors="coerce")
    return d


def score_branch(frame: pd.DataFrame, *, dedupe: str = "earliest"):
    """Brier(market) − Brier(model), game-clustered. Positive = model wins.

    dedupe: "earliest" (one row per market, the first decision — D's default
    and the correct one, since a later mid has drifted toward the outcome),
    "latest", or "all" (every row; reproduces my original figure).
    """
    f = frame.dropna(subset=["y", "fair_value", "mid"]).copy()
    if dedupe in ("earliest", "latest"):
        # .head(1)/.tail(1), NOT .first()/.last(). pandas' GroupBy.first() takes
        # the first NON-NULL value per COLUMN and returns a row that never
        # existed — silently mixing fields across decisions. Demonstrated:
        # on [{t:1, x:nan}, {t:2, x:5}] it returns {t:1, x:5}.
        # Sort key includes `id` so the dedupe is DETERMINISTIC. 24 (market,
        # instant) pairs in the entered branch carry more than one row — same
        # market, same microsecond, side=yes and side=no, sharing a mid and
        # differing in fair_value. Without a tie-break, which row wins is an
        # artefact of input ordering, and the entered model Brier ranges
        # 0.19916–0.19969 across orderings that are all equally "earliest".
        # That is immaterial against a ~0.037 interval and still not
        # reproducible, which is reason enough to pin it.
        f = f.sort_values(["decided_at", "id"])
        g = f.groupby("market_slug", as_index=False)
        f = g.head(1) if dedupe == "earliest" else g.tail(1)
    elif dedupe != "all":
        raise ValueError(f"unknown dedupe policy {dedupe!r}")
    f["b_model"] = (f.fair_value - f.y) ** 2
    f["b_mkt"] = (f["mid"] - f.y) ** 2
    f["b_diff"] = f.b_mkt - f.b_model
    res = clustered_mean({g: v.tolist() for g, v in f.groupby("game_id").b_diff})
    return res, f


def _verdict(r) -> str:
    return "MODEL" if r.lo > 0 else ("MARKET" if r.hi < 0 else "tie")


def main() -> int:
    d = load_joined()
    print(f"joined {len(d):,} rows | coverage {d.y.notna().mean()*100:.1f}% | "
          f"games {d.game_id.nunique()} | markets {d.market_slug.nunique()}\n")
    for dedupe in ("earliest", "all"):
        print(f"--- dedupe={dedupe} " + "-" * 46)
        print(f"  {'branch':>12} {'n':>7} {'G':>4} {'diff':>10} {'95% CI':>22}")
        for lbl, sub in (("enter", d[d.action == "enter"]),
                         ("hold", d[d.action == "hold"]),
                         ("exit", d[d.action == "exit"]),
                         ("declined", d[d.action.isin(["hold", "exit"])]),
                         ("ALL", d)):
            r, f = score_branch(sub, dedupe=dedupe)
            print(f"  {lbl:>12} {len(f):>7,} {r.n_clusters:>4} {r.mean:>+10.5f} "
                  f"[{r.lo:+.5f}, {r.hi:+.5f}] {_verdict(r)}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# RECONCILIATION WITH d5, AND WHAT IT TURNED UP
#
# d5 reported model 0.19969 / market 0.19448; I reported 0.20173 / 0.19692.
# Both differences are now accounted for exactly:
#
#   all enters, every row               2,974   0.19502 / 0.19132
#   native settlement only (my old)     1,944   0.20173 / 0.19692   <- superseded
#   earliest row per market (theirs)      480   0.19928 / 0.19448
#
# The market Brier matches d5 EXACTLY at 0.19448. The residual 0.00041 on the
# model side is tie-breaking on SEVEN markets whose earliest `decided_at` is
# tied to the microsecond — and the tied rows are the same market at the same
# instant with side=yes and side=no, sharing a `mid` and differing in
# `fair_value`. That is precisely the signature: identical market Brier,
# differing model Brier. Tie-break first vs last moves it 0.19928 -> 0.19948.
#
# ★ SO THE UNIT OF DECISION IS (market, side), NOT market. Deduping on
#   market_slug alone collapses a yes/no pair and keeps an arbitrary one.
#
# ★ AND CHECKING THAT TURNED UP A STRUCTURAL FACT NEITHER OF US HAD.
#   `fair_value` is the YES probability, not side-relative — verified, because
#   the side-relative reading was worth ruling out: corr(fv, settlement) stays
#   POSITIVE on side=no (+0.477 against the market's +0.506), and flipping the
#   outcome on `no` rows sends Brier from 0.195 to 0.329. Neither scoring has a
#   sign error.
#
#   But the decision rule fixes the sign of the model-market disagreement on
#   each arm BY CONSTRUCTION:
#
#       side=yes   n 1,342   fv > mid on 100.0%   mean(fv - mid) +0.0727
#       side=no    n 1,632   fv > mid on   0.0%   mean(fv - mid) -0.0870
#
#   The engine enters YES only when it judges yes underpriced and NO only when
#   overpriced. **So the Brier comparison is not run on a neutral sample — it
#   is run on the sample of maximal disagreement, with a fixed sign per arm.**
#   That is a third layer of selection under the two already named (the model
#   chose to enter; the book chose to fill), and it is the one that bears
#   directly on the forecast comparison rather than on the trade.
#
#   Per arm: side=yes diff -0.01487 [-0.04124, +0.01149]; side=no +0.00548
#   [-0.02340, +0.03437]. Both tie. Pooled -0.00370 [-0.01910, +0.01170].
#
#   Four calibration intervals were inspected (model/market x yes/no) and one
#   excluded zero — the market over-predicting YES by 11.06pp on the rows where
#   the model bet against it. One in four is within chance and it is NOT
#   reported as a finding.
