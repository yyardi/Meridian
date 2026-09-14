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


# ------------------------------------------------ polling through the end #
class _Board:
    """Scoreboard + summary in one fake, branching on the URL.

    `on_board` is separate from `states` on purpose: ESPN drops a game from
    the scoreboard's `in` list BEFORE the summary reports `post`, and that gap
    is the whole defect.
    """

    def __init__(self, states: dict, on_board: set | None = None,
                 scores: dict | None = None):
        self.states = states                       # game_id -> (state, clock)
        self.on_board = set(states) if on_board is None else set(on_board)
        self.polled: list[str] = []
        #: game_id -> (home, away). ESPN publishes a score and corrects it
        #: DOWNWARD after `post`, which is why the exit needs a confirming
        #: poll; a fake that cannot change its score cannot test that.
        self.scores = dict(scores or {})

    def _site(self, what: str) -> str:
        return f"https://example.invalid/{what}"

    def get(self, url, params=None):
        if "scoreboard" in url:
            return {"events": [
                {"id": g, "status": {"type": {"state": self.states[g][0]}}}
                for g in sorted(self.on_board)
            ]}
        gid = (params or {}).get("event")
        self.polled.append(gid)
        st, clk = self.states[gid]
        hs, as_ = self.scores.get(gid, (21, 17))
        return {
            "header": {"competitions": [{
                "status": {"type": {"state": st}, "period": 4,
                           "displayClock": clk},
                "competitors": [
                    {"homeAway": "home", "id": "1", "timeoutsUsed": 0,
                     "score": str(hs)},
                    {"homeAway": "away", "id": "2", "timeoutsUsed": 0,
                     "score": str(as_)},
                ]}]},
            "drives": {"current": {"team": {"id": "1"}, "plays": [
                {"id": f"p-{gid}-{st}-{clk}-{len(self.polled)}",
                 "period": {"number": 4}, "clock": {"displayValue": clk},
                 "start": {"team": {"id": "1"}, "down": 1, "distance": 10,
                           "yardsToEndzone": 50},
                 "homeScore": hs, "awayScore": as_}]}},
            "winprobability": [],
        }


def _rec(board, monkeypatch, now):
    """Recorder on a controllable clock. SCOREBOARD_INTERVAL is also measured
    on monotonic(), so driving it keeps the board refresh honest."""
    session = _Session()
    monkeypatch.setattr(rec.time, "monotonic", lambda: now[0])
    return rec.CfbLiveRecorder(board, lambda: session, league="cfb")


def test_a_game_at_in_with_a_zero_clock_is_still_polled(monkeypatch):
    """★ THE DEFECT. `refresh_live` collects only `state == "in"`, so a game
    that leaves the board is never polled again and its `post` transition is
    never observed — live state, no result, on roughly 59% of games.

    A ZERO CLOCK IS NOT A TERMINAL SIGNAL: games sit at `in` with 0:00 through
    reviews, between quarters and all of overtime, and display_clock reads
    "15:00" on a game already 21-0. So the exit is the state field, and this
    game — off the board, still `in`, clock expired — must keep being polled.
    """
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()                                    # live, on the board

    board.on_board.clear()                       # ESPN drops it from `in`
    board.states["401"] = ("in", "0:00")         # still not final
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    before = len(board.polled)
    out = r.cycle()

    assert len(board.polled) > before, (
        "a game off the board and still `in` was not polled — its post "
        "transition can never be observed")
    assert out["live"] == 0 and out["settling"] == 1


def test_a_single_post_does_not_retire_the_game(monkeypatch):
    """★ `post` IS COMPLETE BUT NOT STABLE. Measured 2026-09-14: 12 of 105 CFB
    post games carry a post score BELOW a score seen earlier in the game, and
    the score can still move AFTER the first `post` is observed — 2 of the 37
    games where that is observable, by up to 9 points on the total. (The 112
    of 114 that "agree" are mostly a row compared with itself: the median game
    has exactly ONE post row.)

    So one `post` is not the exit.
    """
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    board.states["401"] = ("post", "0:00")
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    out = r.cycle()

    assert "401" not in r._final, "retired on a single, unconfirmed post"
    assert "401" in r._post_pending
    assert out["settling"] == 1


