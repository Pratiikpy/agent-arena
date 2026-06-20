"""Tests for the quant factor library and QuantFactorPerception."""

from __future__ import annotations

import numpy as np

from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.perception import QuantFactorPerception
from bitarena.perception.factors import (
    bollinger_pctb,
    cci,
    donchian_position,
    macd_hist,
    roc,
    stochastic_k,
    williams_r,
)


def _ohlc(n=120, seed=1, drift=0.0):
    candles = synthetic_series("BTCUSDT", n=n, seed=seed, drift=drift)
    o = np.array([c.open for c in candles], float)
    h = np.array([c.high for c in candles], float)
    lo = np.array([c.low for c in candles], float)
    c = np.array([c.close for c in candles], float)
    return o, h, lo, c


def test_factors_bounded():
    o, h, lo, c = _ohlc()
    for val in (
        stochastic_k(h, lo, c),
        williams_r(h, lo, c),
        roc(c),
        macd_hist(c),
        bollinger_pctb(c),
        cci(h, lo, c),
        donchian_position(h, lo, c),
    ):
        assert -1.0 <= val <= 1.0


def test_factors_directional_in_uptrend():
    # strong uptrend -> momentum-flavored factors lean positive
    o, h, lo, c = _ohlc(drift=0.02, seed=3)
    assert stochastic_k(h, lo, c) > 0
    assert donchian_position(h, lo, c) > 0
    assert roc(c) > 0


def test_perception_emits_factor_signals():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=120, seed=1)})
    md.set_cursor(119)
    sigs = QuantFactorPerception().observe("BTCUSDT", md, ts=0)
    names = {s.name for s in sigs}
    assert {"stochastic", "macd", "bollinger_pctb", "donchian", "roc"} <= names
    for s in sigs:
        assert -1.0 <= s.value <= 1.0 and 0.0 <= s.confidence <= 1.0


def test_perception_insufficient_history():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=120, seed=1)})
    md.set_cursor(10)  # only 11 bars
    sigs = QuantFactorPerception().observe("BTCUSDT", md, ts=0)
    assert len(sigs) == 1 and sigs[0].confidence == 0.0
