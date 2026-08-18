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

## The table shows markets, not only picks

The first version of this page rendered `/api/picks` only. On a night with 95
quoted markets and nothing inside the 14-hour horizon it printed *"No tradeable
pregame markets right now"* and nothing else — true, and useless. The operator
reads this page to see lines; a page that hides every line whenever nothing is
orderable answers a question nobody asked.

The body is now driven by `/api/board` — every market still on the board — with
`/api/picks` merged onto it by `market_slug`:

* a row **with** a pick carries the server's own buy/sell, return, size, stake
  and a SEND button, none of it recomputed here;
* a row **without** one renders the same columns greyed, with the reason where
  the button would be: `beyond 14h`, `spread 12¢`, `moneyline`, `in-play`,
  `no fresh line`.

The reason branches mirror the server's filters and were checked against it:
they reproduce `/api/picks` `filtered` exactly — 77 far-dated, 1 moneyline,
17 unanchored, 0 wide.

### The two endpoints are not the same instant

`/api/picks` prices are `Prediction.market_bid/ask`, frozen at `predicted_at`.
`/api/board` prices are the latest `MarketSnapshot`. Predictions run every 20
minutes, so a pick can be that stale — measured here, a 174.5 total priced
against ask 0.44 while the book had moved to 0.48.

Each row therefore stays internally consistent (pick rows entirely the
server's, board rows entirely the board's), an **Age** column gives the live
quote's freshness per row, and a pick whose book has moved off its priced-at
carries a `▲4¢` marker saying so. Two instants in one table without saying so
is how a row ends up with every number individually right and the row as a
whole wrong.

The client-side side/frame derivation in `positionView()` is applied **only**
to rows with no order path. A row that can become an order always uses the
server's numbers.

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

## Two things the merge with the game tape needed

**Class namespaces.** The strip's cards are `.scard`, not `.gcard`. The game
tape owns `.gcard`/`.gt` and binds its click handlers with a document-wide
`querySelectorAll(".gcard")`, so sharing the name would have hung `openGame()`
off every strip card — silently making a display-only surface clickable — and
the CSS (`:hover`, `.on`) would have collided too.

**Stale league responses.** Every league-scoped loader drops a response for a
league the operator has since switched away from. Measured here,
`/api/picks?league=wnba` took over three seconds while NBA answered
immediately, so switching WNBA → NBA let the late WNBA response overwrite the
NBA view: sixteen WNBA picks under an NBA tab, each with a live SEND button.
Elsewhere a stale table is a nuisance; on the picks table it is an order for a
game the operator is not looking at.

## Deploying it needs `--build`

The Dockerfile does `COPY static ./static`, so this page is baked into the
image rather than mounted. The api service is `build: .`, and a plain
`docker compose up -d api` recreates the container from the **existing**
image — it does not rebuild. So after this merges:

```
docker compose up -d --build api
```

Without `--build` the container comes back serving the previous dashboard, and
the natural reading of that is "the merge did not work".

**The analytics fix does not need the rebuild.** The two halves separate
cleanly, and it is worth knowing which one you are buying:

| What | Needs | Why |
|---|---|---|
| Analytics page ([analytics-path.md](analytics-path.md)) | plain `up -d api` | The path fix is a *mount*. The shipped image already routes through `reports_dir()` and already reads `MERIDIAN_DATA_DIR` per call, so the bind alone resolves it. |
| This page, league tabs, game tape | `up -d --build api` | `static/` is COPY'd into the image, so no amount of recreating shows a page the image does not contain. |

The broken-today half is the cheap one. And note what the expensive one also
does: `--build` bakes whatever is currently on `main` into the production
image, so "rebuild the image" and "ship main" are the same action here. That
is usually fine — the merged trade-sheet work is a script and a module nothing
in any container runs — but it deserves a glance at `main` first rather than
being treated as a no-op.

## Related

* [live-fv-strip.md](live-fv-strip.md) — the display-only fair value below the
  picks table.
