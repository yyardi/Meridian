"""The operator's ladder desk, served on the same host as the executor.

    uvicorn cfb.ladder_desk_app:app --host 0.0.0.0 --port 8011

Why it lives here and not on a hosted page: the executor writes its tickets
to `/out/ladder_intents_<game>.jsonl` and honours `/out/ladder_lock` every
cycle. A page on this host reads the one and writes the other with no
middleman -- the lock takes effect on the executor's next cycle (20 s), and a
ticket is on screen the moment it is written.

What it does: shows ARMED / LOCKED and flips it; lists every ticket in the
venue's own words (row + button, from core.ladder.ui); records what the
operator did (placed / skipped / fills) to `/out/ladder_attempts.jsonl`;
tallies the registered decision rule; and carries the two views a person needs
while a game is running -- `/ladder` (the live rungs) and `/pnl` (what the
night cost, what it pays back, and what went past uncaught).

The index is a status LINE, not a dashboard: one row of state, one row per
live game, then the tickets. The 140px ARM/LOCK dial it replaced was the
biggest thing on a page whose whole job is to show numbers ("its just a big
circle what am i gonna do with that", operator, 2026-09-18).

What it does not do: place, cancel or touch an order. There is no venue call
in this file. Reachable exactly as the dashboard on :8008 is.
"""
from __future__ import annotations

import datetime as dt
import html
import os

from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from cfb import ladder_pnl_page, ladder_tape_page
from cfb.ladder_instructions import HTML as INSTRUCTIONS_HTML
from core.ladder import desk, pnl, tape
from core.ladder.desk import tally, ticket_id  # noqa: F401 -- the desk's public names, kept
from core.ladder.ui import teams_of, ui_wording

# The file helpers live in core.ladder.desk so the dashboard (api image: core/,
# not cfb/) can read the same tickets and write the same records and lock.
# This module keeps its routes, its directory and its public names.
OUT = desk.default_out_dir()
BUDGET_USD = float(os.environ.get("LADDER_BUDGET_USD", "5"))
app = FastAPI(title="Meridian ladder desk")


def lock_path() -> str:
    return desk.lock_path(OUT)


def armed() -> bool:
    return desk.armed(OUT)


def load_tickets() -> list[dict]:
    return desk.load_tickets(OUT)


def tail(path: str, n: int = 3) -> list[str]:
    return desk.tail(path, n)


def _leg_html(n: int, leg: dict, game: str, note: str) -> str:
    row, button = ui_wording(game, float(leg["market_line"]), leg["side"])
    px = float(leg["price"])
    return (f"<div class='leg'><span class='n'>{n}</span><div><div class='row'>{html.escape(row)}</div>"
            f"<div class='btn'>tap <b>{button}</b> &middot; limit {px:.3f} &middot; qty {leg['qty']}"
            f" <span class='muted'>(slug frame: {html.escape(leg['side'])} line {float(leg['market_line']):+g})</span></div>"
            f"<div class='muted'>{note}</div></div></div>")


CSS = """
body{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0F1217;color:#E6E9EE;margin:0;padding:10px 12px 40px;font-variant-numeric:tabular-nums}
.wrap{max-width:1080px;margin:0 auto} a{color:#3F8ED0}
h1{font:600 15px/1.2 -apple-system,system-ui,sans-serif;margin:0;letter-spacing:.02em;display:inline}
h2{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#79808E;margin:22px 0 8px}
.muted{color:#79808E} .k{color:#79808E;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.bar{display:flex;gap:16px;align-items:center;flex-wrap:wrap;border-top:1px solid #262C36;border-bottom:1px solid #262C36;padding:7px 0;margin:8px 0 10px}
.bar b{font-weight:600} .bar .sep{color:#262C36}
.bar form{display:inline;margin:0} .bar button{font:inherit;font-weight:600;letter-spacing:.08em;padding:3px 12px;border:1px solid currentColor;background:#141922;color:#79808E;cursor:pointer}
.bar button.on{color:#E0A94A} .hb{color:#B4BAC6} .hb .stale{color:#D0604F}
table{border-collapse:collapse;width:100%;max-width:1080px}
th{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#79808E;text-align:right;padding:0 8px 6px;border-bottom:1px solid #262C36}
th.l{text-align:left} td{padding:2px 8px;text-align:right;border-bottom:1px solid #1A1F27;white-space:nowrap}
td.l{text-align:left} tr:hover td{background:#161B22} .lit{color:#D07A52;font-weight:600} .warn{color:#E0A94A}
.ticket{background:#141922;border:1px solid #262C36;padding:10px 12px;margin-top:10px}
.leg{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:10px 12px;border-radius:6px;background:#232833;margin-top:6px}
.leg .n{font-weight:700;color:#8C93A1} .leg .row{font-family:ui-monospace,Menlo,monospace;font-size:15px;font-weight:600} .leg .btn{font-family:ui-monospace,Menlo,monospace}
.chip{display:inline-block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:3px;background:#232833;color:#B4BAC6}
.chip.open{color:#E0A94A} .chip.placed{color:#3F8ED0} .chip.recorded{color:#5FBF86}
form.inline{display:inline} button.act{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #333A47;background:#232833;color:#E6E9EE;cursor:pointer;margin-right:6px}
button.act.primary{background:#E6E9EE;color:#15181F} input{font:inherit;font-family:ui-monospace,monospace;width:70px;padding:4px 6px;border:1px solid #333A47;border-radius:4px;background:#15181F;color:#E6E9EE}
.fills{margin-top:10px;padding-top:10px;border-top:1px dashed #333A47;display:grid;gap:6px} pre{background:#232833;padding:10px;border-radius:6px;overflow-x:auto;font-size:12px}
.foot{margin-top:36px;font-size:12px;color:#8C93A1;border-top:1px solid #333A47;padding-top:10px}
"""


