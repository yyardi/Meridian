"""The shadow executor does everything but send, and cannot send."""
from __future__ import annotations

import datetime as dt
import importlib
import json

import pytest
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
EX = importlib.import_module("cfb.run_ladder_executor")
SRC = pathlib.Path(EX.__file__).read_text(encoding="utf-8")
from core.ladder.scan import Violation  # noqa: E402


def test_no_order_path_exists():
    for bad in ("place_order", "submit_order", "create_order", "MERIDIAN_ORDER_TOKEN",
                "requests.post", "httpx", "/orders"):
        assert bad not in SRC
    assert '"meridian_placed": False' in SRC


def test_intent_is_one_contract_at_one_dollar_and_never_exceeds_displayed_size():
    v = Violation("g", -2.5, 0.0, 0.2200, 0.2650, 0.0230, 8215)
    it = EX.intent_for(v, "g", "00:26:20", 1.0)
    assert it["leg1"]["qty"] == 1 and it["leg2"]["qty"] == 1
    assert it["leg1"]["side"] == "BUY YES" and it["leg2"]["side"] == "BUY NO"
    assert abs(it["leg2"]["price"] - 0.735) < 1e-9
    assert abs(it["cost_usd"] - 0.955) < 1e-6
    assert it["guaranteed_usd"] > 0 and it["expected_net_usd"] > 0
    tiny = Violation("g", -2.5, 0.0, 0.2200, 0.2650, 0.0230, 3)
    assert EX.intent_for(tiny, "g", "t", 50.0)["leg1"]["qty"] == 3, "never more than the smaller side"


def test_budget_is_persisted_and_survives_restart(tmp_path):
    p = tmp_path / "i.jsonl"
    assert EX.spent_so_far(str(p)) == 0.0
    p.write_text(json.dumps({"cost_usd": 0.955}) + "\n" + json.dumps({"cost_usd": 0.9}) + "\nnot json\n")
    assert abs(EX.spent_so_far(str(p)) - 1.855) < 1e-9


def test_mid_ladder_is_preferred_and_liquid_pairs_are_not_mid():
    assert EX.is_mid(Violation("g", 10.5, 13.5, 0.5, 0.6, 0.05, 1000))
    assert not EX.is_mid(Violation("g", -2.5, 0.0, 0.22, 0.265, 0.023, 8215))


def test_push_never_prints_and_reads_topic_from_env_only():
    body = SRC[SRC.index("def push("):SRC.index("def main(")]
    assert "MERIDIAN_NTFY_TOPIC" in body and "print(" not in body


def test_operator_lock_gates_issuance_but_not_sampling():
    cands = ["a", "b"]
    assert EX.gate(False, cands) == cands
    assert EX.gate(True, cands) == []
    loop = SRC[SRC.index("while time.time() < end"):]
    assert "os.path.exists(lock)" in loop and "gate(locked, cands)" in loop, "lock is re-read every cycle"
    assert "sample(c, slugs, a.prefix" in loop.split("gate(locked")[0], "sampling happens before the gate"
    assert '"ladder_lock"' in SRC


def test_winner_market_pairs_are_never_candidates():
    assert EX.is_spread_pair(Violation("g", 10.5, 13.5, 0.5, 0.6, 0.05, 1000))
    assert not EX.is_spread_pair(Violation("g", -2.5, 0.0, 0.22, 0.265, 0.023, 8215)), "winner leg excluded"
    loop = SRC[SRC.index("while time.time() < end"):]
    assert "is_spread_pair(x)" in loop.split("gate(locked")[0]


def test_the_executor_samples_through_the_core_module_and_reexports_book_age():
    """cfb/run_ws_freshness.py imports book_age_s from here and the dashboard
    imports it from core.ladder.live; they must be the same function."""
    live = importlib.import_module("core.ladder.live")
    assert EX.book_age_s is live.book_age_s and EX.sample is live.sample and EX.slugs_for is live.slugs_for
    for bad in ("place_order", "submit_order", "create_order", "MERIDIAN_ORDER_TOKEN",
                "requests.post", "httpx", "/orders", "PolymarketOrderClient"):
        assert bad not in pathlib.Path(live.__file__).read_text(encoding="utf-8")


