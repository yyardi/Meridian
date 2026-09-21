#!/usr/bin/env python3
"""The edge ledger: one row per slate per league per gate, accrued nightly,
so "is the edge number solid" is answered by a table and not by memory.

    python3 scripts/edge_ledger.py --date 2026-09-21                 # today's tapes
    python3 scripts/edge_ledger.py --date 2026-09-19 --dirs /out/stream/cfb-a /out/stream/cfb-b
    python3 scripts/edge_ledger.py --show                            # print the ledger, add nothing

What a row holds. Every game's stream tape for the day is scanned with
core.ladder.stream_episodes at TWO gates: 2 s (both legs pushed by the
venue within two seconds when the crossing opened; the conservative
population the measured edge was first reported on) and none (any leg age
at open; on the stream an unchanged quote is the live book, so this is the
full population short of message loss). For each: games, updates, distinct
episodes, how many lived a single update, how many cleared the $25 floor,
their summed and largest best-instant dollars, and the median life of the
ones over the floor. The over-floor episodes themselves are kept on the
row (game, pair, dollars, life, older leg's age at open) so a reader can
see the eight, not just count them.

Why two gates. The REST-era figures (78 % of instants, $413.90 a day) were
one instrument's artifact; a single new number would be one instrument's
claim. Two populations bracket the truth and the gap between them is
itself a fact worth watching night to night.

Nothing here is money. Every dollar is edge x the smaller displayed size
at the best instant of a crossing nobody placed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder import stream_episodes as SE  # noqa: E402

GATES: tuple[float | None, ...] = (2.0, None)
KEEP_TOP = 20


def league_of_dir(d: str) -> str:
    """`/out/stream/nfl-a` -> nfl; `.../cfb-09220005` -> cfb."""
    return os.path.basename(d.rstrip("/")).split("-")[0]


def recent_dirs(root: str, hours: float = 20.0) -> list[str]:
    cut = time.time() - hours * 3600
    out = []
    for d in sorted(glob.glob(os.path.join(root, "*"))):
        base = os.path.basename(d)
        if not os.path.isdir(d) or base.startswith(("smoke", "_")):
            continue
        if os.path.getmtime(d) >= cut:
            out.append(d)
    return out


def rows_for(date: str, dirs: list[str], floor_usd: float) -> list[dict]:
    by_league: dict[str, list[str]] = {}
    for d in dirs:
        by_league.setdefault(league_of_dir(d), []).append(d)
    rows = []
    for league, ds in sorted(by_league.items()):
        for gate in GATES:
            results = []
            for d in ds:
                results += SE.scan_dir(d, gate_s=gate)
            s = SE.summarize(results, floor_usd=floor_usd)
            big = sorted((e for r in results for e in r.over(floor_usd)), key=lambda e: -e.best_usd)
            rows.append({
                "date": date, "league": league, "gate_s": gate,
                "dirs": [os.path.basename(d) for d in ds],
                **s,
                "over_floor_episodes": [
                    {"game": e.game, "pair": [e.low_line, e.high_line],
                     "best_usd": round(e.best_usd, 2), "best_edge_c": round(e.best_edge * 100, 2),
                     "life_s": e.duration_s, "opened_leg_age_s": e.opened_leg_age_s,
                     "opened_at": dt.datetime.fromtimestamp(e.opened_at, dt.timezone.utc).strftime("%H:%M:%S")}
                    for e in big[:KEEP_TOP]],
                "written_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            })
    return rows


def append(ledger: str, rows: list[dict]) -> None:
    with open(ledger, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def load(ledger: str) -> list[dict]:
    if not os.path.exists(ledger):
        return []
    out = []
    with open(ledger, encoding="utf-8") as f:
        for ln in f:
            if ln.strip():
                out.append(json.loads(ln))
    return out


def table(rows: list[dict]) -> str:
    """The ledger as the operator reads it. Latest row per (date, league,
    gate) wins, so a re-run replaces rather than duplicates on screen."""
    latest: dict[tuple, dict] = {}
    for r in rows:
        latest[(r["date"], r["league"], r["gate_s"])] = r
    lines = [f"  {'date':<11}{'lg':<5}{'gate':>5}{'games':>6}{'updates':>9}{'episodes':>9}"
             f"{'1-upd':>7}{'>=$25':>6}{'sum>=25':>9}{'biggest':>9}{'med life>=25':>13}"]
    for k in sorted(latest):
        r = latest[k]
        g = "any" if r["gate_s"] is None else f"{r['gate_s']:g}s"
        ml = r.get("median_life_over_floor_s")
        lines.append(f"  {r['date']:<11}{r['league']:<5}{g:>5}{r['games']:>6}{r['updates']:>9,}"
                     f"{r['episodes']:>9,}{r['one_update']:>7,}{r['over_floor']:>6}"
                     f"{r['sum_over_floor_usd']:>9,.0f}{r['biggest_usd']:>9,.0f}"
                     f"{(f'{ml:.1f}s' if ml is not None else '-'):>13}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--dirs", nargs="*", default=None, help="recorder dirs; default: those written in the last 20h")
    ap.add_argument("--root", default="/out/stream" if os.path.isdir("/out/stream") else "artifacts/reads/stream")
    ap.add_argument("--ledger", default="/out/edge_ledger.jsonl" if os.path.isdir("/out") else "artifacts/reads/edge_ledger.jsonl")
    ap.add_argument("--floor-usd", type=float, default=SE.DEFAULT_FLOOR_USD)
    ap.add_argument("--show", action="store_true", help="print the ledger and add nothing")
    a = ap.parse_args()
    if not a.show:
        dirs = a.dirs if a.dirs else recent_dirs(a.root)
        if not dirs:
            print("edge_ledger: no recorder directories to scan")
        else:
            rows = rows_for(a.date, dirs, a.floor_usd)
            append(a.ledger, rows)
            print(f"edge_ledger: {len(rows)} rows appended for {a.date} from {', '.join(os.path.basename(d) for d in dirs)}")
            for r in rows:
                if r["gate_s"] is not None and r["over_floor_episodes"]:
                    print(f"  {r['league']} at {r['gate_s']:g}s gate, over the floor:")
                    for e in r["over_floor_episodes"][:10]:
                        print(f"    {e['opened_at']}Z {e['game']:<30} {e['pair'][1]:>6}/{e['pair'][0]:<6} "
                              f"${e['best_usd']:>7,.0f}  {e['best_edge_c']:+.2f}c  life {e['life_s']:>6.1f}s  "
                              f"legs {e['opened_leg_age_s']}s apart at open")
    print("\nTHE LEDGER (dollars are quoted edge x size; nothing placed):")
    print(table(load(a.ledger)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
