"""The thin-league speed read, exactly as docs/math/thin-league-speed-preregistration.md registers it.

For each stream window directory (artifacts/reads/stream/<tag>/): the venue's winner-market
book tape (slate_books_<game>.jsonl), its score tape (slate_scores_<game>.jsonl) and, for
EuroLeague, the league's shot log (official_<game>.json).

Event: consecutive LIVE score lines where exactly one team's points rose by 1-3. Scoring
side: YES if the scorer's competitor id is the market's yes_team_id, else NO. Entry at the
side's ask visible 1 s after our receipt of the change (last book line with recv <= t_E;
NO's ask = 1 - YES bid); mark-out M60 = the side's mid at t_E + 60 s - entry - taker fee.
Control: the same M60 at uniformly random live instants on a side chosen by a seeded coin.
Interval: cluster-robust by game, G/(G-1), and by slate date beside it. A game whose book
tape goes quiet for more than 60 s during play is excluded and counted, as registered.
Direction check: the winner the score tape and yes_team_id name must be the side the
book settled toward; a mismatch voids the read. Printed beside: already repriced, venue
score latency against the league's shot log (EuroLeague), stale size.

    python analysis/thin/speed_read.py <stream-dir> [<stream-dir> ...]
"""
from __future__ import annotations

import bisect
import datetime as dt
import glob
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from core.btc15.quant import fee as taker_fee  # noqa: E402  -- 0.0695*p*(1-p) rounded up to the cent
from core.fees import POLYMARKET_TAKER  # noqa: E402

LIVE_PERIODS = {"Q1", "Q2", "Q3", "Q4", "OT", "OT1", "OT2", "OT3", "1H", "2H"}


def ts(s: str | None) -> float | None:
    return None if not s else dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def jl(path: str) -> list[dict]:
    out = []
    with open(path) as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


class Book:
    """The winner market's touch as WE could see it (recv), for bisecting."""

    def __init__(self, rows: list[dict]):
        winner = sorted((r for r in rows if str(r.get("slug", "")).startswith("aec-")), key=lambda r: ts(r["recv"]))
        self.all_t = [ts(r["recv"]) for r in winner]          # every push, for the tape-gap rule
        rows = [r for r in winner if r.get("bid") is not None and r.get("ask") is not None]
        self.t = [ts(r["recv"]) for r in rows]
        self.rows = rows

    def max_gap(self, t0: float, t1: float) -> float:
        """Longest stretch inside [t0, t1] with no push on the winner market."""
        pts = [t0] + [t for t in self.all_t if t0 < t < t1] + [t1]
        return max(b - a for a, b in zip(pts, pts[1:]))

    def settled_toward(self) -> str | None:
        """YES / NO if the last open two-sided touch sat beyond 0.9 / 0.1, else None."""
        for r in reversed(self.rows):
            if r.get("state") in (None, "MARKET_STATE_OPEN"):
                m = (float(r["bid"]) + float(r["ask"])) / 2
                return "YES" if m > 0.9 else "NO" if m < 0.1 else None
        return None

    def at(self, t: float) -> dict | None:
        i = bisect.bisect_right(self.t, t) - 1
        return self.rows[i] if i >= 0 else None


def side_ask(r: dict, side: str) -> float:
    return float(r["ask"]) if side == "YES" else 1 - float(r["bid"])


def side_mid(r: dict, side: str) -> float:
    m = (float(r["bid"]) + float(r["ask"])) / 2
    return m if side == "YES" else 1 - m


def side_size(r: dict, side: str):
    return r.get("ask_size") if side == "YES" else r.get("bid_size")


def parse_score(s: str | None):
    try:
        a, b = s.split("-")
        return int(a), int(b)
    except (AttributeError, ValueError):
        return None


def games_in(dirs: list[str]) -> dict[str, str]:
    """game -> the directory holding its fullest score tape (overlapping windows tape a game twice)."""
    best: dict[str, tuple[int, str]] = {}
    for d in dirs:
        for f in glob.glob(os.path.join(d, "slate_scores_*.jsonl")):
            g = os.path.basename(f)[len("slate_scores_"):-len(".jsonl")]
            n = sum(1 for _ in open(f))
            if g not in best or n > best[g][0]:
                best[g] = (n, d)
    return {g: d for g, (_, d) in best.items()}


