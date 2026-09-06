# The fill rule has two defects pointing opposite ways — 2026-09-06

**Three documents describe the simulator's bias and at least two cannot both be
right as written. They can all be right about different populations, and once
you separate those, the honest conclusion is stronger than any of them: the net
bias is UNKNOWN IN SIGN.**

## The rule

`core/quote/engine.py:260` books a bid fill when:

```python
if mid <= standing.bid_price:
```

`standing.bid_price` is the touch bid at the moment we quoted. For any positive
spread `bid < mid`, so this can never fire on the observation that created the
quote — it fires only when a **later** mid has fallen to or below our **earlier**
bid. That is the book moving down through us.

This is deliberate and pinned by
`test_a_move_inside_the_spread_fills_nothing_but_requotes`. It was a decision,
not an accident.

## The two defects

| | what it is | direction |
|---|---|---|
| **Phantom** | Of the fills the simulator **does** book, a majority could not have occurred as booked — our order was never in the book, and queue position is uncorrected (median 15 contracts ahead, 90th percentile 850). Measured at **63.9%**. | **optimistic** about the booked set |
| **Censoring** | Fills that **would** have occurred produce no row at all. A counterparty crossing to our resting bid while the ask holds leaves the mid above our bid — the rule needs the mid to fall *through* us, so the benign fill is invisible. | **pessimistic** about which fills exist |

**These are not contradictory.** One is a defect in the rows that are present;
the other is a defect in the rows that are absent. They act on different
populations and push in opposite directions.

So `quote-shadow.md`'s "optimistic bounds" is defensible about the first and
wrong only when read as a statement about the net. And 63.9% was never one
quantity: it is a booking defect and a censoring defect sharing a denominator.

## What this costs

**Every making result this programme has produced is computed on a population
SELECTED for having moved against us.** Capture ≤ 0 is forced by construction,
not measured. That includes `−0.38¢/fill`, the `−2.0¢ to −3.2¢` trade-print
range, and every figure conditioned on the real/phantom split.

It also explains an operational mystery cheaply. On 2026-09-05 the venue's
prices froze at 17:39Z and fills collapsed ~1000× **while recorded row volume
rose**:

| hour | games | markets | rows | fills |
|---|---:|---:|---:|---:|
| 17:00 | 16 | 2,655 | 1,138,926 | 4,937 |
| 18:00 | 17 | 2,807 | 1,171,813 | **0** |
| 19:00 | 29 | 4,448 | 1,181,502 | 3 |

A fill requires the mid to move through our bid. A frozen book cannot produce
one. Zero fills during a price freeze is the code behaving exactly as written —
two incidents collapsing into one, with no engine bug to find.

## The conclusion, which is the load-bearing part

**The net bias is unknown in SIGN, not merely uncertain in size.** No document
previously said this, and it is a stronger caveat than any of the three claims
it replaces.

Neither `−0.38¢` nor `63.9%` can authorise anything in either direction. Both
are computed on a population the rule chose.

**And it is not resolvable in simulation.** The missing variable is our own
order, which was never in the book — no quantity of additional tape supplies
it. Only real resting orders can: see `core/quote/probe.py`, built inert, with
its pre-registration in the module rather than in prose.
