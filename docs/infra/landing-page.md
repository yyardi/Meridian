# The landing page is the picks page

`/` · [`static/index.html`](../../static/index.html) · route in
[`core/api.py`](../../core/api.py)

## What changed

The dashboard used to open on a live board: every rung of every ladder, with a
model price and an edge beside it. `/picks` was one click away in the sidebar.

The board is gone. `/` now serves the picks page, and `/picks` 302-redirects to
it.

## Why

The operator's first action every session was to click past the board. The
board answers *what is quoted*; the only question worth opening the dashboard
for is *what do I send*. A first screen that never answers it is a toll.

The second reason is drift. Two documents rendered overlapping views of the
same prediction — the board computed its own side and edge in JavaScript, the
picks page read the server's. Two renderings of one decision diverge, and the
one with the send button under it is the one that matters.

## What came across from the board

Only what the picks page could not already say:

* **The game context strip** — one card per game: teams, tip countdown (amber
  inside 3 hours), live score and period if one is running, market count, and
  how stale that game's quotes are. Scores come from `/api/live-fv`, which the
  page already fetches for the display-only strip below; the card reads that
  cache rather than fetching twice.
* **Recorder health** in the header — `recorder` / `pregame` / `live`. A pick
  priced off a dead writer still renders as a normal row; this is the only
  thing on the page that says otherwise.

Cards are marked `picks below ↓` or `no picks`, with a third state (`…`) while
`/api/picks` is still answering — "no picks for this game" and "we have not
asked yet" are different claims and the strip renders first.

Nothing on the strip is clickable. It has no `openTicket` call, no `PICKS[]`
entry and no order path, and a test asserts so.

## Two game-context surfaces, deliberately not one

The strip renders **current** state — live score, tip countdown, staleness —
and is labelled `now`. The game tape reached from a game renders **historical**
state as of each past decision, under a hard rule that it never reads a
snapshot later than that decision's `decided_at`.

They are not merged into a shared component, and that is a correctness
decision rather than a taste one: a component able to render "now" that is in
scope on the tape can be passed into a decision row, which is exactly the
lookahead the tape exists to prevent. The server-side test catches it, but the
cheaper boundary is to not own one component that straddles it.

What *is* shared is the part that should be — `core.live_fv.minutes_remaining`.
The tape imports it and this strip reads `/api/live-fv`, which is built on it,
so the two surfaces cannot disagree about what quarter it is at the source.

## What did not come across

* **The market table**, its filters and its sparklines. That is the deletion.
* **The SHADOW column** (`REST`/`CROSS` plus the sizer's quantity). The confirm
  ticket computes rests-or-crosses live off the price actually in the box, and
  that label moves as you nudge the price. The column showed the verdict for a
  limit price nobody was going to send — two numbers for one decision, and the
  stale one was larger.

`/api/board` still exists and is still tested. Nothing renders it.

## What is unchanged

The order path, byte for byte: the row button only opens the ticket, the
confirm button inside it is the only thing that posts, `MERIDIAN_ORDER_TOKEN`
still gates `/api/orders`, and the token still lives in `sessionStorage` for
one tab. This change did not touch any of it.

The banner disclaimers are unchanged text — shadow picks, the 60-day window,
the CLV gate, `?` for a disagreement over 15% — and
[`tests/test_landing_page.py`](../../tests/test_landing_page.py) fails if any
of them is lost in a future redesign.

## Related

* [live-fv-strip.md](live-fv-strip.md) — the display-only fair value below the
  picks table.
