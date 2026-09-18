"""The night's money, as a table — served at /pnl.

Three blocks, in the order the operator asks the questions in:

1. what is committed and what it is contracted to pay back (`core.ladder.pnl`
   does the arithmetic; this file only draws it);
2. every attempt, with what filled at what price -- the ledger the registered
   fill test is read off;
3. the opportunity tape per game: how many samples carried a ticketable
   violation and how big the best one was.

Block 3 is the point of the night. Block 2 is what we CAUGHT and block 3 is
what the strategy SAW; a page that showed only the first would report a quiet
night indistinguishable from a night we watched $400 go past.

Markup only. No venue call, no database, no order path.
"""
from __future__ import annotations

import html

CSS = """
body{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0F1217;color:#E6E9EE;margin:0;padding:10px 12px 40px;font-variant-numeric:tabular-nums}
a{color:#3F8ED0} h1{font:600 15px/1.2 -apple-system,system-ui,sans-serif;margin:0 0 2px;letter-spacing:.02em}
h2{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#79808E;margin:22px 0 8px}
.top{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid #262C36;padding-bottom:8px;margin-bottom:10px}
.muted{color:#79808E} .k{color:#79808E;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:1px;background:#262C36;border:1px solid #262C36;max-width:1080px}
.tile{background:#141922;padding:7px 10px} .tile .v{font-size:17px;font-weight:600} .tile .l{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#79808E}
.pos{color:#5FBF86} .neg{color:#D0604F} .warn{color:#E0A94A} .lit{color:#D07A52;font-weight:600}
table{border-collapse:collapse;width:100%;max-width:1080px}
th{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#79808E;text-align:right;padding:0 8px 6px;border-bottom:1px solid #262C36}
th.l{text-align:left} td{padding:2px 8px;text-align:right;border-bottom:1px solid #1A1F27;white-space:nowrap}
td.l{text-align:left} tr:hover td{background:#161B22} tr.sub td{color:#79808E;border-bottom:1px solid #141922}
.chip{font-size:10px;letter-spacing:.06em;text-transform:uppercase;padding:1px 6px;border:1px solid #262C36;color:#B4BAC6}
.chip.open{color:#E0A94A} .chip.placed{color:#3F8ED0} .chip.recorded{color:#5FBF86} .chip.skipped{color:#5B6270}
.note{color:#79808E;max-width:1080px;margin-top:10px;font:12px/1.5 -apple-system,system-ui,sans-serif}
.none{color:#79808E;padding:8px 0}
"""


def _money(x: float) -> str:
    """Sign outside the dollar sign: "-$0.54", never "$-0.54"."""
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def _signed(x: float) -> str:
    cls = "pos" if x > 0 else ("neg" if x < 0 else "muted")
    return f"<span class='{cls}'>{'+' if x > 0 else ''}{_money(x)}</span>"


def _tile(value: str, label: str) -> str:
    return f"<div class='tile'><div class='v'>{value}</div><div class='l'>{html.escape(label)}</div></div>"


def _fill(qty: float, price: float, secs) -> str:
    """What one leg filled at. Zero qty is "did not fill", which is a result
    and not a blank: the fill test turns on exactly this cell."""
    if qty == 0:
        return "&mdash;"
    age = f" <span class='muted'>{secs}s</span>" if secs not in (None, "") else ""
    return f"{qty:g} @ {price:.3f}{age}"


