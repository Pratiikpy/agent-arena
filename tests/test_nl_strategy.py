"""A sandbox-validated strategy backtests, gets admitted only if it trades, and runs as an agent."""

from __future__ import annotations

import numpy as np
import pytest

from bitarena.agents.base import AgentObservation
from bitarena.agents.nl_strategy import NLStrategyAgent
from bitarena.domain.market import InstrumentType
from bitarena.strategy.backtest import admit, backtest
from bitarena.strategy.sandbox import StrategyError, compile_strategy

TREND_FOLLOW = """
def decide(obs):
    fast = sma(obs["prices"], 5)
    slow = sma(obs["prices"], 20)
    if fast > slow:
        return 1.0
    if fast < slow:
        return -1.0
    return 0.0
"""
FLAT = "def decide(obs):\n    return 0.0"


def _walk(n=140, seed=3):
    rng = np.random.default_rng(seed)
    return list(100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.02, n))))


def test_backtest_admits_a_trading_strategy():
    res = backtest(compile_strategy(TREND_FOLLOW), _walk())
    assert res["ok"] is True
    assert res["trades"] >= 2  # it crosses and re-crosses, so it actually trades
    assert admit(res) is True


def test_backtest_rejects_a_flat_strategy():
    res = backtest(compile_strategy(FLAT), _walk())
    assert res["ok"] is True and res["trades"] == 0
    assert admit(res) is False  # a strategy that never trades is not admissible


def test_strategy_runs_as_an_arena_agent():
    agent = NLStrategyAgent.from_code(TREND_FOLLOW, agent_id="nl-test")
    prices = [100.0 * (1.01 ** i) for i in range(30)]  # steady uptrend -> goes long
    intents = []
    for t, px in enumerate(prices):
        obs = AgentObservation(symbol="BTCUSDT", instrument=InstrumentType.PERP, ts=t,
                               equity_usd=10_000.0, position_qty=0.0, price=px, market=None)
        intents.append(agent.decide(obs))
    assert any(i is not None for i in intents)  # it eventually places an order


def test_from_code_rejects_unsafe_strategy():
    with pytest.raises(StrategyError):
        NLStrategyAgent.from_code("import os\ndef decide(obs):\n    return 0.0")


class _StubLLM:
    def __init__(self, responses):
        self._r = list(responses)

    def available(self):
        return True

    def chat(self, system, user, **k):
        return self._r.pop(0) if self._r else None


def test_generate_strips_fences_and_returns_valid_code():
    from bitarena.strategy.generate import generate_strategy
    fenced = "```python\ndef decide(obs):\n    return clip(roc(obs['prices'], 10), -1, 1)\n```"
    code = generate_strategy("momentum", llm=_StubLLM([fenced]))
    compile_strategy(code)  # validates and smoke-runs


def test_generate_retries_past_a_bad_attempt():
    from bitarena.strategy.generate import generate_strategy
    bad = "import os\ndef decide(obs):\n    return 0.0"
    good = "def decide(obs):\n    return clip(roc(obs['prices'], 10), -1, 1)"
    code = generate_strategy("x", llm=_StubLLM([bad, good]), max_tries=3)
    assert "decide" in code


def test_generate_without_a_model_raises():
    from bitarena.llm import QwenClient
    from bitarena.strategy.generate import generate_strategy
    with pytest.raises(StrategyError):
        generate_strategy("x", llm=QwenClient(None, "x", "m"))
