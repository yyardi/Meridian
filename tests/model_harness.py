"""Validation harness for a live model that takes the MARKET as a feature.

Written BEFORE the model produces a number, which is the only time this is
cheap. Once a result exists, every check below becomes an argument about
someone's work instead of a property of the pipeline.

WHAT IT IS FOR
--------------
A model with the market mid as an input can score as well as the market while
carrying no information of its own — by learning to output its own input. That
result looks exactly like the honest tie we already have, so nothing about the
number itself would reveal it. `skill_beyond_market` and
`predictions_track_the_mid` are the two checks that separate those cases.

The rest are the failures this codebase has actually shipped, in the order it
shipped them: a sign that inverts (`exp_devigged_clv.py:133`, over/under index),
a holdout split by row rather than by game, and a feature summarised after the
decision it informs.

HOW TO USE IT
-------------
Implement `Model` — two methods — and hand it to `run_all`:

    from model_harness import Model, run_all
    report = run_all(YourModel)
    assert report.ok, report.failures

Nothing here imports the model under test. It is a protocol, so the harness
can be written and reviewed before the model exists.

WHY THE ADVERSARIAL MODELS ARE IN THE SHIPPED FILE, not the tests
-----------------------------------------------------------------
`MidCopier`, `SignFlipped` and `LeakyModel` exist so every check can be
watched to FAIL on demand. A check nobody has seen fail is the defect this
harness exists to prevent, and three of those shipped today in this repo —
including two of mine. Keeping the adversaries beside the checks means the
next person can re-run the proof rather than trust this docstring.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from core.quote.adverse_selection import clustered_mean

#: A model whose predictions correlate above this with its own mid input has
#: not been shown to add anything. Not a pass mark — a floor below which the
#: comparison against the market is meaningless, because both series are the
#: same series.
MID_ECHO_CORR = 0.98

#: Signal strength for the injected-effect test, in probability units. Large
#: enough that failure to recover it is a pipeline fault rather than noise at
#: the sample sizes a football slate produces.
INJECTED_EDGE = 0.10


@dataclass(frozen=True)
class Row:
    """One decision point. `mid` is the market's price AT DECISION TIME."""

    game_id: str
    t: int                      # ordinal within the game; decisions are ordered
    mid: float                  # the market feature — the thing to beat
    truth: float                # P(outcome) under the generating process
    outcome: int                # realised 0/1
    #: A feature computed AFTER `t`. Present so a leakage check has something
    #: to catch; an honest model must never read it.
    late_mid: float = 0.0


class Model(Protocol):
    def fit(self, rows: Sequence[Row]) -> None: ...
    def predict(self, rows: Sequence[Row]) -> Sequence[float]: ...


# ------------------------------------------------------------------ #
# Synthetic slates
# ------------------------------------------------------------------ #


def make_slate(
    *, n_games: int = 60, per_game: int = 40, edge: float = 0.0,
    mid_is_truth: bool = True, seed: int = 7,
) -> list[Row]:
    """A slate with a KNOWN generating process.

    `edge` is the model-detectable signal the market does not have: the mid is
    set to `truth - edge`, so a model that recovers `truth` beats the market by
    exactly `edge` in probability units and by a computable amount in Brier.
    `edge=0` is the null — the market is already correct and there is nothing
    to find.
    """
    rng = random.Random(seed)
    rows: list[Row] = []
    for g in range(n_games):
        # Per-game level, so rows within a game are correlated — which is why
        # every statistic here clusters by game.
        level = rng.uniform(0.25, 0.75)
        for t in range(per_game):
            truth = min(max(level + rng.gauss(0, 0.05), 0.02), 0.98)
            mid = truth - edge if mid_is_truth else rng.uniform(0.2, 0.8)
            mid = min(max(mid, 0.01), 0.99)
            outcome = 1 if rng.random() < truth else 0
            rows.append(Row(game_id=f"g{g}", t=t, mid=mid, truth=truth,
                            outcome=outcome,
                            # the outcome leaks backwards through this field
                            late_mid=0.98 if outcome else 0.02))
    return rows


def split_by_game(rows: Sequence[Row], *, frac: float = 0.5,
                  seed: int = 11) -> tuple[list[Row], list[Row]]:
    """Hold out WHOLE GAMES. Splitting by row puts ~130 correlated rows from
    the same game on both sides and inflates any score."""
    games = sorted({r.game_id for r in rows})
    rng = random.Random(seed)
    rng.shuffle(games)
    cut = int(len(games) * frac)
    train_g = set(games[:cut])
    return ([r for r in rows if r.game_id in train_g],
            [r for r in rows if r.game_id not in train_g])