def _attempts(rows: list[dict]) -> str:
    """One line per ticket, and a second line only where something filled.

    Open and skipped tickets stay in the table at zero: a ledger that dropped
    them would make five declined chances look like a night with no chances.
    """
    out = [("<table><tr><th class='l'>game</th><th class='l'>ticket</th><th class='l'>pair</th><th>edge</th>"
            "<th class='l'>state</th><th>leg 1 filled</th><th>leg 2 filled</th><th>paired</th>"
            "<th>cost</th><th>fees</th><th>pays</th><th>net if settled</th><th>leg exposure</th></tr>")]
    if not rows:
        out.append("<tr><td colspan='13' class='none'>No tickets yet tonight.</td></tr>")
    for r in rows:
        st = html.escape(str(r["status"]))
        edge = "&mdash;" if r.get("edge_c") is None else f"{float(r['edge_c']):+.2f}¢"
        out.append(
            f"<tr><td class='l'>{html.escape(r['game'].replace('aec-', ''))}</td>"
            f"<td class='l muted'>{html.escape(str(r.get('ts') or '—'))}</td>"
            f"<td class='l'>{r['high_line']:+g} / {r['low_line']:+g}</td>"
            f"<td class='lit'>{edge}</td>"
            f"<td class='l'><span class='chip {st}'>{st}</span></td>"
            f"<td>{_fill(r['l1q'], r['l1p'], r['l1s'])}</td>"
            f"<td>{_fill(r['l2q'], r['l2p'], r['l2s'])}</td>"
            f"<td>{r['qty_filled']:g}</td>"
            f"<td>{_money(r['cost'])}</td><td class='muted'>{_money(r['fees'])}</td>"
            f"<td>{_money(r['guaranteed'])}</td>"
            f"<td>{_signed(r['net_if_settled'])}</td>"
            f"<td class='{'warn' if r['leg_exposure'] > 0 else 'muted'}'>{_money(r['leg_exposure'])}</td></tr>")
        if r["legged"]:
            # Worded from whichever leg is loose: the mirror (leg 2 on, leg 1
            # missed) carries the same exposure and a fixed sentence would name
            # the wrong side of the position back at the operator.
            on = r.get("loose_leg") or 1
            out.append(f"<tr class='sub'><td colspan='13' class='l'>legged &mdash; leg {on} filled and "
                       f"leg {2 if on == 1 else 1} did not; this is a directional holding on the score, "
                       "not an arbitrage</td></tr>")
    out.append("</table>")
    return "".join(out)


def _opportunity(games: list[dict]) -> str:
    out = [("<table><tr><th class='l'>game</th><th>samples</th><th>with a pair</th><th>share</th>"
            "<th>&ge; floor</th><th>share</th><th>best $ at quoted size</th><th class='l'>last sample</th></tr>")]
    if not games:
        out.append("<tr><td colspan='8' class='none'>No freshness tape yet — the stream instrument writes one per live game.</td></tr>")
    for g in games:
        out.append(
            f"<tr><td class='l'><a href='/ladder?game={html.escape(g['game'])}'>{html.escape(g['key'])}</a></td>"
            f"<td>{g['samples']}</td><td>{g['with_violation']}</td><td>{100 * g['share']:.0f}%</td>"
            f"<td>{g['over_floor']}</td><td>{100 * g['share_over_floor']:.0f}%</td>"
            f"<td class='lit'>{_money(g['best_dollars'])}</td>"
            f"<td class='l muted'>{(html.escape(str(g['last_t'])) + 'Z') if g.get('last_t') else '&mdash;'} · "
            f"{g.get('last_spread_pairs') or 0} spread pairs · {g.get('ws_trades') or 0} trades seen</td></tr>")
        for p in g["top"]:
            out.append(f"<tr class='sub'><td class='l'></td><td colspan='7' class='l'>"
                       f"{p['high_line']:+g} / {p['low_line']:+g} &nbsp; buy {p['buy_price']:.3f} sell {p['sell_price']:.3f}"
                       f" &nbsp; {p['edge_c']:+.2f}¢ &times; {p['size']:.0f} = {_money(p['dollars'])}"
                       f" &nbsp; <span class='muted'>{html.escape(str(p.get('t') or ''))}</span></td></tr>")
    out.append("</table>")
    return "".join(out)


