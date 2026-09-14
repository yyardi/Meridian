"""PAPER in-game taker scalps on the football winner market. Places nothing.

    python -m core.gridiron.scalp            # MERIDIAN_LEAGUE=nfl|cfb

One container per league (docker-compose.scalp.yml), heartbeat
`scalp_engine_<league>`. Every 2 s it reads two tables -- the newest
`espn_cfb_live_plays` row per live game and the newest `market_snapshots` row
for that game's winner market -- and writes `paper_scalps`. **It opens no
socket to the venue.** The recorders already hold the tape; this engine is a
reader, and that is the only reason it is safe to leave running.

The rule, all from env
----------------------
    TRIGGER     ytg40 (default) | ytg20 | move2c
    TP          5     percent of the entry price, so of the ticket
    STOP        10    percent
    SIZE_USD    25    cost of the ticket; contracts = SIZE_USD / entry price
    MAKER_EXIT  0|1   1 rests the sell at entry*(1+TP) and fills on the bid
    MAX_AGE_S   30    entry freshness gate, on BOTH the play and the venue tick

`ytg40`/`ytg20` fire on the FIRST play of a drive inside that yard line;
`move2c` fires when the winner mid has moved >= 2c in 60 s. One open position
per game, exited on take-profit, stop, the drive ending (possession changes),
the game going final, or the tape going stale under us.

Which side is the offence's
---------------------------
**YES is always the away team on this venue.** So the offence's side is YES
when the away team has the ball and NO when the home team does -- and buying
NO costs `1 - bid`, not `bid`. Entry crosses the spread; a taker exit crosses
it again, which is what MAKER_EXIT exists to measure against.

What this cannot tell you
-------------------------
It is a paper book, not a fill model. A resting maker sell is counted filled
the moment the bid touches it, with no queue position and no adverse-selection
haircut -- so MAKER_EXIT is an UPPER BOUND on that strategy, and the gap
between the two variants is the honest width of the question, not a result.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time

UTC = dt.timezone.utc
FEE_RATE = 0.06
TRIGGERS = ("ytg40", "ytg20", "move2c")
EXIT_REASONS = ("tp", "stop", "drive_end", "final", "stale")


def params_from_env(env=None):
    e = os.environ if env is None else env
    trig = e.get("TRIGGER", "ytg40")
    if trig not in TRIGGERS:
        raise SystemExit(f"TRIGGER={trig!r} is not one of {TRIGGERS}")
    return {"trigger": trig, "tp": float(e.get("TP", "5")) / 100.0,
            "stop": float(e.get("STOP", "10")) / 100.0,
            "size_usd": float(e.get("SIZE_USD", "25")),
            "maker_exit": e.get("MAKER_EXIT", "0") == "1",
            "max_age_s": float(e.get("MAX_AGE_S", "30")),
            "league": e.get("MERIDIAN_LEAGUE", "nfl")}


# --------------------------------------------------------------------------- #
# The rule. Pure functions with no clock of their own and no database -- every
# instant is passed in, so tests drive them on fixture rows.
# --------------------------------------------------------------------------- #

def fee(px):
    """Taker fee per $1 contract at `px`. Zero at 0 and 1 by construction."""
    return FEE_RATE * px * (1.0 - px)


def entry_side(pos_team, home, away):
    """'yes' when the offence is the AWAY team, 'no' when it is the home team.

    None when possession is unknown or is neither side. A kickoff or
    end-of-period row can carry a team this game does not have, and guessing a
    side there is how a position lands on the wrong team.
    """
    if pos_team is None:
        return None
    p = str(pos_team)
    if p == str(away):
        return "yes"
    if p == str(home):
        return "no"
    return None


def entry_price(side, bid, ask):
    """Cost of one contract of our side: YES pays the ask, NO pays 1 - bid."""
    return ask if side == "yes" else 1.0 - bid


def exit_price(side, bid, ask):
    """Proceeds on a TAKER exit: YES hits the bid, NO hits 1 - ask."""
    return bid if side == "yes" else 1.0 - ask


def is_stale(now, *, play_at, tick_at, max_age_s):
    """True when either input is older than the gate, or missing.

    Both are checked because they fail independently: the venue can keep
    quoting a game whose play feed has died, and the reverse -- and a position
    opened on one fresh input and one dead one is priced off a fiction.
    """
    for t in (play_at, tick_at):
        if t is None:
            return True
        age = (now - t).total_seconds()
        # A TIMESTAMP IN THE FUTURE IS NOT FRESH, IT IS WRONG. `age > max_age`
        # alone treats a negative age as perfectly fresh, so a corrupt row
        # sails through the one gate meant to stop it -- and this is not
        # hypothetical: 85 of 2,727 NFL plays recorded 2026-09-10..14 carry a
        # wall_clock 24 hours ahead (min lag -86,378s, i.e. -86,400 plus the
        # usual lag). Under the old test those 85 were the ONLY rows that
        # passed while 93.7% of good plays were refused for being 52.8s old
        # at first sight. The gate was admitting exactly the corrupt ones.
        #
        # One second of tolerance for ordinary clock skew between the feed's
        # clock and ours; a day is not skew.
        if age > max_age_s or age < -1.0:
            return True
    return False


def triggered(trigger, play, prev_play, *, mid_now=None, mid_60s_ago=None):
    """Does this row fire the configured entry rule?"""
    if trigger in ("ytg40", "ytg20"):
        limit = 40 if trigger == "ytg40" else 20
        ytg = play.get("yards_to_goal")
        if ytg is None or ytg > limit:
            return False
        # FIRST play of a drive: a NEW drive_id, not merely a row inside one.
        return prev_play is None or play.get("drive_id") != prev_play.get("drive_id")
    if trigger == "move2c":
        if mid_now is None or mid_60s_ago is None:
            return False
        return abs(mid_now - mid_60s_ago) >= 0.02
    return False


def exit_check(pos, *, bid, ask, pos_team, game_final, stale, maker_exit):
    """(reason, exit price) for an open position, or None to hold.

    Order: `stale` and `final` first, because neither leaves a price we are
    entitled to keep holding against; then stop, then take-profit.

    **Stop before take-profit is a tie-break that only bites on inverted
    parameters** (a STOP large enough to put the stop above the target). One
    snapshot carries one price, so a single cycle cannot cross both bounds --
    an earlier draft of this docstring claimed the ordering resolved that case,
    and it cannot arise.

    **What the ordering does NOT fix, and no ordering could:** we see one price
    every 2 s, so a position that touched its target and came back between
    cycles is recorded at whatever it did later. The book is therefore a
    LOWER bound on take-profit exits and an upper bound on the rest -- the 2 s
    cadence is the resolution of this instrument, not a detail of it.
    """
    side, entry = pos["side"], pos["entry_px"]
    # ROUNDED TO THE PRICE GRID BEFORE COMPARING. 0.40 * 1.05 is
    # 0.42000000000000004, so a take-profit at exactly 0.42 would never fire --
    # every such position would run on to a stop or a drive end, biasing the
    # whole book toward losses with nothing in the output to show it.
    tp_at = round(entry * (1.0 + pos["tp"]), 4)
    stop_at = round(entry * (1.0 - pos["stop"]), 4)
    # A resting sell of our side fills when OUR side's bid reaches the limit --
    # which is the same quantity a taker would sell into. The two variants
    # share a trigger and differ only in the price got and the fee paid.
    ours = exit_price(side, bid, ask)
    if stale:
        return "stale", ours
    if game_final:
        return "final", ours
    if ours <= stop_at:
        return "stop", ours
    if ours >= tp_at:
        return "tp", tp_at if maker_exit else ours
    if pos_team is not None and str(pos_team) != str(pos["pos_team"]):
        return "drive_end", ours
    return None


def realise(pos, reason, px, *, maker_exit):
    """(pnl, fee) for a closed position. The ENTRY fee is always taker."""
    contracts = pos["size_usd"] / pos["entry_px"] if pos["entry_px"] else 0.0
    f = contracts * fee(pos["entry_px"])
    if not (maker_exit and reason == "tp"):
        f += contracts * fee(px)
    return contracts * (px - pos["entry_px"]) - f, f


# --------------------------------------------------------------------------- #
# The loop. Two SELECTs and one INSERT per cycle; no venue client is imported
# anywhere in this module, which is what makes "it cannot place an order" a
# property of the file rather than a promise in a comment.
# --------------------------------------------------------------------------- #

LIVE_SQL = """
SELECT DISTINCT ON (p.game_id) p.game_id, p.pos_team, p.yards_to_goal, p.period,
       p.clock_minutes, p.clock_seconds, p.drive_id, p.wall_clock, p.home, p.away
