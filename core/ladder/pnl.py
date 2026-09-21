"""What the night cost, what it must pay back, and what it never caught.

The pair is two legs bought at once: leg 1 BUY YES on the EASIER (higher) line
at its ask, leg 2 BUY NO on the HARDER (lower) line at ``1 - bid``. Leg 1 pays
$1 whenever the margin clears the lower line and leg 2 pays $1 whenever it does
not, so a FILLED PAIR collects exactly $1.00 per contract in every score, and a
second $1.00 when the final margin lands strictly between the two lines. Cost
is under $1.00 per contract whenever the ladder contradicted itself, so

    net_if_settled = qty_filled * 1.00 - cash paid

is the SETTLEMENT ARITHMETIC OF A FILLED PAIR. It is not realised, not marked,
and not a price: nothing here is money until the game settles and the venue
pays. Until then it is what the position is contracted to pay.

Two honesty rules the numbers here obey, because both failures are cheap to
make and expensive to read:

* An UNPAIRED leg is not half an arbitrage. It is a directional holding that
  settles at $0 or $1 and nothing in this module has a view on which. So its
  full cash cost is charged against `net_if_settled` (the worst case), and
  `leg_exposure` names the amount that is riding on the score rather than on
  the ladder. A "legged" attempt is the fill test's actual failure mode.
* A pair whose two legs filled DIFFERENT quantities is an arbitrage only to
  the smaller side; the remainder is an unpaired leg. `qty_filled` is the min,
  never the sum and never leg 1.

The tape half answers the other question: what the strategy SAW. The executor
only ever ticketed a spread-vs-spread pair worth $25 at quoted size, so the
per-game figures here filter to exactly that population -- the gap between
samples that carried a ticketable violation and attempts actually placed is
the night's real result, and it is a gap the ticket ledger alone cannot show.

Quoted size is not filled size. Every dollar figure drawn from the tape is
what the venue DISPLAYED; whether any of it is real is what the five attempts
are for.

Reads files. No venue call, no database, no order path.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

from core.ladder import desk, scan, tape

#: The executor's own floor: below this a violation was never ticketed, so a
#: "share of samples with an opportunity" that ignored it would count minutes
#: the strategy was never going to act on.
FLOOR_USD = 25.0

#: The date a game slug ends with, for naming the population a total covers.
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Per game, per render. A 20s cycle over four hours is ~720 samples; the cap
#: is a bound on a page that a person refreshes, not a statistical window.
MAX_SAMPLES = 3000


def _f(v) -> float:
    """A blank, a None or a torn value is 0.0 -- "did not fill" is a result."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _price(recorded, leg: dict | None) -> tuple[float, str]:
    """The price a leg actually traded at, else the limit it was sent at.

    The operator records qty and price by hand and sometimes leaves the price
    blank. A limit order fills at the limit or better, so the limit is the
    conservative stand-in -- but which one was used is reported, because a
    P&L built on order prices is a different number from one built on fills.
    """
    if recorded is not None and str(recorded).strip() != "":
        try:
            return float(recorded), "recorded"
        except ValueError:
            pass
    return _f((leg or {}).get("price")), "limit"


def game_key(game: str) -> str:
    """`aec-cfb-mia-wake-2026-09-18` and `cfb-mia-wake-2026-09-18` are the same
    game: the executor writes its files under the `aec-` prefix and strips it
    out of the ticket body."""
    return str(game or "").replace("aec-", "", 1)


# --------------------------------------------------------------------- #
# What was caught: the ticket ledger
# --------------------------------------------------------------------- #

