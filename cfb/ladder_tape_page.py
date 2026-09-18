"""The live ladder and the stream-vs-REST count — served at /ladder.

The trading surface the operator watches DURING a game: what the venue is
quoting on every rung right now, which rungs contradict each other, and
whether the stream agrees with the book the executor acts on. It reads
`ws_freshness_<game>.jsonl`, which the stream instrument writes every ~20 s
per live game, so it needs no venue call and no rebuilt image --
`core.ladder.tape` turns the newest line into rungs + bounds + violations and
this module draws it.

The money is NOT here. `/pnl` (core.ladder.pnl) owns what the night cost and
what it pays back, and a second money figure computed another way on this
page would be a number that disagrees with it in front of a tired operator at
23:30. This page links there and stays on the book.

Sport-agnostic on purpose. It lives under cfb/ because the desk does, but it
reads a game prefix off a filename and nothing in it knows a down from a
possession: tonight's WNBA tapes render exactly as the college football ones
do, side by side in the same switcher.

Three things are on screen, in the order the operator needs them:

1. the live ladder -- one row per rung, sizes as bars, the bound each rung
   must satisfy beside it, the legs of a tradeable violation lit;
2. the pairs the scanner reports, with edge, size, dollars at QUOTED size,
   and for each one the reason the executor would pass on it if it would;
3. the stream against REST -- viol_ws vs viol_rest vs viol_common and the
   running trade-print count, which is tonight's H1 evidence.

It refreshes itself. It renders strings; it opens no file and calls nothing.
"""
from __future__ import annotations

import html
import math
from urllib.parse import quote

CSS = """
body{font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;background:#0F1217;color:#E6E9EE;margin:0;padding:10px 12px 40px;font-variant-numeric:tabular-nums}
a{color:#3F8ED0} h1{font:600 15px/1.2 -apple-system,system-ui,sans-serif;margin:0 0 2px;letter-spacing:.02em}
h2{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.09em;text-transform:uppercase;color:#79808E;margin:20px 0 7px}
.top{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;border-bottom:1px solid #262C36;padding-bottom:8px;margin-bottom:10px}
.muted{color:#79808E} .k{color:#79808E;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.games{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px}
.games a{display:inline-block;padding:3px 9px;border:1px solid #262C36;color:#B4BAC6;text-decoration:none}
.games a.on{border-color:#D07A52;color:#D07A52}
.strip{display:flex;gap:8px;flex-wrap:wrap;max-width:980px}
.cell{background:#161B22;border:1px solid #262C36;padding:8px 12px;min-width:120px}
.cell .v{font:600 20px/1.2 -apple-system,system-ui,sans-serif} .cell .l{font-size:11px;color:#79808E;margin-top:2px}
.up{color:#5FBF86} .down{color:#D0574A} .warn{color:#E0A94A}
table{border-collapse:collapse;width:100%;max-width:980px}
th{font:500 10px/1 -apple-system,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#79808E;text-align:right;padding:0 8px 6px;border-bottom:1px solid #262C36}
th.l{text-align:left} td{padding:2px 8px;text-align:right;border-bottom:1px solid #1A1F27;white-space:nowrap}
td.l{text-align:left} tr.winner td{color:#5B6270} tr:hover td{background:#161B22}
.line{font-weight:600;color:#E6E9EE;font-size:14px}
.bar{display:inline-block;height:9px;background:#243244;vertical-align:middle;margin-right:5px}
.bar.a{background:#3A2A22}
.lit{color:#D07A52;font-weight:600} .bound{color:#5B6270;font-size:11px}
.d{color:#D07A52;font-weight:600} .none{color:#79808E;padding:8px 0}
.hist td{padding:1px 8px;font-size:12px;color:#B4BAC6}
.foot{margin-top:20px;font-size:12px;color:#79808E;border-top:1px solid #262C36;padding-top:10px;max-width:980px}
"""


def _bar(size: float, biggest: float, cls: str = "") -> str:
    """Width by log of size: the rungs differ by orders of magnitude, so a
    linear bar shows one rung and eleven slivers."""
    if size <= 0 or biggest <= 0:
        return ""
    w = max(2, round(46 * math.log10(1 + size) / math.log10(1 + biggest)))
    return f"<span class='bar {cls}' style='width:{w}px'></span>"


def _cell(value: str, label: str, cls: str = "") -> str:
    return f"<div class='cell'><div class='v {cls}'>{value}</div><div class='l'>{html.escape(label)}</div></div>"


def _line(line: float) -> str:
    """The winner market is line 0 and is never written as a number: `+0` on a
    ladder of signed spreads reads as a rung, and it is the one leg the
    executor may never ticket."""
    return "winner" if float(line) == 0.0 else format(line, "+g")


def _num(v, fmt: str = "{:.0f}", dash: str = "—") -> str:
    """Formatted, or a dash. A missing count and a zero count are different
    facts and the page must not print one as the other."""
    if v is None:
        return dash
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return html.escape(str(v))


