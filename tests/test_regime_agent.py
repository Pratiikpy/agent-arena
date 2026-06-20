"""Tests for the RegimeAgent (the published-Playbook mirror) and its indicators."""

from __future__ import annotations

import numpy as np

from bitarena.agents.base import AgentObservation
from bitarena.agents.regime import RegimeAgent, _ema_last, _pctb, _rsi
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side


def _obs_at(md: ReplayMarketData) -> AgentObservation:
    return AgentObservation(
        symbol="BTCUSDT", instrument=InstrumentType.PERP, ts=0,
        equity_usd=10_000.0, position_qty=0.0, price=md.get_quote("BTCUSDT").mid, market=md,
    )


def test_ema_last_empty_and_constant():
    assert _ema_last(np.array([]), 12) == 0.0
    assert _ema_last(np.array([10.0, 10.0, 10.0]), 3) == 10.0  # constant series -> EMA == value


def test_rsi_insufficient_and_all_gains():
    assert _rsi(np.array([1.0, 2.0]), 14) == 50.0          # not enough data -> neutral
    assert _rsi(np.arange(1.0, 20.0), 14) == 100.0          # strictly rising -> no losses -> 100


def test_pctb_insufficient_and_flat_band():
    assert _pctb(np.array([1.0, 2.0]), 20, 2.0) == 0.5  # insufficient -> neutral
    assert _pctb(np.full(20, 5.0), 20, 2.0) == 0.5      # zero dispersion -> neutral


def test_regime_returns_none_on_insufficient_history():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=10, seed=1)})
    md.set_cursor(9)
    assert RegimeAgent().decide(_obs_at(md)) is None  # below warmup window


def test_regime_goes_long_in_a_clear_uptrend():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=200, seed=3, drift=0.012, vol=0.001)})
    md.set_cursor(199)
    agent = RegimeAgent()
    intent = agent.decide(_obs_at(md))
    assert agent.last_regime == "trend"
    assert intent is not None and intent.side is Side.BUY