def attempt_pnl(t: dict, *, fee_rate: float = scan.DEFAULT_FEE_RATE) -> dict:
    """One ticket's economics from the operator's record of what filled.

    `cost` is all cash paid, including a leg that never found its partner;
    `guaranteed` counts only paired contracts. An open or skipped ticket is
    all zeros -- it is in the ledger so the page can show what was declined.
    """
    rec = t.get("record") or {}
    leg1, leg2 = t.get("leg1") or {}, t.get("leg2") or {}
    l1q, l2q = _f(rec.get("l1q")), _f(rec.get("l2q"))
    l1p, src1 = _price(rec.get("l1p"), leg1)
    l2p, src2 = _price(rec.get("l2p"), leg2)
    qty = min(l1q, l2q)
    cost = l1q * l1p + l2q * l2p
    # At `fee_rate`, the caller's constant: a ticket record carries no fee
    # coefficient (the venue raised it on 2026-09-17; core/fees.py).
    fees = l1q * scan.fee(l1p, fee_rate) + l2q * scan.fee(l2p, fee_rate)
    return {
        "ticket": t.get("id"),
        "game": game_key(t.get("game")),
        "ts": t.get("ts"),
        "at": rec.get("at"),
        "status": t.get("status", "open"),
        "high_line": _f(leg1.get("market_line")),
        "low_line": _f(leg2.get("market_line")),
        "edge_c": t.get("edge_c"),
        "ticket_qty": _f(leg1.get("qty")),
        "ticket_cost_usd": _f(t.get("cost_usd")),
        "l1q": l1q, "l1p": l1p, "l1s": rec.get("l1s"),
        "l2q": l2q, "l2p": l2p, "l2s": rec.get("l2s"),
        "price_source": src1 if src1 == src2 else f"{src1}/{src2}",
        "qty_filled": qty,
        "cost": cost,
        "fees": fees,
        "guaranteed": qty * 1.0,
        "net_if_settled": qty * 1.0 - cost,
        "net_after_fees": qty * 1.0 - cost - fees,
        "bonus_if_between": qty * 1.0,
        # Legged = one leg on, the other not, in EITHER direction. Testing only
        # the leg-1-filled case would call the mirror (leg 1 missed, leg 2 on)
        # not legged while charging it the same one-sided exposure to the
        # score, which is the failure mode the fill test exists to count.
        "legged": qty == 0 and (l1q > 0) != (l2q > 0),
        "loose_leg": 1 if (qty == 0 and l1q > 0) else (2 if (qty == 0 and l2q > 0) else None),
        "unpaired_qty": (l1q - qty) + (l2q - qty),
        "leg_exposure": (l1q - qty) * l1p + (l2q - qty) * l2p,
        "via": rec.get("via"),
    }


def session(out_dir: str, *, tickets: list[dict] | None = None,
            fee_rate: float = scan.DEFAULT_FEE_RATE) -> dict:
    """Every ticket in `out_dir` plus the totals over them.

    The population is the DIRECTORY, not the evening: `games` and `dates` say
    which nights it covers so the page can name it. `placed` and `recorded`
    count all of them; `tally` is the REGISTERED rule, which reads the first
    five placed attempts only and is the thing the finding stands or falls on
    (docs/math/ladder-fill-test.md).
    """
    tickets = desk.load_tickets(out_dir) if tickets is None else tickets
    rows = [attempt_pnl(t, fee_rate=fee_rate) for t in tickets]
    filled = [r for r in rows if r["qty_filled"] > 0]
    # The intents files accumulate across nights, so these totals are over
    # EVERY ticket in the directory, not over tonight. The page has to be able
    # to say which -- a P&L labelled "tonight" that carries last night's legged
    # attempt is the same number with the wrong name on it.
    games = sorted({r["game"] for r in rows})
    dates = sorted({r["game"][-10:] for r in rows if _DATE.match(r["game"][-10:])})
    total = {k: sum(r[k] for r in rows) for k in
             ("cost", "fees", "guaranteed", "net_if_settled", "net_after_fees",
              "bonus_if_between", "leg_exposure", "qty_filled")}
    return {
        "attempts": rows,
        "games": games,
        "dates": dates,
        "placed": sum(1 for r in rows if r["status"] in ("placed", "recorded")),
        "recorded": sum(1 for r in rows if r["status"] == "recorded"),
        "skipped": sum(1 for r in rows if r["status"] == "skipped"),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "pairs_filled": len(filled),
        "legged": sum(1 for r in rows if r["legged"]),
        "committed": total["cost"],
        "fees": total["fees"],
        "guaranteed": total["guaranteed"],
        "net_if_settled": total["net_if_settled"],
        "net_after_fees": total["net_after_fees"],
        "bonus_if_between": total["bonus_if_between"],
        "leg_exposure": total["leg_exposure"],
        "qty_filled": total["qty_filled"],
        "tally": desk.tally(tickets),
    }


# --------------------------------------------------------------------- #
# What was seen: the opportunity tape
# --------------------------------------------------------------------- #

def _samples(path: str, max_samples: int = MAX_SAMPLES) -> list[dict]:
    """Every complete sample in a freshness tape, oldest first, newest kept.

    A torn final line (the instrument was mid-write) is skipped rather than
    raised on, the same way `core.ladder.tape.last_line` treats it.

    ONE rule with `core.ladder.tape.samples`, deliberately: a sample whose
    `rows` is empty (no rung had a two-sided book yet) is a sample the
    instrument took, and dropping it here would divide `with_violation` by a
    denominator that excludes exactly the cycles in which there was nothing to
    find -- flattering every share on the page, under a column headed
    "samples", while /ladder's own history strip counted the same file higher.
    """
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("rows"), list):
                    rows.append(row)
    except OSError:
        return []
    return rows[-max_samples:]