def _stream(snap: dict) -> str:
    """The reviewer's H1 in numbers: does the stream see the same violations
    REST does, and is anyone trading on these rungs?"""
    delta = snap.get("trades_delta")
    return ("<h2>Stream against REST</h2><div class='strip'>"
            + _cell(_num(snap.get("viol_rest")), "violations in the REST book (what the executor acts on)")
            + _cell(_num(snap.get("viol_ws")), "violations in the venue's own stream")
            + _cell(_num(snap.get("viol_common")), "the same pair in both books")
            + _cell(_num(snap.get("ws_trades")) + ("" if delta is None else f" <span class='muted'>+{delta:.0f}</span>"),
                    "trade prints seen (since the last sample)")
            + _cell(_num(snap.get("ws_msgs")), "stream messages")
            + _cell(_num(snap.get("ws_reconnects")), "stream reconnects",
                    "warn" if (snap.get("ws_reconnects") or 0) > 0 else "")
            + "</div>")


def _ladder_table(rungs: list[dict]) -> str:
    big_b = max([r["bid_size"] for r in rungs] or [0])
    big_a = max([r["ask_size"] for r in rungs] or [0])
    body = [("<h2>Ladder</h2><table><tr>"
             "<th>bid size</th><th>bid</th><th class='l'>line</th><th>ask</th><th class='l'>ask size</th>"
             "<th>book age</th><th class='l'>must hold</th><th class='l'>stream</th></tr>")]
    if not rungs:
        body.append("<tr><td colspan='8' class='none'>the newest sample carries no rung with a "
                    "two-sided book</td></tr>")
    for r in rungs:
        bound = []
        if r["lo"] is not None:
            bound.append(f"ask &ge; {r['lo']:.3f}")
        if r["hi"] is not None:
            bound.append(f"bid &le; {r['hi']:.3f}")
        age = r["age_s"]
        label = _line(r["line"])
        # A stream that disagrees with REST on this rung is the one per-rung
        # fact the H1 question turns on, so it gets a column of its own.
        if r["touch_equal"] is None:
            ws = "—"
        elif r["touch_equal"]:
            ws = "same"
        else:
            ws = "<span class='warn'>differs</span>"
        if r["ws_age_s"] is not None:
            ws += f" <span class='muted'>{r['ws_age_s']:.0f}s</span>"
        body.append(
            "<tr class='{}'>".format("winner" if r["winner"] else "")
            + f"<td>{_bar(r['bid_size'], big_b)}{r['bid_size']:,.0f}</td>"
            + f"<td class='{'lit' if r['lit_bid'] else ''}'>{_num(r['bid'], '{:.3f}')}</td>"
            + f"<td class='l line'>{label}</td>"
            + f"<td class='{'lit' if r['lit_ask'] else ''}'>{_num(r['ask'], '{:.3f}')}</td>"
            + f"<td class='l'>{_bar(r['ask_size'], big_a, 'a')}{r['ask_size']:,.0f}</td>"
            + f"<td class='{'warn' if (age or 0) > 120 else ''}'>{_num(age, '{:.0f}s')}</td>"
            + f"<td class='l bound'>{' · '.join(bound) or '—'}"
            # A bound broken by a leg the scanner would trade and one broken by
            # pennies the two fees swallow are different facts; the page must
            # not print them the same way.
            + ("<span class='lit'> broken</span>" if (r["lit_ask"] or r["lit_bid"])
               else "<span class='muted'> crossed, fees eat it</span>"
               if (r["ask_below_lo"] or r["bid_above_hi"]) else "")
            # A row the scanner was not handed must say so, or a stream-only
            # price reads as the book the executor is about to act on.
            + ("" if r["scanned"] else " <span class='muted'>one side quoted</span>" if not r["both"]
               else f" <span class='muted'>{html.escape(str(r['src']))} only — not scanned</span>")
            + f"</td><td class='l'>{ws}</td></tr>")
    body.append("</table>")
    return "".join(body)


def _violations(snap: dict) -> str:
    vios = snap["violations"]
    body = [("<h2>Pairs the ladder contradicts itself on</h2><table><tr>"
             "<th class='l'>buy YES / sell YES</th><th>buy</th><th>sell</th><th>edge</th>"
             "<th>size</th><th>$ at quoted size</th><th class='l'>the executor would</th></tr>")]
    if not vios:
        body.append("<tr><td colspan='7' class='none'>ladder consistent at this sample</td></tr>")
    for v in vios[:12]:
        why = v["why_not"]
        # The mid ladder is an ORDERING, not a gate (core.ladder.tape._why_not),
        # so it is said as a qualifier on a ticket and never as a refusal.
        act = ("<span class='up'>ticket it</span>"
               + ("" if v.get("mid") else " <span class='muted'>&mdash; mid-ladder pairs go first</span>")
               if not why else html.escape(why))
        body.append(
            f"<tr><td class='l'>{_line(v['high_line'])} / {_line(v['low_line'])}</td>"
            f"<td>{v['buy_price']:.3f}</td><td>{v['sell_price']:.3f}</td>"
            f"<td class='lit'>{v['edge_c']:+.2f}&cent;</td><td>{v['size']:,.0f}</td>"
            f"<td class='d'>${v['dollars']:,.2f}</td><td class='l muted'>{act}</td></tr>")
    body.append("</table>")
    skipped = []
    if snap["above_cap"]:
        skipped.append(f"{snap['above_cap']} pair(s) cross by more than "
                       "15&cent; — a stale rung nobody has requoted, not a market, and not counted above")
    if snap.get("fee_eaten"):
        skipped.append(f"{snap['fee_eaten']} pair(s) cross gross and are eaten by the two fees")
    if skipped:
        body.append(f"<div class='muted' style='margin-top:6px'>{' · '.join(skipped)}</div>")
    return "".join(body)