# ------------------------------------------------------------------ #
# Scoring — clustered by game, using the project's own estimator
# ------------------------------------------------------------------ #


def _brier_by_game(rows: Sequence[Row], preds: Sequence[float]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r, p in zip(rows, preds):
        out.setdefault(r.game_id, []).append((p - r.outcome) ** 2)
    return out


def skill_beyond_market(rows: Sequence[Row], preds: Sequence[float]):
    """market Brier - model Brier, clustered by game. Positive = model better.

    The sign is stated here once so every caller inherits it: POSITIVE MEANS
    THE MODEL BEAT THE MARKET. A sign convention that lives in three places
    has been wrong in two of them at least once in this repo.
    """
    model = _brier_by_game(rows, preds)
    market = _brier_by_game(rows, [r.mid for r in rows])
    diff = {g: [m - v for m, v in zip(market[g], model[g])] for g in model}
    return clustered_mean(diff)


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((x - mb) ** 2 for x in b) ** 0.5
    if va == 0 or vb == 0:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb)


# ------------------------------------------------------------------ #
# Reference and adversarial models — the harness's own controls
# ------------------------------------------------------------------ #


class MarketOnly:
    """Outputs the mid. Honest baseline: zero skill by construction."""

    def fit(self, rows): pass
    def predict(self, rows): return [r.mid for r in rows]


class Oracle:
    """Outputs the generating probability. Recovers any injected edge."""

    def fit(self, rows): pass
    def predict(self, rows): return [r.truth for r in rows]


class MidCopier:
    """★ THE FAILURE THIS HARNESS EXISTS FOR. Learns to echo its own market
    input with a whisper of noise, so it ties the market and looks like a
    careful honest model that found nothing."""

    def fit(self, rows): pass
    def predict(self, rows):
        rng = random.Random(3)
        return [min(max(r.mid + rng.gauss(0, 0.001), 0.01), 0.99) for r in rows]


class BaseRateModel:
    """Outputs the training base rate for every row. On a lopsided cohort this
    scores WELL — B's CFB slate is 89.3% home wins, where a constant 0.893
    beats most things — while carrying no per-game information at all."""

    def __init__(self): self._p = 0.5
    def fit(self, rows):
        self._p = sum(r.outcome for r in rows) / max(len(rows), 1)
    def predict(self, rows): return [self._p] * len(rows)


class NoisyBaseRate:
    """The prior with a wobble. Its output VARIES, so the degenerate check
    stays silent, and it still knows nothing per-game — which is what pins
    BASE_RATE on its own. Without it, BaseRateModel trips DEGENERATE and
    BASE_RATE together and neither is individually established."""

    def __init__(self): self._p = 0.5
    def fit(self, rows):
        self._p = sum(r.outcome for r in rows) / max(len(rows), 1)
    def predict(self, rows):
        rng = random.Random(9)
        return [min(max(self._p + rng.gauss(0, 0.02), 0.01), 0.99) for _ in rows]


class ConstantModel:
    """Silently dead: one number, forever, regardless of input."""

    def fit(self, rows): pass
    def predict(self, rows): return [0.5] * len(rows)


class NoiseModel:
    """Uncorrelated with the mid and carrying no signal. Recovers nothing, so
    it pins the INJECTED check WITHOUT tripping the echo check — which the
    market-shaped adversaries cannot do."""

    def fit(self, rows): pass
    def predict(self, rows):
        rng = random.Random(5)
        return [rng.uniform(0.3, 0.7) for _ in rows]


class SignFlipped:
    """Recovers the truth and reports it inverted."""

    def fit(self, rows): pass
    def predict(self, rows): return [1.0 - r.truth for r in rows]


class LeakyModel:
    """Reads a feature summarised AFTER the decision."""

    def fit(self, rows): pass
    def predict(self, rows): return [r.late_mid for r in rows]


