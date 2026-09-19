"""The game log — every opportunity a game showed, served at /log.

The ARB tab hides a ticket that no longer clears, which is right for a screen
you trade off and wrong at the end of the night. This page is the other half:
one row per EPISODE, oldest at the bottom, whether or not anybody acted.

The colour carries the only comparison that matters here. Green is an episode
that was ticketed AND placed, amber one that was ticketed and left, and a row
with no colour at all is one the instrument saw and nobody touched. The eye
should be able to find the third kind without reading a number.

Lives in `core/` and not `cfb/` because the api image COPYs core/ only, the
same reason `core.ladder.desk` and `core.ladder.pnl_page` moved.

Markup only. The arithmetic is `core.ladder.gamelog`'s; no venue call, no
database, no order path.
"""
from __future__ import annotations

import html

from core.ladder.pnl_page import CSS as BASE_CSS

#: The /pnl palette, plus what a log table needs: a wider table, a row tint per
#: outcome, and the switcher. One palette and not a second copy -- two ladder
#: pages that disagreed about what green means would be worse than one page.
CSS = BASE_CSS + """
table.log{max-width:1400px}
tr.placed td:first-child{box-shadow:inset 3px 0 0 #5FBF86}
tr.left td:first-child{box-shadow:inset 3px 0 0 #E0A94A}
tr.placed td.out{color:#5FBF86} tr.left td.out{color:#E0A94A}
.sw{display:flex;gap:1px;flex-wrap:wrap;background:#262C36;border:1px solid #262C36;max-width:1400px;margin-bottom:10px}
.sw a{background:#141922;padding:5px 10px;text-decoration:none;color:#B4BAC6;font-size:11px}
.sw a.on{background:#1D2431;color:#E6E9EE;font-weight:600} .sw a:hover{background:#1A1F27}
.sum{max-width:1400px;border:1px solid #262C36;background:#141922;padding:7px 10px;margin-bottom:10px;line-height:1.7}
.sum b{color:#E6E9EE} .caveat{color:#79808E;max-width:1400px;margin:8px 0 0;font:12px/1.5 -apple-system,system-ui,sans-serif}
"""


def _money(x: float) -> str:
    """Sign outside the dollar sign, as on /pnl: "-$0.54", never "$-0.54"."""
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def _dur(s: float) -> str:
    """A duration the eye can sort. Zero is a REAL value here -- one sample --
    so it prints as the bound it is rather than as a blank."""
    if s <= 0:
        return "<span class='muted'>&le;1 cycle</span>"
    return f"{s:.0f}s" if s < 90 else f"{s / 60:.1f}m"


def _age(v) -> str:
    if v is None:
        return "<span class='muted'>&mdash;</span>"
    return f"{v:.0f}s" if v < 90 else f"{v / 60:.0f}m"


def _switcher(games: list[str], current: str) -> str:
    """Every tape present, the open one marked. Games and not leagues: a tape
    is written per game, and the operator asks the question per game."""
    if not games:
        return ""
    out = ["<div class='sw'>"]
    for g in games:
        on = " class='on'" if g == current else ""
        out.append(f"<a{on} href='/log?game={html.escape(g)}'>"
                   f"{html.escape(g.replace('aec-', ''))}</a>")
    out.append("</div>")
    return "".join(out)