def events_of(scores: list[dict]):
    out = []
    prev = None
    for s in scores:
        live = s.get("live") and s.get("period") in LIVE_PERIODS
        sc = parse_score(s.get("score"))
        if live and prev is not None and sc is not None:
            ps = parse_score(prev.get("score"))
            if ps is not None and prev.get("live"):
                d0, d1 = sc[0] - ps[0], sc[1] - ps[1]
                simple = (1 <= d0 <= 3 and d1 == 0) or (1 <= d1 <= 3 and d0 == 0)
                comp = s.get("competitors") or []
                if len(comp) == 2:
                    scorer = 0 if d0 > 0 else 1
                    side = "YES" if comp[scorer] == s.get("yes_team_id") else "NO"
                    out.append({"simple": simple and (d0 >= 0 and d1 >= 0), "side": side,
                                "t_R": ts(s["recv"]), "t_prev": ts(s.get("prev_recv")),
                                "t_V": ts(s.get("state_updated_at")), "score": sc, "comp": comp,
                                "yes": s.get("yes_team_id")})
        prev = s if sc is not None else prev
    return out


def markout(book: Book, t_e: float, side: str, horizon: float = 60.0):
    e, x = book.at(t_e), book.at(t_e + horizon)
    if e is None or x is None or e.get("state") not in (None, "MARKET_STATE_OPEN"):
        return None
    ask = side_ask(e, side)
    if not (0 < ask < 1):
        return None
    return side_mid(x, side) - ask - taker_fee(ask, POLYMARKET_TAKER), ask, side_size(e, side)


def score_winner(scores: list[dict]) -> str | None:
    """YES / NO: the side the final score and yes_team_id name as the winner."""
    for s in reversed(scores):
        sc, comp = parse_score(s.get("score")), s.get("competitors") or []
        if sc is not None and len(comp) == 2 and sc[0] != sc[1]:
            w = comp[0] if sc[0] > sc[1] else comp[1]
            return "YES" if w == s.get("yes_team_id") else "NO"
    return None


def clustered(vals: list[tuple[str, float]]):
    n = len(vals)
    if n < 2:
        return float("nan"), float("nan"), 0
    m = sum(v for _, v in vals) / n
    by = defaultdict(float)
    for g, v in vals:
        by[g] += v - m
    G = len(by)
    if G < 2:                                  # one cluster has no between-cluster variance to estimate
        return m, float("nan"), G
    var = sum(x * x for x in by.values()) / n ** 2 * (G / (G - 1))
    return m, math.sqrt(var), G


