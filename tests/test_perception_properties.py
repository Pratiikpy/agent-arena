"""Property/fuzz tests for the quant factors — they feed the agents, so they must never
emit NaN/inf or out-of-[-1,1] signals, even on degenerate tapes (flat, monotonic,
extreme, zero-volume). A poisoned signal would silently corrupt every agent's decision.
"""

from __future__ import annotations

import math
import random

import numpy as np

from bitarena.connectors import ReplayMarketData
from bitarena.domain.market import Candle
from bitarena.perception import QuantFactorPerception
from bitarena.perception.factors import (
    bollinger_pctb,
    candle_kmid,
    cci,
    donchian_position,
    efficiency_ratio,
    macd_hist,
    obv_slope,
    return_autocorr,
    roc,
    stochastic_k,
    williams_r,
)


def _closes(rng: random.Random, kind: str, n: int) -> np.ndarray:
    if kind == "flat":
        return np.full(n, rng.choice([1e-6, 1.0, 100.0, 1e9]))
    if kind == "up":
        return np.linspace(100.0, 100.0 + rng.uniform(1, 5_000), n)
    if kind == "down":
        return np.linspace(100.0 + rng.uniform(1, 5_000), 1e-6, n)
    if kind == "alt":
        base = rng.uniform(1, 1_000)
        return np.array([base * (1.05 if i % 2 else 0.95) for i in range(n)])
    if kind == "extreme":
        return np.array([rng.choice([1e-9, 1e12]) for _ in range(n)])
    return np.cumprod(1.0 + np.array([rng.uniform(-0.1, 0.1) for _ in range(n)])) * 100.0  # random walk


def test_every_factor_is_finite_and_bounded():
    rng = random.Random(7)
    kinds = ["flat", "up", "down", "alt", "extreme", "random"]
    for _ in range(1_500):
        n = rng.randint(1, 140)
        c = np.clip(_closes(rng, rng.choice(kinds), n), 1e-9, None)
        h = c * (1.0 + rng.uniform(0.0, 0.02))
        low = c * (1.0 - rng.uniform(0.0, 0.02))
        o = np.concatenate([[c[0]], c[:-1]])
        v = np.array([rng.choice([0.0, rng.uniform(0.0, 1e6)]) for _ in range(n)])

        unit_factors = [
            stochastic_k(h, low, c), williams_r(h, low, c), roc(c), macd_hist(c),
            bollinger_pctb(c), cci(h, low, c), obv_slope(c, v), candle_kmid(o, c),
            return_autocorr(c), donchian_position(h, low, c),
        ]
        for val in unit_factors:
            assert math.isfinite(val), f"non-finite factor on n={n}"
            assert -1.0 <= val <= 1.0, f"out-of-bounds factor {val} on n={n}"

        er = efficiency_ratio(c)
        assert math.isfinite(er) and 0.0 <= er <= 1.0


def _flat_market(price: float, n: int = 60) -> ReplayMarketData:
    candles = [
        Candle(ts=1_700_000_000_000 + i * 60_000, open=price, high=price, low=price, close=price, volume=0.0)
        for i in range(n)
    ]
    md = ReplayMarketData({"BTCUSDT": candles})
    md.set_cursor(n - 1)
    return md


def test_quant_perception_emits_clean_signals_on_flat_tape():
    for price in (1e-6, 1.0, 50_000.0):
        sigs = QuantFactorPerception().observe("BTCUSDT", _flat_market(price), ts=0)
        assert sigs
        for s in sigs:
            assert math.isfinite(s.value) and -1.0 <= s.value <= 1.0
            assert math.isfinite(s.confidence) and 0.0 <= s.confidence <= 1.0
