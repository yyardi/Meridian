"""The ladder strategies: a rule over one priced market row.

ARCHITECTURE.md §4 step 2. This registry WAS `cfb/run_paper_book.py`'s, moved
here verbatim so the paper book, the sandbox and anything later read one table
instead of three copies. A strategy is registered by name BEFORE its weeks
accrue; adding one is a new entry, CHANGING ONE IS A NEW NAME.

The rule is a predicate on a priced row and nothing else -- no clock, no
settlement, no database -- which is what makes `select` testable without any of
them, and what let the move be proved byte-identical on a 200-row fixture
rather than argued.
"""
from __future__ import annotations

from strategies.base import Bet, price_of


def mid(r):
    return (r["bid"] + r["ask"]) / 2


#: Names that select IDENTICAL rows with opposite sides. Their P&Ls sum to minus
#: the round-trip cost (spread + both fees), a constant that does not depend on
#: any outcome -- so one of a pair beating the other is arithmetic, not evidence,
#: and the two carry one statistic between them. Printed beside the verdict so a
#: reader cannot take "under beat over" for a finding (audit, 2026-09-13).
COMPLEMENTS = {
    "cfb_total_under_all": "cfb_total_over_all",
    "nfl_total_under_all": "nfl_total_over_all",
    "mlb_total_under_all": "mlb_total_over_all",
    "mlb_f5_total_under_all": "mlb_f5_total_over_all",
    # Identical rows, opposite side: all winner rows in 0.05-0.95, and the
    # coin-flip band of the first-five spread. Their P&Ls sum to minus the
    # round-trip cost, so one beating the other is arithmetic.
    "mlb_winner_home_all": "mlb_winner_away_all",
    "mlb_f5_spread_no_40_60": "mlb_f5_spread_yes_40_60",
    "cricket_home_yes_all": "cricket_away_no_all",
}
COMPLEMENTS.update({v: k for k, v in list(COMPLEMENTS.items())})

