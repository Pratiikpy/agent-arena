"""Perception primitives: a Signal, a SignalBundle, and the source protocol.

A Signal is a named, directional read in [-1, 1] (positive = bullish) with a
confidence in [0, 1] and a source tag. A SignalBundle aggregates the signals for
one symbol at one moment and exposes the two quantities the thesis needs: the
confidence-weighted ``net_signal`` and the ``agreement`` (how aligned the signals
are). The arena's swarm sizes positions by agreement — that is the core bet.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from ..connectors.base import MarketData
from ..domain.market import InstrumentType


class Signal(BaseModel):
    """One directional view from one source."""

    model_config = ConfigDict(frozen=True)

    name: str
    source: str
    value: float  # [-1, 1]; positive bullish, negative bearish
    confidence: float  # [0, 1]
    detail: str = ""


class SignalBundle(BaseModel):
    """All signals observed for a symbol at a point in time."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    ts: int
    signals: tuple[Signal, ...]

    @property
    def net_signal(self) -> float:
        """Confidence-weighted mean signal in [-1, 1]."""
        weight = sum(s.confidence for s in self.signals)
        if weight <= 0:
            return 0.0
        return sum(s.value * s.confidence for s in self.signals) / weight

    @property
    def agreement(self) -> float:
        """How aligned the signals are, in [0, 1]. 1 = unanimous, 0 = perfectly split."""
        denom = sum(abs(s.value) for s in self.signals)
        if denom <= 0:
            return 0.0
        return abs(sum(s.value for s in self.signals)) / denom

    @property
    def mean_confidence(self) -> float:
        if not self.signals:
            return 0.0
        return sum(s.confidence for s in self.signals) / len(self.signals)

    def by_source(self, prefix: str) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.source.startswith(prefix))


@runtime_checkable
class PerceptionSource(Protocol):
    """Anything that can produce signals for a symbol from market data."""

    name: str

    def observe(
        self,
        symbol: str,
        market: MarketData,
        ts: int,
        instrument: InstrumentType = InstrumentType.SPOT,
    ) -> list[Signal]: ...


def aggregate(
    symbol: str,
    ts: int,
    sources: list[PerceptionSource],
    market: MarketData,
    instrument: InstrumentType = InstrumentType.SPOT,
) -> SignalBundle:
    """Collect signals from every source into one bundle."""
    signals: list[Signal] = []
    for source in sources:
        signals.extend(source.observe(symbol, market, ts, instrument))
    return SignalBundle(symbol=symbol, ts=ts, signals=tuple(signals))
