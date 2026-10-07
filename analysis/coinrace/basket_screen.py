"""Coin Race question 2 (Basket), a SCREEN on the once-a-minute book samples of the farm scorer.

Exactly one of a window's five markets pays $1 (a tie settles scalar; both tied legs pay the scalar
value, which sums to $1 in the 24 tie windows on the public API). On Kalshi the book lists YES bids and
NO bids, so the YES ask of a market = 1 - its best NO bid and its NO ask = 1 - its best YES bid.

  YES basket: buy all five YES at the asks.  net = 1 - sum(yes_ask) - sum(fee(yes_ask))
  NO  basket: buy all five NO  at the asks.  net = 4 - sum(1 - yes_bid) - sum(fee(1 - yes_bid))

fee(p, c) = ceil(0.07 * c * p * (1 - p)) to the cent for an order of c contracts (taker; makers pay
nothing). At c = 1 every leg costs at least 1c of fee, so a five-leg basket needs at least 5c of book
incoherence; at c = 200 the rounding is negligible.

The sample (`lip_sample` in farm_scorer.sqlite) stores each side's best bid, the reference price
(first level, walking down, whose cumulative size reaches 200 = Target/5), the incumbents' score and
the whole side's depth -- NOT the size at the best level. So the displayed size at an ask is only
bounded: >= 200 when that side's reference equals its best bid, < 200 otherwise.

    python analysis/coinrace/basket_screen.py --book DATA/book_minute.csv --markets DATA/raw/markets.jsonl
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math

FEE_NUM = 7            # 0.07 = 7/100


def fee_cents(p_cents: int, c: int) -> int:
    """Taker fee in whole cents for c contracts at p_cents: ceil(0.07 * c * p * (1-p)) dollars to the cent,
    in integer arithmetic (p in cents: 0.07*c*(p/100)*(1-p/100)*100 cents = 7*c*p*(100-p)/10000)."""
    if not 0 < p_cents < 100:
        raise ValueError(p_cents)
    num = FEE_NUM * c * p_cents * (100 - p_cents)
    return -(-num // 10000)


def basket_net(yes_bids: list[int], no_bids: list[int], c: int = 1) -> tuple[float, float]:
    """Net cents PER BASKET (one contract of each leg) at order size c, for the YES basket and the NO
    basket of one window. yes_bids/no_bids: the five markets' best bids in cents, same order."""
    assert len(yes_bids) == len(no_bids) == 5
    yes_asks = [100 - nb for nb in no_bids]
    no_asks = [100 - yb for yb in yes_bids]
    yes_cost = sum(a * c + fee_cents(a, c) for a in yes_asks)
    no_cost = sum(a * c + fee_cents(a, c) for a in no_asks)
    return (100 * c - yes_cost) / c, (400 * c - no_cost) / c


def load(book_csv: str, markets_jsonl: str):
    import csv
    mk = {}
    with open(markets_jsonl) as f:
        for line in f:
            m = json.loads(line)
            mk[m["ticker"]] = m
    ticks: dict[tuple[float, str], dict] = collections.defaultdict(dict)
    with open(book_csv) as f:
        for r in csv.DictReader(f):
            ev = r["ticker"].rsplit("-", 1)[0]
            ticks[(float(r["t"]), ev)][r["ticker"].rsplit("-", 1)[1]] = r
    return ticks, mk


