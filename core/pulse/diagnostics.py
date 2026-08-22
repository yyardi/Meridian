"""PULSE tape diagnostics — the why behind every trade.

**DESCRIPTIVE. NO VERDICT, NO GATE.** The registered PULSE tape verdict arms at
its own floor, and nothing computed here may feed it: every number below was
computed *after* seeing the tape, which is precisely what a pre-registration
forbids as evidence. This module reports what the tape contains and draws no
conclusion — the same standing as :mod:`core.audit.hand_trades`.

Read [`docs/math/pulse-diagnostics.md`](../../docs/math/pulse-diagnostics.md)
for the findings; this file is how they are produced.

THE FUNNEL IS THE POINT, and it is not the funnel the brief assumed
--------------------------------------------------------------------
A decision is not a position. The tape records an *intent* to enter, a limit
order resting at the touch, and only some of those are ever hit:

    entries decided      116
      filled              63     <- these are the positions
      never filled        53     <- 46%: the order rested and the book left

Every P&L statement here is over the 63 **filled** entries. Quoting a rate over
116 counts orders that never existed as trades, which flatters or damns the
strategy depending on which way you round.

MONEY AT PRICE (C11), and the frame that has to be right
---------------------------------------------------------
Cost is what the contract cost in its own frame: a YES contract costs the price
paid, a NO contract costs ``1 - price``. Verified against the tape's own
``stake_usd``: entry id=3, side=no, price 0.90, 4.653 contracts, stake $0.4653
= 4.653 x (1 - 0.90). The venue quotes everything in the YES frame (V14/V19),
so a NO position's proceeds at exit price ``p`` are ``contracts x (1 - p)``,
and at settlement it wins when the market settles 0.

Getting that backwards produces plausible numbers with inverted meaning, which
is how #16 passed a gate it should have failed.

    python -m core.pulse.diagnostics            # text report
    python -m core.pulse.diagnostics --json     # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text as sql

#: Bucket edges for the edge->outcome diagnostic. Fixed here rather than fitted
#: to the data: buckets chosen after seeing where the mass fell would be a
#: shape read off its own noise.
EDGE_BUCKETS = ((0.00, 0.05), (0.05, 0.075), (0.075, 0.10),
                (0.10, 0.15), (0.15, 0.25), (0.25, 1.00))

#: Below this many filled entries a bucket reports NO DATA rather than a
#: number. A realised ROI on n=4 is an anecdote with a decimal point.
MIN_BUCKET_N = 10

#: Counterfactual profit targets for the exit-policy description. NOT a tuning
#: exercise and NOT a verdict — any change to the live target needs its own
#: registration, written before the number is computed.
COUNTERFACTUAL_TARGETS = (0.03, 0.05, 0.08, 0.10)


# --------------------------------------------------------------------------- #
# The queries. Aggregation stays in SQL; the tape is small but the habit is not
# optional after 2026-08-18 (see core/pulse/replay.py).
# --------------------------------------------------------------------------- #

_FUNNEL = """
select
  (select count(*) from pulse_decisions where action='enter')                    as decided,
  (select count(*) from pulse_decisions where action='enter'
     and filled_at is not null)                                                  as filled,
  (select count(*) from pulse_decisions where action='enter'
     and filled_at is null)                                                      as never_filled,
  (select count(distinct entry_id) from pulse_decisions where action='exit')     as entries_with_exit_row,
  (select count(distinct entry_id) from pulse_decisions where action='exit'
     and filled_at is not null)                                                  as entries_with_filled_exit,
  (select count(*) from pulse_decisions where action='exit')                     as exit_rows,
  (select count(distinct event_slug) from pulse_decisions)                       as games,
  (select count(distinct market_slug) from pulse_decisions)                      as markets
"""

#: Proceeds in the position's own frame — the single expression every money
#: figure here depends on.
_PROCEEDS = """
    case
      when x.entry_id is not null then
        f.contracts * (case when f.side='yes' then x.limit_price else 1 - x.limit_price end)
      when f.settlement is not null then
        f.contracts * (case when (f.side='yes') = (f.settlement = 1) then 1 else 0 end)
      else 0
    end
