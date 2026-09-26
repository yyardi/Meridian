# The ladder desk — a one-page guide for the two of you trading Sunday

Written 2026-09-26 for two people who have not seen this system before and
will be clicking SEND on NFL Sunday 2026-09-27. Read it once, start to end.
It is short on purpose. Where it says *record*, that is the whole job.

## 1. What the trade is, in one line

On the same game, the venue lists a ladder of spread lines for one team:
"wins by over 1.5", "by over 3.5", "by over 6.5" … A harder line can never
be *more* likely than an easier one, so the price of "over 3.5" can never
legitimately sit above the price of "over 1.5". For a few seconds, sometimes,
it does. When it does you **buy the easy line and sell the hard line**, pay
both fees, and every possible final score pays the pair at least $1 back —
$2 if the margin lands between the two lines. That difference, minus fees,
is the edge. Typically 2–10 cents per contract. It lives for **under a
second** most of the time; a few times a Sunday it stands for 1–5 seconds.

You are not there to make money. You are there to answer one question the
tape cannot: **does the size the venue displays actually fill when you take
it?** Five attempts answer it. That is the whole point of Sunday.

## 2. What you need before kickoff

- **The desk:** `http://<the address Yash gives you>:8008/arb` — it is on his
  private network (Tailscale), so you must be on it; if the page does not
  load, that is the first thing to fix, not the desk. The address is not
  written here on purpose (this repository is public).
- **The order token.** Yash gives it to you in person. Paste it into the
  password box at the top of the page. It lives in that browser tab only —
  close the tab and you paste it again. Without it every SEND is refused.
- **Money.** The desk caps a pair at **$25** (`MERIDIAN_ARB_MAX_PAIR_USD`) or
  the account balance, whichever is smaller, and sizes each ticket to a
  **$20 attempt** — about 21–23 contracts. Five attempts ≈ $100 of turnover,
  all of it back at settlement if both legs fill (this is an arbitrage), a
  small directional position if only leg 1 fills.
- **The venue's own page open beside it** (polymarket.us, the same game), so
  you can see what a human sees when the desk says something is there.

## 3. What the page shows

- **Left: the ladder** for the game you picked — each line with its YES
  bid/ask and displayed sizes, and the **age** of each quote in seconds. A
  **green ASK** is one we would lift (leg 1); a **red BID** is one we would
  hit (leg 2, which on this venue is buying that row's *No*). A tinted row is
  a rung breaking its bound.
- **Middle: tickets.** The executor writes one per crossing that passes the
  gate: the thin leg shows at least the contracts $20 buys, at ≥ 2c net
  edge, both legs spread lines (never the winner market). Each ticket names,
  in the venue's own words, the **row** ("KC to win by over 6.5 points") and
  the **button** (Yes / No) for each leg, the price, the quantity, the pair
  cost and the guaranteed amount. A ticket older than a few seconds is
  history — check the ages before you send.
- **Right top: LOCKED / ARMED.** LOCKED means the executor issues nothing and
  SEND is refused. Click **ARM** when you sit down; **LOCK** when you leave.
- **Right: balance, pair cap, recorded fills.**

## 4. How to send one pair

1. Pick a game that is live. Wait for a ticket whose two leg ages are both
   under ~2 s and whose sizes are still there on the venue's page.
2. Click **SEND…**. A confirmation ticket opens — titled *"Confirm — this
   sends real money, two legs"* — and spells every term in words: row,
   button, side, price, quantity, cost, guaranteed amount. Read it against
   the venue's page. Tick **Acknowledge**, then click **Confirm & send both
   legs**. Nothing is sent from the first button; **Meridian never sends
   without that second click.**
3. What happens: leg 1 (BUY YES on the easier line, at its ask) goes first as
   an immediate-or-cancel order. Leg 2 (BUY NO on the harder line, at
   1 − bid) goes **only for the quantity leg 1 filled**, and not at all if
   leg 1 filled nothing. Nothing rests on the book.
4. The venue's reply is written to the desk automatically (state, quantity,
   average price per leg). If the reply was unreadable or pending, the desk
   marks the attempt *placed* and you **record the real fills by hand** in
   **Recorded fills** once you can see them on the venue's page: filled
   quantity, price, seconds, per leg. "Did not fill" is a result — record it.

