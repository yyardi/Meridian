"""The shadow executor does everything but send, and cannot send."""
from __future__ import annotations

import importlib
import json
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
    assert "sample(c, slugs, a.prefix)" in loop.split("gate(locked")[0], "sampling happens before the gate"
    assert '"ladder_lock"' in SRC
