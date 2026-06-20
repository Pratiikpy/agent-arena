"""RegimeAgent — the Arena competitor that mirrors the published Bitget Playbook.

Same adaptive-regime logic as the "Adaptive Regime (Conflict-Gated)" Playbook
published on Bitget GetAgent: trend-follow in committed trends, mean-revert in
clear ranges, and stay flat when the regime is ambiguous. Bringing it into the
Arena unifies the two assets — the exact strategy shipped to Bitget is also a
firewall-gated, trust-scored competitor here.
"""

from __future__ import annotations


import numpy as np

from ..domain.market import InstrumentType
from .base import AgentObservation, rebalance_to_target


def _ema_last(closes: np.ndarray, period: int) -> float:
    if closes.size == 0:
        return 0.0
    alpha = 2.0 / (period + 1)
    ema = float(closes[0])
    for v in closes[1:]:
        ema = alpha * float(v) + (1.0 - alpha) * ema
    return ema


def _rsi(closes: np.ndarray, period: int) -> float:
    if closes.size < period + 1:
        return 50.0
    seg = closes[-(period + 1):]
    diff = np.diff(seg)
    gains = float(np.sum(np.where(diff > 0, diff, 0.0)))
    losses = float(np.sum(np.where(diff < 0, -diff, 0.0)))
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = (gains / period) / (losses / period)
    return 100.0 - 100.0 / (1.0 + rs)


def _pctb(closes: np.ndarray, period: int, k: float) -> float:
    if closes.size < period:
        return 0.5
    seg = closes[-period:]
    mean = float(seg.mean())
    sd = float(seg.std(ddof=1)) if period > 1 else 0.0
    if sd == 0:
        return 0.5
    upper, lower = mean + k * sd, mean - k * sd
    if upper == lower:
        return 0.5
    return (float(closes[-1]) - lower) / (upper - lower)


class RegimeAgent:
    """Adaptive regime agent (mirror of the published Playbook)."""

    def __init__(
        self,
        agent_id: str = "regime",
        *,
        lookback: int = 120,
        ema_fast: int = 12,
        ema_slow: int = 48,
        rsi_period: int = 14,
        bb_period: int = 20,
        bb_k: float = 2.0,
        trend_threshold: float = 0.012,
        range_threshold: float = 0.004,
        rsi_low: float = 35.0,
        rsi_high: float = 65.0,
        base_fraction: float = 0.6,
    ) -> None:
        self.agent_id = agent_id
        self.lookback = lookback
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_k = bb_k
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold
        self.rsi_low = rsi_low
        self.rsi_high = rsi_high
        self.base_fraction = base_fraction
        self.last_regime = "flat"

    def decide(self, obs: AgentObservation):
        candles = obs.market.get_candles(obs.symbol, obs.instrument, limit=self.lookback)
        closes = np.array([c.close for c in candles], dtype=float)
        warmup = max(self.ema_slow, self.bb_period, self.rsi_period) + 2
        if closes.size < warmup:
            return None

        ema_fast = _ema_last(closes, self.ema_fast)
        ema_slow = _ema_last(closes, self.ema_slow)
        if ema_slow == 0:
            return None
        spread = (ema_fast - ema_slow) / ema_slow
        strength = abs(spread)
        rsi = _rsi(closes, self.rsi_period)
        pctb = _pctb(closes, self.bb_period, self.bb_k)

        allow_short = obs.instrument is InstrumentType.PERP
        if strength >= self.trend_threshold:
            target = (1.0 if spread > 0 else -1.0) * self.base_fraction * obs.equity_usd
            self.last_regime = "trend"
        elif strength <= self.range_threshold:
            if rsi < self.rsi_low and pctb < 0.10:
                target = self.base_fraction * obs.equity_usd
            elif rsi > self.rsi_high and pctb > 0.90:
                target = -self.base_fraction * obs.equity_usd
            else:
                target = 0.0
            self.last_regime = "range"
        else:
            target = 0.0
            self.last_regime = "conflict"

        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=allow_short,
            rationale=f"regime={self.last_regime} spread={spread:+.4f} rsi={rsi:.0f} %b={pctb:.2f}",
        )