def _summary(s: dict) -> str:
    """The per-game line above the table.

    Both denominators are printed beside their counts. "12 episodes" on its own
    says nothing about whether the night was busy; "12 over 703 samples" does,
    and the missed count is the one the page is for.
    """
    pair = lambda p: f"{p[0]:+g} / {p[1]:+g}" if p else "&mdash;"   # noqa: E731
    span = ""
    if s.get("first_t") and s.get("last_t"):
        span = (f" &middot; <span class='muted'>{html.escape(str(s['first_t']))}"
                f"&ndash;{html.escape(str(s['last_t']))}Z</span>")
    return (
        f"<div class='sum'><b>{s['episodes']}</b> episode"
        f"{'' if s['episodes'] == 1 else 's'} over <b>{s['samples']}</b> samples"
        f"{span}<br>"
        f"<b>{s['episodes_over_floor']}</b> at or over the ${s['floor_usd']:.0f} floor "
        f"&middot; best per episode totals <span class='lit'>{_money(s['sum_best_usd'])}</span> "
        f"(<span class='lit'>{_money(s['sum_best_over_floor_usd'])}</span> of it over the floor) "
        f"&middot; biggest <span class='lit'>{_money(s['max_best_usd'])}</span> on "
        f"{pair(s['biggest_pair'])} &middot; longest {_dur(s['longest_s'])} on "
        f"{pair(s['longest_pair'])}<br>"
        f"ticketed <b>{s['ticketed']}</b> &middot; placed <b>{s['placed']}</b> "
        f"&middot; skipped <b>{s['skipped']}</b> &middot; "
        f"<b class='warn'>{s['missed_over_floor']}</b> over the floor and never ticketed"
        f"{'' if s.get('anchored') else ' &middot; <span class=muted>undated tape: book ages withheld</span>'}"
        "</div>")


def _outcome_cell(r: dict) -> str:
    """What happened to the episode's tickets, in the cell the eye lands on.

    An episode with no ticket gets a dash and no chip: a chip reading "none"
    would look like a decision, and nobody decided -- the chance went past.
    """
    if not r["ticketed"]:
        return "<td class='out muted'>&mdash;</td>"
    st = r["outcome"]
    fills = f" {r['qty_filled']:g} filled" if r["qty_filled"] else ""
    return (f"<td class='out l'><span class='chip {html.escape(st)}'>{html.escape(st)}</span>"
            f"{html.escape(fills)}</td>")


def _table(rows: list[dict]) -> str:
    """One row per episode, NEWEST FIRST: the operator reads the top of the
    page first and the last thing that happened is what they came for."""
    out = [("<table class='log'><tr><th class='l'>window</th><th>lasted</th><th>samples</th>"
            "<th class='l'>pair</th><th>best edge</th><th>best $</th><th>size</th>"
            "<th>buy</th><th>sell</th><th>book age hi/lo</th><th>ticketed</th>"
            "<th class='l'>outcome</th><th>net if settled</th></tr>")]
    if not rows:
        out.append("<tr><td colspan='13' class='none'>No episode in this tape — "
                   "every sample's ladder was consistent, or the tape has not started.</td></tr>")
    for r in reversed(rows):
        cls = "placed" if r["outcome"] in ("placed", "recorded") else (
            "left" if r["ticketed"] else "")
        net = (f"<td class='{'pos' if r['net_if_settled'] > 0 else 'neg'}'>"
               f"{_money(r['net_if_settled'])}</td>") if r["ticketed"] and r["qty_filled"] \
            else "<td class='muted'>&mdash;</td>"
        out.append(
            f"<tr class='{cls}'><td class='l'>{html.escape(str(r['start']))}"
            f"{'' if r['start'] == r['end'] else '&ndash;' + html.escape(str(r['end']))}</td>"
            f"<td>{_dur(r['duration_s'])}</td><td>{r['samples']}</td>"
            f"<td class='l'>{r['high_line']:+g} / {r['low_line']:+g}"
            f"{' <span class=muted>mid</span>' if r['mid'] else ''}</td>"
            f"<td class='lit'>{r['best_edge_c']:+.2f}¢</td>"
            f"<td class='{'lit' if r['over_floor'] else 'muted'}'>{_money(r['best_dollars'])}</td>"
            f"<td>{r['best_size']:,.0f}</td>"
            f"<td class='muted'>{r['best_buy']:.3f}</td><td class='muted'>{r['best_sell']:.3f}</td>"
            f"<td class='muted'>{_age(r['best_high_age_s'])} / {_age(r['best_low_age_s'])}</td>"
            f"<td>{r['ticketed'] or '<span class=muted>&mdash;</span>'}</td>"
            + _outcome_cell(r) + net + "</tr>")
    out.append("</table>")
    return "".join(out)


