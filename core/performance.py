"""Performance queries over the prediction log.

Answers the question the log exists for:

    "How would every prediction I have ever made have performed?"

Grouping defaults to ``(model_version, config_hash)`` and **refuses to
aggregate across differing hashes**. Blending two model generations averages
materially different models into one meaningless number — the exact failure the
config hash exists to prevent. A cross-config view must be asked for
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.storage import Prediction


class MixedConfigError(RuntimeError):
    """Raised when a query would blend model generations."""


@dataclass
class Cohort:
    model_version: str
    config_hash: str
    n_total: int = 0
    n_resolved: int = 0
    n_correct: int = 0
    avg_edge: float = 0.0
    avg_model_prob: float = 0.0

    @property
    def hit_rate(self) -> float | None:
        return self.n_correct / self.n_resolved if self.n_resolved else None


@dataclass
class CalibrationBucket:
    """Predicted probability bucket vs. realised frequency."""

    lower: float
    upper: float
    n: int = 0
    n_hit: int = 0

    @property
    def predicted(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def realised(self) -> float | None:
        return self.n_hit / self.n if self.n else None


def list_cohorts(session: Session) -> list[Cohort]:
    """Every (model_version, config_hash) generation present in the log."""
    rows = session.execute(
        select(
            Prediction.model_version,
            Prediction.config_hash,
            func.count(Prediction.id),
            func.count(Prediction.resolved_outcome),
            func.avg(Prediction.edge),
            func.avg(Prediction.model_probability),
        ).group_by(Prediction.model_version, Prediction.config_hash)
    ).all()

    out = []
    for version, cfg_hash, n, n_res, avg_edge, avg_p in rows:
        cohort = Cohort(
            model_version=version,
            config_hash=cfg_hash or "",
            n_total=n,
            n_resolved=n_res,
            avg_edge=float(avg_edge) if avg_edge is not None else 0.0,
            avg_model_prob=float(avg_p) if avg_p is not None else 0.0,
        )
        cohort.n_correct = session.scalar(
            select(func.count(Prediction.id))
            .where(Prediction.model_version == version)
            .where(Prediction.config_hash == cfg_hash)
            .where(Prediction.was_correct.is_(True))
        ) or 0
        out.append(cohort)
    return out


def assert_single_generation(session: Session, *, allow_mixed: bool = False) -> None:
    """Guard against silently blending model generations."""
    if allow_mixed:
        return
    n = session.scalar(
        select(func.count(func.distinct(
            func.concat(Prediction.model_version, ":", Prediction.config_hash)
        )))
    ) or 0
    if n > 1:
        raise MixedConfigError(
            f"{n} (model_version, config_hash) generations in the log. "
            "Aggregating across them averages different models together. "
            "Filter to one, or pass allow_mixed=True deliberately."
        )


def calibration(
    session: Session,
    *,
    model_version: str | None = None,
    config_hash: str | None = None,
    playoffs: bool | None = None,
    buckets: int = 10,
) -> list[CalibrationBucket]:
    """Predicted probability vs. realised frequency.

    A well-calibrated model's 70% predictions win ~70% of the time. This
    catches systematic over-confidence that a headline hit rate hides.

    `playoffs` splits the cohort: playoff predictions carry `reduced_confidence`
    and should not be blended into headline calibration.
    """
    stmt = select(Prediction.model_probability, Prediction.resolved_outcome).where(
        Prediction.resolved_outcome.isnot(None)
    )
    if model_version:
        stmt = stmt.where(Prediction.model_version == model_version)
    if config_hash:
        stmt = stmt.where(Prediction.config_hash == config_hash)
    if playoffs is not None:
        stmt = stmt.where(Prediction.reduced_confidence.is_(playoffs))

    out = [
        CalibrationBucket(lower=i / buckets, upper=(i + 1) / buckets)
        for i in range(buckets)
    ]
    for prob, outcome in session.execute(stmt).all():
        if prob is None:
            continue
        p = float(prob)
        idx = min(int(p * buckets), buckets - 1)
        out[idx].n += 1
        if outcome == 1:
            out[idx].n_hit += 1
    return out


def summary(session: Session, *, allow_mixed: bool = False) -> str:
    """Human-readable report over the whole prediction log."""
    cohorts = list_cohorts(session)
    lines = ["PREDICTION LOG", "=" * 78]
    if not cohorts:
        lines.append("  (no predictions yet)")
        return "\n".join(lines)

    lines.append(
        f"{'version':<10}{'config_hash':<14}{'total':>8}{'resolved':>10}"
        f"{'hit rate':>10}{'avg edge':>11}"
    )
    lines.append("-" * 78)
    for c in cohorts:
        hr = f"{c.hit_rate:.3f}" if c.hit_rate is not None else "n/a"
        lines.append(
            f"{c.model_version:<10}{c.config_hash[:12]:<14}{c.n_total:>8}"
            f"{c.n_resolved:>10}{hr:>10}{c.avg_edge:>11.4f}"
        )

    if len(cohorts) > 1:
        lines.append("")
        lines.append(
            f"  ⚠️  {len(cohorts)} model generations present. They are NOT blended — "
            "each row is a separate model."
        )

    resolved = sum(c.n_resolved for c in cohorts)
    lines.append("")
    if resolved == 0:
        lines.append("  No resolved predictions yet — hit rate and calibration")
        lines.append("  become available once games settle.")
    elif resolved < 100:
        lines.append(
            f"  ⚠️  Only {resolved} resolved predictions. Win rate is dominated by"
        )
        lines.append("      noise at this sample size; prefer CLV. See docs/math/clv.md.")
    return "\n".join(lines)
