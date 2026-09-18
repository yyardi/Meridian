"""Kept so the desk module and its tests import the page from one place.

The renderer moved to `core.ladder.pnl_page` because `core/api.py` serves it
now and the api image does not carry `cfb/`.
"""
from __future__ import annotations

from core.ladder.pnl_page import *  # noqa: F401,F403
from core.ladder.pnl_page import CSS, render  # noqa: F401
