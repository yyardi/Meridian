"""Deterministic hashing of model configuration.

Why this exists
---------------
`model_version` is a hand-bumped module constant. Tunable parameters live in
`strategies/wnba_totals/config.py` — decay half-life, shrinkage k, the
Pythagorean exponent, the record coefficient. Changing any of those silently
changes the model *without* bumping `model_version`, so two materially
different models would share a version tag and the backtest would average them
together.

Hashing the config the model actually ran with makes that impossible by
accident. The backtest groups on `(model_version, config_hash)` and refuses to
aggregate across differing hashes.

The hash must be stable across processes and machines, so:
  - keys are sorted
  - separators are canonical (no incidental whitespace)
  - Decimal/date/etc. are normalised to strings rather than relying on repr
  - `ensure_ascii=True` so encoding differences can't shift bytes
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from decimal import Decimal
from typing import Any


def _canonicalize(value: Any) -> Any:
    """Convert a config value into something JSON-canonical and stable.

    Floats are deliberately routed through `repr` via Decimal conversion so
    that 0.25 and 0.2500000001 do not collide, while ints/strings/bools pass
    through untouched.
    """
    if isinstance(value, Decimal):
        return f"decimal:{value.normalize()}"
    if isinstance(value, (_dt.datetime, _dt.date)):
        return f"datetime:{value.isoformat()}"
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, set):
        return sorted(_canonicalize(v) for v in value)
    if isinstance(value, float):
        # repr() round-trips exactly in Python 3, unlike str() on older versions.
        return f"float:{value!r}"
    return value


def canonical_json(config: dict[str, Any]) -> str:
    """Render a config dict as canonical JSON: sorted keys, no stray whitespace."""
    return json.dumps(
        _canonicalize(config),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def compute_config_hash(config: dict[str, Any]) -> str:
    """Return a deterministic SHA-256 hex digest of a model config.

    Identical configs always hash identically, regardless of key insertion
    order or which process computes it.
    """
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()