def test_a_confirmed_post_retires_the_game(monkeypatch):
    """Two `post` observations SETTLE_CONFIRM_SECONDS apart with the same
    score, and then it costs nothing further."""
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    board.states["401"] = ("post", "0:00")
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    r.cycle()                                    # first post
    assert "401" not in r._final

    now[0] += rec.SETTLE_CONFIRM_SECONDS + 1
    r.cycle()                                    # confirming poll
    assert "401" in r._final, "a confirmed post did not retire the game"

    settled = len(board.polled)
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_CONFIRM_SECONDS * 10
    out = r.cycle()
    assert len(board.polled) == settled, "kept polling a game already final"
    assert out["settling"] == 0


def test_a_post_score_that_moves_restarts_the_confirmation(monkeypatch):
    """The correction is the point. ESPN publishes a score and corrects it
    DOWNWARD — in 9 of the 12 measured cases the maximum home score and the
    maximum away score never co-existed in any row, so the earlier value was
    never a real scoreline. A move restarts the window rather than failing it,
    and the CORRECTED score is what retires the game.
    """
    board = _Board({"401": ("in", "12:00")}, scores={"401": (31, 17)})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    board.states["401"] = ("post", "0:00")
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    r.cycle()                                    # post at 31-17

    board.scores["401"] = (24, 17)               # ESPN takes 7 points back
    now[0] += rec.SETTLE_CONFIRM_SECONDS + 1
    r.cycle()
    assert "401" not in r._final, "retired on a score that had just moved"
    assert r._post_pending["401"][1] == (24, 17)

    now[0] += rec.SETTLE_CONFIRM_SECONDS + 1
    r.cycle()
    assert "401" in r._final
    assert r._observed_score["401"] == (24, 17), "kept the pre-correction score"


def test_a_revert_to_in_before_confirmation_starts_over(monkeypatch):
    """ESPN reverts: one game went post -> in -> post with the `in` row 9.75
    hours after the first post. A revert before confirmation must clear the
    pending post, not confirm against it."""
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    board.states["401"] = ("post", "0:00")
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    r.cycle()
    assert "401" in r._post_pending

    board.states["401"] = ("in", "0:00")         # back under review
    now[0] += rec.SETTLE_CONFIRM_SECONDS + 1
    r.cycle()
    assert "401" not in r._post_pending, "confirmed against a reverted game"
    assert "401" not in r._final


def test_confirmation_costs_one_extra_poll_not_five(monkeypatch):
    """A game awaiting confirmation is due at SETTLE_CONFIRM_SECONDS, not at
    SETTLE_INTERVAL_SECONDS. At 60s settle and 300s confirm, polling at the
    settle cadence would cost five extra requests per game instead of one."""
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    board.states["401"] = ("post", "0:00")
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    r.cycle()                                    # first post
    after_first = len(board.polled)

    # Four settle intervals pass, short of the confirm interval: no poll.
    for _ in range(4):
        now[0] += rec.SETTLE_INTERVAL_SECONDS + 1
        r.cycle()
    assert len(board.polled) == after_first, (
        "polled at the settle cadence while awaiting confirmation")
    assert "401" not in r._final

    now[0] += rec.SETTLE_CONFIRM_SECONDS + 1
    r.cycle()
    assert len(board.polled) == after_first + 1, "more than one extra request"
    assert "401" in r._final


def test_a_game_that_never_posts_is_abandoned_loudly(monkeypatch):
    """Bounded give-up, clocked from DEPARTURE rather than kickoff. A silent
    give-up is what produced this defect, so the log names the game and how
    long it waited — asserted here as the game leaving the queue without ever
    being counted final."""
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()

    board.on_board.clear()
    now[0] += rec.SCOREBOARD_INTERVAL + rec.SETTLE_INTERVAL_SECONDS + 1
    assert r.cycle()["settling"] == 1             # departure observed here

    now[0] += rec.SETTLE_MAX_SECONDS + 1
    out = r.cycle()
    assert out["settling"] == 0
    assert "401" not in r._seen_live, "abandoned game still queued"
    assert "401" not in r._final, "abandoned is not final — it never posted"


def test_a_live_game_is_still_polled_every_cycle(monkeypatch):
    """The control. Three tests above are equally satisfied by a recorder that
    polls nothing; the settle cadence must not slow down a game in progress."""
    board = _Board({"401": ("in", "12:00")})
    now = [1000.0]
    r = _rec(board, monkeypatch, now)
    r.cycle()
    n1 = len(board.polled)
    now[0] += 1.0                                 # well under SETTLE_INTERVAL
    r.cycle()
    assert len(board.polled) == n1 + 1, "a live game was throttled"
