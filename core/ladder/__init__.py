"""Ladder consistency: the venue's own prices against its own arithmetic.

Within one game, covering a larger number is strictly harder, and the winner
market is covering zero. So for lines a < b, P(cover b) >= P(cover a) must hold
for every pair -- no model, no view on the sport. Buying the easier rung and
selling the harder one pays +1 when the margin lands between them and 0
otherwise, so the position CANNOT LOSE. Being paid to hold it is arbitrage.

The relation is verified against settled outcomes, not assumed: 84,646 pairs
across 144 settled CFB and NFL ladders, zero cases where the harder rung paid
and the easier one did not (STATUS 0bi, 0bk).

PLACES NOTHING. Reads recorded snapshots and reports. The module imports no
venue client, which is a property of its imports rather than a promise.
"""
