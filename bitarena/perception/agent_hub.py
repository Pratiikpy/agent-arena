"""Bitget Agent Hub perception adapter — the five analyst Skills as signal sources.

Each instance maps one Agent Hub Skill (macro / sentiment / news / on-chain /
technical) to a Signal. If a JSON brief is available (the shape a live Skill Hub
export produces) it is used directly; otherwise the adapter derives a deterministic
fallback from recent price action, clearly tagged ``(fallback)`` so nothing is
presented as a live skill call when it is not.

This is what makes the thesis testable: the five Skills naturally disagree
(sentiment turns contrarian at extremes; macro and on-chain lag), and the swarm
agent sizes by how much they agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..connectors.base import MarketData
from ..domain.market import InstrumentType
from .base import Signal

AGENT_HUB_SKILLS = ("macro", "sentiment", "news", "onchain", "technical")


def _clip01(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def _clip11(x: float) -> float:
    return float(np.clip(x, -1.0, 1.0))


class AgentHubPerception:
    """One Bitget Agent Hub Skill as a perception source."""

    def __init__(self, skill: str, brief_dir: Path | str | None = None) -> None:
        if skill not in AGENT_HUB_SKILLS:
            raise ValueError(f"unknown Agent Hub skill: {skill}")
        self.skill = skill
        self.name = f"agent_hub:{skill}"
        self._dir = Path(brief_dir) if brief_dir else None

    def observe(
        self,
        symbol: str,
        market: MarketData,
        ts: int,
        instrument: InstrumentType = InstrumentType.SPOT,
    ) -> list[Signal]:
        brief = self._load_brief(symbol)
        if brief is not None:
            return [
                Signal(
                    name=self.skill,
                    source=self.name,
                    value=_clip11(float(brief.get("score", 0.0))),
                    confidence=_clip01(float(brief.get("confidence", 0.6))),
                    detail=str(brief.get("summary", ""))[:160],
                )
            ]
        return [self._fallback(symbol, market, instrument)]

    def _load_brief(self, symbol: str) -> dict | None:
        if self._dir is None:
            return None
        candidates = (
            self._dir / f"{self.skill}_{symbol.upper()}.json",
            self._dir / f"{self.skill}.json",
        )
        for path in candidates:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return data if isinstance(data, dict) else None
                except (ValueError, OSError):
                    return None
        return None

    def _fallback(self, symbol: str, market: MarketData, instrument: InstrumentType) -> Signal:
        """Skill-specific heuristic proxy used when no live Skill brief is available.

        Each skill reads a *different* feature/timescale so the five channels can
        genuinely disagree (slow trend vs fast momentum vs contrarian extension) —
        which is what makes the swarm's agreement-gating meaningful even offline.
        Clearly tagged ``(fallback)``; real Agent Hub Skills replace these directly.
        """
        candles = market.get_candles(symbol, instrument, limit=80)
        closes = np.array([c.close for c in candles], dtype=float)
        if closes.size < 6:
            return Signal(
                name=self.skill,
                source=f"{self.name}(fallback)",
                value=0.0,
                confidence=0.1,
                detail="fallback: insufficient data",
            )

        def trend(window: int) -> float:
            w = min(window, closes.size - 1)
            return closes[-1] / closes[-1 - w] - 1.0

        def zscore(window: int) -> float:
            w = min(window, closes.size)
            seg = closes[-w:]
            sd = seg.std(ddof=1) or 1e-9
            return (closes[-1] - seg.mean()) / sd

        if self.skill == "macro":
            value, detail = np.tanh(trend(60) / 0.06), "slow 60-bar trend"
        elif self.skill == "onchain":
            value, detail = np.tanh(trend(30) / 0.04), "30-bar accumulation trend"
        elif self.skill == "news":
            value, detail = np.tanh(trend(10) / 0.03), "10-bar momentum"
        elif self.skill == "sentiment":
            value, detail = np.tanh(-zscore(20) / 1.5), "contrarian 20-bar z-score"
        else:  # technical
            value, detail = np.tanh(trend(20) / 0.035), "20-bar momentum"

        return Signal(
            name=self.skill,
            source=f"{self.name}(fallback)",
            value=_clip11(float(value)),
            confidence=0.4,
            detail=f"fallback: {detail}",
        )


def agent_hub_sources(brief_dir: Path | str | None = None) -> list[AgentHubPerception]:
    """All five Agent Hub Skills as perception sources."""
    return [AgentHubPerception(skill, brief_dir) for skill in AGENT_HUB_SKILLS]
