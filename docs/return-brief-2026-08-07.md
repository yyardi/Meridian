# Return brief — week of 2026-08-07

Read this first. Everything else has a link.

**One sentence: the week measured nine ideas, killed most of them, built the
tools that made the killing cheap, and found that the one thing making money is
your own live-totals trading.**

**Still $0 traded by the system.** Every order this project has ever sent was
clicked by you.

---

## 1. The verdicts

Every one had its pass/fail bar written down *before* the number was computed.

| What | Verdict | The number | Detail |
|---|---|---|---|
| **Run overreaction** | ❌ **FAIL** | 444 runs / 11 games. Prices move ~11¢ on a run **and stay there** | [run-overreaction.md](math/run-overreaction.md) |
| **First-score overreaction** | ❌ **FAIL** | −3.9¢ per contract, 75 trades / 11 games | [first-score.md](math/first-score.md) |
| **Adverse selection** (market making) | ❌ **FAIL** | −2.66¢ per filled quote, 630k fills / 11 games | [adverse-selection.md](math/adverse-selection.md) |
| **Whale / depth signal** | ❌ **FAIL** | +0.22¢, CI spans zero. Big resting orders predict nothing | [depth-signal.md](math/depth-signal.md) |
| **Trailing-team underpricing** (your IND trade) | ⚠️ **PASSED — and not tradable** | +6.8¢ on its stated terms, but **−2.2¢** once you account for who's playing | [win-curve.md](math/win-curve.md) |
| **Tail volatility** | ⏳ Not enough games — **and pointing the wrong way** | Tails are *quieter* early, not livelier. Needs 2 more games to close | [tail-volatility.md](math/tail-volatility.md) |
| **ANCHOR's +0.75% edge** | ❌ **Gone** | Recalibrated to **−2.33%**. The old number rested on a 0.5¢ guess; measured reality is 2.11¢ | findings C13 |
| **Kalshi second-venue gap** — *the founding question* | ❌ **No gap** (gate met, 10 games) | 773 matched contract-pairs: the venues agree **within one tick**, median gap **0.00¢**, 97.2% within a cent, and exactly identical inside 3h of tip-off | [venue-gap.md](math/venue-gap.md) |

### The one that deserves a paragraph

You bought IND at 30% when they were down 5, sold at 45, made +50%. That
became a formal hypothesis, and **it passed its test** — trailing teams do
price below the historical base rate.

Then it failed a follow-up check, and the failure is the interesting part. The
history says *"a team down 5 at this point wins 30% of the time"* — averaged
over every team that has ever been down 5. The market knows it's Indiana. Once
you compare like with like, the trailing team turns out to be **over**priced by
2.2¢, not under.

Your specific trade is in the data: fair value at the moment you bought was
about 28%, and you paid 31.5%. **It was a fair price and the game went your
way.** That is a good outcome, not an edge — and telling those two apart is the
single most expensive mistake available here, which is why it got a test
instead of a position.

---

## 2. What got built, and works

- **Order path** — real orders, human-clicked, two-step ticket, editable price.
- **Exits** — pre-authorised sell orders the fill-watcher submits with terms you fixed.
- **Cancel path** — built, **PR #2 open, not merged**. See the click list.
- **Live fair value on `/picks`** — moneylines *and* totals, side by side with the book. Both captioned **unvalidated, display only**; neither can place an order.
- **EV alerts (`ev_guard`)** — pushes to your phone when the model's value drops to what you paid (*edge gone*), or when the price drops but the value holds (*price noise — don't panic*). Covers moneylines and totals; spreads say outright that they're uncovered.
- **Trade audit** — your whole app-trading history, scored at real prices.
- **Alerter + health checks** — the system tells you when it's broken.
- **Dedicated test database** — the test suite no longer corrupts the analysis data. Suite went from ~77s to **8.75s**, 834 passing.
- **Board survey tool** — `python -m core.survey --league nba`, ready for October.

---

## 3. Where this actually stands

**What the week closed.** The whole "prices overreact in-game and come back"
family is dead — four separate tests, all failed on their own terms. Market
making is dead: the spread doesn't survive being filled. ANCHOR's headline edge
did not survive being measured honestly rather than assumed.