# ------------------------------------------------------------------ #
# The checks
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class Failure:
    """A structured verdict. `code` is what tests assert on.

    Prose is for humans and is free to change; a test that matches a SUBSTRING
    of prose is a test that can be satisfied by a different check's wording.
    That happened here: the LEAKAGE message contained the word "NULL", so an
    assertion for the NULL check passed while NULL was disabled. Codes remove
    the whole class."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass
class Report:
    failures: list[Failure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def codes(self) -> set[str]:
        return {f.code for f in self.failures}


def run_all(model_cls) -> Report:
    """Every check, against one model class. Returns rather than asserts so a
    caller can report all failures at once."""
    rep = Report()

    # 1. NULL — the market is already right; there is nothing to find.
    rows = make_slate(edge=0.0)
    tr, te = split_by_game(rows)
    m = model_cls(); m.fit(tr)
    cm = skill_beyond_market(te, m.predict(te))
    rep.notes.append(f"null skill {cm.mean:+.5f} [{cm.lo:+.5f}, {cm.hi:+.5f}]")
    if cm.lo > 0:
        rep.failures.append(Failure("NULL",
            f"claims skill on data with none — {cm.mean:+.5f} "
            f"CI [{cm.lo:+.5f}, {cm.hi:+.5f}] excludes zero (WAVE_STANDARD r4)"))

    # 2. INJECTED EFFECT — a planted edge must come back.
    rows = make_slate(edge=INJECTED_EDGE)
    tr, te = split_by_game(rows)
    m = model_cls(); m.fit(tr)
    cm2 = skill_beyond_market(te, m.predict(te))
    rep.notes.append(f"injected skill {cm2.mean:+.5f}")
    if cm2.mean <= 0:
        rep.failures.append(Failure("INJECTED",
            f"planted a {INJECTED_EDGE:.2f} edge and recovered "
            f"{cm2.mean:+.5f} — a pipeline that cannot find a known effect "
            "cannot be trusted to report a real one"))

    # 3. SIGN — inverted predictions must score WORSE, not better.
    inverted = [1.0 - p for p in m.predict(te)]
    cm3 = skill_beyond_market(te, inverted)
    if cm3.mean >= cm2.mean:
        rep.failures.append(Failure("SIGN",
            f"inverting predictions did not reduce skill "
            f"({cm3.mean:+.5f} vs {cm2.mean:+.5f}) — the score cannot tell "
            "the direction, so it cannot tell a model from its mirror"))

    # 4. MID ECHO — the check specific to a market-as-feature model.
    preds = list(m.predict(te))
    corr = correlation(preds, [r.mid for r in te])
    rep.notes.append(f"corr(pred, mid) {corr:+.4f}")
    if corr >= MID_ECHO_CORR and cm2.lo <= 0:
        rep.failures.append(Failure("MID_ECHO",
            f"predictions correlate {corr:.4f} with the mid feature "
            f"and add no skill beyond it (CI [{cm2.lo:+.5f}, {cm2.hi:+.5f}]) — "
            "the model may be reproducing its own input"))

    # 5. DEGENERATE — a model whose output does not vary has learned nothing,
    #    and on a lopsided cohort it can still SCORE well. B's CFB slate is
    #    89.3% home wins, where a constant 0.893 beats a lot. No comparison
    #    against a market or a benchmark reveals this; only the spread of the
    #    predictions does.
    spread = max(preds) - min(preds)
    rep.notes.append(f"prediction spread {spread:.4f}")
    if spread < 0.01:
        rep.failures.append(Failure("DEGENERATE",
            f"predictions span {spread:.4f} — the model emits one number "
            "regardless of input. On a lopsided base rate this still scores "
            "well, so the score cannot tell you"))

    # 6. BASE RATE — beating the market is not the only bar. A model that
    #    cannot beat "always predict the training mean" has learned the prior
    #    and nothing else.
    br = BaseRateModel(); br.fit(tr)
    base = _brier_by_game(te, br.predict(te))
    mine = _brier_by_game(te, preds)
    vs_base = clustered_mean({g: [b - m for b, m in zip(base[g], mine[g])]
                              for g in mine})
    rep.notes.append(f"skill vs base rate {vs_base.mean:+.5f}")
    if vs_base.mean <= 0:
        rep.failures.append(Failure("BASE_RATE",
            f"scores {vs_base.mean:+.5f} against a training-mean predictor on "
            "data with a planted edge — it has learned the prior, not the game"))

    # 7. LEAKAGE, held out by game.
    rows = make_slate(edge=0.0)
    tr, te = split_by_game(rows)
    overlap = {r.game_id for r in tr} & {r.game_id for r in te}
    if overlap:
        rep.failures.append(Failure("SPLIT", f"{len(overlap)} games in both halves"))

    # 8. LEAKAGE, the late feature. A model reading it scores impossibly well.
    m = model_cls(); m.fit(tr)
    cm4 = skill_beyond_market(te, m.predict(te))
    if cm4.mean > 0.20:
        rep.failures.append(Failure("LEAKAGE",
            f"skill {cm4.mean:+.4f} on signal-free data is not attainable "
            "without reading the outcome — check for a feature summarised "
            "after the decision it informs"))
    return rep
