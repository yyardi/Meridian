"""The operator's instructions page, served by the desk at /instructions.

Plain words for a person at a phone: what the signal is, which contract to
buy and which to sell, how to read a ticket, the steps on the venue, the
rules, how to record, and why the two legs cannot both lose.
"""
from __future__ import annotations

CSS = """
body{font:16px/1.55 -apple-system,system-ui,sans-serif;background:#15181F;color:#E6E9EE;margin:0;padding:16px 16px 60px}
.wrap{max-width:720px;margin:0 auto} h1{font-size:26px;margin:0 0 6px} h2{font-size:18px;margin:28px 0 8px;padding-top:14px;border-top:1px solid #333A47}
p{margin:8px 0} .muted{color:#8C93A1;font-size:13px} a{color:#3F8ED0}
table{border-collapse:collapse;width:100%;font-size:14px;margin:10px 0} th,td{padding:7px 8px;border-bottom:1px solid #333A47;text-align:left;vertical-align:top}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#8C93A1} tr.hi td{background:#2C2416}
.box{background:#1C2028;border:1px solid #333A47;border-radius:8px;padding:12px 14px;margin:10px 0}
.leg{font-family:ui-monospace,Menlo,monospace;font-size:14px;background:#232833;padding:10px 12px;border-radius:6px;margin:6px 0}
.big{font-size:18px;font-weight:600} ol li{margin:6px 0} .warn{border-left:4px solid #E0A94A;padding-left:12px}
"""

