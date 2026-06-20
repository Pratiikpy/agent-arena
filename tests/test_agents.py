"""Tests for competitor agents and the rebalance helper."""

from __future__ import annotations

from bitarena.agents import (
    AgentObservation,
    BuyAndHold,
    ConflictGatedSwarm,
    MomentumBaseline,
    TradingAgent,
    rebalance_to_target,
)
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side
from bitarena.perception.base import Signal


class _FixedSource:
    """A perception source that always emits one fixed signal (for tests)."""

    name = "fixed"

    def __init__(self, value: float) -> None:
        self._v = value

    def observe(self, symbol, market, ts, instrument=InstrumentType.SPOT):
        return [Signal(name="x", source="fixed", value=self._v, confidence=1.0)]


def _obs(market, *, position_qty=0.0, equity=10_000.0, instrument=InstrumentType.PERP):
    price = market.get_quote("BTCUSDT").mid
    return AgentObservation(
        symbol="BTCUSDT",
        instrument=instrument,
        ts=0,
        equity_usd=equity,
        position_qty=position_qty,
        price=price,
        market=market,
    )


def _trending_market(n=150, seed=1):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed, drift=0.01, vol=0.004)})
    md.set_cursor(n - 1)
    return md


def test_agents_satisfy_protocol():
    for agent in (MomentumBaseline(), BuyAndHold(), ConflictGatedSwarm()):
        assert isinstance(agent, TradingAgent)


def test_rebalance_delta_and_reduce_only():
    md = _trending_market()
    obs = _obs(md, position_qty=0.0)
    # open from flat -> not reduce_only
    buy = rebalance_to_target(agent_id="t", obs=obs, target_notional_signed=2_000.0)
    assert buy is not None and buy.side is Side.BUY and not buy.reduce_only
    assert abs(buy.notional_usd - 2_000.0) < 1.0

    # shrink a long -> reduce_only
    long_obs = _obs(md, position_qty=2_000.0 / obs.price)
    trim = rebalance_to_target(agent_id="t", obs=long_obs, target_notional_signed=500.0)
    assert trim is not None and trim.side is Side.SELL and trim.reduce_only

    # tiny move -> None
    assert rebalance_to_target(agent_id="t", obs=long_obs, target_notional_signed=2_000.0, min_trade_usd=10.0) is None


def test_rebalance_disallows_short_for_spot():
    md = _trending_market()
    obs = _obs(md, position_qty=0.0, instrument=InstrumentType.SPOT)
    assert rebalance_to_target(agent_id="t", obs=obs, target_notional_signed=-2_000.0, allow_short=False) is None


def test_swarm_flattens_on_disagreement():
    md = _trending_market()
    swarm = ConflictGatedSwarm(sources=[_FixedSource(0.8), _FixedSource(-0.8)])  # agreement 0
    obs = _obs(md, position_qty=0.0)
    assert swarm.decide(obs) is None  # no conviction, no position -> hold flat
    assert swarm.last_bundle.agreement == 0.0


def test_swarm_takes_position_on_agreement():
    md = _trending_market()
    swarm = ConflictGatedSwarm(sources=[_FixedSource(0.8), _FixedSource(0.7)])  # aligned bullish
    obs = _obs(md, position_qty=0.0)
    intent = swarm.decide(obs)
    assert intent is not None and intent.side is Side.BUY
    assert swarm.last_bundle.agreement == 1.0


def test_momentum_baseline_acts_in_trend():
    md = _trending_market(seed=2)
    intent = MomentumBaseline(threshold=0.05).decide(_obs(md))
    assert intent is not None and intent.side is Side.BUY


def test_buy_and_hold_opens_long():
    md = _trending_market()
    intent = BuyAndHold().decide(_obs(md, position_qty=0.0))
    assert intent is not None and intent.side is Side.BUY and not intent.reduce_only
