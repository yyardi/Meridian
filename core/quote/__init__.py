"""Measurements that gate the QUOTE (market-making) strategy.

Nothing here places, prices or sizes an order. These modules answer the two
questions that decide whether market making on this venue is viable at all:

* `adverse_selection` — does the spread survive being filled precisely when
  you are wrong?
* `depth_signal` — does large resting size predict the next move?

QUOTE is not built until those gates pass. Building the strategy first and
measuring afterwards is the mistake this project keeps not making.
"""