STRATEGIES = {
    # --- the two the operator asked to keep alive, exactly as they were found
    "cfb_spread_no_20_30":    dict(league="cfb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    "wnba_spread_yes_80_100": dict(league="wnba", types=("full_game_spread",), side="yes",
                                   rule=lambda r: mid(r) >= 0.80),
    # --- cricket and table tennis, registered 2026-09-13 BEFORE any tape.
    # YES IS THE HOME TEAM on these (nfl/cfb/mlb are the exception, not these).
    # county can settle 0.5 on a draw, which bet_pnl handles arithmetically:
    # a half settlement pays half the ticket and still charges the full fee.
    "cricket_home_yes_all":   dict(league="cricket", types=("match_winner",), side="yes",
                                   rule=lambda r: True),
    "cricket_away_no_all":    dict(league="cricket", types=("match_winner",), side="no",
                                   rule=lambda r: True),
    "cricket_home_fav_yes_60": dict(league="cricket", types=("match_winner",), side="yes",
                                    rule=lambda r: mid(r) >= 0.60),
    "cricket_home_dog_yes_40": dict(league="cricket", types=("match_winner",), side="yes",
                                    rule=lambda r: mid(r) <= 0.40),
    "tt_home_fav_yes_60":     dict(league="tabletennis", types=("match_winner",), side="yes",
                                   rule=lambda r: mid(r) >= 0.60),
    "tt_home_dog_yes_40":     dict(league="tabletennis", types=("match_winner",), side="yes",
                                   rule=lambda r: mid(r) <= 0.40),
    "wnba_total_under_all":   dict(league="wnba", types=("full_game_total",), side="no",
                                   rule=lambda r: True),
    # --- the decomposition's cleaner versions (home-referenced twins), beside them
    "cfb_spread_home_all":    dict(league="cfb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),   # NO on every away rung = home side, every rung
    "wnba_spread_no_00_20":   dict(league="wnba", types=("full_game_spread",), side="no",
                                   rule=lambda r: mid(r) <= 0.20),            # the home-favourite twin of yes_80_100
    # --- NFL, same rules as CFB, no prior
    "nfl_spread_no_20_30":    dict(league="nfl",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    "nfl_spread_home_all":    dict(league="nfl",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),
    # --- MLB, registered before any tape exists (recorder overlay staged 2026-09-13)
    "mlb_total_under_all":    dict(league="mlb",  types=("full_game_total",), side="no",
                                   rule=lambda r: True),
    "mlb_total_over_all":     dict(league="mlb",  types=("full_game_total",), side="yes",
                                   rule=lambda r: True),
    "mlb_winner_fav_yes":     dict(league="mlb",  types=("full_game_winner",), side="yes",
                                   rule=lambda r: mid(r) >= 0.60),
    "mlb_winner_dog_yes":     dict(league="mlb",  types=("full_game_winner",), side="yes",
                                   rule=lambda r: mid(r) <= 0.40),
    "mlb_spread_no_20_30":    dict(league="mlb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    # --- registered 2026-09-13 18:30Z by the manager: the WNBA under/over asymmetry tried on football, and
    #     MLB first-five markets (thinner, retail). CFB/NFL totals already have two Saturdays of tape: the
    #     first read of those is a back-read, labelled so; pre-registered from 09-19 on.
    "cfb_total_under_all":    dict(league="cfb",  types=("full_game_total",), side="no",  rule=lambda r: True),
    "cfb_total_over_all":     dict(league="cfb",  types=("full_game_total",), side="yes", rule=lambda r: True),
    "nfl_total_under_all":    dict(league="nfl",  types=("full_game_total",), side="no",  rule=lambda r: True),
    "nfl_total_over_all":     dict(league="nfl",  types=("full_game_total",), side="yes", rule=lambda r: True),
    "mlb_f5_total_under_all": dict(league="mlb",  types=("first_five_total",), side="no",  rule=lambda r: True),
    "mlb_f5_total_over_all":  dict(league="mlb",  types=("first_five_total",), side="yes", rule=lambda r: True),
    "mlb_f5_spread_no_20_30": dict(league="mlb",  types=("first_five_spread",), side="no",
                                   rule=lambda r: 0.20 <= mid(r) < 0.30),
    # --- MLB, registered 2026-09-14 15:00Z by the manager, BEFORE the tape exists:
    #     exactly ONE MLB game has settled, so no outcome can have chosen these.
    #     They are POPULATIONS, not theories about what the venue gets wrong. Each
    #     is picked because baseball's structure differs from football in a way
    #     that makes the football-derived buckets the wrong shape:
    #
    #     * Home advantage is the smallest of the major leagues, so a generic home
    #       adjustment is a larger relative error here than anywhere else. That
    #       makes the home/away split the FIRST cut on this league rather than a
    #       robustness check -- and every price-bucket finding this project has
    #       produced turned out to be that split.
    #     * The run line is a FIXED +/-1.5, not a fitted spread, so "heavy
    #       favourite on the spread" is one population in baseball and a moving
    #       target in football. The two arms below are the away-favourite and the
    #       home-favourite versions of the same bet, in the two frames the venue
    #       offers, so neither can be reported without the other.
    #     * First five innings excludes the bullpen entirely, which is a different
    #       game with different variance, and it is the thinnest MLB market.
    "mlb_winner_away_all":    dict(league="mlb",  types=("full_game_winner",), side="yes",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),
    "mlb_winner_home_all":    dict(league="mlb",  types=("full_game_winner",), side="no",
                                   rule=lambda r: 0.05 <= mid(r) <= 0.95),
    "mlb_spread_yes_70_100":  dict(league="mlb",  types=("full_game_spread",), side="yes",
                                   rule=lambda r: mid(r) >= 0.70),
    "mlb_spread_no_00_30":    dict(league="mlb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: mid(r) <= 0.30),
    "mlb_f5_spread_yes_40_60": dict(league="mlb", types=("first_five_spread",), side="yes",
                                    rule=lambda r: 0.40 <= mid(r) <= 0.60),
    "mlb_f5_spread_no_40_60": dict(league="mlb",  types=("first_five_spread",), side="no",
                                   rule=lambda r: 0.40 <= mid(r) <= 0.60),
    # --- registered 2026-09-13 20:05Z from the decomposition grid (cfb/run_longshot_decomp.py, one of ~20 cells looked
    #     at): buying the AWAY side at YES-mid 50-60c lost -11.62c/contract [-21.74, -1.50] on 104 games; the mirror is
    #     NO (home) on those rungs. Pre-registered here with its twin for the 09-19 read; NFL gets the same pair, no prior.
    "cfb_spread_no_50_60":    dict(league="cfb",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.50 <= mid(r) < 0.60),
    "cfb_spread_yes_40_50":   dict(league="cfb",  types=("full_game_spread",), side="yes",
                                   rule=lambda r: 0.40 <= mid(r) < 0.50),   # the twin: away side at the same price
    "nfl_spread_no_50_60":    dict(league="nfl",  types=("full_game_spread",), side="no",
                                   rule=lambda r: 0.50 <= mid(r) < 0.60),
    "nfl_spread_yes_40_50":   dict(league="nfl",  types=("full_game_spread",), side="yes",
                                   rule=lambda r: 0.40 <= mid(r) < 0.50),
}


def select(rows, registry=None):
    """Every bet the registry's strategies take on these rows.

    Returns `{name: [Bet, ...]}`. A strategy that matches nothing gets an empty
    list rather than being absent -- "registered and picked nothing this week"
    and "not registered" are different facts, and the paper book prints them
    differently.
    """
    reg = STRATEGIES if registry is None else registry
    out = {}
    for name, st in reg.items():
        out[name] = [
            Bet(market_slug=r["market_slug"], side=st["side"],
                price=price_of(st["side"], r["bid"], r["ask"]),
                stake=price_of(st["side"], r["bid"], r["ask"]),
                game_id=r["game_id"])
            for r in rows
            if r.get("league") == st["league"]
            and any(r["mtype"].endswith(t) for t in st["types"])
            and st["rule"](r)
        ]
    return out
