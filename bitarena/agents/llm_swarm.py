"""LLMDebateSwarm — a Qwen-driven multi-analyst debate agent.

Each decision gathers the perception signals (technicals + the five Bitget Agent Hub
Skills) and asks Qwen to run a bull/bear/risk debate, returning a stance and a
conviction that explicitly penalizes signal disagreement. The conviction sizes the
position. LLM calls are throttled (every ``decide_every`` ticks; cached in between) to
control cost, and the agent falls back to the deterministic ``net x agreement`` rule
whenever the LLM is unavailable or returns unparseable output — so it always runs.

Like every competitor, its orders are still gated by the firewall: even a confident
LLM cannot place a trade that breaches the mandate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from ..domain.market import InstrumentType
from ..llm import QwenClient
from ..perception.agent_hub import agent_hub_sources
from ..perception.base import PerceptionSource, SignalBundle, aggregate
from ..perception.factors import QuantFactorPerception
from ..perception.market_features import TechnicalPerception
from .base import AgentObservation, rebalance_to_target

_SYSTEM = (
    "You are the portfolio manager of a disciplined multi-analyst crypto trading desk. "
    "You weigh competing analyst signals, run a brief bull-vs-bear debate, then a risk "
    "check that reduces conviction when the analysts disagree. You never over-trade noise."
)


def _extract_json(text: str) -> dict | None:
    try:
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0)) if match else None
    except (ValueError, AttributeError):
        return None


class LLMDebateSwarm:
    """Conviction-sized agent whose conviction comes from a Qwen debate (with fallback)."""

    def __init__(
        self,
        agent_id: str = "llm-swarm",
        *,
        sources: list[PerceptionSource] | None = None,
        brief_dir: Path | str | None = None,
        llm: QwenClient | None = None,
        base_fraction: float = 0.7,
        entry_threshold: float = 0.12,
        decide_every: int = 15,
        smoothing: float = 0.35,
    ) -> None:
        self.agent_id = agent_id
        if sources is not None:
            self._sources = sources
        else:
            self._sources = [TechnicalPerception(), QuantFactorPerception(), *agent_hub_sources(brief_dir)]
        self._llm = llm if llm is not None else QwenClient.from_settings()
        self.base_fraction = base_fraction
        self.entry_threshold = entry_threshold
        self.decide_every = decide_every
        self.smoothing = smoothing
        self._tick = 0
        self._cached_llm_conviction = 0.0
        self._ema = 0.0
        self.last_bundle: SignalBundle | None = None
        self.last_rationale = ""
        self.last_source = "deterministic"

    def decide(self, obs: AgentObservation):
        bundle = aggregate(obs.symbol, obs.ts, self._sources, obs.market, obs.instrument)
        self.last_bundle = bundle
        deterministic = bundle.net_signal * bundle.agreement

        conviction = deterministic
        self.last_source = "deterministic"
        if self._llm.available():
            if self._tick % self.decide_every == 0:
                llm_conv, rationale = self._debate(bundle)
                if llm_conv is not None:
                    self._cached_llm_conviction = llm_conv
                    self.last_rationale = rationale
                    self.last_source = "qwen"
                    conviction = llm_conv
                else:  # call or parse failed -> deterministic fallback this tick
                    conviction = deterministic
                    self.last_source = "deterministic"
            else:
                # between LLM calls, blend the last LLM read with the live deterministic signal
                conviction = 0.5 * self._cached_llm_conviction + 0.5 * deterministic
                self.last_source = "qwen-cached"
        self._tick += 1

        self._ema = self.smoothing * conviction + (1.0 - self.smoothing) * self._ema
        smoothed = self._ema
        allow_short = obs.instrument is InstrumentType.PERP
        if abs(smoothed) < self.entry_threshold:
            target = 0.0
        else:
            target = float(np.clip(smoothed, -1.0, 1.0)) * self.base_fraction * obs.equity_usd

        rationale = self.last_rationale or f"det={deterministic:+.2f}"
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"[{self.last_source}] {rationale}"[:140],
        )

    def _debate(self, bundle: SignalBundle) -> tuple[float | None, str]:
        signals = "\n".join(
            f"- {s.name} ({s.source}): value={s.value:+.2f} conf={s.confidence:.2f} {s.detail}"
            for s in bundle.signals
        )
        user = (
            f"Symbol {bundle.symbol}. Analyst signals (value in [-1,1], + = bullish):\n{signals}\n"
            f"Net signal = {bundle.net_signal:+.2f}, agreement = {bundle.agreement:.2f}.\n"
            "Run a brief bull-vs-bear debate, then a risk check that lowers conviction when "
            "the analysts disagree. Respond ONLY as compact JSON: "
            '{"stance":"long|short|flat","conviction":0..1,"reason":"<=20 words"}.'
        )
        raw = self._llm.chat(_SYSTEM, user)
        if not raw:
            return None, ""
        data = _extract_json(raw)
        if not data:
            return None, ""
        stance = str(data.get("stance", "flat")).lower()
        try:
            conviction = max(0.0, min(1.0, float(data.get("conviction", 0.0))))
        except (TypeError, ValueError):
            conviction = 0.0
        signed = conviction if stance == "long" else (-conviction if stance == "short" else 0.0)
        return signed, str(data.get("reason", ""))[:140]
