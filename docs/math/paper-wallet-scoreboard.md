# The Scoreboard — paper-wallet registration

**Research agent, 2026-09-02/03 (operator-ordered: "add ur own fake wallet
put 1000$ in it and trade urself. that way u can really see"). Landed by
the manager; this commit is the cutoff. A and D build to this text.**

**PURPOSE:** the operator's $1,000, made into a running scoreboard against
the $3.29/day bar. AN INSTRUMENT, NEVER EVIDENCE — the capital clause
stands unchanged: a month of paper profit justifies the operator
conversation; it justifies nothing else.

1. **One $1,000 bankroll, two league-tagged ledgers** (Meridian/basketball,
   GRIDIRON/NFL — $500 each at birth, operator may re-split by recorded
   word). Separation applies to money most of all: fills route by league
   tag from the recording; an unknown-league fill is REFUSED loudly, never
   defaulted.
2. **Both arms, always, on every number:** the optimistic shadow-fill
   basis AND the measured-concession basis, labelled, never one without
   the other. The ~6¢/leg gap between them is the most expensive lesson
   this project owns; the dashboard never hides it.
3. **Sizing honest:** capped by RECORDED book depth at the quoted level at
   fill time (never "1 contract assumed fillable") AND by ledger balance;
   clipped fills logged as clipped. Fees at the venue coefficient (maker
   θ=0; taker arm charged 0.06·p·(1−p) if any lever crosses).
4. **Settlement into the wallet on market resolution** from resolved
   outcomes; open positions marked at recorded mid, labelled UNREALIZED —
   never summed silently into realized.
5. **Daily line: P&L vs $3.29, per arm, per ledger, plus month-to-date vs
   $100.** The bar is printed on the dashboard next to the number, both
   arms.
6. **Anti-hope-machine structure:** the wallet cannot be reset, edited, or
   re-split except by operator word recorded as a dated ledger line — a
   reset is a visible line, never a fresh table. History is append-only.
7. **Rules 16/18 before first live print:** replay the Aug pin through the
   wallet and reproduce the capture ledger's totals on both arms (known
   answer); two plants — a fabricated fill at known price/size moves the
   ledger by exactly the computed amount; a fill exceeding recorded depth
   clips and logs. A wallet that can't fail its selftest is a hope machine
   with extra steps.

---

*Results and dated ledger lines append below; the registration text above
is signed and never edited.*

## DATED LINE (2026-09-03, manager's interpretation ruling, RATIFIED by the author)

Terms 2+3 admitted two accounting models; ruled and ratified: **(a) — one
sizing per fill, both arms as parallel valuations of one activity, with
the sizing balance being the CONCESSION-ARM balance.** Hope may value the
book; it may never buy contracts. The author's completion, two
consequences chosen now rather than discovered:

1. **Concession-arm bankruptcy HALTS the ledger** — if the pessimistic
   balance reaches zero, the wallet stops trading even while the
   optimistic line shows profit, and the halt prints as a visible ledger
   line. A LEGITIMATE scoreboard outcome, not a defect: a book that only
   survives on the optimistic valuation is exactly the book the operator
   asked this instrument to expose.
2. **Cumulative toll paid is a dashboard line** — the arms' divergence
   over time IS the measured concession cost in dollars; printing it
   turns the project's most expensive lesson into a running meter.

## DATED LINE (2026-09-03, manager's ruling within model (a), for the author's morning ratification)

"Ledger balance" for sizing means **cash accounting with open-exposure
reservation**: available-to-size = concession-arm realized equity −
Σ(open positions' cost basis), freed on settlement — never realized
equity alone. Reason, arithmetic not taste: on a 12-game NFL Sunday at
the memo's own operating point, intra-day open cost stacks past a $500
ledger before evening settlements return; realized-equity sizing would
let the paper book carry exposure a real $1,000 could not afford,
inflating both arms on exactly the days the scoreboard matters most —
the structural optimism leak, distinct from the valuation kind the arms
already price. The real venue's rule is the model (bankroll = min(cash,
buyingPower), cash consumed at fill). A reservation-clipped fill logs as
clipped with its reason; that meter going visible on a big slate is
itself scoreboard information — it answers the operator's "unless you
need capital" with data.

## DATED LINE (2026-09-03, manager's ruling, for the author's morning ratification — the halt under reservation)

Reservation rewrote what ruin means: a book that never reserves more than
available can only ASYMPTOTE to zero, so the ratified zero-balance halt
became a knife-edge that essentially never fires (A's catch). Ruled:

1. **The live "bleeding" read is CONTINUOUS** — two dashboard meters:
   concession-equity drawdown, and capital-clip rate (reservation-clips
   as a share of fills; the "$1,000 binds" answer as a running number).
2. **The discrete halt moves to concession equity < 20% of seed** ($100
   on a $500 ledger), named a-priori: OPERATIONAL ruin — at $100 under
   reservation a single game's normal quoting consumes the entire
   available balance, and an 80% drawdown on cent-scale maker edges is
   refutation on this bankroll, not variance. The halt's ratified purpose
   (the enacted bar) transfers intact; the epsilon-at-zero form is
   superseded. X does not move once data exists.

## DATED LINE (2026-09-03, D's depth-join rulings from the artifacts; for the author's morning batch)

Term 3's "recorded book depth at the quoted level" is now pinned by the
writer code and the data, not convention: book_levels is ONE YES-frame
book per market stored verbatim from the venue (bids descending, offers
ascending, level_index 0 = top). **A maker ASK joins side='offer' at
price == quote_price; a BID joins side='bid' at quote_price** — the V28
mechanics/economics divergence governs P&L direction, never book
residence. **Price matching is EXACT at 4dp, clip-to-zero logged and
counted** — at-or-through flatters in both directions (better-priced size
fills before our level and was never ours; worse-priced size is reachable
only after our level is consumed). The clip-to-zero rate prints every
run; if the tick-neighbor artifact proves material, the revisit is a
within-one-min_tick snap as its OWN labelled column, never silently
merged.

Two caveats CARRIED, not fixed: (1) recorded depth at our price is
OTHERS' resting size holding time priority — treating it as our fill
capacity is per-fill OPTIMISTIC; the truly pessimistic bound
(traded-through volume) is not on this tape. Known optimism, stated.
(2) The join keys on book_levels.captured_at (which can be SECONDS
younger than its parent snapshot and is NULLABLE on old rows) with the
staleness bound stated per the ffill-hazard rule; NULL-stamped rows are
counted out, never inherited in.
