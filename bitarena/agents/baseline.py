"""Baseline competitors: a naive single-signal momentum bot and a buy-and-hold benchmark.

These are the controls. The momentum bot acts on one signal and ignores conflict,
so it overtrades in chop — the foil the conflict-gated swarm is meant to beat on
risk-adjusted terms.
"""

from __future__ import annotations

import numpy as np

from ..domain.market import InstrumentType
from ..perception.market_features import TechnicalPerception
from .base import AgentObservation, rebalance_to_target


class MomentumBaseline:
    """Single-signal trend follower (the control)."""

    def __init__(
        self,
        agent_id: str = "baseline-momentum",
        *,
        target_fraction: float = 0.5,
        threshold: float = 0.15,
        technical: TechnicalPerception | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.target_fraction = target_fraction
        self.threshold = threshold
        self._tech = technical or TechnicalPerception()

    def decide(self, obs: AgentObservation):
        signals = self._tech.observe(obs.symbol, obs.market, obs.ts, obs.instrument)
        momentum = next((s for s in signals if s.name == "momentum"), None)
        if momentum is None or momentum.confidence <= 0 or abs(momentum.value) < self.threshold:
            return None  # ignores all other signals and conflict by design
        allow_short = obs.instrument is InstrumentType.PERP
        target = float(np.sign(momentum.value)) * self.target_fraction * obs.equity_usd
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"momentum {momentum.value:+.2f} (single-signal)",
        )


class BuyAndHold:
    """Passive long benchmark; buys once toward a target and only rebalances on big drift."""

    def __init__(self, agent_id: str = "benchmark-buyhold", *, target_fraction: float = 0.6) -> None:
        self.agent_id = agent_id
        self.target_fraction = target_fraction

    def decide(self, obs: AgentObservation):
        target = self.target_fraction * obs.equity_usd
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            allow_short=False,
            min_trade_usd=max(10.0, 0.05 * obs.equity_usd),
            rationale="buy & hold benchmark",
        )
