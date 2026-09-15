"""The 15c quote cap decided what the adverse-selection result could see.

It is read at import time, so an override that does not survive a reload is an
override in name only. These tests pin the BEHAVIOUR (the constant tracks the
environment) rather than the value, so they still pass when the default is
deliberately changed -- except the one test whose whole job is to notice that.
"""
from __future__ import annotations

import importlib
import os
import unittest.mock

import core.quote.adverse_selection as advsel


def _reload(**env):
    with unittest.mock.patch.dict(os.environ, env, clear=False):
        return importlib.reload(advsel)


def test_default_is_still_15c_and_a_change_must_be_deliberate():
    """If someone edits the default, this fails and they must say why in the
    commit. That is the point: the constant silently bounded every maker
    number we have ever published."""
    with unittest.mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MERIDIAN_QUOTE_MAX_SPREAD", None)
        assert _reload().MAX_SPREAD == 0.15


def test_the_override_actually_moves_the_constant():
    assert _reload(MERIDIAN_QUOTE_MAX_SPREAD="0.40").MAX_SPREAD == 0.40


def test_the_override_moves_the_GATE_not_just_the_constant():
    """A constant nothing reads is decoration. A 30c-spread quote must be
    refused at the default and admitted once the cap is raised -- otherwise
    raising it accrues no new fills and the experiment cannot run."""
    wide = 0.30
    m = _reload(MERIDIAN_QUOTE_MAX_SPREAD="0.15")
    assert not (m.MIN_SPREAD <= wide <= m.MAX_SPREAD), "30c must be OUT at the default"
    m = _reload(MERIDIAN_QUOTE_MAX_SPREAD="0.40")
    assert m.MIN_SPREAD <= wide <= m.MAX_SPREAD, "30c must be IN once the cap is raised"


def teardown_module(_):
    os.environ.pop("MERIDIAN_QUOTE_MAX_SPREAD", None)
    importlib.reload(advsel)
