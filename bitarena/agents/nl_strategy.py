"""NLStrategyAgent: a validated, model-generated ``decide(obs) -> float`` running as a real
competitor in the arena, gated by the firewall like every other agent.

The wrapper keeps its own rolling price buffer (so it needs nothing from the market internals),
hands the strategy a plain dict of numbers, clips the returned exposure to [-1, 1], and converts
it into a firewall-gated order. The strategy is compiled through the sandbox before it ever runs.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from ..domain.market import InstrumentType
from ..strategy.sandbox import compile_strategy
from .base import AgentObservation, rebalance_to_target


class NLStrategyAgent:
    """Wraps a sandbox-validated strategy function as an arena agent."""

    def __init__(
        self,
        decide_fn,
        *,
        agent_id: str = "nl-strategy",
        description: str = "",
        base_fraction: float = 0.7,
        entry_threshold: float = 0.1,
        lookback: int = 240,
    ) -> None:
        self.agent_id = agent_id
        self.description = description  # the English brief this strategy came from
        self._fn = decide_fn
        self.base_fraction = base_fraction
        self.entry_threshold = entry_threshold
        self._prices: deque[float] = deque(maxlen=lookback)

    @classmethod
    def from_code(cls, code: str, **kwargs) -> "NLStrategyAgent":
        """Compile ``code`` through the sandbox (raises StrategyError if unsafe), then wrap it."""
        return cls(compile_strategy(code), **kwargs)

    def decide(self, obs: AgentObservation):
        self._prices.append(float(obs.price))
        payload = {
            "price": float(obs.price),
            "prices": list(self._prices),
            "position": float(obs.position_qty),
            "equity": float(obs.equity_usd),
        }
        try:
            sig = float(self._fn(payload))
        except Exception:  # a strategy that throws at runtime simply holds (never crashes the arena)
            return None
        if not np.isfinite(sig):
            return None
        sig = float(np.clip(sig, -1.0, 1.0))

        allow_short = obs.instrument is InstrumentType.PERP
        target = 0.0 if abs(sig) < self.entry_threshold else sig * self.base_fraction * obs.equity_usd
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"[nl-strategy] {self.description}"[:140],
        )