HTML = f"""<style>{CSS}</style><div class='wrap'>
<div class='muted'><a href='/'>&larr; back to the desk</a></div>
<h1>How to place a ladder ticket</h1>
<p class='muted'>Read once before the first ticket. Two minutes.</p>

<h2>1 &middot; What the signal is</h2>
<p>Every game has a ladder of spread contracts. For one team, a contract with <b>more points given to that team</b> is <b>easier</b> to win than one with fewer: "Detroit +13.5" (Detroit wins, or loses by 13 or fewer) pays in every world "Detroit +10.5" pays in, plus a few more. So the easier one must always cost at least as much as the harder one.</p>
<p class='big'>The signal: someone is <i>offering</i> the easier contract for less than someone else is <i>bidding</i> for the harder one.</p>
<p>That is a mistake in the book, not a prediction about the game. It appears for minutes after a score, on the middle rungs, because the maker who rests orders there is slow to re-quote.</p>

<h2>2 &middot; Which one you buy, which one you sell</h2>
<table>
<tr><th></th><th>in Detroit's words</th><th>in Buffalo's words (what the screen shows)</th><th>what it is supposed to be</th></tr>
<tr class='hi'><td><b>BUY (leg 1)</b></td><td>the <b>easier</b> contract: DET +13.5</td><td>row "BUF to win by over 13.5 points" &rarr; tap <b>No</b></td><td>the dearer of the two</td></tr>
<tr><td><b>SELL (leg 2)</b></td><td>the <b>harder</b> contract: DET +10.5 (selling it = buying its No)</td><td>row "BUF to win by over 10.5 points" &rarr; tap <b>Yes</b></td><td>the cheaper of the two</td></tr>
</table>
<p>You buy the cheap easy thing and sell the expensive hard thing. The difference, minus fees, is yours at settlement whatever the score. The ticket already says which row and which button; you do not have to work this out under time pressure.</p>

<h2>3 &middot; Reading a ticket</h2>
<div class='leg'>1) BUF to win by over 13.5 points -&gt; tap No,&nbsp; limit 0.410 x 1&nbsp; &lt;- FIRST</div>
<div class='leg'>2) BUF to win by over 10.5 points -&gt; tap Yes, limit 0.530 x 1</div>
<p><b>Row</b> = the line to pick in the venue's line picker. <b>Button</b> = Yes or No under that row. <b>Limit</b> = the price the book showed; enter exactly that as a limit price (never a market order). <b>x 1</b> = quantity. "FIRST" marks the stale leg &mdash; the one that disappears when the maker wakes up &mdash; so it goes first.</p>
<p class='muted'>The two prices should add to a little under $1.00 (here 0.94). If the screen shows the button at a very different price from the ticket, the moment has passed: skip it and mark it skipped.</p>

<h2>4 &middot; The steps on the venue</h2>
<ol>
<li>Open the game. Under <b>Spread</b> there is one row: "<i>TEAM</i> to win by over [N] points" with a line picker.</li>
<li>Open the picker and scroll to the row named on the ticket. The list holds both teams' lines: the other team's rows are further down.</li>
<li>Tap the button the ticket names (Yes or No). Enter the <b>limit price</b> and <b>quantity</b> from the ticket. Submit.</li>
<li>Watch whether it fills. Then do leg 2 the same way, <b>within 60 seconds</b>.</li>
<li>Back on the desk: tap <b>I placed it</b>, then enter the fills when the venue shows them (filled qty, price, seconds to fill, per leg). <b>0 filled is a result too</b> &mdash; it is the result this test exists to find.</li>
</ol>

<h2>5 &middot; The rules</h2>
<div class='box warn'>
<p><b>Leg 1 first, always.</b> If leg 1 does not fill, stop; record it; that is a result.</p>
<p><b>Never chase leg 2 past 60 seconds.</b> If leg 1 filled and leg 2 did not, you hold one ordinary one-sided contract worth at most what you paid for it (a few dollars at test size). Record it and let it settle.</p>
<p><b>Never the winner market.</b> Tickets are spread-vs-spread only; an NFL tie settles the winner contract at $0.50 and would break the guarantee.</p>
<p><b>Skip a game with weather or postponement risk.</b> A postponed game settles every contract at "last fair market price", not $0/$1.</p>
<p><b>The lock is yours.</b> One click on the desk stops the executor writing or pushing anything; it keeps watching.</p>
</div>

<h2>6 &middot; Why the two legs cannot both lose</h2>
<p>Leg 1 (DET +5.5) pays if Detroit loses by 5 or fewer, or wins. Leg 2 (No on DET +3.5) pays if Detroit loses by 4 or more. For both to lose, Detroit would have to lose by 6 or more <i>and</i> by 3 or fewer at the same time. That cannot happen. Every final score pays at least one leg $1.00; a loss by exactly 4 or 5 pays both, $2.00. You paid $0.94 for the pair.</p>
<table>
<tr><th>final score</th><th>leg 1 (DET +5.5)</th><th>leg 2 (No on DET +3.5)</th><th>paid</th></tr>
<tr><td>Detroit wins, or loses by 1&ndash;3</td><td>$1</td><td>$0</td><td>$1</td></tr>
<tr class='hi'><td>Detroit loses by 4 or 5</td><td>$1</td><td>$1</td><td><b>$2</b></td></tr>
<tr><td>Detroit loses by 6 or more</td><td>$0</td><td>$1</td><td>$1</td></tr>
</table>
<p>Real example: Buffalo won 41&ndash;31, Detroit lost by 10. Leg 1 paid $0, leg 2 paid $1: $1.00 back on $0.94. Where money can still be lost: only one leg fills; the wrong button; a postponed game. Not the score.</p>

<h2>7 &middot; What the money looks like</h2>
<p>Per pair you put in about 0.92&ndash;0.98 and get $1.00 back &mdash; roughly 2&ndash;8 % on the money, once, locked until the game settles (about 3.5 hours). Tonight's tickets are one contract each under a $5 budget: they exist to answer <b>whether displayed size fills at all</b>, not to make money. Five recorded attempts decide it: three with both legs filled &rarr; size is real; three with leg 1 unfilled &rarr; it is phantom and the idea is withdrawn.</p>
<p class='muted'>Full write-up with the measurements, the maths and the reviewer's verdict: the Ladder Lag Review report. Once the ARB tab ships, SEND on the dashboard fires both legs on one click.</p>
</div>"""
