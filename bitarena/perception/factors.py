"""Quant factor perception — a library of single-asset technical factors.

These factors are reimplemented in pure NumPy from their published formulas (factual
mathematical content, not copyrightable): the classic technical indicators plus
time-series entries from Kakushadze (2015) "101 Formulaic Alphas", the Guotai Junan
"191 Alpha Factors" (2014), and the Microsoft Qlib Alpha158 feature set. Only
single-asset / time-series factors are included (no cross-sectional rank factors), since
each arena agent trades one symbol. See NOTICE for attribution.

Each factor returns a directional signal in [-1, 1] (positive = bullish). They give the
swarm / persona / LLM agents a much richer, more independent set of views to weigh — which
also makes the disagreement-gating meaningful.
"""

from __future__ import annotations

import numpy as np

from ..connectors.base import MarketData
from ..domain.market import InstrumentType
from .base import Signal


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    if x.size == 0:
        return x
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, x.size):
        out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def stochastic_k(h, low, c, n=14):
    if c.size < n:
        return 0.0
    hh, ll = h[-n:].max(), low[-n:].min()
    if hh - ll <= 0:
        return 0.0
    k = (c[-1] - ll) / (hh - ll)  # [0,1]
    return float(np.clip(2.0 * k - 1.0, -1.0, 1.0))


def williams_r(h, low, c, n=14):
    if c.size < n:
        return 0.0
    hh, ll = h[-n:].max(), low[-n:].min()
    if hh - ll <= 0:
        return 0.0
    wr = (hh - c[-1]) / (hh - ll)  # [0,1], 0 = strong
    return float(np.clip(1.0 - 2.0 * wr, -1.0, 1.0))


def roc(c, n=10):
    if c.size < n + 1 or c[-1 - n] == 0:
        return 0.0
    return float(np.tanh((c[-1] / c[-1 - n] - 1.0) / 0.05))


def macd_hist(c, fast=12, slow=26, signal=9):
    if c.size < slow + signal:
        return 0.0
    macd = _ema(c, fast) - _ema(c, slow)
    hist = macd - _ema(macd, signal)
    denom = c[-1] if c[-1] > 0 else 1.0
    return float(np.tanh((hist[-1] / denom) / 0.01))


def bollinger_pctb(c, n=20):
    """Mean-reversion (contrarian): high %b (overbought) -> bearish."""
    if c.size < n:
        return 0.0
    window = c[-n:]
    sd = window.std(ddof=1)
    if sd <= 0:
        return 0.0
    pct_b = (c[-1] - window.mean()) / (2.0 * sd)  # ~[-1,1] at the bands
    return float(np.clip(-pct_b, -1.0, 1.0))


def cci(h, low, c, n=20):
    if c.size < n:
        return 0.0
    tp = (h + low + c) / 3.0
    window = tp[-n:]
    mean_dev = np.mean(np.abs(window - window.mean()))
    if mean_dev <= 0:
        return 0.0
    val = (tp[-1] - window.mean()) / (0.015 * mean_dev)
    return float(np.tanh(val / 150.0))


def obv_slope(c, v, n=20):
    if c.size < n + 1:
        return 0.0
    direction = np.sign(np.diff(c))
    obv = np.cumsum(direction * v[1:])
    seg = obv[-n:]
    if seg.size < 2:
        return 0.0
    x = np.arange(seg.size)
    slope = np.polyfit(x, seg, 1)[0]
    scale = np.std(seg) or 1.0
    return float(np.tanh(slope / scale))


def candle_kmid(o, c):
    if c.size < 1 or o[-1] == 0:
        return 0.0
    return float(np.tanh(((c[-1] - o[-1]) / o[-1]) / 0.02))


def return_autocorr(c, n=20):
    """Trend-persistence: + = momentum regime, - = mean-reverting regime."""
    if c.size < n + 2:
        return 0.0
    r = np.diff(c[-(n + 1):]) / c[-(n + 1):-1]
    if r.size < 3 or r.std() == 0:
        return 0.0
    a, b = r[1:], r[:-1]
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.clip(np.corrcoef(a, b)[0, 1], -1.0, 1.0))


def donchian_position(h, low, c, n=20):
    if c.size < n:
        return 0.0
    hh, ll = h[-n:].max(), low[-n:].min()
    if hh - ll <= 0:
        return 0.0
    return float(np.clip(2.0 * (c[-1] - ll) / (hh - ll) - 1.0, -1.0, 1.0))


def efficiency_ratio(c, n=10):
    """Kaufman efficiency ratio in [0,1]: trendiness. Used as a confidence weight."""
    if c.size < n + 1:
        return 0.0
    change = abs(c[-1] - c[-1 - n])
    volatility = np.sum(np.abs(np.diff(c[-(n + 1):])))
    if volatility <= 0:
        return 0.0
    return float(np.clip(change / volatility, 0.0, 1.0))


class QuantFactorPerception:
    """Emits a library of single-asset quant factors as directional signals."""

    name = "quant_factors"

    def __init__(self, lookback: int = 120) -> None:
        self.lookback = lookback

    def observe(
        self,
        symbol: str,
        market: MarketData,
        ts: int,
        instrument: InstrumentType = InstrumentType.SPOT,
    ) -> list[Signal]:
        candles = market.get_candles(symbol, instrument, limit=self.lookback)
        if len(candles) < 26:
            return [Signal(name="quant_insufficient", source="quant_factors", value=0.0, confidence=0.0)]
        o = np.array([c.open for c in candles], dtype=float)
        h = np.array([c.high for c in candles], dtype=float)
        low = np.array([c.low for c in candles], dtype=float)
        c = np.array([c.close for c in candles], dtype=float)
        v = np.array([c.volume for c in candles], dtype=float)

        # efficiency ratio modulates confidence: trendier tape -> more confident factors
        er = efficiency_ratio(c)
        conf = float(np.clip(0.4 + 0.5 * er, 0.4, 0.9))

        factors = {
            "stochastic": (stochastic_k(h, low, c), conf),
            "williams_r": (williams_r(h, low, c), conf),
            "roc": (roc(c), conf),
            "macd": (macd_hist(c), conf),
            "bollinger_pctb": (bollinger_pctb(c), conf * 0.9),
            "cci": (cci(h, low, c), conf),
            "obv": (obv_slope(c, v), conf * 0.8),
            "kmid": (candle_kmid(o, c), conf * 0.7),
            "autocorr": (return_autocorr(c), conf * 0.6),
            "donchian": (donchian_position(h, low, c), conf),
        }
        return [
            Signal(name=name, source="quant_factors", value=float(val), confidence=float(cf))
            for name, (val, cf) in factors.items()
        ]