def screen(ticks, mk, c: int = 1, shift: tuple[str, int] | None = None):
    """One row per sample tick with all five books. shift=(coin, cents) adds cents to that coin's best NO
    bid and best YES bid (i.e. moves both of its asks DOWN by cents): the control."""
    rows = []
    for (t, ev), legs in sorted(ticks.items()):
        if len(legs) != 5:
            continue
        coins = sorted(legs)
        yb = [round(float(legs[k]["yes_best"]) * 100) for k in coins]
        nb = [round(float(legs[k]["no_best"]) * 100) for k in coins]
        if shift is not None:
            i = coins.index(shift[0])
            yb[i] += shift[1]; nb[i] += shift[1]
            if not (0 < yb[i] < 100 and 0 < nb[i] < 100):
                continue
        ny, nn = basket_net(yb, nb, c)
        m0 = mk.get(f"{ev}-{coins[0]}", {})
        ot = dt.datetime.fromisoformat(m0["open_time"].replace("Z", "+00:00")).timestamp() if m0 else math.nan
        # displayed size bound: YES basket takes the NO bids, NO basket takes the YES bids
        big_y = all(float(legs[k]["ref_no"]) == float(legs[k]["no_best"]) for k in coins)
        big_n = all(float(legs[k]["ref_yes"]) == float(legs[k]["yes_best"]) for k in coins)
        rows.append({"t": t, "ev": ev, "minute": (t - ot) / 60, "yes_net": ny, "no_net": nn,
                     "sum_yes_ask": sum(100 - x for x in nb), "sum_yes_bid": sum(yb),
                     "size_ge200_yes": big_y, "size_ge200_no": big_n,
                     "min_depth_no": min(float(legs[k]["depth_no"]) for k in coins),
                     "min_depth_yes": min(float(legs[k]["depth_yes"]) for k in coins),
                     "results": {k: mk.get(f"{ev}-{k}", {}).get("result") for k in coins},
                     "yes_bids": dict(zip(coins, yb)), "no_bids": dict(zip(coins, nb))})
    return rows


def episodes(rows, key: str, gap_s: float = 90.0):
    """Runs of consecutive sample ticks (<= gap_s apart, same window) with net > 0. Each episode is
    counted once at its FIRST observed tick: the liquidity it displays can be taken once."""
    eps, cur = [], None
    for r in rows:
        pos = r[key] > 0
        if pos and cur is not None and r["ev"] == cur["ev"] and r["t"] - cur["t_last"] <= gap_s:
            cur["n"] += 1; cur["t_last"] = r["t"]; cur["max_net"] = max(cur["max_net"], r[key])
            continue
        if cur is not None:
            eps.append(cur); cur = None
        if pos:
            cur = {"ev": r["ev"], "t0": r["t"], "t_last": r["t"], "n": 1, "net0": r[key], "max_net": r[key], "row": r}
    if cur is not None:
        eps.append(cur)
    return eps