**And the founding thesis lost its mechanism.** The whole project started from
"Polymarket's thin WNBA board prices below a sharper reference". Measured
against Kalshi on 773 contracts that are identical line-for-line, across all 10
games, the two venues quote **the same number to within one tick** — median gap
zero, 97.2% within a cent, and *exactly* identical inside three hours of
tip-off. There is no gap to translate.

One structural detail worth knowing: both venues list nine totals rungs three
points apart, and in 7 of 10 games those ladders sit exactly one point apart —
so most contracts on the two boards cannot be compared at all, let alone
arbitraged.

**What's still alive:**

1. **Your live-totals trading.** The audit found one pocket that made money:
   live totals, **+9.4% over 31 round trips**. Small sample, but it's the only
   positive thing in the file, and it's yours. The new totals FV strip exists
   specifically to give that instinct a number to check itself against.
2. **Ladder sigma** — the theory that Polymarket shapes its totals ladders too
   narrowly, so both tails are cheap. Untested, needs ~35 more resolved games,
   and it needs no basketball model at all if it holds.
3. **NBA in October** — a much bigger board. The survey tool is built and
   validated. **One caveat matters:** a far-dated board looks artificially wide
   (12× on the same board), and *wide* looks like *tradable*. The tool now
   refuses to compare two boards observed at different distances from tip-off.
   Don't let anyone skip that (findings V22).

---

## 4. The click list — only you can do these

1. **Verify the cancel endpoint.** One live cancel of a 1-share resting order.
   Nothing in the system has ever sent a cancel, so `DELETE /v1/orders/{id}` is
   an educated guess until a human clicks it once. It's the last unmeasured
   number in the latency picture (findings V21).
2. **PR #2 — review and merge, or don't.** Branch `feature/cancel-path`: the
   token-gated cancel button and its evidence trail. It's open and waiting on
   your call.
3. **Restart the manager session's file permissions.** macOS is denying that
   session access to Documents. It needs your password, so no agent can fix it.
4. **Decide whether the venue-gap gate should be restated.** It is written in
   *games* (10), but two of the ten contribute a single contract each because
   the ladders don't overlap — so 10 games is weaker evidence than it sounds.
   Restating it in *matched contracts* may be right. **Changing a
   pre-registered gate is your call alone**, which is why no agent has touched
   it. Detail in [venue-gap.md](math/venue-gap.md).
5. **ntfy topics.** Alerts go to the topic in `MERIDIAN_NTFY_TOPIC` in `.env`.
   Two things push: the **alerter** (something broke) and **ev_guard** (a
   position's edge is gone, or a drawdown is just noise). The alerter refuses to
   start without a topic set, so silence means it isn't running.

---

## 5. Your trading, straight

You asked for this to be measured, so here it is without softening.

| slice | trips | staked | returned | ROI |
|---|---:|---:|---:|---:|
| **everything** | 250 | $2,313 | $2,147 | **−7.2%** |
| live (in-game) | 146 | $894 | $836 | −6.5% |
| pregame | 104 | $1,420 | $1,311 | −7.6% |
| moneyline (all sports) | 168 | $1,905 | $1,749 | −8.2% |
| **totals · live** | **31** | **$140** | **$153** | **+9.4%** |

Across seven months and 250 round trips you are **down about 7%**, roughly
$166. The moneyline is where it went: 168 trips at −8.2%.

Two honest caveats in your favour: 250 round trips is not many, and they
cluster within games and days, so the true uncertainty is wider than the
numbers look. This is descriptive — no target was set in advance, so it isn't
a verdict on you.

But the shape is consistent and worth acting on: **the moneyline is where the
losses are, and live totals is the one place you're ahead.** That is also the
one thing the system has now built a live number for. If there's a single
practical takeaway from the week, it's *do more of the totals thing and less of
the moneyline thing* — and now there's a fair value on screen to check yourself
against while you do it.

One last thing worth saying plainly: the model doesn't currently beat the
market either. ANCHOR is at −2.33% once measured properly. Nobody in this
project has demonstrated an edge yet — you, the model, or the market maker.
What has been built is the apparatus for telling the difference, and this week
it worked exactly as intended: it killed nine ideas, including two of its own.