"""

_FILLED_ENTRIES = """
with filled_entry as (
  select id, side, contracts, stake_usd, settlement, edge_net,
         sports_market_type, period, event_slug
  from pulse_decisions where action='enter' and filled_at is not null
),
best_exit as (
  select distinct on (entry_id) entry_id, reason, limit_price
  from pulse_decisions where action='exit' and filled_at is not null
  order by entry_id, filled_at
)
"""


def _rows(session, statement: str) -> list:
    return session.execute(sql(statement)).all()


def exit_anatomy(session) -> dict:
    """P&L decomposed by how the position ended. Question 1."""
    rows = _rows(session, _FILLED_ENTRIES + f"""
        select coalesce(x.reason, 'rode_to_settlement') as path,
               count(*) as n,
               round(sum(f.stake_usd)::numeric, 4) as staked,
               round(sum({_PROCEEDS})::numeric, 4) as returned
        from filled_entry f left join best_exit x on x.entry_id = f.id
        group by 1 order by 2 desc
    """)
    paths = []
    for path, n, staked, returned in rows:
        staked, returned = float(staked), float(returned)
        paths.append({
            "path": path, "n": n,
            "staked": round(staked, 2), "returned": round(returned, 2),
            "net": round(returned - staked, 2),
            "roi": round((returned - staked) / staked, 4) if staked else None,
        })
    total_s = sum(p["staked"] for p in paths)
    total_r = sum(p["returned"] for p in paths)
    return {
        "paths": paths,
        "total": {
            "staked": round(total_s, 2), "returned": round(total_r, 2),
            "net": round(total_r - total_s, 2),
            "roi": round((total_r - total_s) / total_s, 4) if total_s else None,
        },
    }


def distribution(session) -> dict:
    """Where the entries actually are. Question 2."""
    def by(column: str, label: str) -> list[dict]:
        return [
            {label: r[0], "decided": r[1], "filled": r[2],
             "fill_rate": round(r[2] / r[1], 3) if r[1] else None}
            for r in _rows(session, f"""
                select coalesce({column}, '(none)'), count(*), count(filled_at)
                from pulse_decisions where action='enter'
                group by 1 order by 2 desc""")
        ]
    return {
        "by_market_type": by(
            "replace(sports_market_type,'basketball_team_full_game_','')", "type"),
        "by_period": by("period", "period"),
        "by_game": [
            {"game": r[0], "decided": r[1], "markets": r[2], "filled": r[3]}
            for r in _rows(session, """
                select event_slug, count(*), count(distinct market_slug), count(filled_at)
                from pulse_decisions where action='enter'
                group by 1 order by 2 desc""")
        ],
    }


def edge_to_outcome(session) -> dict:
    """Claimed edge at decision vs realised money. Question 3.

    A bucket thinner than MIN_BUCKET_N filled entries reports NO DATA. The
    pregame model's edge/outcome correlation was -0.069 on far more bets; a
    shape read off n=4 here would be noise with a decimal point.
    """
    out = []
    for lo, hi in EDGE_BUCKETS:
        (n, staked, returned), = _rows(session, _FILLED_ENTRIES + f"""
            select count(*), coalesce(round(sum(f.stake_usd)::numeric,4),0),
                   coalesce(round(sum({_PROCEEDS})::numeric,4),0)
            from filled_entry f left join best_exit x on x.entry_id = f.id
            where f.edge_net >= {lo} and f.edge_net < {hi}
        """)
        decided, = _rows(session, f"""
            select count(*) from pulse_decisions where action='enter'
              and edge_net >= {lo} and edge_net < {hi}""")[0]
        bucket = {"edge_from": lo, "edge_to": hi,
                  "decided": decided, "filled": n,
                  "fill_rate": round(n / decided, 3) if decided else None}
        if n < MIN_BUCKET_N:
            bucket |= {"status": "NO DATA", "roi": None,
                       "note": f"{n} filled entries, below the {MIN_BUCKET_N} floor"}
        else:
            staked, returned = float(staked), float(returned)
            bucket |= {"status": "measured",
                       "staked": round(staked, 2), "returned": round(returned, 2),
                       "roi": round((returned - staked) / staked, 4) if staked else None}
        out.append(bucket)
    return {"buckets": out, "min_bucket_n": MIN_BUCKET_N}


def suppressed_intent(session) -> dict:
    """What the bankroll, not the model, decided. Question 4.

    ``binding_constraint`` names what SET the size, not what refused the trade —
    a distinction the brief's framing blurs. Rows annotated
    ``below_minimum_trade_qty`` were still placed and many still filled; the
    venue minimum set their size upward, it did not suppress them.
    """
    caps = [
        {"constraint": r[0], "entries": r[1], "filled": r[2],
         "desired_stake": round(float(r[3]), 2),
         "avg_bankroll": round(float(r[4]), 2) if r[4] is not None else None}
        for r in _rows(session, """
            select binding_constraint, count(*), count(filled_at),
                   coalesce(sum(stake_usd),0), avg(bankroll_usd)
            from pulse_decisions
            where action='enter' and binding_constraint is not null
            group by 1 order by 2 desc""")
    ]
    return {"by_constraint": caps,
            "entries_total": sum(c["entries"] for c in caps)}


def report(session, *, export_label: str) -> dict:
    (decided, filled, never, with_exit_row, with_filled_exit,
     exit_rows, games, markets), = _rows(session, _FUNNEL)
    return {
        "kind": "DESCRIPTIVE — no verdict, no gate, computed after seeing the tape",
        "export": export_label,
        "funnel": {
            "entries_decided": decided,
            "entries_filled": filled,
            "entries_never_filled": never,
            "fill_rate": round(filled / decided, 4) if decided else None,
            "entries_with_exit_row": with_exit_row,
            "entries_with_filled_exit": with_filled_exit,
            "rode_to_settlement": filled - with_filled_exit,
            "exit_rows": exit_rows,
            "games": games, "markets": markets,
        },
        "exit_anatomy": exit_anatomy(session),
        "distribution": distribution(session),
        "edge_to_outcome": edge_to_outcome(session),
        "suppressed_intent": suppressed_intent(session),
    }


def _print(r: dict) -> None:
    f = r["funnel"]
    print(f"\nPULSE TAPE DIAGNOSTICS — {r['export']}")
    print("DESCRIPTIVE ONLY. No verdict, no gate.")
    print("=" * 70)
    print(f"\nFUNNEL  {f['entries_decided']} decided -> {f['entries_filled']} filled "
          f"({f['fill_rate']:.0%}) · {f['entries_never_filled']} never filled")
    print(f"        of the filled: {f['entries_with_filled_exit']} exited, "
          f"{f['rode_to_settlement']} rode to settlement")
    print("\nEXIT ANATOMY (filled entries, money at price)")
    print(f"   {'path':<22}{'n':>4}{'staked':>10}{'returned':>10}{'net':>9}{'ROI':>9}")
    for p in r["exit_anatomy"]["paths"]:
        roi = "n/a" if p["roi"] is None else f"{p['roi']:+.1%}"
        print(f"   {p['path']:<22}{p['n']:>4}{p['staked']:>10.2f}"
              f"{p['returned']:>10.2f}{p['net']:>9.2f}{roi:>9}")
    t = r["exit_anatomy"]["total"]
    print(f"   {'TOTAL':<22}{'':>4}{t['staked']:>10.2f}{t['returned']:>10.2f}"
          f"{t['net']:>9.2f}{t['roi']:>+8.1%}")
    print("\nEDGE -> OUTCOME")
    for b in r["edge_to_outcome"]["buckets"]:
        if b["status"] == "NO DATA":
            print(f"   {b['edge_from']:.0%}-{b['edge_to']:.0%}  "
                  f"decided={b['decided']:<4} filled={b['filled']:<4} NO DATA")
        else:
            print(f"   {b['edge_from']:.0%}-{b['edge_to']:.0%}  "
                  f"decided={b['decided']:<4} filled={b['filled']:<4} "
                  f"ROI {b['roi']:+.1%}")
    print("\nBINDING CONSTRAINT (what SET the size, not what refused the trade)")
    for c in r["suppressed_intent"]["by_constraint"]:
        print(f"   {c['constraint']:<26} entries={c['entries']:<4} "
              f"filled={c['filled']:<4} desired ${c['desired_stake']:.2f}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-pulse-diagnostics")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--database-url", default=None,
                        help="defaults to the eval copy; never production")
    parser.add_argument("--export-label", default="unlabelled run",
                        help="which tape export this run read")
    args = parser.parse_args()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = args.database_url or (
        "postgresql+psycopg://meridian:meridian@localhost:5433/meridian_eval")
    with sessionmaker(bind=create_engine(url))() as session:
        result = report(session, export_label=args.export_label)
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        print()
    else:
        _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
