"""PersonaTeam — a bull/bear/quant/risk ensemble competitor.

Distinct from the conflict-gated swarm: it splits the signals into a trend-following
lens (bull) and a contrarian lens (bear), blends them with a quant net read (PM), and
lets a risk persona veto the whole position when the analysts disagree. A different
way to combine the same perception — useful as an independent competitor.
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

_TREND_SIGNALS = {"momentum", "trend", "news", "macro", "onchain"}
_CONTRARIAN_SIGNALS = {"mean_reversion", "rsi", "sentiment"}


class PersonaTeam:
    """Ensemble agent: bull + bear + quant, gated by a risk persona."""

    def __init__(
        self,
        agent_id: str = "persona-team",
        *,
        sources: list[PerceptionSource] | None = None,
        brief_dir: Path | str | None = None,
        base_fraction: float = 0.6,
        veto_agreement: float = 0.25,
    ) -> None:
        self.agent_id = agent_id
        if sources is not None:
            self._sources = sources
        else:
            self._sources = [TechnicalPerception(), QuantFactorPerception(), *agent_hub_sources(brief_dir)]
        self.base_fraction = base_fraction
        self.veto_agreement = veto_agreement
        self.last_bundle: SignalBundle | None = None
        self.last_votes: dict = {}

    def decide(self, obs: AgentObservation):
        bundle = aggregate(obs.symbol, obs.ts, self._sources, obs.market, obs.instrument)
        self.last_bundle = bundle

        def group_mean(names: set[str]) -> float:
            vals = [s.value * s.confidence for s in bundle.signals if s.name in names]
            return float(np.mean(vals)) if vals else 0.0

        trend = group_mean(_TREND_SIGNALS)
        contrarian = group_mean(_CONTRARIAN_SIGNALS)
        bull = max(0.0, trend)  # the bull only ever argues the long case
        bear = min(0.0, contrarian)  # the bear only ever argues the short case
        quant = bundle.net_signal
        pm = (bull + bear + quant) / 3.0
        risk_mult = 0.0 if bundle.agreement < self.veto_agreement else min(1.0, bundle.agreement)
        conviction = pm * risk_mult
        self.last_votes = {
            "bull": round(bull, 3),
            "bear": round(bear, 3),
            "quant": round(quant, 3),
            "risk_mult": round(risk_mult, 3),
        }

        allow_short = obs.instrument is InstrumentType.PERP
        target = float(np.clip(conviction, -1.0, 1.0)) * self.base_fraction * obs.equity_usd
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"bull={bull:+.2f} bear={bear:+.2f} quant={quant:+.2f} risk={risk_mult:.2f}",
        )