def _age(secs: float | None, stale_after: float = 90.0) -> str:
    """A writer's last write, in seconds. Red past `stale_after` -- at a 20 s
    cycle, a minute and a half of silence is a process that stopped, not a
    slow cycle. It says the writer is alive, NOT that the venue is moving."""
    if secs is None:
        return "<span class='muted'>&mdash;</span>"
    return f"<span class='{'stale' if secs > stale_after else ''}'>{secs:.0f}s</span>"


def _short(key: str) -> str:
    """'MIA-WAKE' from the slug. A status line has room for the matchup, not
    for the league and the date; the link carries the full prefix."""
    try:
        return "-".join(teams_of(key))
    except ValueError:
        return key


def _status_bar(is_armed: bool, t: dict, live: list[dict]) -> str:
    """One line: the lock, what is waiting, what it has cost, and whether the
    two writers per live game are still writing.

    The budget is PER EXECUTOR, one process per game, while `t['issued']` is
    every intent in the directory and across nights (core.ladder.pnl). Six
    games at $2 each is $12 issued with no cap breached anywhere, so the
    comparison that turns this figure red is made per game against that game's
    own issued total, and the bar's own number says which population it is.
    """
    beats = " <span class='sep'>|</span> ".join(
        f"{html.escape(_short(g['key']))} {_age(g['executor_age_s'])}/{_age(g['tape_age_s'])}"
        for g in live) or "<span class='muted'>no live game</span>"
    over = [g for g in live if (g.get("issued_usd") or 0) > BUDGET_USD]
    return (f"<div class='bar'><form method='post' action='{'/lock' if is_armed else '/arm'}'>"
            f"<button type='submit' class='{'on' if is_armed else ''}' "
            f"title='click to {'lock' if is_armed else 'arm'}'>{'ARMED' if is_armed else 'LOCKED'}</button></form>"
            f"<span><b>{t['open']}</b> waiting</span>"
            f"<span>issued <b class='{'warn' if over else ''}'>${t['issued']:.2f}</b>"
            f" <span class='muted'>in this directory &middot; ${BUDGET_USD:.2f} cap per game"
            + (f", {len(over)} over" if over else "") + "</span></span>"
            f"<span>placed <b>{t['placed']} / 5</b></span>"
            f"<span class='hb'><span class='k'>exec/stream</span> {beats}</span>"
            "<span style='margin-left:auto'><a href='/ladder'>ladder</a> &middot; <a href='/pnl'>P&amp;L</a>"
            " &middot; <a href='/instructions'>instructions</a></span></div>")