def render(sess: dict, games: list[dict], out_dir: str, stamp: str = "") -> str:
    """The whole page. `sess` is `core.ladder.pnl.session`, `games` is
    `core.ladder.pnl.opportunity`."""
    t = sess["tally"]
    seen = sum(g["over_floor"] for g in games)
    head = (f"<style>{CSS}</style><div class='top'><h1>P&amp;L and the tape</h1>"
            "<span class='muted'><a href='/'>desk</a> &middot; <a href='/ladder'>ladder</a> &middot; "
            "<a href='/instructions'>instructions</a></span>"
            f"<span class='k'>as of</span><span>{html.escape(stamp)}Z</span></div>")

    tiles = ("<div class='tiles'>"
             + _tile(_money(sess["committed"]), "cash committed")
             + _tile(_money(sess["guaranteed"]), "pays at settlement")
             + _tile(_signed(sess["net_if_settled"]), "net if settled")
             + _tile(_signed(sess["net_after_fees"]), "net after fees")
             + _tile(f"{sess['pairs_filled']}", "pairs filled")
             + _tile(f"{sess['qty_filled']:g}", "contracts paired")
             + _tile(f"{sess['legged']}", "legged attempts")
             + _tile(_money(sess["leg_exposure"]), "unpaired leg at risk")
             + _tile(f"{sess['placed']}", "attempts placed")
             + _tile(f"{sess['recorded']}", "attempts recorded")
             # Identical to "pays at settlement" by construction (both are
             # qty x $1.00), and it lands only when EVERY filled pair's margin
             # finishes strictly between its own two lines. Labelled as the
             # maximum it is: a tile the eye reads as money must not be the
             # joint best case over a conjunction of unlikely events.
             + _tile(f"{_money(sess['bonus_if_between'])}", "at most, if every margin lands between")
             + "</div>")

    dates = sess["dates"]
    span = "" if not dates else (dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}")
    population = (f"<div class='note'>Totals over <b>{len(sess['attempts'])}</b> tickets in this directory, "
                  f"{len(sess['games'])} game{'' if len(sess['games']) == 1 else 's'}"
                  f"{', ' + span if span else ''} &mdash; the intents files accumulate across nights, "
                  f"so the population is the directory and not one evening.</div>"
                  if sess["attempts"] else "")

    # The thresholds are printed beside the counts they are read against: the
    # verdict string alone is a conclusion whose rule lives in a doc nobody has
    # open at 23:30, and this ledger is what the finding stands or falls on
    # (core.ladder.desk.tally, docs/math/ladder-fill-test.md).
    rule = (f"<h2>Registered decision rule</h2><div class='muted'>first five placed: {t['placed']} / 5 &middot; "
            f"recorded {t['recorded']} &middot; both legs &ge; 80 % filled <b>{t['both']}</b> &middot; "
            f"leg 1 unfilled <b>{t['none']}</b><br>"
            "&ge; 3 of 5 both filled &rarr; size is real. &ge; 3 of 5 leg 1 unfilled &rarr; phantom. "
            "The same rung vanishing on contact in 3 of 5 withdraws the finding."
            f"<br><b class='warn'>{html.escape(t['verdict'])}</b></div>")

    total_samples = sum(g["samples"] for g in games)
    filled = sess["pairs_filled"]
    gap = (f"<div class='note'><b>Seen vs caught.</b> The tape carried a ticketable pair "
           f"(spread vs spread, at or over the ${games[0]['floor_usd']:.0f} floor) in <b>{seen}</b> of "
           f"{total_samples} samples across {len(games)} game{'' if len(games) == 1 else 's'}; "
           f"<b>{filled}</b> pair{' has' if filled == 1 else 's have'} actually filled. That gap, not the "
           f"P&amp;L above, is what the night measures — and a sample is not an opportunity until the "
           f"displayed size proves real.</div>" if games else "")

    return (head + tiles + population + rule
            + "<h2>Attempts</h2>" + _attempts(sess["attempts"])
            + "<h2>What the ladder showed</h2>" + _opportunity(games) + gap
            + "<div class='note'>Net if settled is the settlement arithmetic of a FILLED pair: a pair pays exactly "
              "$1.00 per contract in every score and $2.00 when the final margin lands strictly between the two "
              "lines. It is not realised until the game settles. An unpaired leg is charged at its full cost here "
              "because it settles at $0 or $1 and nothing on this page knows which. Tape dollars are QUOTED size "
              "— whether that size is real is the question the five attempts answer.<br>"
              f"<span class='muted'>reading {html.escape(out_dir)}</span></div>"
            + "<script>setTimeout(function(){location.reload()},15000)</script>")
