"""Tests for the RegimeAgent (mirror of the published Bitget Playbook)."""

from __future__ import annotations

from bitarena.agents import RegimeAgent, TradingAgent
from bitarena.agents.base import AgentObservation
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side


def _obs(market, *, equity=10_000.0, position_qty=0.0, instrument=InstrumentType.PERP):
    price = market.get_quote("BTCUSDT").mid
    return AgentObservation(
        symbol="BTCUSDT", instrument=instrument, ts=0,
        equity_usd=equity, position_qty=position_qty, price=price, market=market,
    )


def _market(n=160, seed=1, drift=0.0, vol=0.01):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed, drift=drift, vol=vol)})
    md.set_cursor(n - 1)
    return md


def test_regime_satisfies_protocol():
    assert isinstance(RegimeAgent(), TradingAgent)


def test_regime_trend_follows_uptrend():
    md = _market(drift=0.02, vol=0.004, seed=3)  # strong, clean uptrend
    intent = RegimeAgent().decide(_obs(md))
    assert intent is not None and intent.side is Side.BUY
    assert RegimeAgent().decide(_obs(md)) is not None


def test_regime_flat_on_insufficient_history():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=160, seed=1)})
    md.set_cursor(10)  # only 11 bars
    assert RegimeAgent().decide(_obs(md)) is None


def test_regime_deterministic():
    md1 = _market(drift=0.02, vol=0.004, seed=7)
    md2 = _market(drift=0.02, vol=0.004, seed=7)
    a = RegimeAgent().decide(_obs(md1))
    b = RegimeAgent().decide(_obs(md2))
    assert (a is None) == (b is None)
    if a is not None:
        assert a.side is b.side and abs((a.notional_usd or 0) - (b.notional_usd or 0)) < 1e-6
