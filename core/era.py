"""The era boundary: where the pregame ANCHOR record ends and PULSE begins.

The operator asked for a clean slate without deleting history (2026-08-18).
Everything shadow-traded before PULSE's first live decision is the **ANCHOR
era** — the pregame model's record. Everything from that instant on is the
**PULSE era**. The operator-facing pages default to the PULSE era and keep the
ANCHOR record behind an explicit archive toggle, labelled as what it is.

This module answers exactly one question — *when did the PULSE era begin?* —
and is deliberately consumed only by presentation code:

* **No row is touched.** The boundary is a filter applied at query time on the
  operator-facing endpoints (`/api/results`, `/api/games`). Nothing is
  deleted, nothing is rewritten, and flipping the toggle shows the full
  archive.
* **The registered measurements never see it.** `core/analytics.py`,
  `core/quote/report.py` and `core/scorecard.py` keep reading full history —
  their provenance (C11/C14) depends on it, and a test bans this module from
  their import graphs. Era filtering is presentation, not measurement.

The boundary itself:

* ``MERIDIAN_ERA_BOUNDARY`` (ISO-8601), when set, wins. The explicit constant
  exists because a derived boundary moves — it is None until the first live
  decision lands, then jumps backward in no run ever — and an operator who
  wants the era to start at a specific instant should be able to say so.
* Otherwise: ``min(decided_at)`` over ``pulse_decisions`` rows whose phase is
  not pregame — the dispatch's "PULSE's first live decision timestamp",
  taken literally. Before any live decision exists the answer is None and the
  PULSE era has not started; pages say so rather than showing the archive
  under a new name.

A game belongs to the era of its **last** decision. Games straddling the
boundary (ANCHOR kept deciding pregame after PULSE went live) land in the
PULSE era rather than being split — splitting one game's tape across two
views would break the deep dive's "every decision in this game" promise.
"""

from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import text

UTC = dt.timezone.utc

ERA_ENV = "MERIDIAN_ERA_BOUNDARY"

#: The archive's display name. One spelling, used by every page.
ANCHOR_LABEL = "ANCHOR — the pregame model's record"


def era_boundary(session) -> dt.datetime | None:
    """When the PULSE era began, or None if it has not.

    The env override is read per call, not at import — same rule as
    ``core.paths.data_dir``, for the same reason: tests and containers set
    the environment after import.
    """
    override = (os.environ.get(ERA_ENV) or "").strip()
    if override:
        try:
            parsed = dt.datetime.fromisoformat(override)
        except ValueError as exc:
            raise ValueError(
                f"{ERA_ENV}={override!r} is not ISO-8601; refusing to guess "
                "an era boundary") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    row = session.execute(text(
        "SELECT min(decided_at) FROM pulse_decisions WHERE phase != 'pregame'"
    )).scalar()
    if row is None:
        return None
    return row if row.tzinfo else row.replace(tzinfo=UTC)