def _history(hist: list[dict]) -> str:
    if len(hist) < 2:
        return ""
    body = [("<h2>Last samples</h2><table class='hist'><tr><th class='l'>time</th><th>rungs</th>"
             "<th>rest</th><th>stream</th><th>both</th><th>trades</th></tr>")]
    for h in reversed(hist[-20:]):
        body.append(f"<tr><td class='l'>{html.escape(str(h['t'] or '—'))}Z</td><td>{h['rungs']}</td>"
                    f"<td>{_num(h['viol_rest'])}</td><td>{_num(h['viol_ws'])}</td>"
                    f"<td>{_num(h['viol_common'])}</td><td>{_num(h['ws_trades'])}</td></tr>")
    body.append("</table>")
    return "".join(body)


def _switcher(games: list[str], picked: str | None) -> str:
    if not games:
        return ""
    out = ["<div class='games'>"]
    for g in games:
        on = " class='on'" if picked and g.replace("aec-", "", 1) == picked.replace("aec-", "", 1) else ""
        out.append(f"<a href='/ladder?game={quote(g)}'{on}>{html.escape(g.replace('aec-', '', 1))}</a>")
    out.append("</div>")
    return "".join(out)


def render(snap: dict | None, games: list[str], picked: str | None, out_dir: str) -> str:
    """One page. `snap` is `core.ladder.tape.latest`, None when no tape has
    been written yet -- which is a state this page must render, because the
    first thing the operator does tonight is open it before kickoff."""
    shown = (snap or {}).get("game") or picked
    head = [f"<style>{CSS}</style><div class='top'><h1>Live ladder</h1>",
            ("<span class='muted'><a href='/'>desk</a> &middot; "
             "<a href='/pnl'>money</a> &middot; <a href='/instructions'>instructions</a></span>")]
    if snap:
        age = snap.get("tape_age_s")
        # The tape's own timestamp cannot say the writer is alive; its mtime can.
        stale = age is not None and age > 90
        head.append(f"<span class='k'>game</span> <span>{html.escape(str(shown))}</span>"
                    f"<span class='k'>sample</span> <span>{html.escape(str(snap.get('t') or '—'))}Z</span>"
                    f"<span class='k'>fetch</span> <span>{_num(snap.get('took_s'), '{:.1f}s')}</span>"
                    f"<span class='k'>tape written</span> "
                    f"<span class='{'warn' if stale else ''}'>{_num(age, '{:.0f}s ago')}"
                    f"{' — instrument may have stopped' if stale else ''}</span>")
    head.append("</div>")
    head.append(_switcher(games, shown))

    if not snap:
        # "No tape at all" and "no tape for the game you asked for" are
        # different states, and printing the first for the second would say
        # the instrument is down while five other games are sampling fine.
        if games and picked:
            miss = (f"No freshness tape yet for <b>{html.escape(picked)}</b>. "
                    f"{len(games)} other game(s) are sampling — pick one above.")
        else:
            miss = ("No freshness tape yet. The stream instrument writes one per live game from "
                    "kickoff, and this page draws whichever games are running — college football "
                    "and WNBA alike.")
        return ("".join(head) + f"<p class='none'>{miss}<br>"
                f"<span class='muted'>looking in {html.escape(out_dir)}/ws_freshness_*.jsonl</span></p>"
                "<script>setTimeout(function(){location.reload()},15000)</script>")

    body = [_ladder_table(snap["rungs"]), _violations(snap), _stream(snap),
            _history(snap.get("history") or [])]
    body.append(
        "<div class='foot'>Sizes are QUOTED, not filled. A rung is consistent when its ask is at or above "
        "every harder rung's bid and its bid at or below every easier rung's ask; a lit price is a leg the "
        "scanner would trade at this sample, after both fees. The pair costs (ask of the easier line) + "
        "(1 &minus; bid of the harder line) and pays $1.00 per contract in every final score, $2.00 if the "
        f"margin lands strictly between the two lines. A ticket also needs ${snap['floor_usd']:.0f} of edge "
        "&times; displayed size and two spread rungs — never the winner market. Those two tests are the "
        "executor's whole gate; the mid ladder (3.5 to 20.5) only decides which candidate it sends FIRST, "
        "which is why a &plusmn;2.5 WNBA pair is a ticket and not a skip. "
        "Book age is the venue's own last-update stamp for that rung.</div>")
    body.append("<script>setTimeout(function(){location.reload()},15000)</script>")
    return "".join(head) + "".join(body)