def _live_table(live: list[dict]) -> str:
    """One row per game with a file touched tonight: what the ladder is doing
    now, and the best the strategy has SEEN there against what it issued."""
    rows = ["<table><tr><th class='l'>game</th><th>spread pairs now</th>"
            "<th title='the stream instrument&#39;s own count over its two books'>rest/stream/both</th>"
            "<th>samples</th><th>with a pair</th><th>&ge; $25</th><th>best $ seen</th>"
            "<th>tickets</th><th>issued</th><th class='l'>last sample</th></tr>"]
    if not live:
        rows.append("<tr><td colspan='10' class='muted' style='padding:8px'>No game files touched in the last six "
                    "hours. The executor and the stream instrument each write one file per live game.</td></tr>")
    for g in live:
        share = "" if not g.get("samples") else f"{100 * (g.get('share') or 0):.0f}%"
        floor = "" if not g.get("samples") else f"{100 * (g.get('share_over_floor') or 0):.0f}%"
        rows.append(
            f"<tr><td class='l'><a href='/ladder?game={html.escape(g['game'])}' "
            f"title='{html.escape(g['key'])}'>{html.escape(_short(g['key']))}</a></td>"
            f"<td class='{'lit' if (g.get('last_spread_pairs') or 0) else 'muted'}'>"
            f"{g.get('last_spread_pairs') or 0}</td>"
            # A game whose stream instrument has not written yet has NO count
            # here, which is not the count 0: routed through the tape page's
            # own dash helper so this cell says absence the way its neighbours
            # do rather than printing the Python literal None.
            f"<td class='muted'>{' / '.join(ladder_tape_page._num(g.get(k), dash='&mdash;') for k in ('viol_rest', 'viol_ws', 'viol_common'))}</td>"
            f"<td>{g.get('samples') or 0}</td><td>{share or '&mdash;'}</td>"
            f"<td class='{'warn' if (g.get('over_floor') or 0) else ''}'>{floor or '&mdash;'}</td>"
            f"<td class='lit'>${g.get('best_dollars') or 0:,.2f}</td>"
            f"<td>{g['tickets']}</td><td>${g['issued_usd']:.2f}</td>"
            f"<td class='l muted'>{(html.escape(str(g['last_t'])) + 'Z') if g.get('last_t') else '&mdash;'}"
            f" &middot; {g.get('ws_trades') or 0} trades seen</td></tr>")
    rows.append("</table>")
    return "".join(rows)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    is_armed = armed()
    tickets = load_tickets()
    t = tally(tickets)
    live = pnl.game_status(OUT)
    parts = [f"<style>{CSS}</style><div class='wrap'>"
             f"<h1>Ladder desk</h1> <span class='muted'>MERIDIAN &middot; FILL TEST &middot; "
             f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z &middot; "
             + ("ARMED: tickets are written under the budget and pushed to your phone; you place them, leg 1 first."
                if is_armed else "LOCKED: observe only. The executor keeps sampling; it writes and pushes nothing.")
             + " Takes effect on the executor's next cycle (&le; 20 s).</span>",
             _status_bar(is_armed, t, live),
             # Trades first, games second (operator, 2026-09-18: "make it like
             # the trades we are taking ... having the ladder is nice i guess").
             # What the desk is FOR is the two clicks on a ticket; the games
             # table is context for a night with no ticket in it yet.
             "<h2>Trades</h2>"]
    if not tickets:
        # The condition is the executor's, word for word: two spread rungs over
        # the floor. Naming the mid ladder here would tell the operator on a
        # WNBA night that a +/-2.5 pair cannot produce a ticket, when it does.
        parts.append("<div class='muted'>No tickets yet. A ticket appears here and on your phone when a pair of "
                     "spread rungs clears the floor &mdash; on any line, in either sport.</div>")
    for tk in tickets:
        game, st = str(tk.get("game")), tk["status"]
        parts.append(f"<div class='ticket'><div><b>{html.escape(game)}</b> <span class='muted'>{html.escape(str(tk.get('ts')))}Z &middot; edge {tk.get('edge_c')}&cent; &middot; displayed {tk.get('displayed_size')}</span> <span class='chip {st}'>{st}</span></div>")
        try:
            parts.append(_leg_html(1, tk["leg1"], game, f"FIRST -- the stale leg; its book last updated {tk.get('leg1_book_age_s')}s before the ticket"))
            parts.append(_leg_html(2, tk["leg2"], game, f"within 60 s of leg 1, or don't chase; book age {tk.get('leg2_book_age_s')}s"))
        except ValueError as e:
            parts.append(f"<div class='muted'>cannot word this ticket: {html.escape(str(e))}</div>")
        parts.append(f"<div class='muted'>cost ${float(tk.get('cost_usd') or 0):.2f} &middot; pays ${tk['leg1']['qty']:.2f} at settlement any score, ${2 * tk['leg1']['qty']:.2f} if the margin lands between the lines</div>")
        tid = html.escape(tk["id"])
        if st == "open":
            parts.append(f"<div style='margin-top:10px'><form class='inline' method='post' action='/ticket'><input type='hidden' name='id' value='{tid}'><input type='hidden' name='action' value='placed'><button class='act primary'>I placed it</button></form>"
                         f"<form class='inline' method='post' action='/ticket'><input type='hidden' name='id' value='{tid}'><input type='hidden' name='action' value='skipped'><button class='act'>Skipped</button></form></div>")
        elif st == "placed":
            parts.append(f"<form method='post' action='/ticket' class='fills'><input type='hidden' name='id' value='{tid}'><input type='hidden' name='action' value='record'>"
                         f"<div>leg 1 filled qty <input name='l1q' inputmode='decimal'> price <input name='l1p'> secs <input name='l1s'></div>"
                         f"<div>leg 2 filled qty <input name='l2q' inputmode='decimal'> price <input name='l2p'> secs <input name='l2s'></div>"
                         f"<div><button class='act primary'>Save fills</button> <span class='muted'>0 in qty means it did not fill -- that is a result too</span></div></form>")
        elif st == "recorded":
            r = tk["record"]
            parts.append(f"<div class='muted' style='margin-top:8px'>leg 1 filled {r.get('l1q')} @ {r.get('l1p')} in {r.get('l1s')} s &middot; leg 2 filled {r.get('l2q')} @ {r.get('l2p')} in {r.get('l2s')} s</div>")
        elif st == "skipped":
            parts.append(f"<form class='inline' method='post' action='/ticket' style='margin-top:8px'><input type='hidden' name='id' value='{tid}'><input type='hidden' name='action' value='reopen'><button class='act'>Reopen</button></form>")
        parts.append("</div>")
    parts.append("<h2>Games</h2>")
    parts.append(_live_table(live))
    parts.append(f"<h2>Decision rule (registered)</h2><div class='ticket'>recorded {t['recorded']} &middot; both legs &ge; 80 % filled: <b>{t['both']}</b> &middot; leg 1 unfilled: <b>{t['none']}</b> &middot; <b>{html.escape(t['verdict'])}</b>"
                 " <a href='/pnl'>money and the tape &rarr;</a></div>")
    parts.append("<h2>Executor and stream, latest lines</h2>")
    for p in desk.log_files(OUT, "executor") + desk.log_files(OUT, "freshness"):
        lines = tail(p)
        if lines:
            parts.append(f"<div class='muted'>{html.escape(os.path.basename(p))}</div><pre>{html.escape(chr(10).join(lines))}</pre>")
    parts.append("<div class='foot'>Lock = a file the executor re-reads every cycle. Tickets = the executor's intent files. Your records = ladder_attempts.jsonl.</div></div>")
    # This is the page carrying the writer heartbeats, whose whole purpose is to
    # go stale, and it re-rendered only on a manual reload while /ladder and
    # /pnl refreshed themselves. It reloads on the same 15 s -- except while a
    # ticket is `placed`, which is the one state with fill boxes open under the
    # operator's hands; a reload there would clear what they were typing.
    if all(tk["status"] != "placed" for tk in tickets):
        parts.append("<script>setTimeout(function(){location.reload()},15000)</script>")
    return "".join(parts)


