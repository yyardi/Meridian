"""poll_game must not let a state-parse failure cost the plays.

There was no test for `poll_game` at all, which is how this landed. The
hardening commit changed `parse_game_state` to raise instead of returning
None -- a good contract for a parser -- but the raise escapes `poll_game`,
and `cycle` catches it per game. So a payload carrying drives and
winprobability but no `header.competitions` now records NOTHING, where
before it recorded every play and skipped only the state row.

The three payload keys are independent: `parse_plays` reads `drives`,
`parse_win_probability` reads `winprobability`, and only `parse_game_state`
reads `header`. `parse_plays` takes `home`/`away` as `str | None` and
branches on None throughout -- the None case is designed for, not an
accident, and the `if state else None` fallbacks in poll_game are its
callers.

Why the regression is invisible to the cycle's own instruments: state_rows
is 0 either way (that was the argument for the change), and plays_attempted
is a SUM over live games, so one game contributing 0 instead of N is a dip,
not a signal. Nothing in the log line names the game that vanished.
"""
import pytest

from core.feeds import espn_cfb_recorder as rec


class _Session:
    """Enough session to satisfy _write and the state add; no database."""

    def __init__(self) -> None:
        self.executed: list = []
        self.added: list = []
        self.commits = 0

    def execute(self, stmt) -> None:
        self.executed.append(stmt)

    def add(self, obj) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Client:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def _site(self, what: str) -> str:
        return f"https://example.invalid/{what}"

    def get(self, url, params=None) -> dict:
        return self._payload


def _headerless_payload() -> dict:
    """Drives and win probability present; `header` absent entirely."""
    return {
        "drives": {
            "current": {
                "team": {"id": "1"},
                "plays": [
                    {"id": "p1", "period": {"number": 1},
                     "clock": {"displayValue": "10:00"},
                     "start": {"team": {"id": "1"}, "down": 1,
                               "distance": 10, "yardsToEndzone": 75},
                     "homeScore": 0, "awayScore": 0},
                    {"id": "p2", "period": {"number": 1},
                     "clock": {"displayValue": "9:12"},
                     "start": {"team": {"id": "1"}, "down": 2,
                               "distance": 6, "yardsToEndzone": 71},
                     "homeScore": 0, "awayScore": 0},
                ],
            }
        },
        "winprobability": [
            {"playId": "p1", "homeWinPercentage": 0.51},
            {"playId": "p2", "homeWinPercentage": 0.53},
        ],
    }


def _recorder(payload: dict) -> tuple[rec.CfbLiveRecorder, _Session]:
    session = _Session()
    r = rec.CfbLiveRecorder(_Client(payload), lambda: session, league="cfb")
    return r, session


# ------------------------------------------------------------------ the bug #
def test_a_missing_header_does_not_discard_the_plays():
    """THE REGRESSION. Plays and WP are recoverable without the header."""
    r, session = _recorder(_headerless_payload())

    n_plays, n_wp, n_state = r.poll_game("401")

    assert n_plays == 2, "the two drives plays must still be written"
    assert n_wp == 2, "win probability does not read the header at all"
    assert n_state == 0, "no header means no state row -- that part is correct"


def test_the_cycle_still_counts_the_plays_of_a_headerless_game():
    """poll_game returning is not enough: cycle must not swallow it.

    Asserted at the level the alarm reads -- plays_attempted -- because that
    is the number a human or a rule would look at, not poll_game's return.
    """
    r, _ = _recorder(_headerless_payload())
    r._live = {"401"}
    r._last_board = float("inf")  # skip the scoreboard call entirely

    out = r.cycle()

    assert out["plays"] == 2, "the cycle dropped a game it successfully parsed"
    assert out["wp"] == 2
    assert out["state"] == 0


# ------------------------------------------------ the contract it must keep #
def test_parse_game_state_still_raises_on_a_headerless_payload():
    """The fix must not revert the hardening: the parser still names a cause.

    Without this, 'fixing' the regression by restoring `return None` would
    pass the tests above and silently undo the diagnosis the commit added.
    """
    with pytest.raises(ValueError, match="header.competitions"):
        rec.parse_game_state(_headerless_payload(), "401")


def test_a_normal_payload_still_writes_its_state_row():
    """Control: the ordinary path is unchanged."""
    payload = _headerless_payload()
    payload["header"] = {"competitions": [{
        "status": {"type": {"state": "in"}, "period": 1,
                   "displayClock": "10:00"},
        "competitors": [
            {"homeAway": "home", "id": "1", "timeoutsUsed": 0, "score": "7"},
            {"homeAway": "away", "id": "2", "timeoutsUsed": 1, "score": "3"},
        ],
    }]}
    r, session = _recorder(payload)

    n_plays, n_wp, n_state = r.poll_game("401")

    assert (n_plays, n_wp, n_state) == (2, 2, 1)
    assert len(session.added) == 1, "the state row is the one session.add"