**If leg 1 fills and leg 2 does not:** do **not** chase. You hold a small YES
position on the easier line. Either leave it to settle or click **UNWIND…**
(it sells what leg 1 filled at the current bid, or a price you type). Record
which you did.

**If leg 1 fills nothing:** stop, record it. That is the most important
result of the day — it is what "phantom" means: the displayed size was not
there.

## 5. The protocol (this is pre-registered; do not improvise)

- **Five attempts** across the day, different games if you can, mid-ladder
  lines preferred (roughly +3.5 to +20.5 — the desk sorts those first).
- **Size = the ticket's quantity.** Do not size up. Do not send a single leg
  on purpose. Do not send the same ticket twice (the desk refuses it anyway).
- **Record every attempt**, including the ones where nothing filled. The desk
  keeps the machine record; keep a plain list too — time (UTC), game, the
  two lines, the two prices, the displayed sizes, what filled, seconds to
  fill, and anything the venue's own page showed that the desk did not.
- **Read the tally at the end, not during.** The registered rule: ≥ 3 of 5
  with both legs ≥ 80 % filled at the ticket's prices → displayed size is
  real. ≥ 3 of 5 with leg 1 filling nothing → it is phantom. Anything else →
  not yet; the next Sunday adds five more.

## 6. Rules that are not negotiable

- Only the **ARB** tab. The other tabs are archived research; touch nothing.
- Never more than **one pair open at a time**. Wait for leg 2's outcome
  before the next send.
- **Never** place a leg at the venue's own screen to "help" a half-filled
  pair. Record and stop.
- Do not restart anything, do not edit the schedule, do not run commands on
  the server. Everything launches itself (see §7); if something looks dead,
  message Yash.
- If the page shows **LOCKED** and you did not lock it, a red banner, or
  errors on SEND (5xx, "refused", "over cap") — stop and message Yash.
- Expect small numbers. A pair at 20 contracts and 4c edge nets ~$0.80. Five
  clean fills is a great day; the money comes later, at size, if fills are
  real.

## 7. Sunday's schedule (UTC; ET is −4)

Everything below starts itself from cron. You only click SEND.

| UTC | ET | what |
|---|---|---|
| 12:10 | 08:10 | the planner reads the board and installs the day |
| 16:50 | 12:50 | NFL stream recorder for the 17:00 / 20:05 / 20:25 waves |
| 16:58 | 12:58 | executors for the 17:00 games: TEN–NYG, NE–JAX, CAR–CLE, CIN–PIT, HOU–IND, KC–MIA, LAC–BUF, SEA–WAS, NYJ–DET |
| 20:03 / 20:23 | 16:03 / 16:23 | executors for ARI–SF, MIN–TB, then LV–NO, BAL–DAL |
| 00:10 / 00:18 (Mon) | 20:10 / 20:18 | SNF recorder and executor: LAR–DEN |
| ~04:40 (Mon) | 00:40 | the verdict: ledger rows, phantom check, fee line, pushed to Yash's phone |

Last Sunday this slate showed 27 crossings at your size across 7 games,
median edge 3c, most gone within 0.1 s, three that stood a full second. Be
sat down and ARMED by 17:00Z; the first quarter of a 17:00 wave is where the
ladders get noisy.

## 8. Words you will see

- **YES / NO** — on NFL the YES side of a spread market is the **away** team
  covering. The ticket names the venue's row and button so you never have to
  work this out.
- **Line** — "over 6.5" means wins by 7 or more. Easier line = smaller number
  = dearer YES.
- **Edge (c)** — per contract, after both taker fees (6.95 % × p × (1 − p)
  each leg).
- **Size / thin leg** — the smaller displayed quantity of the two legs; a
  ticket is never larger than it.
- **Age** — seconds since the venue last pushed that quote. Two ages under
  2 s means the two legs were quoted together; that is the only kind of
  crossing worth sending.
- **Phantom** — a displayed quote that prints trade *through* (someone got a
  better price than shown), i.e. it was a picture. 11 of the 33 biggest
  crossings so far were.
- **Candidate** — a crossing that passes the gate right now.

## 9. If in doubt

Do less. An attempt you did not make costs nothing and proves nothing; an
attempt you made and did not record cost money and proves nothing. Record.
