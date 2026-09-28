"""The OpenAI decision: one structured call per window, one short lesson per settlement.

The model returns a probability, not a trade. The harness turns it into a side
deterministically (YES if p_up >= 0.5, else NO) and buys one contract of that
side at the ask; the model never sizes, never times, never cancels. Output is
schema-constrained JSON; anything else -- a refusal, a malformed answer, a
p_up outside [0, 1], a timeout -- is recorded and means no trade.

What makes it learn is the ``experience`` block the ledger builds each call:
its own record (hit rate, Brier against the market's mid and a random walk,
P&L, drawdown), its last twenty calls with outcomes, and the lessons it wrote
after each settlement.

Configuration (environment): OPENAI_API_KEY, MERIDIAN_BTC15_MODEL (required
to decide; without them the harness records features and outcomes only),
MERIDIAN_BTC15_REASONING_EFFORT (optional, for reasoning models),
MERIDIAN_BTC15_TIMEOUT_S (default 300), OPENAI_BASE_URL (default api.openai.com).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx

SYSTEM = """You are the decision model inside an automated trading harness for Kalshi's 15-minute Bitcoin market (series KXBTC15M).

The contract: YES pays $1 if the simple average of CF Benchmarks' BRTI over the 60 seconds before the window closes is at least the strike, which is the same 60-second average before the window opened. Otherwise NO pays $1.

Your only job is to estimate p_up, the probability that YES pays. The harness then buys exactly one contract of the side you favour (YES if p_up >= 0.5, otherwise NO) at the current ask, holds it to settlement and pays the venue's fee. You do not size, time or cancel anything. You will be scored on calibration and accuracy over many windows: across all the times you say 0.62, YES should pay about 62% of the time.

How to think about it:
- The decisive quantity is where the price sits relative to the strike, in units of volatility over the time left (price.distance_in_sigma_to_close; baselines.brownian_p_up is what a driftless random walk implies). The less time left, the more the current distance decides it.
- The market's own mid (baselines.market_p_up) is informed. Say where and why you differ from it.
- Momentum and mean reversion on 1m, 5m and 1h timeframes, volatility regime, volume, funding and the recent run of window results are evidence, not rules.
- Read your record and your own lessons. If you have been systematically wrong in a direction or a regime, correct for it.

Return only the JSON object the schema asks for."""

DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "p_up": {"type": "number", "description": "probability that YES pays, between 0 and 1"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "key_factors": {"type": "array", "items": {"type": "string"}, "description": "at most five, most important first"},
        "rationale": {"type": "string", "description": "two or three sentences"},
    },
    "required": ["p_up", "confidence", "key_factors", "rationale"],
}

LESSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"lesson": {"type": "string", "description": "one or two sentences you would want to read before the next window"}},
    "required": ["lesson"],
}


class ModelError(RuntimeError):
    pass


@dataclass
class ModelConfig:
    api_key: str | None
    model: str | None
    reasoning_effort: str | None = None
    timeout_s: float = 300.0
    base_url: str = "https://api.openai.com/v1"

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY") or None,
            model=os.environ.get("MERIDIAN_BTC15_MODEL") or None,
            reasoning_effort=os.environ.get("MERIDIAN_BTC15_REASONING_EFFORT") or None,
            timeout_s=float(os.environ.get("MERIDIAN_BTC15_TIMEOUT_S") or 300),
            base_url=(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        )

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.model)


def side_of(p_up: float) -> str:
    """Deterministic: the model states a probability, the harness picks the side."""
    return "YES" if p_up >= 0.5 else "NO"


def validate(obj: dict) -> dict:
    p = obj.get("p_up")
    if not isinstance(p, (int, float)) or not (0.0 <= float(p) <= 1.0):
        raise ModelError(f"p_up must be a number in [0, 1], got {p!r}")
    if obj.get("confidence") not in ("low", "medium", "high"):
        raise ModelError(f"confidence {obj.get('confidence')!r}")
    return {"p_up": float(p), "confidence": obj["confidence"],
            "key_factors": [str(x)[:200] for x in (obj.get("key_factors") or [])][:5],
            "rationale": str(obj.get("rationale") or "")[:1200]}


class OpenAIModel:
    def __init__(self, cfg: ModelConfig, client: httpx.Client | None = None) -> None:
        self.cfg = cfg
        self._http = client or httpx.Client(timeout=cfg.timeout_s)

    def _call(self, messages: list[dict], schema: dict, name: str) -> tuple[dict, dict, float]:
        body = {
            "model": self.cfg.model,
            "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        }
        if self.cfg.reasoning_effort:
            body["reasoning_effort"] = self.cfg.reasoning_effort
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"}
        last: Exception | None = None
        for attempt in range(2):                      # one retry, transient failures only
            t0 = time.monotonic()
            try:
                r = self._http.post(f"{self.cfg.base_url}/chat/completions", json=body, headers=headers,
                                    timeout=self.cfg.timeout_s)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                continue
            took = time.monotonic() - t0
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                last = ModelError(f"HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(3)
                continue
            if r.status_code != 200:
                raise ModelError(f"HTTP {r.status_code}: {r.text[:500]}")
            d = r.json()
            msg = (d.get("choices") or [{}])[0].get("message") or {}
            if msg.get("refusal"):
                raise ModelError(f"refusal: {msg['refusal'][:300]}")
            try:
                obj = json.loads(msg.get("content") or "")
            except json.JSONDecodeError as e:
                raise ModelError(f"not JSON: {(msg.get('content') or '')[:300]}") from e
            return obj, d.get("usage") or {}, took
        raise ModelError(f"no answer after retry: {last}")

    def decide(self, features: dict, experience: dict) -> tuple[dict, dict, float]:
        user = {"features": features, "experience": experience}
        obj, usage, took = self._call(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(user)}],
            DECISION_SCHEMA, "btc15_decision")
        return validate(obj), usage, took

    def lesson(self, decision: dict, outcome: dict) -> str:
        prompt = {
            "your_call": decision, "outcome": outcome,
            "instruction": "Write the lesson you would want to read before the next window. Be specific about what you "
                           "over- or under-weighted. If the call was right for the right reason, say what to keep doing.",
        }
        obj, _, _ = self._call(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(prompt)}],
            LESSON_SCHEMA, "btc15_lesson")
        return str(obj.get("lesson") or "")[:600]

    def list_models(self) -> list[str]:
        r = self._http.get(f"{self.cfg.base_url}/models", headers={"Authorization": f"Bearer {self.cfg.api_key}"})
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))
