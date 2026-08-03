"""Measurements that gate the PULSE (in-game directional) strategy.

`overreaction` asks the one question that decides whether PULSE can exist: do
prices overshoot on a scoring run and then revert by more than the round trip
costs? If they do not, no live model rescues the strategy, and the right answer
is to not build it.
"""
