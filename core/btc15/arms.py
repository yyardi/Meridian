"""Strategy arms: several price-aware ways to trade the same window, paper-traded side by side.

Iteration 1 bought the model's favoured side at the ask, whatever the ask was. This
layer makes the price part of the decision and lets the data pick the rule: every arm
sees the same window, the same book and the same probabilities, and each keeps its
own ledger file and its own $10 allocation, so their records compare like for like.

An arm is (probability source, execution kind, margin):

  probability  walk   driftless random walk to the settlement average (core.btc15.quant)
               quant  logistic on market, distance, momentum and volatility, fitted on
                      Kalshi's settled history (quant_coef.json)
               llm    the model's p_up for this window (usable for a taker only within
                      llm_fresh_s of its answer: the price it priced has moved after)
               kalshi Kalshi's mid on the SAME window (KXBTC15M settles on the same BRTI
                      averages), read in the same tick as the venue's book, only when
                      its window matches to the second and its spread is <= 3c. Kalshi is
                      the deeper market; this arm asks whether the venue lags it.
               mid    the market's own mid -- a CONTROL, the cost of trading on nothing
  kind         agent  the LLM trades for itself: it sees the book, Kalshi and the fees and
                      answers buy Up / buy Down / pass with the most it will pay; at or
                      above the ask it takes, below it rests (no fee); a first-look pass
                      earns one second look at second_look_s (the harness asks again)
               taker  buy the better side at its ask the first second
                      p_side - ask - fee > margin; never otherwise
               maker  once, at start_s, rest a bid at (p_side - margin) on the side p
                      favours over the mid; filled only when the book later trades
                      THROUGH it (the other side's touch crosses our price by a tick);
                      the venue charges makers nothing; cancelled min_lead_s before close
               join   BOTH sides at the venue's own touch, re-joined whenever the touch
                      moves, filled by PRINTS (2026-09-30, needs the stream's trade tape).
                      Queue model: an order placed at price P at t0 stands behind the size
                      displayed at P at t0 (``ahead``). It fills when the prints at P or
                      through it on our side since t0 sum to MORE than ``ahead``, or when
                      the book trades through P. Size arriving at P after us is behind us
                      and ignored; size that leaves P without printing is NOT credited
                      (ahead shrinks only by prints -- the pessimistic reading). When the
                      touch moves away from P the quote is re-joined at the new touch (new
                      t0, new ahead): the arm never stands alone at a level the market
                      maker has left, which is what the retired mid_maker did (-13c). With
                      prob=kalshi, a side is quoted only when Kalshi's mid is at least
                      ``margin`` better than our price (a bid at P only if Kalshi >= P +
                      margin; an offer at P only if Kalshi <= P - margin); with prob=mid
                      both sides always (the control). The venue pays makers a rebate
                      (docs.polymarket.us/fees, 2026-09-25) which the ledger does NOT
                      credit: makers are booked at zero, the conservative reading.

At most one contract per arm per window, held to settlement. A window the arm saw and
did not trade is recorded (no_edge / expired), so "chose not to trade" is data.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import math
import zlib
from dataclasses import asdict, dataclass

from core.btc15 import quant as Q
from core.btc15.ledger import UNIT, Ledger

log = logging.getLogger("btc15.arms")

#: The venue's price increment for these markets (orderPriceMinTickSize 0.01).
BTC_PRICE_TICK = 0.01
#: A join arm quotes only into a book at most this wide: a wider book is the maker gone.
MAX_JOIN_SPREAD = 0.03
#: The venue's intents on a print (core/ladder/stream.trade_row), read off the recorded WNBA
#: prints of 2026-09-19 beside the touch before each: a taker BUY_SHORT (buys NO) or SELL_LONG
#: (sells YES) prints AT THE YES BID, in YES terms, and fills a resting YES bid; a taker BUY_LONG
#: or SELL_SHORT prints at the ask and fills a resting YES offer. When the taker's intent is
#: undefined, the MAKER's says which side rested: maker BUY_LONG was the bid, maker BUY_SHORT the
#: offer. A print with both undefined is counted for neither (the pessimistic reading).
HITS_BID_TAKER = ("ORDER_INTENT_BUY_SHORT", "ORDER_INTENT_SELL_LONG")
HITS_BID_MAKER = "ORDER_INTENT_BUY_LONG"
LIFTS_OFFER_TAKER = ("ORDER_INTENT_BUY_LONG", "ORDER_INTENT_SELL_SHORT")
LIFTS_OFFER_MAKER = "ORDER_INTENT_BUY_SHORT"


@dataclass(frozen=True)
class ArmSpec:
    name: str
    prob: str                   # walk | quant | llm | kalshi | mid
    kind: str                   # agent | taker | maker
    margin: float
    start_s: float = 30.0       # earliest second after the open to act (a maker posts then)
    llm_fresh_s: float = 60.0

    def describe(self) -> str:
        if self.kind == "requote":
            return (f"two-sided zero-fee quotes on the venue at Kalshi's live mid −/+ {round(self.margin * 100)}¢, "
                    f"moved on every price message; filled only when traded through")
        if self.kind == "join":
            gate = (f"; a side only when Kalshi's mid is {round(self.margin * 100)}¢ better than our price"
                    if self.prob == "kalshi" else " (both sides always: the control)")
            return ("zero-fee quotes joined to the venue's own touch on every message, filled by prints beyond "
                    "the size ahead of us or a trade-through" + gate)
        what = {"walk": "random walk", "quant": "fitted model", "llm": "the LLM", "kalshi": "Kalshi's price",
                "mid": "the market mid"}[self.prob]
        if self.kind == "agent":
            return f"{what} trades for itself: buy Up, buy Down or pass, at a limit it sets; a pass gets a second look"
        how = ("buys at the ask when its edge beats the fee by" if self.kind == "taker"
               else "rests a zero-fee bid below its fair value by")
        return f"{what}; {how} {self.margin * 100:.0f}c"


def cents(n: int) -> float:
    """An entry margin written in whole cents (never a fee coefficient)."""
    return n / 100


#: The arms run by default (MERIDIAN_BTC15_ARMS overrides with a JSON list of specs).
#: Chosen by the 45-day backtest on Kalshi's history (docs/math/btc15-v2-arms.md):
#: random-walk and fitted-model arms lost out of sample at every margin and timing,
#: so they are not run; the model's fitted probability still goes to the LLM. The
#: Kalshi taker runs at six margins side by side (2026-09-29); the joint quote tape
#: replays any margin (analysis/btc15/replay_kalshi_margins.py).
DEFAULT_ARMS = (
    ArmSpec("llm_agent", "llm", "agent", 0.0),
    ArmSpec("kalshi_taker", "kalshi", "taker", cents(2)),
    ArmSpec("kalshi_taker_3c", "kalshi", "taker", cents(3)),
    ArmSpec("kalshi_taker_wide", "kalshi", "taker", cents(4)),
    ArmSpec("kalshi_taker_5c", "kalshi", "taker", cents(5)),
    ArmSpec("kalshi_taker_6c", "kalshi", "taker", cents(6)),
    ArmSpec("kalshi_taker_8c", "kalshi", "taker", cents(8)),
    # 2026-09-30: Kalshi's book moves first and the venue follows a tick later (live tape,
    # corr +0.05 vs 0.00). This rests zero-fee quotes on the venue at Kalshi's live mid
    # -/+ 2c and moves them on every price message; it is filled only when the venue
    # trades through one of them. At 3-s staleness it lost 2.6c a fill (adverse
    # selection); message-driven is the version being measured.
    ArmSpec("kalshi_requote", "kalshi", "requote", cents(2)),
    # 2026-09-30: makers judged by PRINTS, not trade-through, now that the stream's trades are
    # kept. touch_maker joins both sides of the venue's touch (the control: what joining the
    # market maker's queue earns); touch_maker_k joins a side only when Kalshi's mid says that
    # side is 1c or more below fair. One contract per window each, like every arm.
    ArmSpec("touch_maker", "mid", "join", 0.0),
    ArmSpec("touch_maker_k", "kalshi", "join", cents(1)),
)

#: Retired 2026-09-29 21:50Z on the operator's call, every one losing on paper as the
#: 45-day backtest predicted (their ledgers are kept under <data>/retired/):
#:   kalshi_maker  86 trades  -7.9c/contract  t -1.65
#:   llm_maker     78 trades  -5.9c           t -1.15
#:   llm_taker     82 trades  -2.1c           t -0.43
#:   mid_maker     72 trades -13.0c           t -2.71  (the control: resting orders get picked off)
RETIRED_ARMS = ("kalshi_maker", "llm_maker", "llm_taker", "mid_maker")


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _floor_cent(x: float) -> float:
    return math.floor(x * 100 + 1e-9) / 100


class Arm:
    def __init__(self, spec: ArmSpec, ledger: Ledger, limit_u: int, prints=None) -> None:
        self.spec, self.ledger, self.limit_u = spec, ledger, limit_u
        #: prints(ticker, since) -> [(at, price, quantity, taker_intent, maker_intent)] (the stream's);
        #: none means no print seen, so a join arm can only be filled by a trade-through.
        self.prints = prints or (lambda ticker, since: [])
        self.ledger.put("arm_spec", json.dumps(asdict(spec)))

    # ------------------------------------------------------------------ one second
    def tick(self, now: float, m: dict, probs: dict, fee_coef: float | None, min_lead_s: float) -> None:
        t = m["ticker"]
        if now < m["open_ts"] + self.spec.start_s:
            return
        self.ledger.upsert_window(m)
        d = self.ledger.decision(t)
        if d is None:
            self.ledger.start_decision(t, self.spec.name, {"spec": asdict(self.spec)})
            self.ledger.finish_decision(t, status="watching")
            d = self.ledger.decision(t)
        status = d["status"]
        if status in ("filled", "no_edge", "expired", "no_fee", "not_filled"):
            return
        closing = now >= m["close_ts"] - min_lead_s
        if self.spec.kind == "agent":
            self._agent(now, m, probs, fee_coef, closing, d)
            return
        if self.spec.kind == "requote":
            if closing:
                self.ledger.finish_decision(t, status="expired" if status == "resting" else "no_edge")
                return
            self._requote(now, m, probs, d)
            return
        if self.spec.kind == "join":
            if closing:
                self.ledger.finish_decision(t, status="expired" if status == "resting" else "no_edge")
                return
            self._join(now, m, probs, d)
            return
        if self.spec.kind == "taker":
            if closing:
                self.ledger.finish_decision(t, status="no_edge")
                return
            self._take(now, m, probs, fee_coef)
        else:
            if status == "watching":
                if closing:
                    self.ledger.finish_decision(t, status="no_edge")
                    return
                self._post(now, m, probs, d)
            elif status == "resting":
                if closing:
                    self.ledger.finish_decision(t, status="expired")
                    return
                self._check_fill(now, m, d)

    # ------------------------------------------------------------------ the agent
    def _agent(self, now: float, m: dict, probs: dict, fee_coef: float | None, closing: bool, d) -> None:
        t, st = m["ticker"], d["status"]
        if st == "resting":
            if closing:
                self.ledger.finish_decision(t, status="expired")
            else:
                self._check_fill(now, m, d)
            return
        if closing:
            if st in ("watching", "passed", "second_look"):
                self.ledger.finish_decision(t, status="no_edge")
            return
        if st == "watching":
            act, look = probs.get("llm_action"), "first"
        elif st == "second_look":
            act, look = json.loads(d["response"] or "{}"), "second"
        else:                                                    # passed: the harness owns the second look
            return
        if not act or act.get("action") not in ("buy_up", "buy_down", "pass"):
            return
        base = {k: act.get(k) for k in ("action", "limit_price", "p_up", "confidence")}
        base["look"] = look
        why = (act.get("rationale") or "")[:300]
        if act["action"] == "pass":
            self.ledger.finish_decision(t, status="passed" if look == "first" else "no_edge", p_up=act.get("p_up"),
                                        response=json.dumps(base), rationale=f"{look} look: pass. {why}")
            return
        side = "YES" if act["action"] == "buy_up" else "NO"
        limit = float(act["limit_price"])
        ask = m.get("yes_ask") if side == "YES" else (None if m.get("yes_bid") is None else round(1 - m["yes_bid"], 4))
        if ask is not None and fee_coef is not None and limit >= ask - 1e-9:
            price_u = int(round(ask * UNIT))
            fee_u = int(round(Q.fee(ask, fee_coef) * UNIT))
            if not (0 < price_u < UNIT) or price_u + fee_u > UNIT:
                return
            book = {k: m.get(k) for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u", "yes_bid_size", "yes_ask_size")}
            fid, err = self.ledger.record_fill("paper", t, side, price_u, fee_u, self.limit_u, book=book)
            self.ledger.finish_decision(t, status="filled" if fid else "not_filled", side=side, p_up=act.get("p_up"),
                                        answered_at=_iso(now), error=None if fid else err, response=json.dumps(base),
                                        rationale=f"{look} look: took {side} at {ask:.2f} + {fee_u / UNIT:.2f} fee "
                                                  f"(limit {limit:.2f}). {why}")
            return
        price = _floor_cent(limit) if ask is None else min(_floor_cent(limit), round(ask - BTC_PRICE_TICK, 2))
        if price < BTC_PRICE_TICK:
            self.ledger.finish_decision(t, status="no_edge", p_up=act.get("p_up"), response=json.dumps(base),
                                        rationale=f"{look} look: limit {limit:.2f} leaves no resting bid. {why}")
            return
        self.ledger.finish_decision(t, status="resting", side=side, p_up=act.get("p_up"), answered_at=_iso(now),
                                    response=json.dumps({**base, "resting_price": price, "posted_at": now}),
                                    rationale=f"{look} look: resting {side} bid at {price:.2f} (limit {limit:.2f}, ask "
                                              f"{'-' if ask is None else f'{ask:.2f}'}). {why}")

    def _prob(self, now: float, probs: dict) -> float | None:
        p = probs.get(self.spec.prob)
        if p is None:
            return None
        if self.spec.prob == "llm" and self.spec.kind == "taker":
            at = probs.get("llm_at")
            if at is None or now - at > self.spec.llm_fresh_s:
                return None
        return p

    def _take(self, now: float, m: dict, probs: dict, fee_coef: float | None) -> None:
        p = self._prob(now, probs)
        if p is None or fee_coef is None:
            return
        side, ev, price = Q.edge(p, m.get("yes_ask"), m.get("yes_bid"), fee_coef)
        if side is None or ev <= self.spec.margin:
            return
        price_u = int(round(price * UNIT))
        fee_u = int(round(Q.fee(price, fee_coef) * UNIT))
        if not (0 < price_u < UNIT) or price_u + fee_u > UNIT:
            return
        book = {k: m.get(k) for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u", "yes_bid_size", "yes_ask_size")}
        fid, why = self.ledger.record_fill("paper", m["ticker"], side, price_u, fee_u, self.limit_u, book=book)
        self.ledger.finish_decision(m["ticker"], status="filled" if fid else "not_filled", side=side, p_up=round(p, 4),
                                    answered_at=_iso(now), error=None if fid else why,
                                    rationale=f"{side} at {price:.2f} + {fee_u / UNIT:.2f} fee, EV {ev:+.3f} > {self.spec.margin:.2f}")

    def _post(self, now: float, m: dict, probs: dict, d) -> None:
        p = self._prob(now, probs)
        bid, ask = m.get("yes_bid"), m.get("yes_ask")
        if p is None or bid is None or ask is None:
            return
        mid = (bid + ask) / 2
        # A resting bid sits below the side's ask: at fair - margin, or one tick inside the
        # spread when fair - margin would cross it (the edge is larger, the order still makes).
        # The market-mid control has no view, so its side is a coin keyed on the window:
        # random, reproducible, and symmetric across Up and Down.
        yes = (zlib.crc32(m["ticker"].encode()) % 2 == 0) if self.spec.prob == "mid" else p >= mid
        if yes:
            side = "YES"
            price = min(_floor_cent(p - self.spec.margin), round(ask - BTC_PRICE_TICK, 2))
        else:
            side = "NO"
            price = min(_floor_cent((1 - p) - self.spec.margin), round((1 - bid) - BTC_PRICE_TICK, 2))
        if price < BTC_PRICE_TICK:
            self.ledger.finish_decision(m["ticker"], status="no_edge", p_up=round(p, 4),
                                        rationale=f"fair {p:.3f} leaves no resting {side} bid above a cent")
            return
        self.ledger.finish_decision(m["ticker"], status="resting", side=side, p_up=round(p, 4), answered_at=_iso(now),
                                    response=json.dumps({"resting_price": price, "posted_at": now, "mid": mid}),
                                    rationale=f"resting {side} bid at {price:.2f} (fair {p if side == 'YES' else 1 - p:.3f}, mid {mid:.3f})")

    def _requote(self, now: float, m: dict, probs: dict, d) -> None:
        """Two-sided zero-fee quotes at fair -/+ margin, moved whenever fair or the book moves,
        filled only when the venue trades THROUGH one of them (the other side's touch crosses
        our price by a tick). The first fill takes the window's one contract."""
        t = m["ticker"]
        r = json.loads(d["response"] or "{}") if d["status"] == "resting" else {}
        bid, offer, posted = r.get("bid"), r.get("offer"), r.get("posted_at")
        yb, ya = m.get("yes_bid"), m.get("yes_ask")
        if posted is not None and now > posted:                  # quotes from an earlier tick can be hit
            if bid is not None and ya is not None and ya <= bid - BTC_PRICE_TICK + 1e-9:
                self._maker_fill(now, m, d, "YES", bid)
                return
            if offer is not None and yb is not None and yb >= offer + BTC_PRICE_TICK - 1e-9:
                self._maker_fill(now, m, d, "NO", round(1 - offer, 2))
                return
        p = self._prob(now, probs)
        if p is None or yb is None or ya is None:
            if d["status"] == "resting":
                self.ledger.finish_decision(t, status="watching", response=None, rationale="quotes pulled: no fair price")
            return
        nb = min(_floor_cent(p - self.spec.margin), round(ya - BTC_PRICE_TICK, 2))
        no = max(math.ceil((p + self.spec.margin) * 100 - 1e-9) / 100, round(yb + BTC_PRICE_TICK, 2))
        if not (BTC_PRICE_TICK <= nb < no <= 1 - BTC_PRICE_TICK):
            if d["status"] == "resting":
                self.ledger.finish_decision(t, status="watching", response=None, rationale="quotes pulled: no room inside the book")
            return
        if (nb, no) != (bid, offer):
            self.ledger.finish_decision(t, status="resting", p_up=round(p, 4), answered_at=_iso(now),
                                        response=json.dumps({"bid": nb, "offer": no, "posted_at": now, "fair": round(p, 4)}),
                                        rationale=f"quoting {nb:.2f} / {no:.2f} around Kalshi {p:.3f}")

    def _join(self, now: float, m: dict, probs: dict, d) -> None:
        """Both sides at the venue's touch; see the module docstring for the queue model."""
        t = m["ticker"]
        st = json.loads(d["response"] or "{}") if d["status"] == "resting" else {}
        yb, ya = m.get("yes_bid"), m.get("yes_ask")
        # 1. what was resting: filled by prints beyond the size ahead, or by a trade-through
        for side in ("bid", "offer"):
            q = st.get(side)
            if q is None:
                continue
            since, ahead = st.get(f"{side}_since", now), st.get(f"{side}_ahead") or 0.0
            hit = 0.0
            for (_at, px, qty, ti, mi) in self.prints(t, since):
                if px is None or not qty:
                    continue
                if side == "bid" and px <= q + 1e-9 and (ti in HITS_BID_TAKER or mi == HITS_BID_MAKER):
                    hit += qty
                elif side == "offer" and px >= q - 1e-9 and (ti in LIFTS_OFFER_TAKER or mi == LIFTS_OFFER_MAKER):
                    hit += qty
            if side == "bid":
                through = ya is not None and ya <= q - BTC_PRICE_TICK + 1e-9
            else:
                through = yb is not None and yb >= q + BTC_PRICE_TICK - 1e-9
            if through or hit > ahead:
                how = "traded through" if through else f"prints {hit:.0f} > {ahead:.0f} ahead"
                if side == "bid":
                    self._maker_fill(now, m, d, "YES", q, how)
                else:
                    self._maker_fill(now, m, d, "NO", round(1 - q, 2), how)
                return
        # 2. re-quote to the touch, or pull
        k = probs.get("kalshi") if self.spec.prob == "kalshi" else None
        gated = self.spec.prob == "kalshi"
        if yb is None or ya is None or ya - yb > MAX_JOIN_SPREAD + 1e-9 or (gated and k is None):
            if d["status"] == "resting":
                self.ledger.finish_decision(t, status="watching", response=None,
                                            rationale="quotes pulled: no two-sided book" if k is None and gated and yb is not None
                                            else "quotes pulled: no two-sided book within 3c")
            return
        want = {"bid": yb, "offer": ya}
        if gated:
            if k < yb + self.spec.margin - 1e-9:
                want["bid"] = None
            if k > ya - self.spec.margin + 1e-9:
                want["offer"] = None
        new = dict(st)
        changed = False
        for side, size_key in (("bid", "yes_bid_size"), ("offer", "yes_ask_size")):
            if want[side] != st.get(side) or side not in st:
                changed = changed or want[side] != st.get(side)
                new[side] = want[side]
                new[f"{side}_since"] = now if want[side] is not None else None
                new[f"{side}_ahead"] = float(m.get(size_key) or 0.0) if want[side] is not None else None
        if want["bid"] is None and want["offer"] is None:
            if d["status"] == "resting":
                self.ledger.finish_decision(t, status="watching", response=None,
                                            rationale=f"quotes pulled: Kalshi {k:.3f} inside {yb:.2f}/{ya:.2f} by less than the margin")
            return
        if changed or d["status"] != "resting":
            self.ledger.finish_decision(
                t, status="resting", answered_at=_iso(now), response=json.dumps(new),
                p_up=None if k is None else round(k, 4),
                rationale=(f"joined {'-' if new.get('bid') is None else f'{new['bid']:.2f}'} / "
                           f"{'-' if new.get('offer') is None else f'{new['offer']:.2f}'} "
                           f"(ahead {new.get('bid_ahead')}/{new.get('offer_ahead')})"
                           + ("" if k is None else f", Kalshi {k:.3f}")))

    def _maker_fill(self, now: float, m: dict, d, side: str, price: float, how: str | None = None) -> None:
        price_u = int(round(price * UNIT))
        book = {k: m.get(k) for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u", "yes_bid_size", "yes_ask_size")}
        fid, why = self.ledger.record_fill("paper", m["ticker"], side, price_u, 0, self.limit_u, book=book)
        self.ledger.finish_decision(m["ticker"], status="filled" if fid else "not_filled", side=side, error=None if fid else why,
                                    rationale=(d["rationale"] or "") + f"; {how or 'traded through'}: {side} at {price:.2f}, no fee, {_iso(now)}")

    def _check_fill(self, now: float, m: dict, d) -> None:
        r = json.loads(d["response"] or "{}")
        price = r.get("resting_price")
        if price is None or now <= (r.get("posted_at") or now):
            return
        side = d["side"]
        # Through, not touch: the other side's touch must cross our price by a tick.
        if side == "YES":
            crossed = m.get("yes_ask") is not None and m["yes_ask"] <= price - BTC_PRICE_TICK + 1e-9
        else:
            crossed = m.get("yes_bid") is not None and m["yes_bid"] >= (1 - price) + BTC_PRICE_TICK - 1e-9
        if not crossed:
            return
        price_u = int(round(price * UNIT))
        book = {k: m.get(k) for k in ("yes_bid_u", "yes_ask_u", "no_bid_u", "no_ask_u")}
        fid, why = self.ledger.record_fill("paper", m["ticker"], side, price_u, 0, self.limit_u, book=book)
        self.ledger.finish_decision(m["ticker"], status="filled" if fid else "not_filled", error=None if fid else why,
                                    rationale=(d["rationale"] or "") + f"; filled at {price:.2f} {_iso(now)}")

    # ------------------------------------------------------------------ settlement
    def settle(self, results: dict[str, str], finals: dict[str, tuple]) -> None:
        for t, (res, value, proxy) in finals.items():
            w = self.ledger._conn.execute("SELECT result FROM windows WHERE ticker=?", (t,)).fetchone()
            if w is not None and w["result"] is None:
                self.ledger.finalize_window(t, res, value, proxy)
        for f in self.ledger.unsettled_fills():
            if f["ticker"] in results:
                self.ledger.settle(f["id"], results[f["ticker"]])


def specs_from_env(raw: str | None) -> tuple[ArmSpec, ...]:
    if not raw:
        return DEFAULT_ARMS
    if raw.strip().lower() in ("none", "off", "[]"):
        return ()
    return tuple(ArmSpec(**x) for x in json.loads(raw))
