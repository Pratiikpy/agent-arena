"""QLearningAgent — a lightweight online reinforcement-learning competitor.

A dependency-free tabular Q-learner: the state is (discretized net signal, position
sign), the actions are {flat, long, short}, and the reward is the change in equity
since its last action (which it reads from the observation each tick). It learns
online during a tournament. This is the always-available RL competitor; a heavier
FinRL/Stable-Baselines policy can be dropped in behind the optional ``[rl]`` extra
using the same TradingAgent interface.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..domain.market import InstrumentType
from ..perception.agent_hub import agent_hub_sources
from ..perception.base import PerceptionSource, aggregate
from ..perception.market_features import TechnicalPerception
from .base import AgentObservation, rebalance_to_target

# actions: 0 = flat, 1 = long, 2 = short
_ACTION_FRACTION = {0: 0.0, 1: 1.0, 2: -1.0}


class QLearningAgent:
    """Tabular epsilon-greedy Q-learning over a small discretized state space."""

    def __init__(
        self,
        agent_id: str = "rl-qlearn",
        *,
        sources: list[PerceptionSource] | None = None,
        brief_dir: Path | str | None = None,
        base_fraction: float = 0.5,
        alpha: float = 0.2,
        gamma: float = 0.9,
        epsilon: float = 0.1,
        seed: int = 0,
    ) -> None:
        self.agent_id = agent_id
        if sources is not None:
            self._sources = sources
        else:
            self._sources = [TechnicalPerception(), *agent_hub_sources(brief_dir)]
        self.base_fraction = base_fraction
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self._q: dict[tuple[int, int], np.ndarray] = {}
        self._rng = np.random.default_rng(seed)
        self._last_state: tuple[int, int] | None = None
        self._last_action: int | None = None
        self._last_equity: float | None = None

    @property
    def states_seen(self) -> int:
        return len(self._q)

    def state_dict(self) -> dict:
        """Serializable learning state (the Q-table) — persisted across live runs so the
        agent keeps learning rather than restarting each scheduled invocation."""
        return {f"{b},{p}": [float(x) for x in row] for (b, p), row in self._q.items()}

    def load_state_dict(self, data: dict | None) -> None:
        self._q = {}
        for key, row in (data or {}).items():
            try:
                b, p = str(key).split(",")
                self._q[(int(b), int(p))] = np.array(row, dtype=float)
            except (ValueError, TypeError):
                continue

    def _q_row(self, state: tuple[int, int]) -> np.ndarray:
        if state not in self._q:
            self._q[state] = np.zeros(3, dtype=float)
        return self._q[state]

    @staticmethod
    def _state(net_signal: float, position_qty: float, price: float) -> tuple[int, int]:
        bucket = int(np.clip((net_signal + 1.0) / 2.0 * 4.0, 0, 4))
        notional = position_qty * price
        pos = 1 if notional > 1.0 else (-1 if notional < -1.0 else 0)
        return (bucket, pos)

    def _choose(self, state: tuple[int, int]) -> int:
        if self._rng.random() < self.epsilon:
            return int(self._rng.integers(0, 3))
        return int(np.argmax(self._q_row(state)))

    def decide(self, obs: AgentObservation):
        bundle = aggregate(obs.symbol, obs.ts, self._sources, obs.market, obs.instrument)
        state = self._state(bundle.net_signal, obs.position_qty, obs.price)

        # learn from the outcome of the previous action
        if self._last_state is not None and self._last_action is not None and self._last_equity is not None:
            reward = obs.equity_usd - self._last_equity
            row = self._q_row(self._last_state)
            best_next = float(np.max(self._q_row(state)))
            row[self._last_action] += self.alpha * (reward + self.gamma * best_next - row[self._last_action])

        action = self._choose(state)
        self._last_state = state
        self._last_action = action
        self._last_equity = obs.equity_usd

        allow_short = obs.instrument is InstrumentType.PERP
        fraction = _ACTION_FRACTION[action]
        if not allow_short and fraction < 0:
            fraction = 0.0
        target = fraction * self.base_fraction * obs.equity_usd
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"q-learn action={action} state={state}",
        )
