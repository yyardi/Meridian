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
tallies the registered decision rule; tails the executor and freshness logs.

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

from cfb.ladder_instructions import HTML as INSTRUCTIONS_HTML
from core.ladder import desk
from core.ladder.desk import tally, ticket_id  # noqa: F401 -- the desk's public names, kept
from core.ladder.ui import ui_wording

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
body{font:15px/1.5 -apple-system,system-ui,sans-serif;background:#15181F;color:#E6E9EE;margin:0;padding:16px 16px 60px}
.wrap{max-width:760px;margin:0 auto} h1{font-size:24px;margin:0 0 4px} h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#8C93A1;margin:28px 0 8px}
.muted{color:#8C93A1;font-size:12px} .lock{display:flex;gap:18px;align-items:center;padding:16px;border-radius:10px;border:2px solid #AAB6CC;background:#222835;margin-top:14px}
.lock.armed{border-color:#E0A94A;background:#2C2416} .lock button{width:140px;height:140px;border-radius:50%;border:4px solid currentColor;background:#1C2028;color:inherit;font:inherit;font-weight:700;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}
.lock .state{font-size:22px;font-weight:600} .armed .state{color:#E0A94A}
.strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:14px} .cell{background:#1C2028;border:1px solid #333A47;border-radius:6px;padding:10px 12px}
.cell .v{font-size:22px;font-weight:600} .cell .l{font-size:12px;color:#8C93A1}
.ticket{background:#1C2028;border:1px solid #333A47;border-radius:8px;padding:14px 16px;margin-top:12px}
.leg{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:10px 12px;border-radius:6px;background:#232833;margin-top:6px}
.leg .n{font-weight:700;color:#8C93A1} .leg .row{font-family:ui-monospace,Menlo,monospace;font-size:15px;font-weight:600} .leg .btn{font-family:ui-monospace,Menlo,monospace}
.chip{display:inline-block;font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:3px;background:#232833;color:#B4BAC6}
.chip.open{color:#E0A94A} .chip.placed{color:#3F8ED0} .chip.recorded{color:#5FBF86}
form.inline{display:inline} button.act{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid #333A47;background:#232833;color:#E6E9EE;cursor:pointer;margin-right:6px}
button.act.primary{background:#E6E9EE;color:#15181F} input{font:inherit;font-family:ui-monospace,monospace;width:70px;padding:4px 6px;border:1px solid #333A47;border-radius:4px;background:#15181F;color:#E6E9EE}
.fills{margin-top:10px;padding-top:10px;border-top:1px dashed #333A47;display:grid;gap:6px} pre{background:#232833;padding:10px;border-radius:6px;overflow-x:auto;font-size:12px}
.foot{margin-top:36px;font-size:12px;color:#8C93A1;border-top:1px solid #333A47;padding-top:10px}
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    is_armed = armed()
    tickets = load_tickets()
    t = tally(tickets)
    parts = [f"<style>{CSS}</style><div class='wrap'><div class='muted'>MERIDIAN &middot; FILL TEST &middot; {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z</div>",
             "<h1>Ladder desk</h1><div class='muted'>The executor finds and sizes the trade and writes a ticket here. You decide, and you place it. <a href='/instructions' style='color:#3F8ED0'>How to place a ticket &rarr;</a></div>",
             f"<div class='lock {'armed' if is_armed else ''}'><form method='post' action='{'/lock' if is_armed else '/arm'}'>"
             f"<button type='submit'>{'Armed' if is_armed else 'Locked'}<br><span class='muted'>click to {'lock' if is_armed else 'arm'}</span></button></form>"
             f"<div><div class='state'>Meridian is {'ARMED' if is_armed else 'LOCKED'}</div><div>"
             + ("Tickets are written under the budget and pushed to your phone. You place them by hand, leg 1 first."
                if is_armed else "Observe only. The executor keeps sampling; it writes nothing and pushes nothing.")
             + "</div><div class='muted'>takes effect on the executor's next cycle (&le; 20 s)</div></div></div>",
             f"<div class='strip'><div class='cell'><div class='v'>${BUDGET_USD:.2f}</div><div class='l'>hard budget</div></div>"
             f"<div class='cell'><div class='v'>${t['issued']:.2f}</div><div class='l'>issued so far</div></div>"
             f"<div class='cell'><div class='v'>{t['open']}</div><div class='l'>tickets waiting on you</div></div>"
             f"<div class='cell'><div class='v'>{t['placed']} / 5</div><div class='l'>attempts placed, of the first five</div></div></div>",
             "<h2>Tickets</h2>"]
    if not tickets:
        parts.append("<div class='muted'>No tickets yet. A ticket appears here and on your phone when a mid-ladder pair clears the floor.</div>")
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
    parts.append(f"<h2>Decision rule (registered)</h2><div class='ticket'>recorded {t['recorded']} &middot; both legs &ge; 80 % filled: <b>{t['both']}</b> &middot; leg 1 unfilled: <b>{t['none']}</b><br><b>{html.escape(t['verdict'])}</b>"
                 "<div class='muted'>&ge; 3 of 5 both filled &rarr; size is real. &ge; 3 of 5 leg 1 unfilled &rarr; phantom. Same rung vanishing on contact in 3 of 5 withdraws the finding.</div></div>")
    parts.append("<h2>Executor and stream, latest lines</h2>")
    for p in desk.log_files(OUT, "executor") + desk.log_files(OUT, "freshness"):
        lines = tail(p)
        if lines:
            parts.append(f"<div class='muted'>{html.escape(os.path.basename(p))}</div><pre>{html.escape(chr(10).join(lines))}</pre>")
    parts.append("<div class='foot'>Lock = a file the executor re-reads every cycle. Tickets = the executor's intent files. Your records = ladder_attempts.jsonl.</div></div>")
    return "".join(parts)


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