@app.get("/ladder", response_class=HTMLResponse)
def ladder(game: str | None = None) -> str:
    """The live rungs from the freshness tape. The tape is a file the stream
    instrument writes every ~20 s, so this page needs no venue call: what it
    shows is as fresh as the instrument's last cycle and no fresher."""
    return ladder_tape_page.render(tape.latest(OUT, game), tape.games(OUT), game, OUT)


@app.get("/pnl", response_class=HTMLResponse)
def pnl_view() -> str:
    """What the night cost, what it is contracted to pay back, and what the
    ladder showed while we were not in it."""
    return ladder_pnl_page.render(pnl.session(OUT), pnl.opportunity(OUT), OUT,
                                  dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"))


@app.get("/instructions", response_class=HTMLResponse)
def instructions() -> str:
    return INSTRUCTIONS_HTML


@app.post("/lock")
def lock() -> RedirectResponse:
    desk.lock(OUT, "the desk")
    return RedirectResponse("/", status_code=303)


@app.post("/arm")
def arm() -> RedirectResponse:
    desk.arm(OUT)
    return RedirectResponse("/", status_code=303)


def _num(v: str | None) -> float | None:
    try:
        return None if v is None or str(v).strip() == "" else float(v)
    except ValueError:
        return None


@app.post("/ticket")
async def ticket(request: Request) -> RedirectResponse:
    """Plain urlencoded form, parsed by hand: the api image carries no
    python-multipart and the desk must not need a dependency change."""
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8", errors="replace")).items()}
    tid, action = form.get("id", ""), form.get("action", "")
    status = {"placed": "placed", "skipped": "skipped", "reopen": "open", "record": "recorded"}.get(action)
    if status is None or not tid:
        return RedirectResponse("/", status_code=303)
    fills = None
    if action == "record":
        fills = {k: _num(form.get(k)) for k in ("l1q", "l1p", "l1s", "l2q", "l2p", "l2s")}
    desk.record_attempt(OUT, tid, status, fills)
    return RedirectResponse("/", status_code=303)
