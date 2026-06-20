"""Native technical perception: momentum, trend, mean-reversion, and RSI signals.

Trend/momentum are trend-following; mean-reversion/RSI are contrarian. They agree
in clean trends and disagree in chop — which is exactly the disagreement the swarm
agent is designed to exploit (size up on agreement, down on conflict).
"""

from __future__ import annotations

import numpy as np

from ..connectors.base import MarketData
from ..domain.market import InstrumentType
from .base import Signal


def sma(values: np.ndarray, n: int) -> float:
    if values.size < n or n <= 0:
        return float(values.mean()) if values.size else 0.0
    return float(values[-n:].mean())


def rsi(closes: np.ndarray, n: int = 14) -> float:
    if closes.size < n + 1:
        return 50.0
    diff = np.diff(closes)
    gains = np.where(diff > 0, diff, 0.0)[-n:]
    losses = np.where(diff < 0, -diff, 0.0)[-n:]
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


class TechnicalPerception:
    """Computes a small, interpretable set of technical signals from candles."""

    name = "technical"

    def __init__(
        self,
        lookback: int = 120,
        fast: int = 10,
        slow: int = 30,
        mom_window: int = 20,
        rsi_n: int = 14,
    ) -> None:
        self.lookback = lookback
        self.fast = fast
        self.slow = slow
        self.mom_window = mom_window
        self.rsi_n = rsi_n

    def observe(
        self,
        symbol: str,
        market: MarketData,
        ts: int,
        instrument: InstrumentType = InstrumentType.SPOT,
    ) -> list[Signal]:
        candles = market.get_candles(symbol, instrument, limit=self.lookback)
        closes = np.array([c.close for c in candles], dtype=float)
        if closes.size < self.slow + 2:
            return [
                Signal(
                    name="technical_insufficient",
                    source="technical",
                    value=0.0,
                    confidence=0.0,
                    detail="insufficient history",
                )
            ]

        mom = (closes[-1] / closes[-1 - self.mom_window] - 1.0) if closes.size > self.mom_window else 0.0
        mom_v = float(np.tanh(mom / 0.05))

        fast_ma = sma(closes, self.fast)
        slow_ma = sma(closes, self.slow)
        trend = (fast_ma - slow_ma) / slow_ma if slow_ma else 0.0
        trend_v = float(np.tanh(trend / 0.03))

        window = closes[-self.slow:]
        mu = window.mean()
        sd = window.std(ddof=1) or 1e-9
        z = (closes[-1] - mu) / sd
        mr_v = float(np.tanh(-z / 2.0))  # contrarian: stretched up -> sell

        r = rsi(closes, self.rsi_n)
        rsi_v = float(np.clip((50.0 - r) / 50.0, -1.0, 1.0))  # overbought -> bearish

        rets = np.diff(closes) / closes[:-1]
        vol = float(np.std(rets)) if rets.size else 0.0
        conf = float(np.clip(1.0 - vol * 5.0, 0.2, 1.0))

        return [
            Signal(name="momentum", source="technical", value=mom_v, confidence=conf,
                   detail=f"{self.mom_window}-bar return {mom:.2%}"),
            Signal(name="trend", source="technical", value=trend_v, confidence=conf,
                   detail=f"SMA{self.fast} vs SMA{self.slow}: {trend:.2%}"),
            Signal(name="mean_reversion", source="technical", value=mr_v, confidence=conf * 0.8,
                   detail=f"z-score {z:.2f}"),
            Signal(name="rsi", source="technical", value=rsi_v, confidence=conf * 0.8,
                   detail=f"RSI {r:.1f}"),
        ]