def report(rows, eps_y, eps_n, span_days: float) -> dict:
    out = {"n_ticks": len(rows), "span_days": span_days}
    for name, key, eps, szk, dk in (("yes", "yes_net", eps_y, "size_ge200_yes", "min_depth_no"),
                                     ("no", "no_net", eps_n, "size_ge200_no", "min_depth_yes")):
        clear = [r for r in rows if r[key] > 0]
        nets = sorted(r[key] for r in rows)
        per_ev = collections.defaultdict(float)
        lo = hi = 0.0
        for e in eps:
            r = e["row"]
            size_lo, size_hi = (200, r[dk]) if r[szk] else (1, 199)
            lo += e["net0"] * size_lo / 100; hi += e["net0"] * size_hi / 100
            per_ev[e["ev"]] += e["net0"] * size_hi / 100
        top5 = sum(sorted(per_ev.values(), reverse=True)[:5])
        out[name] = {"ticks_clearing": len(clear), "frac": len(clear) / max(len(rows), 1),
                     "median_net_c": nets[len(nets) // 2] if nets else None,
                     "p99_net_c": nets[int(0.99 * (len(nets) - 1))] if nets else None,
                     "max_net_c": nets[-1] if nets else None,
                     "episodes": len(eps), "episode_ticks": [e["n"] for e in eps],
                     "episode_net0_c": [e["net0"] for e in eps],
                     "episode_size_ge200": [e["row"][szk] for e in eps],
                     "usd_total_lo": lo, "usd_total_hi": hi,
                     "usd_per_day_lo": lo / span_days, "usd_per_day_hi": hi / span_days,
                     "top5_share": (top5 / sum(per_ev.values())) if per_ev and sum(per_ev.values()) > 0 else None}
    return out


# ---------------------------------------------------------------- second instrument: the venue's 1-minute candles
def screen_candles(candles, c: int = 1):
    """candles: rows (ticker, end_period_ts, yes_bid_close, yes_ask_close). One basket per (window, minute end)
    at which ALL FIVE markets have a candle with a two-sided book (0 < bid, ask < 1): a simultaneous snapshot
    from the venue itself, independent of the farm scorer's book tracker. No sizes."""
    by = collections.defaultdict(dict)
    for tk, e, yb, ya in candles:
        if yb is None or ya is None or not (0 < yb) or not (ya < 1):
            continue
        ev, coin = tk.rsplit("-", 1)
        by[(float(e), ev)][coin] = (round(yb * 100), round((1 - ya) * 100))
    rows = []
    for (e, ev), legs in sorted(by.items()):
        if len(legs) != 5:
            continue
        coins = sorted(legs)
        yb = [legs[k][0] for k in coins]; nb = [legs[k][1] for k in coins]
        if any(not (0 < x < 100) for x in yb + nb) or any(y + n >= 100 for y, n in zip(yb, nb)):
            continue
        ny, nn = basket_net(yb, nb, c)
        rows.append({"t": e, "ev": ev, "yes_net": ny, "no_net": nn, "sum_yes_ask": sum(100 - x for x in nb),
                     "sum_yes_bid": sum(yb)})
    return rows


# ---------------------------------------------------------------- third instrument: baskets executed on the tape
def leg_fee_cents(fills: list[tuple[float, int]]) -> int:
    """Fee of one leg's taker order: ceil(0.07 * sum c p (1-p)) to the cent over its fills (count, price c)."""
    num = sum(FEE_NUM * cnt * p * (100 - p) for cnt, p in fills)
    return math.ceil(num / 10000 - 1e-9)


def tape_baskets(prints, gap_s: float = 1.0, tol: float = 0.005):
    """prints: (event, coin, ts, taker_side, count, yes_price_c). A basket = a run of same-taker_side prints in
    one window, consecutive prints <= gap_s apart, touching all five coins with equal per-coin size (within
    tol, relative). taker_side 'yes' on all five = the YES basket (bought every YES at the ask); 'no' = the NO
    basket. Returns one dict per basket with size N, the five legs' VWAP and the net after taker fees."""
    by = collections.defaultdict(list)
    for ev, coin, ts, side, cnt, yp in prints:
        by[(ev, side)].append((ts, coin, cnt, yp))
    out = []
    for (ev, side), xs in by.items():
        xs.sort()
        runs, cur = [], [xs[0]]
        for x in xs[1:]:
            if x[0] - cur[-1][0] <= gap_s:
                cur.append(x)
            else:
                runs.append(cur); cur = [x]
        runs.append(cur)
        for r in runs:
            legs = collections.defaultdict(list)
            for ts, coin, cnt, yp in r:
                legs[coin].append((cnt, yp if side == "yes" else 100 - yp))
            if len(legs) != 5:
                continue
            sizes = {k: sum(c for c, _ in v) for k, v in legs.items()}
            n = min(sizes.values())
            if n <= 0 or max(sizes.values()) - n > tol * n + 1e-9:
                continue
            vw = {k: sum(c * p for c, p in v) / sizes[k] for k, v in legs.items()}
            cost_c = sum(c * p for v in legs.values() for c, p in v)
            fee_c = sum(leg_fee_cents(v) for v in legs.values())
            pay = 100 if side == "yes" else 400
            marg = {k: max(p for _, p in v) for k, v in legs.items()}          # the worst level each leg reached
            out.append({"ev": ev, "side": side, "t0": r[0][0], "t1": r[-1][0], "n": n, "vwap_sum": sum(vw.values()),
                        "marginal_sum": sum(marg.values()), "levels": sum(len({p for _, p in v}) for v in legs.values()),
                        "fee_c_per_basket": fee_c / n,
                        "gross_c": pay - sum(vw.values()), "net_c": (pay * n - cost_c - fee_c) / n,
                        "net_usd": (pay * n - cost_c - fee_c) / 100, "legs": {k: round(v, 2) for k, v in vw.items()}})
    out.sort(key=lambda b: b["t0"])
    return out


def basket_detail(bk, candles, opens: dict[str, float], samples=None) -> list[dict]:
    """Per executed basket: when in the window, what was paid against $1 (or $4) after the five fees, the
    worst level each leg reached, and the RESIDUE -- the same basket priced on the venue's book at the first
    minute close after the basket (and, if given, the farm scorer's first sample after it, a bound biased
    toward clearing). candles: {ticker: sorted [(end_ts, yes_bid_c, yes_ask_c)]}; samples likewise with
    (t, yes_bid_c, no_bid_c)."""
    import bisect
    rows = []
    for b in bk:
        ev = b["ev"]
        coins = sorted(b["legs"])
        d = {k: v for k, v in b.items() if k != "legs"}
        d["minute_of_window"] = (b["t0"] - opens.get(ev, float("nan"))) / 60
        for tag, src in (("after", candles), ("sample_after", samples)):
            if src is None:
                continue
            yb, nb, lag = [], [], []
            for c in coins:
                xs = src.get(f"KXCRYPTOLEAD15M-{ev}-{c}", [])
                i = bisect.bisect_left([x[0] for x in xs], b["t1"] + 1e-6)
                if i >= len(xs) or xs[i][0] - b["t1"] > 60:
                    break
                lag.append(xs[i][0] - b["t1"])
                if tag == "after":                          # candle: (end, yes_bid, yes_ask) -> NO bid = 100 - ask
                    yb.append(xs[i][1]); nb.append(100 - xs[i][2])
                else:                                       # sample: (t, yes_bid, no_bid)
                    yb.append(xs[i][1]); nb.append(xs[i][2])
            if len(yb) == 5 and all(0 < x < 100 for x in yb + nb):
                ny, nn = basket_net(yb, nb, 1)
                ny200, nn200 = basket_net(yb, nb, 200)
                d[f"{tag}_net_c1"] = ny if b["side"] == "yes" else nn
                d[f"{tag}_net_c200"] = ny200 if b["side"] == "yes" else nn200
                d[f"{tag}_lag_s"] = max(lag)
        rows.append(d)
    return rows


def summarise_rows(rows, span_days: float) -> dict:
    out = {"n_minutes": len(rows), "n_windows": len({r["ev"] for r in rows}), "span_days": span_days}
    for key in ("yes_net", "no_net"):
        eps = episodes(rows, key)
        pos = [e["net0"] for e in eps]
        nets = sorted(r[key] for r in rows)
        out[key] = {"minutes_clearing": sum(r[key] > 0 for r in rows), "episodes": len(eps),
                    "episodes_per_day": len(eps) / span_days, "episode_minutes": [e["n"] for e in eps],
                    "net0_c_per_basket": pos, "median_net_c": nets[len(nets) // 2] if nets else None,
                    "p99_net_c": nets[int(0.99 * (len(nets) - 1))] if nets else None,
                    # size each episode would need, every episode taken once, to reach $50/day
                    "size_needed_for_50usd_day": (50 * span_days / (sum(pos) / 100)) if pos and sum(pos) > 0 else None}
    return out


def summarise_tape(bk, span_days: float, n_windows: int) -> dict:
    out = {"span_days": span_days, "n_windows_with_trades": n_windows, "windows_with_a_basket": len({b["ev"] for b in bk})}
    for side in ("yes", "no"):
        b = [x for x in bk if x["side"] == side]
        ns = sorted(x["n"] for x in b); nc = sorted(x["net_c"] for x in b)
        q = lambda xs, f: xs[int(f * (len(xs) - 1))] if xs else None
        out[side] = {"baskets": len(b), "net_positive": sum(x["net_c"] > 0 for x in b),
                     "contracts_per_leg": sum(ns), "size_p50_p90_max": [q(ns, .5), q(ns, .9), q(ns, 1)],
                     "net_c_p10_p50_p90": [q(nc, .1), q(nc, .5), q(nc, .9)],
                     "net_usd": sum(x["net_usd"] for x in b), "net_usd_per_day": sum(x["net_usd"] for x in b) / span_days}
    per = collections.defaultdict(float)
    for x in bk:
        per[x["ev"]] += x["net_usd"]
    tot = sum(per.values())
    out["net_usd_per_day"] = tot / span_days
    out["top5_window_share"] = sum(sorted(per.values(), reverse=True)[:5]) / tot if tot > 0 else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="book_minute.csv (farm scorer lip_sample)")
    ap.add_argument("--markets", required=True, help="markets.jsonl from fetch_trades.py")
    ap.add_argument("--candles", help="venue 1-minute candlesticks parquet (ticker, end_period_ts, yes_bid_close, yes_ask_close)")
    ap.add_argument("--trades", help="trades.parquet")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None)
    ap.add_argument("--size", type=int, default=1)
    ap.add_argument("--detail", default=None, help="write one JSON row per executed tape basket here")
    a = ap.parse_args()
    ts0 = dt.datetime.fromisoformat(a.since.replace("Z", "+00:00")).timestamp() if a.since else -math.inf
    ts1 = dt.datetime.fromisoformat(a.until.replace("Z", "+00:00")).timestamp() if a.until else math.inf
    rep = {"size": a.size, "since": a.since, "until": a.until}
    if a.book:
        ticks, mk = load(a.book, a.markets)
        ticks = {k: v for k, v in ticks.items() if ts0 < k[0] <= ts1}
        ts = [t for t, _ in ticks]
        span = (max(ts) - min(ts)) / 86400
        rows = screen(ticks, mk, a.size)
        crossed = sum(1 for legs in ticks.values() for r in legs.values() if float(r["yes_best"]) + float(r["no_best"]) > 1.0)
        rep["sample"] = report(rows, episodes(rows, "yes_net"), episodes(rows, "no_net"), span)
        rep["sample"]["crossed_rows_excluded"] = crossed
        for k in ("yes", "no"):
            for drop in ("episode_ticks",):
                rep["sample"][k].pop(drop, None)
    if a.candles or a.trades:
        import duckdb
        duckdb.sql("SET threads=2")                  # the operator's laptop: keep it quiet
    if a.candles:
        cand = duckdb.sql(f"SELECT ticker, end_period_ts, yes_bid_close, yes_ask_close FROM read_parquet('{a.candles}') "
                          f"WHERE end_period_ts > {ts0 if ts0 > -math.inf else 0} AND end_period_ts <= {ts1 if ts1 < math.inf else 4e9}").fetchall()
        rows = screen_candles(cand, a.size)
        span = (max(r["t"] for r in rows) - min(r["t"] for r in rows)) / 86400
        rep["candles"] = summarise_rows(rows, span)
    if a.trades and a.detail:
        pr = duckdb.sql(f"""SELECT split_part(ticker, '-', 2), coin, epoch(created_time), taker_side, count,
                                   CAST(round(yes_price * 100) AS INTEGER) FROM read_parquet('{a.trades}')
                            WHERE epoch(window_end_utc) > {ts0 if ts0 > -math.inf else 0}
                              AND epoch(window_end_utc) <= {ts1 if ts1 < math.inf else 4e9}""").fetchall()
        bk = tape_baskets(pr)
        opens = {}
        with open(a.markets) as f:
            for line in f:
                m = json.loads(line)
                opens[m["event_ticker"].split("-", 1)[1]] = dt.datetime.fromisoformat(m["open_time"].replace("Z", "+00:00")).timestamp()
        cand = collections.defaultdict(list)
        if a.candles:
            for tk, e, yb, ya in duckdb.sql(f"SELECT ticker, end_period_ts, yes_bid_close, yes_ask_close FROM read_parquet('{a.candles}') "
                                            f"WHERE yes_bid_close > 0 AND yes_ask_close < 1 ORDER BY 1, 2").fetchall():
                cand[tk].append((float(e), round(yb * 100), round(ya * 100)))
        samp = None
        if a.book:
            import csv
            samp = collections.defaultdict(list)
            with open(a.book) as f:
                for r in csv.DictReader(f):
                    samp[r["ticker"]].append((float(r["t"]), round(float(r["yes_best"]) * 100), round(float(r["no_best"]) * 100)))
            for v in samp.values():
                v.sort()
        rows = basket_detail(bk, cand, opens, samp)
        with open(a.detail, "w") as f:
            json.dump(rows, f)
    if a.trades:
        pr = duckdb.sql(f"""SELECT split_part(ticker, '-', 2), coin, epoch(created_time), taker_side, count,
                                   CAST(round(yes_price * 100) AS INTEGER) FROM read_parquet('{a.trades}')
                            WHERE epoch(window_end_utc) > {ts0 if ts0 > -math.inf else 0}
                              AND epoch(window_end_utc) <= {ts1 if ts1 < math.inf else 4e9}""").fetchall()
        wins = {p[0] for p in pr}
        ends = duckdb.sql(f"""SELECT min(epoch(window_end_utc)), max(epoch(window_end_utc)) FROM read_parquet('{a.trades}')
                              WHERE epoch(window_end_utc) > {ts0 if ts0 > -math.inf else 0}
                                AND epoch(window_end_utc) <= {ts1 if ts1 < math.inf else 4e9}""").fetchone()
        span = (ends[1] - ends[0]) / 86400 + 15 / 1440
        rep["tape"] = summarise_tape(tape_baskets(pr), span, len(wins))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
