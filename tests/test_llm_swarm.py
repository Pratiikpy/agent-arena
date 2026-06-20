"""Tests for the LLM debate swarm: fallback behavior and JSON parsing."""

from __future__ import annotations

from bitarena.agents import AgentObservation, LLMDebateSwarm
from bitarena.agents.llm_swarm import _extract_json
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side
from bitarena.perception.base import Signal


class _FakeLLM:
    """A QwenClient stand-in that returns a fixed completion."""

    def __init__(self, content: str | None, available: bool = True) -> None:
        self._content = content
        self._available = available

    def available(self) -> bool:
        return self._available

    def chat(self, system, user, **kwargs):
        return self._content


class _FixedSource:
    """A perception source emitting one fixed signal — makes the deterministic path predictable."""

    name = "fixed"

    def __init__(self, value: float) -> None:
        self._v = value

    def observe(self, symbol, market, ts, instrument=InstrumentType.SPOT):
        return [Signal(name="x", source="fixed", value=self._v, confidence=1.0)]


def _obs():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=120, seed=2)})
    md.set_cursor(119)
    return AgentObservation(
        symbol="BTCUSDT", instrument=InstrumentType.PERP, ts=0,
        equity_usd=10_000.0, position_qty=0.0, price=md.get_quote("BTCUSDT").mid, market=md,
    )


def test_extract_json_handles_noise():
    assert _extract_json('sure: {"stance":"long","conviction":0.8} ok')["stance"] == "long"
    assert _extract_json("no json here") is None


def test_llm_unavailable_falls_back_to_deterministic():
    agent = LLMDebateSwarm(llm=_FakeLLM(None, available=False), sources=[_FixedSource(0.8), _FixedSource(0.7)])
    intent = agent.decide(_obs())
    assert agent.last_source == "deterministic"
    assert intent is not None and intent.side is Side.BUY  # aligned bullish signals


def test_llm_long_decision_used():
    agent = LLMDebateSwarm(
        llm=_FakeLLM('{"stance":"long","conviction":0.9,"reason":"trend + aligned"}'),
        sources=[_FixedSource(0.0)],  # neutral deterministic; LLM should drive
        decide_every=1,
    )
    intent = agent.decide(_obs())
    assert agent.last_source == "qwen"
    assert intent is not None and intent.side is Side.BUY


def test_llm_flat_decision_holds():
    agent = LLMDebateSwarm(
        llm=_FakeLLM('{"stance":"flat","conviction":0.0,"reason":"too much disagreement"}'),
        sources=[_FixedSource(0.8)],  # bullish, but LLM vetoes to flat
        decide_every=1,
    )
    intent = agent.decide(_obs())
    assert agent.last_source == "qwen"
    assert intent is None


def test_qwen_client_is_offline_safe_without_key():
    # the "whole system runs offline" guarantee: no key -> unavailable, chat never raises
    from bitarena.llm import QwenClient

    c = QwenClient(None, "https://example.invalid/v1", "qwen-test")
    assert c.available() is False
    assert c.chat("system", "user") is None


def test_llm_garbage_falls_back_to_deterministic():
    agent = LLMDebateSwarm(
        llm=_FakeLLM("the market looks interesting today"),
        sources=[_FixedSource(0.8), _FixedSource(0.7)],
        decide_every=1,
    )
    intent = agent.decide(_obs())
    assert agent.last_source == "deterministic"  # unparseable -> deterministic this tick
    assert intent is not None and intent.side is Side.BUY
