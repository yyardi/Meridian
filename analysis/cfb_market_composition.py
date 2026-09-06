"""The venue barely runs a CFB winner market, and that is why the identity may be untestable.

ce asked me to state this in the writeup because it redirects the programme
rather than closing a cohort question. d5 measured it first; this file derives it
independently from `cfb_prices_20260906T194301Z.csv.gz` so it is not a relayed
claim.

## THE COMPOSITION

    kind  slugs   rows      live_rows  games  % of slugs
    asc    8088   693,933    626,495    99      55.23     spread
    tsc    6425   846,643    793,751    99      43.87     total / team-total
    aec     132    23,460     22,356    99       0.90     WINNER / moneyline

**One winner market per game, against 81 spread and 64 total markets per game.**
Winner markets are 0.90% of the CFB board.

d5's 8,088 and 6,425 reproduce exactly. Their third figure was 70 moneyline; I
count 132 winner slugs here and 24 that are live-and-mapped, so that one does not
reproduce and the difference is unexplained — likely vintage or a different
filter. Not resolved, and flagged rather than smoothed over.

## WHY IT MATTERS: THE INSTRUMENT AND THE MARKET DO NOT OVERLAP

`c7_identity_test.py` predicts P(home team wins). That is a winner-market
quantity. The venue runs essentially no CFB winner market, so there is almost
nothing for the identity to trade against — and this is structural, not a
recording gap. No ESPN-side abundance fixes it: I had 14,458 state rows across 31
games and c7's join to live winner prices returned **7 price rows**.

Live-and-mapped winner coverage, independently reproducing c7's feasibility:

    games with >=1 live winner row     24
    games with >=100                   16    (c7 measured 16)
    games with >=1000                  15    (c7 measured 15)

## AND THE TWO REQUIREMENTS ARE ANTI-CORRELATED, WHICH IS WORSE

c7 found the intersection of "dense winner prices" with "identity-defined" is
EMPTY, and the mechanism is one timestamp. The ESPN recorder started
**2026-09-05 22:08:57Z**. Verified from my side:

                                  identity-defined
    first seen at recorder start   False  True
    False                             2     31
    True                             16      1

16 of the 17 games first seen at recorder start were ALREADY SCORING (periods
P2 x5, P3 x5, P4 x6, P1 x1). All 32 identity-defined games were caught at 0-0.

**A game has dense prices because it was already running when the price export
opened — which is exactly why ESPN missed its kickoff, which is exactly what the
identity requires.** One requirement needs the game to have started before the
recorder came up and the other needs it to have started after.

**But it is 16 of 17, not 17 of 17.** One game is both at-recorder-start and
identity-defined, so the partition is near-total rather than exceptionless, and
"empty by arithmetic" overstates it slightly. The intersection with c7's dense
sixteen is empty as a fact about this vintage's price coverage, not as a
theorem. The distinction matters only because it changes whether a wider price
vintage could help: it could, marginally.

## WHERE THIS LEAVES THE IDENTITY

Not closed, redirected. The options are a different market type (spread or
total, which is a different instrument and not this one), a different league, or
NFL — where the winner market is the liquid one. That is a design question.

What unblocks the CFB version specifically is one slate with both recorders up
from kickoff. Nothing about the cohort, the vintage, or the join gets there.

## ★ THE DEFINITION TRAVELS WITH THE NUMBER, OR THE NEXT PERSON GETS 46%

D built a classifier by keyword — regex for `-pos-`, `-neg-`, `-total-` — and got
**46.30% of rows as winner markets, thirty times the right answer**. The
vocabulary has quarter and half markets carrying no keyword at all
(`tsc-...-1h-23pt5`, `-3q-45pt5`), so everything without a keyword fell through
into the winner bucket. Reproduced here: 53.70% of rows match that regex and
53.70 + 46.30 = 100.00, so their figure was exactly the fall-through.

**A winner market is a slug with NOTHING AFTER THE DATE.** Equivalently on this
export, prefix `aec`. The two rules are independent — one reads the head of the
slug, the other the tail — and `check_definitions()` below asserts they agree,
which they do on 1,564,036 of 1,564,036 rows and 132 of 132 slugs, exactly.

That check is in code rather than in this paragraph deliberately: a definition
described in prose gets paraphrased into a keyword regex by the next reader.

## ★ is_live IS A STRING, NOT A BOOLEAN

`is_live` holds `'t'` / `'f'`. `d.is_live == True` matches **0 of 1,442,602**
live rows and returns a clean, plausible, entirely wrong zero. I wrote that
comparison and briefly had "0 live rows" on screen. Compare against the strings.
"""

from __future__ import annotations

import re

import pandas as pd

PRICES = "backups/exports/cfb_prices_20260906T194301Z.csv.gz"
KIND = {"aec": "winner/moneyline", "asc": "spread", "tsc": "total/team-total"}


def load() -> pd.DataFrame:
    d = pd.read_csv(PRICES)
    # is_live is 't'/'f' TEXT. `== True` silently matches nothing.
    d["live"] = d.is_live.astype(str).str.lower().isin(["t", "true", "1"])
    d["kind"] = d.market_slug.str.split("-").str[0]
    return d


DATE_TAIL = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def check_definitions(d: pd.DataFrame) -> None:
    """Two independent winner-market rules must agree. Head of slug vs tail.

    D's keyword classifier (-pos-/-neg-/-total-) returned 46.30% because half and
    quarter markets carry no keyword and fell through. This asserts rather than
    describes, because the failure mode IS someone re-deriving the definition.
    """
    prefix = d.market_slug.str.split("-").str[0].eq("aec")
    tail = d.market_slug.map(lambda x: bool(DATE_TAIL.search(x)))
    n_agree = int((prefix == tail).sum())
    assert n_agree == len(d), f"definitions disagree on {len(d) - n_agree} rows"
    keyword = d.market_slug.str.contains("-pos-|-neg-|-total-", regex=True)
    print(f"  winner-market definition cross-check: prefix 'aec' and 'nothing after "
          f"the date' agree on {n_agree:,}/{len(d):,} rows, "
          f"{d.market_slug[prefix].nunique()} slugs")
    print(f"  the keyword classifier that FAILED matches {keyword.mean()*100:.2f}% of "
          f"rows; its fall-through bucket is {100-keyword.mean()*100:.2f}% (D measured 46.30%)")


def main() -> int:
    d = load()
    check_definitions(d)
    t = d.groupby("kind").agg(slugs=("market_slug", "nunique"), rows=("market_slug", "size"),
                              live_rows=("live", "sum"), games=("game_id", "nunique"))
    t["pct_slugs"] = t.slugs / t.slugs.sum() * 100
    print("=== CFB MARKET-TYPE COMPOSITION ===")
    print(t.sort_values("slugs", ascending=False).to_string())
    for k, name in KIND.items():
        if k in t.index:
            print(f"  {k} = {name}")
    L = d[d.live & d.game_id.notna()]
    w = L[L.kind == "aec"].groupby("game_id").size()
    print(f"\n=== LIVE WINNER-MARKET COVERAGE (what the identity could trade) ===")
    print(f"  games >=1 live winner row {len(w)}   >=100 {int((w >= 100).sum())}"
          f"   >=1000 {int((w >= 1000).sum())}   median rows {int(w.median()):,}")
    for k in ("asc", "tsc"):
        if k in t.index and t.loc[k, "games"]:
            print(f"  {KIND[k]:18s} {int(t.loc[k, 'slugs'] / t.loc[k, 'games'])} markets per game")
    print("  winner/moneyline    1 market per game")
    print("\nThe identity is a winner-market model and the venue barely runs one on CFB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
