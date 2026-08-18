"""The per-market-type split, pinned.

The split's whole risk is that it makes an unvalidated number look validated.
Totals are the only market type ever backtested, and the only source of money
and CLV; spread and moneyline exist in the prediction log alone. So every test
here is about keeping those two facts visible rather than about arithmetic.

The second risk is quieter: prediction counts and money come from DIFFERENT
SAMPLES. ~50k live predictions sit in the same row as a few hundred backtested
bets, and a reader who takes n_preds as the ROI's sample size is out by two
orders of magnitude. Each block therefore carries its own n.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.analytics import CAPTION, _backtest_money, _brier, by_market_type

TYPES = ("total", "winner", "spread")
PHASES = ("pregame", "ingame")


# ------------------------------------------------------------------ #
# Fakes — the shape the producer consumes, not a live database
# ------------------------------------------------------------------ #


@dataclass
class _Bet:
    filled: bool = True
    #: 100 contracts a bet, so $100 staked over two bets is $0.50 a contract —
    #: a price a 0-1 market can actually quote. An earlier version of this
    #: fixture used 2.0 and implied $25 a contract, which no market could.
    contracts: float = 100.0


@dataclass
class _Metrics:
    n_bets: int = 100
    n_filled: int = 90
    n_wins: int = 48
    n_resolved: int = 90
    total_pnl: float = -5.0
    total_staked: float = 100.0
    total_fees: float = 1.25
    clv_points: list[float] = field(default_factory=lambda: [1.0, 2.0, 3.0])
    n_with_closing_line: int = 3

    @property
    def hit_rate(self):
        return self.n_wins / self.n_resolved

    @property
    def roi(self):
        return self.total_pnl / self.total_staked

    @property
    def mean_clv(self):
        return sum(self.clv_points) / len(self.clv_points)

    @property
    def clv_stderr(self):
        return 0.5


@dataclass
class _Result:
    metrics: _Metrics = field(default_factory=_Metrics)
    bets: list = field(default_factory=lambda: [_Bet(), _Bet()])


class _FakeSession:
    """Returns the two row shapes `_prediction_rows` asks for, in order."""

    def __init__(self, counts, resolved):
        self._queues = [counts, resolved]

    def execute(self, _stmt):
        payload = self._queues.pop(0)
        return _Rows(payload)


@dataclass
class _Rows:
    rows: list

    def all(self):
        return self.rows


def _session(counts=None, resolved=None):
    return _FakeSession(
        counts if counts is not None else [
            ("basketball_team_full_game_total", "pregame", 50481, 45841, 54),
            ("basketball_team_full_game_winner", "pregame", 11636, 10000, 60),
            ("basketball_team_full_game_spread", "ingame", 84, 84, 5),
        ],
        resolved if resolved is not None else [
            ("basketball_team_full_game_total", "pregame", 0.6, 0.5, 1),
            ("basketball_team_full_game_total", "pregame", 0.4, 0.5, 0),
        ],
    )


# ------------------------------------------------------------------ #
# Only totals are backtested, and only pregame
# ------------------------------------------------------------------ #


def test_money_and_clv_appear_on_exactly_one_row():
    """The backtest is totals-only AND pregame-only. Any other row carrying
    money would be presenting the totals result under another type's name."""
    block = by_market_type(_session(), _Result())
    carrying = [(r["type"], r["phase"]) for r in block["rows"] if r["money"]]
    assert carrying == [("total", "pregame")]
    assert [(r["type"], r["phase"]) for r in block["rows"] if r["clv"]] == carrying


def test_backtested_is_true_on_exactly_that_row():
    block = by_market_type(_session(), _Result())
    assert [(r["type"], r["phase"]) for r in block["rows"] if r["backtested"]] \
        == [("total", "pregame")]


def test_unbacktested_rows_say_so_in_their_note():
    block = by_market_type(_session(), _Result())
    for row in block["rows"]:
        if not row["backtested"]:
            assert "never backtested" in row["note"] or "pregame-only" in row["note"]


def test_the_backtested_row_warns_that_money_is_a_different_sample():
    """~50k predictions beside a few hundred bets. The row must say so."""
    block = by_market_type(_session(), _Result())
    row = next(r for r in block["rows"] if r["backtested"])
    assert "different" in row["note"] and "sample" in row["note"]
    # And each block carries its own n, so neither can be read off the other.
    assert row["money"]["n_bets"] != row["n_preds"]
    assert "n" in row["clv"]


# ------------------------------------------------------------------ #
# Shape stability — the renderer draws rows verbatim
# ------------------------------------------------------------------ #


def test_every_type_and_phase_is_emitted_even_at_zero():
    """Zero-bet rows are emitted, not omitted, so the table does not reshape
    between runs and an absence stays legible."""
    block = by_market_type(_session(counts=[], resolved=[]), _Result())
    assert [(r["type"], r["phase"]) for r in block["rows"]] == [
        (t, p) for t in TYPES for p in PHASES
    ]
    for row in block["rows"]:
        assert row["n_preds"] == 0 and row["n_games"] == 0


def test_every_row_has_the_full_key_set():
    expected = {"type", "phase", "n_preds", "n_resolved", "n_games",
                "brier_model", "brier_market", "clv", "money",
                "backtested", "note"}
    for row in by_market_type(_session(), _Result())["rows"]:
        assert set(row) == expected


def test_missing_metrics_are_null_never_zero():
    """A null means "no data"; 0.0 means "measured zero". Rendering them the
    same would present an unmeasured row as a break-even one."""
    block = by_market_type(_session(counts=[], resolved=[]), _Result())
    for row in block["rows"]:
        if not row["backtested"]:
            assert row["money"] is None and row["clv"] is None
            assert row["brier_model"] is None and row["brier_market"] is None


def test_an_unknown_market_type_does_not_become_a_row():
    """A new venue type must not silently land in the totals row."""
    block = by_market_type(
        _session(counts=[("basketball_team_first_half_total", "pregame", 9, 9, 2)],
                 resolved=[]),
        _Result())
    assert all(r["n_preds"] == 0 for r in block["rows"])


# ------------------------------------------------------------------ #
# The numbers themselves
# ------------------------------------------------------------------ #


def test_brier_is_mean_squared_error_and_lower_is_better():
    assert _brier([(1.0, 1), (0.0, 0)]) == 0.0          # perfect
    assert _brier([(0.0, 1), (1.0, 0)]) == 1.0          # exactly wrong
    assert _brier([(0.5, 1), (0.5, 0)]) == 0.25         # uninformative
    assert _brier([]) is None


def test_caption_states_the_brier_direction():
    """Lower-is-better is not obvious, and two Brier columns side by side are
    worse than useless without it — a reader could read the model beating the
    market off a row that says the opposite."""
    assert "LOWER IS BETTER" in CAPTION
    assert "backtested" in CAPTION and "entry cost" in CAPTION


def test_entry_cost_is_stake_weighted_per_contract():
    """The breakeven the win rate must beat (C11). $100 staked over 200
    contracts is $0.50 a contract, so a 53.3% win rate there is a thin profit
    — and the same win rate on 25c entries would be a large one. That is why
    the two numbers may never be shown apart."""
    money, _ = _backtest_money(_Result())
    assert money["entry_cost"] == 0.50        # 100.0 staked / (2 bets x 100)
    assert money["win_rate"] == 0.5333
    assert money["returned"] == 95.0          # staked + pnl


def test_no_money_block_when_nothing_filled():
    result = _Result(bets=[_Bet(filled=False)])
    money, clv = _backtest_money(result)
    assert money is None and clv is None