def main(dirs: list[str]) -> int:
    games = games_in(dirs)
    rng = random.Random(20260928)
    m60, ctl, rep, lat, sizes, compound, notscored = [], [], [], [], [], 0, 0
    gapped, direction = [], []
    info = {h: [] for h in (10, 30, 60)}          # the addendum's information mark-out, by horizon
    per_league = defaultdict(list)
    for g, d in sorted(games.items()):
        scores = jl(os.path.join(d, f"slate_scores_{g}.jsonl"))
        bpath = os.path.join(d, f"slate_books_{g}.jsonl")
        if not os.path.exists(bpath):
            continue
        book = Book(jl(bpath))
        evs = events_of(scores)
        live_t = [ts(s["recv"]) for s in scores if s.get("live") and s.get("period") in LIVE_PERIODS]
        direction.append((g, score_winner(scores), book.settled_toward()))
        if len(live_t) >= 2 and book.max_gap(live_t[0], live_t[-1]) > 60.0:
            gapped.append((g, round(book.max_gap(live_t[0], live_t[-1]))))
            continue
        for ev in evs:
            if not ev["simple"]:
                compound += 1
                continue
            r = markout(book, ev["t_R"] + 1.0, ev["side"])
            if r is None:
                notscored += 1
                continue
            v, ask, sz = r
            m60.append((g, v))
            per_league[g.split("-")[0]].append((g, v))
            sizes.append(sz)
            if ev["t_prev"] is not None:
                b0 = book.at(ev["t_prev"])
                if b0 is not None:
                    rep.append(side_ask(book.at(ev["t_R"] + 1.0), ev["side"]) > side_ask(b0, ev["side"]) + 1e-9)
        if len(live_t) >= 2:
            for _ in range(max(1, len(evs))):
                t = rng.uniform(live_t[0], live_t[-1])
                r = markout(book, t, rng.choice(("YES", "NO")))
                if r is not None:
                    ctl.append((g, r[0]))
        # venue score latency against the league's clock (EuroLeague)
        opath = os.path.join(d, f"official_{g}.json")
        if os.path.exists(opath):
            o = json.load(open(opath))
            if o.get("points") and evs:
                yes, comp = evs[0]["yes"], evs[0]["comp"]
                home_idx = comp.index(yes) if yes in comp else None
                seen = {}
                for s in scores:
                    sc = parse_score(s.get("score"))
                    if sc is None or home_idx is None or not s.get("state_updated_at"):
                        continue
                    key = (sc[home_idx], sc[1 - home_idx])
                    seen.setdefault(key, ts(s["state_updated_at"]))
                last = (0, 0)
                for p in o["points"]:
                    if p.get("ID_ACTION") not in ("2FGM", "3FGM", "FTM") or not p.get("UTC"):
                        continue
                    key = (p.get("POINTS_A"), p.get("POINTS_B"))
                    t_l = dt.datetime.strptime(p["UTC"], "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc).timestamp()
                    if key in seen:
                        lat.append(seen[key] - t_l)
                    # A = the league's local club = the venue's home team = YES (checked 10 of 10)
                    if key[0] is not None and key[1] is not None:
                        side = "YES" if key[0] > last[0] else "NO" if key[1] > last[1] else None
                        if side:
                            for h in info:
                                r = markout(book, t_l + 1.0, side, float(h))
                                if r is not None:
                                    info[h].append((g, r[0]))
                        last = key

    def line(name, vals):
        m, se, G = clustered(vals)
        t = m / se if se and se == se and se > 0 else float("nan")
        print(f"  {name:40s} events {len(vals):5d}  games {G:3d}  mean {m*100:+6.2f}c  se {se*100:5.2f}c  t {t:+5.2f}")

    print(f"games {len(games)}; excluded for a book-tape gap > 60 s in play {len(gapped)} {gapped}; "
          f"scored simple events {len(m60)}; compound (skipped) {compound}; not scored (book closed/empty) {notscored}")
    checked = [(g, a, b) for g, a, b in direction if a and b]
    bad = [(g, a, b) for g, a, b in checked if a != b]
    print(f"direction check (score winner via yes_team_id vs the side the book settled toward): "
          f"{len(checked) - len(bad)}/{len(checked)} agree" + (f"  MISMATCH {bad} -- VOID" if bad else ""))
    print("M60 (buy the scorer at the ask 1 s after the venue's own score change, mid 60 s later, net of fee):")
    line("all leagues", m60)
    by_date = [(g[-10:], v) for g, v in m60]            # game keys end in the slate's YYYY-MM-DD
    line("  (clustered by slate date)", by_date)
    for lg, vals in sorted(per_league.items()):
        line(f"  {lg}", vals)
    line("CONTROL: random live instant, coin side", ctl)
    for h, vals in info.items():
        line(f"INFO: scorer at the official shot time + 1 s, {h} s", vals)
    if rep:
        print(f"already repriced by entry (scorer's ask above its value at the poll before): {sum(rep)}/{len(rep)} = {sum(rep)/len(rep):.0%}")
    if lat:
        s = sorted(lat)
        print(f"venue score latency vs EuroLeague's shot clock (UTC seconds): n {len(s)}  median {s[len(s)//2]:.1f} s  "
              f"p10 {s[len(s)//10]:.1f} s  p90 {s[9*len(s)//10]:.1f} s")
    zs = [float(z) for z in sizes if z is not None]
    if zs:
        zs.sort()
        print(f"size at the entry ask: median {zs[len(zs)//2]:.0f} contracts, p25 {zs[len(zs)//4]:.0f}, p75 {zs[3*len(zs)//4]:.0f}")
    G = len({g for g, _ in m60})
    print(f"\nregistration gate: G >= 30 games with a scored event, mean > 0, both intervals exclude 0, control < 0. "
          f"G = {G}: {'UNDERPOWERED -- not a read' if G < 30 else 'read'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