FROM espn_cfb_live_plays p
WHERE p.league = :lg AND p.wall_clock > now() - interval '6 hours'
ORDER BY p.game_id, p.wall_clock DESC, p.sequence_number DESC
"""
TICK_SQL = """
SELECT DISTINCT ON (s.game_id) s.game_id, s.market_slug, s.best_bid::float bid,
       s.best_ask::float ask, s.captured_at
FROM market_snapshots s
WHERE s.market_slug LIKE :pat AND s.captured_at > now() - interval '1 hour'
  AND s.best_bid IS NOT NULL AND s.best_ask IS NOT NULL
ORDER BY s.game_id, s.captured_at DESC
"""
MAP_SQL = "SELECT espn_game_id, venue_game_id FROM cfb_game_map WHERE venue_game_id IS NOT NULL"
MID60_SQL = """
SELECT best_bid::float, best_ask::float FROM market_snapshots
WHERE game_id = :vg AND market_slug LIKE :pat AND captured_at <= :t
  AND best_bid IS NOT NULL AND best_ask IS NOT NULL
ORDER BY captured_at DESC LIMIT 1
"""


def main():                                                   # pragma: no cover
    import structlog
    from sqlalchemy import text
    from core.heartbeat import Heartbeat
    from core.storage import get_database_url
    from core.storage.base import get_engine, get_sessionmaker

    log = structlog.get_logger(__name__)
    p = params_from_env()
    lg = p["league"]
    if lg not in ("nfl", "cfb"):
        raise SystemExit(f"MERIDIAN_LEAGUE={lg!r}: this engine is football only")
    eng = get_engine()
    hb = Heartbeat(get_sessionmaker(eng), f"scalp_engine_{lg}")
    pat = f"aec-{lg}-%"
    # prev_play is its OWN dict: keying it into open_pos would leave a stale
    # entry behind every closed position and make "is there a position on this
    # game" depend on a string prefix.
    open_pos, prev_play, unmapped, stale_skips, written = {}, {}, set(), 0, 0
    log.info("scalp.start", league=lg, params={k: v for k, v in p.items()}, db=get_database_url()[:24])

    while True:
        t0 = time.monotonic()
        now = dt.datetime.now(UTC)
        rows, plays = 0, {}
        try:
            with eng.begin() as c:
                vmap = {str(r[0]): str(r[1]) for r in c.execute(text(MAP_SQL))}
                plays = {str(r._mapping["game_id"]): dict(r._mapping)
                         for r in c.execute(text(LIVE_SQL), {"lg": lg})}
                ticks = {str(r._mapping["game_id"]): dict(r._mapping)
                         for r in c.execute(text(TICK_SQL), {"pat": pat})}
                for eg, play in plays.items():
                    vg = vmap.get(eg)
                    if vg is None:
                        unmapped.add(eg)
                        continue
                    tick = ticks.get(vg)
                    if tick is None:
                        continue
                    bid, ask = tick["bid"], tick["ask"]
                    stale = is_stale(now, play_at=play["wall_clock"],
                                     tick_at=tick["captured_at"], max_age_s=p["max_age_s"])
                    pos = open_pos.get(eg)
                    if pos is not None:
                        got = exit_check(pos, bid=bid, ask=ask, pos_team=play["pos_team"],
                                         game_final=False, stale=stale,
                                         maker_exit=p["maker_exit"])
                        if got is not None:
                            reason, px = got
                            pnl, f = realise(pos, reason, px, maker_exit=p["maker_exit"])
                            c.execute(text(
                                "INSERT INTO paper_scalps (league, game_id, market_slug, side,"
                                " trigger, entered_at, entry_px, exit_at, exit_px, exit_reason,"
                                " pnl, fee, params) VALUES (:lg,:g,:m,:s,:t,:ea,:ep,:xa,:xp,:xr,"
                                ":pnl,:fee,CAST(:pa AS JSONB))"),
                                {"lg": lg, "g": eg, "m": pos["market_slug"], "s": pos["side"],
                                 "t": p["trigger"], "ea": pos["entered_at"], "ep": pos["entry_px"],
                                 "xa": now, "xp": px, "xr": reason, "pnl": pnl, "fee": f,
                                 "pa": json.dumps(p)})
                            del open_pos[eg]; rows += 1; written += 1
                        continue
                    if stale:
                        stale_skips += 1
                        continue
                    side = entry_side(play["pos_team"], play["home"], play["away"])
                    if side is None:
                        continue
                    mid_now = (bid + ask) / 2.0
                    mid_old = None
                    if p["trigger"] == "move2c":
                        old = c.execute(text(MID60_SQL), {
                            "vg": vg, "pat": pat, "t": now - dt.timedelta(seconds=60)}).first()
                        mid_old = (old[0] + old[1]) / 2.0 if old else None
                    fired = triggered(p["trigger"], play, prev_play.get(eg),
                                      mid_now=mid_now, mid_60s_ago=mid_old)
                    prev_play[eg] = play
                    if not fired:
                        continue
                    px = entry_price(side, bid, ask)
                    open_pos[eg] = {"side": side, "entry_px": px, "entered_at": now,
                                    "market_slug": tick["market_slug"], "pos_team": play["pos_team"],
                                    "tp": p["tp"], "stop": p["stop"], "size_usd": p["size_usd"]}
        except Exception:                                     # never die on one bad cycle
            log.exception("scalp.cycle_failed")
        hb.beat(interval_seconds=2.0, rows_written=rows,
                cycle_seconds=time.monotonic() - t0, game_live=bool(plays))
        if unmapped:
            log.info("scalp.unmapped", league=lg, n=len(unmapped))
        time.sleep(max(0.0, 2.0 - (time.monotonic() - t0)))


if __name__ == "__main__":                                    # pragma: no cover
    main()
