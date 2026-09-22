"""Record a WHOLE SLATE's ladders off the venue's stream, read-only.

    python cfb/run_stream_slate.py --league cfb --date 2026-09-19 --minutes 300
    python cfb/run_stream_slate.py --league nfl --minutes 240 --max-games 13

`cfb/run_live_ladder.py` samples ONE game over REST at 20-30s and is the
instrument every ladder number so far came from. It does not scale: the venue
allows 20 requests a second per IP, the live recorder holds 12 of them, and
four games of REST sampling starves it. Saturday is 49 CFB games / 1,856
spread markets.

This runner resolves the slate from `market_snapshots` (the same six market
families `slugs_for` uses, driven by `game_start_time` so a finished game is
not subscribed), splits it into subscriptions of at most 100 slugs, opens as
few sockets as that needs, and writes two JSONL files per game. The stream
costs no request budget, so the live recorder is untouched while this runs.

It prints one status line a minute: per-connection counters (messages, books,
trades, reconnects, how old the newest message is) and the busiest games by
trade count. The age is there because a count alone cannot tell a live socket
from a dead one -- a connection with 400,000 messages and a last message two
minutes old is a dark quarter of the slate.

At `--minutes` it stops, closes every file and exits. Analysis is a separate
pass (`core.ladder.stream_scan`), deliberately: the recorder's one job is to
not lose the tape.

PLACES NOTHING, and cannot. It opens the PUBLIC markets stream, makes no REST
call, and writes only to files under `--out-dir`. Nothing here is scheduled;
the manager decides when it runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.ladder.live import slate_slugs  # noqa: E402
from core.ladder.stream import (  # noqa: E402
    DEFAULT_SLUGS_PER_CONNECTION,
    MAX_SLUGS_PER_SUBSCRIPTION,
    SlateRecorder,
)

from core.ladder.live import CRICKET_STREAM_LEAGUES  # noqa: E402

LEAGUES = ("cfb", "nfl", "mlb", "wnba") + CRICKET_STREAM_LEAGUES


def _age(seconds: float | None) -> str:
    """A never-heard-from connection prints `-`, not `0s`. The two are opposite
    facts and a zero would read as the healthiest socket on the slate."""
    return "-" if seconds is None else f"{seconds:.0f}s"


def status_line(totals: dict, rows: list[dict], top: list[tuple[str, int]]) -> str:
    """The slate, then every connection, then the busiest games."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
    head = (f"=== {now}Z conns {totals['connected']}/{totals['connections']} "
            f"games {totals['games']} slugs {totals['slugs']} | msgs {totals['messages']:,} "
            f"books {totals['books']:,} trades {totals['trades']:,} hb {totals['heartbeats']:,} "
            f"| reconn {totals['reconnects']} errors {totals['errors']} torn {totals['torn']} "
            f"| stalest {_age(totals['stalest_s'])} silent {totals['silent_connections']}")
    per = " | ".join(
        f"{r['name']}:{'up' if r['connected'] else 'DOWN'} m{r['messages']:,} b{r['books']:,} "
        f"t{r['trades']:,} r{r['reconnects']} age {_age(r['last_msg_age_s'])}"
        for r in rows)
    busy = " ".join(f"{g}:{n}" for g, n in top) or "(no prints yet)"
    return f"{head}\n    {per}\n    top {busy}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=LEAGUES, required=True)
    ap.add_argument("--date", default=None,
                    help="UTC date of KICKOFF (a 23:30 ET Saturday game is the Sunday). "
                         "Omitted: every game inside the live window.")
    ap.add_argument("--minutes", type=float, default=240.0)
    ap.add_argument("--out-dir", default="/out" if os.path.isdir("/out") else "artifacts/reads")
    ap.add_argument("--max-games", type=int, default=0,
                    help="0 = the whole slate; otherwise the N games starting soonest")
    ap.add_argument("--within-hours", type=float, default=None,
                    help="how long after kickoff a game can still be live "
                         "(default: per league, core.ladder.live.LIVE_WINDOW_HOURS)")
    ap.add_argument("--lookahead-hours", type=float, default=3.0,
                    help="how far ahead of now to take pregame games")
    ap.add_argument("--slugs-per-subscription", type=int, default=MAX_SLUGS_PER_SUBSCRIPTION,
                    help="the venue's cap is 100; lower only to test")
    ap.add_argument("--slugs-per-connection", type=int, default=DEFAULT_SLUGS_PER_CONNECTION)
    ap.add_argument("--debounced", action="store_true",
                    help="ask the venue to batch updates on high-frequency markets")
    ap.add_argument("--status-every", type=float, default=60.0)
    a = ap.parse_args()

    by_game = slate_slugs(a.league, a.date, within_hours=a.within_hours,
                          lookahead_hours=a.lookahead_hours)
    if a.max_games > 0:
        by_game = dict(list(by_game.items())[:a.max_games])
    slugs = [s for g in by_game for s in by_game[g]]
    if not slugs:
        print(f"no {a.league} games resolved for date={a.date} "
              f"within {a.within_hours or 'league default'}h -- nothing to record")
        return 1
    os.makedirs(a.out_dir, exist_ok=True)

    rec = SlateRecorder(slugs, a.out_dir, per_subscription=a.slugs_per_subscription,
                        per_connection=a.slugs_per_connection, debounced=a.debounced)
    print(f"stream slate  league={a.league}  date={a.date or '(live window)'}  "
          f"games={len(by_game)}  slugs={len(slugs)}  connections={len(rec.connections)}  "
          f"for {a.minutes:g} min -> {a.out_dir}")
    for g in by_game:
        print(f"  {g}  {len(by_game[g])} rungs")
    sys.stdout.flush()

    rec.start()
    end = time.time() + a.minutes * 60
    try:
        while time.time() < end:
            time.sleep(min(a.status_every, max(0.0, end - time.time())))
            print(status_line(rec.totals(), rec.counters(), rec.top_games()))
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("interrupted -- closing files")
    finally:
        rec.stop()
    t = rec.totals()
    print(f"done  games {t['games']}  books {t['books']:,}  trades {t['trades']:,}  "
          f"reconnects {t['reconnects']}  errors {t['errors']}  torn {t['torn']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