def _slate(slate: dict, current: str) -> str:
    """One line per game with a tape, and the roll-up under it."""
    out = [("<table><tr><th class='l'>game</th><th>samples</th><th>episodes</th>"
            "<th>&ge; floor</th><th>sum of bests</th><th>biggest</th>"
            "<th>ticketed</th><th>placed</th><th>missed &ge; floor</th></tr>")]
    if not slate["games"]:
        out.append("<tr><td colspan='9' class='none'>No freshness tape in this "
                   "directory — the stream instrument writes one per live game.</td></tr>")
    for g in slate["games"]:
        on = " style='background:#1A1F27'" if g["game"] == current else ""
        out.append(
            f"<tr{on}><td class='l'><a href='/log?game={html.escape(g['game'])}'>"
            f"{html.escape(g['key'])}</a></td>"
            f"<td>{g['samples']}</td><td>{g['episodes']}</td>"
            f"<td>{g['episodes_over_floor']}</td>"
            f"<td class='lit'>{_money(g['sum_best_usd'])}</td>"
            f"<td>{_money(g['max_best_usd'])}</td>"
            f"<td>{g['ticketed']}</td><td>{g['placed']}</td>"
            f"<td class='{'warn' if g['missed_over_floor'] else 'muted'}'>"
            f"{g['missed_over_floor']}</td></tr>")
    # A page that raises is worse than one that renders empty: this is the
    # view an operator opens when something looks wrong, and it is served
    # by a route whose smoke test requires it to answer without files.
    t = slate.get("total") or {}
    if slate.get("games"):
        out.append(
            f"<tr><td class='l'><b>{t['games']} game"
            f"{'' if t['games'] == 1 else 's'}</b></td>"
            f"<td><b>{t['samples']}</b></td><td><b>{t['episodes']}</b></td>"
            f"<td><b>{t['episodes_over_floor']}</b></td>"
            f"<td class='lit'><b>{_money(t['sum_best_usd'])}</b></td>"
            f"<td>{_money(t['max_best_usd'])}</td>"
            f"<td><b>{t['ticketed']}</b></td><td><b>{t['placed']}</b></td>"
            f"<td class='warn'><b>{t['missed_over_floor']}</b></td></tr>")
    out.append("</table>")
    return "".join(out)


def render(log: dict | None, slate: dict, games: list[str], out_dir: str,
           stamp: str = "") -> str:
    """The whole page. `log` is `core.ladder.gamelog.game_log` for the game on
    screen (None when no tape matches), `slate` is `gamelog.slate_log`, and
    `games` is every tape present."""
    current = log["game"] if log else ""
    head = (f"<style>{CSS}</style><div class='top'><h1>Game log</h1>"
            "<span class='muted'><a href='/arb'>ARB</a> &middot; "
            "<a href='/pnl'>P&amp;L</a> &middot; "
            "<a href='/instructions'>how to place one</a></span>"
            "<span class='muted'>every opportunity the tape showed, acted on or not</span>"
            f"<span class='k'>as of</span><span>{html.escape(stamp)}Z</span></div>")

    if log is None:
        body = ("<div class='none'>No freshness tape for that game. The switcher "
                "below lists every tape in this directory.</div>")
    else:
        body = (f"<h2>{html.escape(log['key'])}</h2>"
                + _summary(log["summary"]) + _table(log["episodes"]))

    # One line, not a paragraph: the resolution of the instrument, stated where
    # the durations are read. A log that let a 20-second sample read as
    # minute-by-minute truth would be quoted back without this.
    caveat = ("<div class='caveat'>The tape samples every ~20 s, so a one-sample "
              "episode lasted somewhere between an instant and one cycle (its "
              "duration is a lower bound), and an episode spanning two samples "
              "may have closed and reopened in between; dollars are edge &times; "
              "the smaller <b>quoted</b> size, and nothing here has filled.</div>")

    return (head + _switcher(games, current) + body + caveat
            + "<h2>The slate</h2>" + _slate(slate, current)
            + f"<div class='note'><span class='muted'>reading {html.escape(out_dir)}"
              "</span></div>"
            + "<script>setTimeout(function(){location.reload()},60000)</script>")
