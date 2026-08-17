# The live FV strip — a number on a screen, and nothing else

On the landing page `/`, under the pregame picks table: one row per in-game
moneyline, showing a formula fair value beside the market's bid/ask.
(It was `/picks` until the two pages were merged —
[landing-page.md](landing-page.md).)

Module: [`core/live_fv.py`](../../core/live_fv.py) · endpoint `/api/live-fv` ·
maths in [math/win-curve.md](../math/win-curve.md)

$$
P_{\text{live}} = \Phi\!\left(
\frac{\text{margin} + E_{\text{pregame}}\cdot t/40}{\sigma\sqrt{t}}
\right)
$$

with σ = 2.628 fitted from 787 games, $t$ = estimated minutes left, and
$E_{\text{pregame}}$ the expected margin implied by the pregame moneyline.

## It is display only, and that is enforced rather than intended

**Nothing on this strip is orderable.** No ticket, no size, no confirm button,
no `PICKS[]` entry. Two tests assert it rather than trusting review:

- `test_the_module_never_imports_the_executor` — greps the module source for
  `core.executor`, `build_order`, `LimitOrder`, `ShadowOrder`, `place_order`,
  `kelly`.
- `test_the_strip_markup_has_no_ticket_handler` — greps the strip's own
  JavaScript block for `openTicket`, `sendCell`, `PICKS[`, `confirmBtn`.

The caption on the page says **"formula FV — unvalidated, display only"** and
that is the literal status. The one hypothesis this formula has been pointed
at — #16 — passed its pre-registered gate and then inverted under a confound
check. A number acquires authority just by being on a screen next to a price;
this one has not earned any.

Endpoint separation is part of the same guard. `/api/picks` returns things with
an order behind them; `/api/live-fv` returns a float and a caption. Keeping
them apart is what stops the second becoming the first by accident.

## Three ways it refuses to answer

The interesting engineering here is where the strip prints `—` instead of a
number. Each is a case where the arithmetic would have produced something
confident and wrong.

| situation | what it shows | why |
|---|---|---|
| **clock estimate exhausted** | `—` | The venue publishes **no game clock**. Minutes left is interpolated from wall clock, and a WNBA quarter takes 15–20 real minutes for 10 game-minutes — so the estimate saturates in every game. At `t = 0` the formula stops being a probability and becomes a step function: it printed **FV 1.000 on a three-point game** before this was caught. |
| **overtime** | `—` | OT is 5-minute periods, the pregame edge is spent by definition (the teams are level), and the 40-minute denominator describes nothing. Printing a number under a note saying the model does not apply just invites reading the number. |
| **no pregame quote** | `—` | Without a pregame anchor the only alternative is a 50/50 prior, and a coin flip on a 0.68 team against a 0.30 team is a *wrong* assumption, not a neutral one. It is precisely the assumption that made hypothesis #16 look like a 6.8¢ edge. |

`Clock.usable` carries this, separately from `Clock.is_estimate`. Most of the
strip runs on estimates and that is fine — they are labelled `est.`.
`usable=False` is the stronger claim: the estimate has degraded to where the
formula produces confidence rather than approximation.

## What is labelled, and why

- **`est.`** appears on every interpolated clock. It is absent only at a period
  boundary and at halftime, the two instants the figure is exact. That is the
  same reason [win-curve.md](../math/win-curve.md) measures only at boundaries.
- **The gap is coloured only past 3¢.** Below that the difference is inside the
  noise the formula carries anyway, and colouring it would manufacture signal
  out of rounding.
- **Frames.** The margin is computed in the first team's frame because that is
  the frame the YES side of the book is quoted in (V20 in
  [findings.md](../findings.md)). Model and market are therefore directly
  comparable, which is the V15 lesson: a price is meaningless without its side.

## Refreshing σ

`DEFAULT_SIGMA` is hardcoded at 2.628 rather than recomputed per request — the
fit walks every completed game and this endpoint is polled every 15 seconds.
Re-run `python -m core.pulse.win_curve` when the season's history has grown,
update the constant, and update the number in
[math/win-curve.md](../math/win-curve.md) at the same time.
