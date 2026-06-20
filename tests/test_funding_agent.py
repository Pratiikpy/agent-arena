"""Tests for the FundingCarryAgent (positions to receive perpetual funding)."""

from __future__ import annotations

from bitarena.agents import FundingCarryAgent, TradingAgent
from bitarena.agents.base import AgentObservation
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side


def _obs(market, *, ts, instrument=InstrumentType.PERP, equity=10_000.0, position_qty=0.0):
    price = market.get_quote("BTCUSDT").mid
    return AgentObservation(
        symbol="BTCUSDT", instrument=instrument, ts=ts,
        equity_usd=equity, position_qty=position_qty, price=price, market=market,
    )


def _market(n=60):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=1)})
    md.set_cursor(n - 1)
    return md


_FUNDING = [
    {"ts": 0, "funding_rate": 0.0005},        # strongly positive -> short
    {"ts": 1_000, "funding_rate": -0.0005},   # strongly negative -> long
    {"ts": 2_000, "funding_rate": 0.00001},   # tiny -> flat
]


def test_funding_agent_satisfies_protocol():
    assert isinstance(FundingCarryAgent(), TradingAgent)


def test_rate_at_returns_most_recent():
    a = FundingCarryAgent(_FUNDING)
    assert a.rate_at(-1) == 0.0          # before first
    assert a.rate_at(500) == 0.0005      # after first, before second
    assert a.rate_at(1_500) == -0.0005   # after second
    assert a.rate_at(9_999) == 0.00001   # after last


def test_positions_to_receive_funding():
    md = _market()
    a = FundingCarryAgent(_FUNDING)
    assert a.decide(_obs(md, ts=500)).side is Side.SELL   # positive funding -> short receives
    assert a.decide(_obs(md, ts=1_500)).side is Side.BUY  # negative funding -> long receives
    assert a.decide(_obs(md, ts=2_500)) is None           # tiny funding -> flat


def test_flat_without_funding_data_or_on_spot():
    md = _market()
    assert FundingCarryAgent().decide(_obs(md, ts=500)) is None  # no funding -> flat
    assert FundingCarryAgent(_FUNDING).decide(_obs(md, ts=500, instrument=InstrumentType.SPOT)) is None


def test_funding_agent_handles_malformed_funding():
    # funding comes from the live API — malformed rows must be skipped, not crash
    bad = [
        {"ts": "notint", "funding_rate": 0.001},  # unparseable ts
        {"ts": 1000},                             # missing rate
        {"funding_rate": 0.001},                  # missing ts
        "not-a-dict",                             # wrong type entirely
        {"ts": 2000, "funding_rate": "x"},        # unparseable rate
        {"ts": 3000, "funding_rate": 0.0005},     # the one valid row
    ]
    a = FundingCarryAgent(bad)
    assert a.rate_at(5000) == 0.0005
    assert FundingCarryAgent([]).rate_at(1000) == 0.0  # empty schedule -> neutral


def test_deterministic():
    md1, md2 = _market(), _market()
    a, b = FundingCarryAgent(_FUNDING), FundingCarryAgent(_FUNDING)
    x, y = a.decide(_obs(md1, ts=500)), b.decide(_obs(md2, ts=500))
    assert x.side is y.side and abs((x.notional_usd or 0) - (y.notional_usd or 0)) < 1e-9


def test_build_index_accepts_dict_form_and_skips_bad_values():
    # funding may also be supplied as a {ts: rate} mapping; unparseable entries are skipped
    a = FundingCarryAgent({0: 0.0005, 1_000: -0.0005, "bad": "x"})
    assert a.rate_at(500) == 0.0005
    assert a.rate_at(1_500) == -0.0005
