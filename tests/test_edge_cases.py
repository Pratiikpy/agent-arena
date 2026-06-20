"""Edge-case coverage for newer code: spot no-short, research degenerate inputs."""

from __future__ import annotations

from bitarena.agents import RegimeAgent
from bitarena.agents.base import AgentObservation, rebalance_to_target
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType, Side
from bitarena.research import study, walk_forward_arena
from bitarena.research.funding_carry import carry_returns, equity_curve


def _obs(market, *, instrument, equity=10_000.0, position_qty=0.0):
    price = market.get_quote("BTCUSDT").mid
    return AgentObservation(
        symbol="BTCUSDT", instrument=instrument, ts=0,
        equity_usd=equity, position_qty=position_qty, price=price, market=market,
    )


def _market(*, drift, vol=0.004, seed=3, n=160):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed, drift=drift, vol=vol)})
    md.set_cursor(n - 1)
    return md


# --- RegimeAgent on SPOT: longs are fine, shorts are impossible ---------------

def test_regime_spot_long_in_uptrend():
    md = _market(drift=0.02, seed=3)
    intent = RegimeAgent().decide(_obs(md, instrument=InstrumentType.SPOT))
    assert intent is not None and intent.side is Side.BUY


def test_regime_spot_never_opens_short_in_downtrend():
    md = _market(drift=-0.02, seed=4)
    intent = RegimeAgent().decide(_obs(md, instrument=InstrumentType.SPOT))
    # a short signal on spot with no position cannot be acted on -> hold (or, if any
    # intent at all, it must not be a fresh sell-short)
    assert intent is None or intent.side is Side.BUY


def test_regime_perp_can_short_in_downtrend():
    md = _market(drift=-0.02, seed=4)
    intent = RegimeAgent().decide(_obs(md, instrument=InstrumentType.PERP))
    assert intent is not None and intent.side is Side.SELL


# --- rebalance_to_target no-short clamp --------------------------------------

def test_rebalance_no_short_from_flat_holds():
    md = _market(drift=0.0)
    obs = _obs(md, instrument=InstrumentType.SPOT, position_qty=0.0)
    assert rebalance_to_target(agent_id="x", obs=obs, target_notional_signed=-5_000.0, allow_short=False) is None


def test_rebalance_no_short_reduces_existing_long():
    md = _market(drift=0.0)
    price = md.get_quote("BTCUSDT").mid
    qty = 5_000.0 / price  # a $5k long
    obs = _obs(md, instrument=InstrumentType.SPOT, position_qty=qty)
    intent = rebalance_to_target(agent_id="x", obs=obs, target_notional_signed=-5_000.0, allow_short=False)
    assert intent is not None and intent.side is Side.SELL and intent.reduce_only is True


# --- research modules: degenerate inputs must not crash ----------------------

def test_carry_returns_high_threshold_all_zero():
    rates = [0.0001, 0.0002, 0.00005]
    out = carry_returns(rates, adaptive=True, threshold=1.0)  # nothing clears 100%/interval
    assert list(out) == [0.0, 0.0, 0.0]


def test_equity_curve_empty_is_safe():
    eq = equity_curve([])
    assert list(eq) == [1.0]


def test_funding_study_small_input_is_safe():
    s = study([0.0001, -0.0002, 0.0003, 0.0001, 0.0, 0.0002, -0.0001, 0.00015, 0.0001, 0.0002])
    assert s["intervals"] == 10
    assert "passive_carry" in s and s["passive_carry"]["intervals"] == 10
    assert s["walk_forward_passive"] == []  # too few points to fold -> empty, not a crash


def test_walk_forward_arena_tiny_input_collapses_to_one_fold():
    candles = synthetic_series("BTCUSDT", n=50, seed=2, drift=0.001, vol=0.01)
    report = walk_forward_arena(candles, symbol="BTCUSDT", folds=5)
    assert report["folds"] >= 1 and report["summary"]
    for s in report["summary"].values():
        assert s["folds"] >= 1
