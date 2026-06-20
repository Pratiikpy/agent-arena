"""ConflictGatedSwarm — the thesis agent.

Target exposure is proportional to ``net_signal x agreement`` across all perception
sources (technicals + the five Bitget Agent Hub Skills). When the sources disagree,
``agreement`` collapses toward 0 and the agent sizes down or flattens; it only takes
conviction-sized positions when the signals align. "Disagreement is information,
and the right response to it is smaller size" — that is the bet this agent makes.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..domain.market import InstrumentType
from ..perception.agent_hub import agent_hub_sources
from ..perception.base import PerceptionSource, SignalBundle, aggregate
from ..perception.factors import QuantFactorPerception
from ..perception.market_features import TechnicalPerception
from .base import AgentObservation, rebalance_to_target


class ConflictGatedSwarm:
    """Multi-source agent that sizes by signal agreement."""

    def __init__(
        self,
        agent_id: str = "swarm",
        *,
        sources: list[PerceptionSource] | None = None,
        brief_dir: Path | str | None = None,
        base_fraction: float = 0.7,
        entry_threshold: float = 0.12,
        smoothing: float = 0.35,
    ) -> None:
        self.agent_id = agent_id
        if sources is not None:
            self._sources = sources
        else:
            self._sources = [TechnicalPerception(), QuantFactorPerception(), *agent_hub_sources(brief_dir)]
        self.base_fraction = base_fraction
        self.entry_threshold = entry_threshold
        self.smoothing = smoothing
        self._conviction_ema = 0.0  # smooths conviction to avoid whipsaw churn
        self.last_bundle: SignalBundle | None = None

    def state_dict(self) -> dict:
        """Smoothing state, persisted across live runs so conviction doesn't reset to 0
        each scheduled invocation (which would keep the agent flat in live mode)."""
        return {"conviction_ema": self._conviction_ema}

    def load_state_dict(self, data: dict | None) -> None:
        if data:
            try:
                self._conviction_ema = float(data.get("conviction_ema", 0.0))
            except (TypeError, ValueError):
                self._conviction_ema = 0.0

    def decide(self, obs: AgentObservation):
        bundle = aggregate(obs.symbol, obs.ts, self._sources, obs.market, obs.instrument)
        self.last_bundle = bundle
        net = bundle.net_signal
        agreement = bundle.agreement
        conviction = net * agreement  # the core: disagreement shrinks conviction
        self._conviction_ema = (
            self.smoothing * conviction + (1.0 - self.smoothing) * self._conviction_ema
        )
        smoothed = self._conviction_ema

        allow_short = obs.instrument is InstrumentType.PERP
        if abs(smoothed) < self.entry_threshold:
            target = 0.0  # no conviction -> flatten
        else:
            target = float(np.clip(smoothed, -1.0, 1.0)) * self.base_fraction * obs.equity_usd

        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),  # only act on meaningful changes
            allow_short=allow_short,
            rationale=f"net={net:+.2f} agree={agreement:.2f} conviction={conviction:+.2f}",
        )