def test_book_age_parses_nanosecond_stamps_and_rides_on_the_ticket():
    now = 1_800_000_000.0
    stamp = dt.datetime.fromtimestamp(now - 412.25, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + ".000000000Z"
    assert abs(EX.book_age_s(stamp, now) - 412.0) < 1.0 or abs(EX.book_age_s(stamp, now) - 413.0) < 1.0
    assert EX.book_age_s(None, now) is None and EX.book_age_s("garbage", now) is None
    assert "leg1_book_age_s" in SRC and "leg2_book_age_s" in SRC
    body = SRC[SRC.index("def push("):SRC.index("def main(")]
    assert "leg1_book_age_s" in body, "the phone message says how stale each book is"


def test_intent_and_push_speak_the_screen_language():
    v = Violation("cfb-mia-wake-2026-09-18", 7.5, 10.5, 0.41, 0.47, 0.05, 966)
    it = EX.intent_for(v, "cfb-mia-wake-2026-09-18", "23:41:07", 1.0)
    assert it["leg1"]["screen_row"] == "WAKE to win by over 10.5 points" and it["leg1"]["screen_button"] == "No"
    assert it["leg2"]["screen_row"] == "WAKE to win by over 7.5 points" and it["leg2"]["screen_button"] == "Yes"
    body = SRC[SRC.index("def push("):SRC.index("def main(")]
    assert "screen_row" in body and "screen_button" in body, "the phone message names the row and the button"


def test_over_cap_tickets_are_written_but_never_charged_to_the_budget(tmp_path):
    """The cap limits PLACING, not detection: past it the executor keeps
    ticketing so the operator sees what went by. Those rows must not be
    charged, or a restart re-reads them as spend and the game goes silent."""
    p = tmp_path / "i.jsonl"
    p.write_text("\n".join([
        json.dumps({"cost_usd": 0.96}),
        json.dumps({"cost_usd": 0.96}),
        json.dumps({"cost_usd": 0.95, "over_budget": True}),
        json.dumps({"cost_usd": 0.97, "over_budget": True}),
    ]) + "\n")
    assert EX.spent_so_far(str(p)) == pytest.approx(1.92), "only the charged ones"
    src = SRC[SRC.index("while time.time() < end"):]
    assert 'it["over_budget"] = over' in src, "every ticket says which it is"
    gate = src[src.index("if not (over or a.quiet)"):src.index("push(it)")]
    assert "over" in gate and "a.quiet" in gate and "pushed.get(key" in gate, \
        "an over-cap ticket is not pushed, and --quiet silences the rest"


def test_the_phone_has_its_own_floor_and_it_reads_the_same_number_as_the_page():
    """Two floors, two questions. --floor-usd asks whether a pair is worth the
    desk showing; --push-floor-usd asks whether it is worth waking someone.
    Collapsing them is what makes a phone useless: on 2026-09-18, three games
    put 93 episodes over $25 and only 13 over $500.

    The floor must be measured in the SAME expression the ladder page ranks
    by, or a number read off /log means something else here. Both scan with
    max_size=1e12, and the push gate reads `x.dollars` -- the Violation field
    /log's best_dollars comes from -- not a recomputed cost."""
    src = SRC[SRC.index("def main("):]
    assert '"--push-floor-usd", type=float, default=0.0' in src, \
        "default 0 pushes every ticket: the floor is opt-in, not a silent mute"
    loop = SRC[SRC.index("while time.time() < end"):]
    assert "loud = x.dollars >= a.push_floor_usd" in loop
    assert "and loud" in loop, "the floor is ANDed into the push gate, not into ticketing"
    assert "max_size=1e12" in loop, "the same size cap /log's scan uses"
    write = loop[:loop.index("loud =")]
    assert "push_floor_usd" not in write, \
        "the floor must not touch the write: a ticket below it still reaches the desk"


def test_the_phone_is_deduped_per_pair_but_the_ticket_is_not():
    """Writing and pushing answer different questions. Every qualifying pair is
    ticketed every cycle so the ladder shows what went past; the phone is
    deduped, because one pair crossing for twenty minutes is one opportunity
    and sixty identical alerts make the phone useless when it matters."""
    src = SRC[SRC.index("def main("):]
    assert '"--cooldown", type=float, default=0.0' in src, "no ticket cooldown by default"
    assert '"--push-cooldown", type=float, default=5.0' in src, "the phone is deduped"
    assert 'default=float("inf")' in src, "no cap by default"
    loop = SRC[SRC.index("while time.time() < end"):]
    assert "pushed[key] = time.time()" in loop and "a.push_cooldown * 60" in loop
