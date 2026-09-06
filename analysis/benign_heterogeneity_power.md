# Market selection for benign fills: the power answer, and it stops here

Assigned: is the benign event rate heterogeneous across markets, and by how
much? First step was to establish whether n=118 can support any such test.
**It cannot, for the bar that matters, so no split was run.**

Inputs validated against c7's published figures before use: n=118, benign
23.7%, normal 95% upper **0.314** — reproduces c7's 31.4% exactly. That implies
**28 benign events**.

The bar is fixed and high: a selection rule must lift the benign share from
~24% **past 48%** — a doubling.

## ★ WHAT A SUBGROUP WOULD HAVE TO LOOK LIKE

To establish a subgroup at >=48%, its CI **lower** bound must clear 0.48:

    subgroup m   p-hat needed   benign needed   available   possible?
            20          0.684              14          28   yes
            30          0.651              20          28   yes
            40          0.630              26          28   yes
            50          0.615              31          28   NO
            58          0.606              36          28   NO
           118          0.569              68          28   NO

**Any subgroup of 50 or more events is arithmetically impossible** — it would
need more benign events than exist on the whole tape.

The reachable cases require near-total separation:

* m=20 needs **50% of all benign events inside 17% of the tape**
* m=30 needs **71% inside 25%**
* m=40 needs **93% inside 34%**

## ★ AND CLUSTERING, WHICH THE n=118 FIGURE DOES NOT ACCOUNT FOR

The 118 events sit inside a handful of markets and games. With within-market
correlation the SE inflates by `sqrt(1 + (m_bar - 1) * rho)`:

    G=20 clusters, rho=0.3   SE x1.57   overall half-width 0.121 (vs 0.077)
    G=10 clusters, rho=0.3   SE x2.06   overall half-width 0.158

At G=20 and rho=0.3 **the tape-wide rate alone spans 0.12 to 0.36.** Every
subgroup threshold above moves further out of reach.

## VERDICT

**118 events cannot support a heterogeneity test against a 48% bar.** The test
fires only under near-total separation and only if the events are treated as
independent, which they are not. **No split was run, because running one would
produce a number that could not mean anything.**

Per the standing instruction: that is a complete answer, and it is where this
stops.

## WHAT WOULD MAKE IT ANSWERABLE

For a *realistic* selection rule — a subgroup genuinely at r, covering fraction
f, with the remainder making up the 23.7% average:

    subgroup rate   fraction   implied rest   events needed
             0.55       0.20          0.159             975
             0.55       0.30          0.103             650
             0.60       0.20          0.146             325
             0.70       0.15          0.155             114

**Only the last is within reach of the current tape, and it requires a subgroup
running at 70% — three times the tape-wide rate.** Anything less extreme needs
325 to 975 events against the 118 available.

## The two traps, unexercised but recorded for whoever runs it on more tape

* **Do not select on anything correlated with our own fill rate.** "How often
  the mid crossed down through a touch" is a near-proxy for our fill rate and
  makes the comparison tautological. Prefer exogenous market properties —
  spread width, price level, market type, time-to-settlement.
* **Anything observable only after the quote is not a selection rule.** The cut
  must be computable at quote time.