def tape_summary(path: str, *, floor_usd: float = FLOOR_USD,
                 max_samples: int = MAX_SAMPLES,
                 fee_rate: float = scan.DEFAULT_FEE_RATE) -> dict:
    """One game's tape as the opportunity it showed: how often, how big.

    ONE pair per sample, not all of them. A single mispriced rung contradicts
    every other rung it pairs with -- six in one recorded ladder -- and those
    pairs share a leg, so they compete for the same displayed depth. Counting
    them all would multiply one opportunity by the size of the ladder
    (`core.ladder.scan.best_per_game`, which overstated CFB by 2.5x).

    Winner-leg pairs are dropped: the executor never ticketed one, so counting
    them here would credit the strategy with chances it declined by design.
    """
    game = tape.game_of(path)
    samples = _samples(path, max_samples)
    bests: list[dict] = []
    with_violation = over_floor = 0
    last: dict = {}
    for s in samples:
        last = tape.ladder(s, game, fee_rate=fee_rate)
        pairs = [v for v in last["violations"] if v["spread_pair"]]
        if not pairs:
            continue
        with_violation += 1
        best = max(pairs, key=lambda v: v["dollars"])
        if best["dollars"] >= floor_usd:
            over_floor += 1
        bests.append({**best, "t": s.get("t")})

    seen: dict[tuple[float, float], dict] = {}
    for b in sorted(bests, key=lambda v: -v["dollars"]):
        seen.setdefault((b["high_line"], b["low_line"]), b)
    return {
        "game": game,
        "key": game_key(game),
        "samples": len(samples),
        "with_violation": with_violation,
        "share": (with_violation / len(samples)) if samples else 0.0,
        "over_floor": over_floor,
        "share_over_floor": (over_floor / len(samples)) if samples else 0.0,
        "floor_usd": floor_usd,
        "best_dollars": max((b["dollars"] for b in bests), default=0.0),
        "top": list(seen.values())[:5],
        "last_t": last.get("t"),
        # Two counts, deliberately not one name: `last_pairs` is every pair the
        # scanner reports at the last sample and `last_spread_pairs` only those
        # the executor would ticket. The instrument's own `viol_*` are a THIRD
        # count, over its two books; they are carried, not merged.
        "last_pairs": len(last.get("violations") or []),
        "last_spread_pairs": sum(1 for v in (last.get("violations") or []) if v["spread_pair"]),
        "viol_rest": last.get("viol_rest"), "viol_ws": last.get("viol_ws"),
        "viol_common": last.get("viol_common"),
        "ws_msgs": last.get("ws_msgs"), "ws_trades": last.get("ws_trades"),
    }


def opportunity(out_dir: str, **kw) -> list[dict]:
    """Every game with a freshness tape tonight, by game."""
    return sorted((tape_summary(p, **kw) for p in tape.tape_files(out_dir, last=12)),
                  key=lambda s: s["key"])


# --------------------------------------------------------------------- #
# The live strip: is anything actually running?
# --------------------------------------------------------------------- #

def _age(path: str, now: float) -> float | None:
    try:
        return now - os.path.getmtime(path)
    except OSError:
        return None


def game_status(out_dir: str, *, now: float | None = None,
                within_s: float = 6 * 3600, **kw) -> list[dict]:
    """One row per game with a file touched in the window: tickets issued, the
    tape's last sample, and how long since each writer last wrote.

    The two ages are FILE ages, which say the process is alive, not that the
    venue is moving: a frozen board still gets sampled every 20s and every
    arrival alarm stays green (docs/ops/freshness-is-not-liveness). `ws_msgs`
    and the last sample's stamp are carried beside them for that reason.
    """
    now = dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now
    tapes = {tape.game_of(p): p for p in tape.tape_files(out_dir, last=12)}
    # A game the executor has not ticketed still has a stream writing every
    # ~20s, and `desk.recent_games` only knows the executor's two files. Taking
    # the union means a live game cannot be missing from the strip because the
    # half of it that found nothing is the half that was asked.
    live = list(desk.recent_games(out_dir, within_s=within_s, now=now))
    fresh = [g for g, p in tapes.items()
             if g not in live and _age(p, now) is not None and _age(p, now) <= within_s]
    live += sorted(fresh)
    rows = []
    for game in live:
        intents = desk.read_jsonl(os.path.join(out_dir, f"ladder_intents_{game}.jsonl"))
        tape_path = tapes.get(game)
        summary = tape_summary(tape_path, **kw) if tape_path else {}
        rows.append({
            "game": game,
            "key": game_key(game),
            "tickets": sum(1 for it in intents if "leg1" in it and "leg2" in it),
            "issued_usd": sum(_f(it.get("cost_usd")) for it in intents),
            "executor_age_s": _age(os.path.join(out_dir, f"live_ladder_{game}.txt"), now),
            "tape_age_s": _age(tape_path, now) if tape_path else None,
            **{k: summary.get(k) for k in
               ("samples", "share", "over_floor", "share_over_floor", "best_dollars",
                "last_t", "last_pairs", "last_spread_pairs", "viol_rest", "viol_ws",
                "viol_common", "ws_msgs", "ws_trades")},
        })
    return rows
