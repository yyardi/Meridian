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

SYSTEM = """You are the decision model inside an automated trading harness for a Bitcoin "Up or Down" prediction market (Polymarket US; the same contract Kalshi lists as KXBTC15M). The window's length is in features.window.length_s: 900 for the 15-minute market, 3600 for the hourly one.

The contract: YES (Up) pays $1 if the simple average of CF Benchmarks' BRTI over the 60 seconds before the window closes is at least the strike, which is the same 60-second average before the window opened. Otherwise NO (Down) pays $1.

Your only job is to estimate p_up, the probability that YES pays. Trading strategies then compare your probability with the prices on the book: a side is bought only when your probability for it beats its ask plus the fee (about 2 cents near 50c) by a margin, or a bid is rested below your fair value. So a probability that merely repeats the market's mid never trades, and a confident number that is wrong loses money on both sides. You will be scored on calibration over many windows (Brier score beside the market's own mid): across all the times you say 0.62, YES should pay about 62% of the time. Deviate from the market only where you have a reason, and by as much as that reason is worth.

How to think about it:
- The decisive quantity is where the price sits relative to the strike, in units of volatility over the time left (price.distance_in_sigma_to_close; baselines.brownian_p_up is what a driftless random walk implies). The less time left, the more the current distance decides it.
- The market's own mid (baselines.market_p_up) is informed and has been hard to beat. baselines.fitted_p_up, when present, is a logistic model fitted on weeks of settled windows of this contract (market, distance, momentum, volatility). Say where and why you differ from both.
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


#: USD per 1M tokens (input, cached input, cache write, output), Standard tier,
#: short context, read from https://developers.openai.com/api/docs/pricing on
#: 2026-09-28. The API writes prompts to its cache on its own and reports them
#: as ``prompt_tokens_details.cache_write_tokens``, billed at the cache-write
#: rate instead of the input rate. gpt-6-astra's row was read in full ($12.50);
#: for the others the cache-write rate is ASSUMED to be 1.25x input, astra's
#: ratio. A price is a constant of a period: each call's cost is computed and
#: stored when it is made, so a later price change never rewrites the history.
PRICES_PER_M = {
    "gpt-6-astra": (10.00, 1.00, 12.50, 50.00),
    "gpt-6-sol": (2.00, 0.20, 2.50, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
    "gpt-5.6-sol": (4.00, 0.40, 5.00, 20.00),
    "gpt-5.6-luna": (0.20, 0.02, 0.25, 1.20),
    "gpt-5.5": (5.00, 0.50, 6.25, 30.00),
    "gpt-5.4-mini": (0.75, 0.075, 0.9375, 4.50),
    "gpt-5-mini": (0.25, 0.025, 0.3125, 2.00),
}


def cost_usd(model: str | None, usage: dict | None) -> float | None:
    """What one call cost, from the tokens the API reported; None for a model with no listed price."""
    price = PRICES_PER_M.get(model or "")
    if price is None:
        return None
    u = usage or {}
    details = u.get("prompt_tokens_details") or {}
    prompt = int(u.get("prompt_tokens") or 0)
    cached = int(details.get("cached_tokens") or 0)
    written = int(details.get("cache_write_tokens") or 0)
    out = int(u.get("completion_tokens") or 0)
    p_in, p_cached, p_write, p_out = price
    fresh = max(prompt - cached - written, 0)
    return (fresh * p_in + cached * p_cached + written * p_write + out * p_out) / 1_000_000


@dataclass
class ModelConfig:
    api_key: str | None
    model: str | None
    reasoning_effort: str | None = None
    timeout_s: float = 300.0
    base_url: str = "https://api.openai.com/v1"
    #: Hard ceiling on one answer's output (reasoning included). An answer that
    #: runs out is truncated JSON -> a recorded model_error, never a trade.
    max_output_tokens: int = 4000

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY") or None,
            model=os.environ.get("MERIDIAN_BTC15_MODEL") or None,
            reasoning_effort=os.environ.get("MERIDIAN_BTC15_REASONING_EFFORT") or None,
            timeout_s=float(os.environ.get("MERIDIAN_BTC15_TIMEOUT_S") or 300),
            base_url=(os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
            max_output_tokens=int(os.environ.get("MERIDIAN_BTC15_MAX_OUTPUT_TOKENS") or 4000),
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
        if self.cfg.max_output_tokens:
            body["max_completion_tokens"] = self.cfg.max_output_tokens
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

    def lesson(self, decision: dict, outcome: dict) -> tuple[str, dict]:
        prompt = {
            "your_call": decision, "outcome": outcome,
            "instruction": "Write the lesson you would want to read before the next window. Be specific about what you "
                           "over- or under-weighted. If the call was right for the right reason, say what to keep doing.",
        }
        obj, usage, _ = self._call(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(prompt)}],
            LESSON_SCHEMA, "btc15_lesson")
        return str(obj.get("lesson") or "")[:600], usage

    def list_models(self) -> list[str]:
        r = self._http.get(f"{self.cfg.base_url}/models", headers={"Authorization": f"Bearer {self.cfg.api_key}"})
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))
