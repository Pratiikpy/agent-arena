"""Tests for the persona team and Q-learning competitors."""

from __future__ import annotations

from bitarena.agents import (
    AgentObservation,
    PersonaTeam,
    QLearningAgent,
    TradingAgent,
)
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side
from bitarena.perception.base import Signal


class _FixedSource:
    name = "fixed"

    def __init__(self, value: float, signal_name: str = "x") -> None:
        self._v = value
        self._name = signal_name

    def observe(self, symbol, market, ts, instrument=InstrumentType.SPOT):
        return [Signal(name=self._name, source="fixed", value=self._v, confidence=1.0)]


def _obs(seed=2, position_qty=0.0):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=150, seed=seed, drift=0.01, vol=0.004)})
    md.set_cursor(149)
    return AgentObservation(
        symbol="BTCUSDT", instrument=InstrumentType.PERP, ts=0,
        equity_usd=10_000.0, position_qty=position_qty, price=md.get_quote("BTCUSDT").mid, market=md,
    )


def test_agents_satisfy_protocol():
    assert isinstance(PersonaTeam(), TradingAgent)
    assert isinstance(QLearningAgent(), TradingAgent)


def test_persona_team_vetoes_on_disagreement():
    team = PersonaTeam(sources=[_FixedSource(0.8, "trend"), _FixedSource(-0.8, "sentiment")])
    intent = team.decide(_obs())
    assert team.last_bundle.agreement == 0.0
    assert team.last_votes["risk_mult"] == 0.0  # risk persona vetoes
    assert intent is None


def test_persona_team_goes_long_on_bull_alignment():
    team = PersonaTeam(sources=[_FixedSource(0.8, "trend"), _FixedSource(0.7, "momentum")])
    intent = team.decide(_obs())
    assert intent is not None and intent.side is Side.BUY


def test_qlearning_is_deterministic_given_seed():
    def run():
        md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=120, seed=5, drift=0.005, vol=0.01)})
        agent = QLearningAgent(seed=42)
        sides = []
        for _ in range(60):
            q = md.get_quote("BTCUSDT")
            obs = AgentObservation(
                symbol="BTCUSDT", instrument=InstrumentType.PERP, ts=q.ts,
                equity_usd=10_000.0, position_qty=0.0, price=q.mid, market=md,
            )
            intent = agent.decide(obs)
            sides.append(intent.side.value if intent else None)
            if not md.advance():
                break
        return sides, agent.states_seen

    a, sa = run()
    b, sb = run()
    assert a == b and sa == sb
    assert sa > 0  # it explored some states
