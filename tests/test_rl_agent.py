"""Tests for the QLearningAgent: state persistence robustness and spot short-suppression."""

from __future__ import annotations

import numpy as np

from bitarena.agents.base import AgentObservation
from bitarena.agents.rl import QLearningAgent
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType
from bitarena.perception.base import Signal


class _FixedSrc:
    name = "fixed"

    def __init__(self, v: float) -> None:
        self._v = v

    def observe(self, symbol, market, ts, instrument=InstrumentType.SPOT):
        return [Signal(name="x", source="fixed", value=self._v, confidence=1.0)]


def test_load_state_dict_skips_malformed_entries():
    a = QLearningAgent()
    a.load_state_dict({"2,1": [0.1, 0.2, 0.3], "bad-key": [1, 2, 3], "3": [0.0]})
    assert a.states_seen == 1  # only the well-formed "bucket,pos" key survives
    assert a._q[(2, 1)].tolist() == [0.1, 0.2, 0.3]


def test_spot_action_suppresses_short_to_flat():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=30, seed=1)})
    md.set_cursor(29)
    price = md.get_quote("BTCUSDT").mid
    obs = AgentObservation(
        symbol="BTCUSDT", instrument=InstrumentType.SPOT, ts=0,
        equity_usd=10_000.0, position_qty=0.0, price=price, market=md,
    )
    agent = QLearningAgent(sources=[_FixedSrc(0.5)], epsilon=0.0)  # injected-sources path, greedy
    state = QLearningAgent._state(0.5, 0.0, price)
    agent._q[state] = np.array([0.0, 0.0, 1.0])  # make "short" the greedy action
    # on SPOT the short action is forced flat -> no position change -> no order
    assert agent.decide(obs) is None
