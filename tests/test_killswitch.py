"""Tests for the market-regime detector and the firewall's fleet-wide kill-switch."""

from __future__ import annotations

from bitarena.domain import Side, TradeIntent, default_arena_mandate
from bitarena.domain.market import Quote
from bitarena.firewall import EvalContext, Firewall
from bitarena.firewall.gates import gate_market_regime
from bitarena.firewall.regime import MarketRegime, assess_regime


def _quote(mid=63_000.0, ts=1_000) -> Quote:
    return Quote(symbol="BTCUSDT", bid=mid - 1, ask=mid + 1, last=mid, ts=ts)


def _ctx(regime, *, position_qty=0.0, exposure=0.0):
    return EvalContext(
        mandate=default_arena_mandate(10_000, allowed_symbols=("BTCUSDT",)),
        equity_usd=10_000.0, quote=_quote(), current_exposure_usd=exposure,
        position_qty=position_qty, regime=regime, now_ms=1_000, max_quote_age_ms=60_000,
    )


def _intent(side=Side.BUY, notional=50.0, reduce_only=False):
    return TradeIntent(
        agent_id="a", symbol="BTCUSDT", side=side, notional_usd=notional, reduce_only=reduce_only
    )


# -- detector ----------------------------------------------------------------

def test_regime_normal_when_flat_or_rising():
    assert assess_regime([100.0] * 12) is MarketRegime.NORMAL
    assert assess_regime([100, 101, 102, 103, 104, 105]) is MarketRegime.NORMAL


def test_regime_fast_risk_off_on_sharp_drop():
    # ~9% peak-to-now drop within the window → kill-switch state
    assert assess_regime([100] * 8 + [99, 97, 94, 91]) is MarketRegime.FAST_RISK_OFF


def test_regime_risk_off_on_moderate_drop():
    # ~5% drop: elevated but not acute
    assert assess_regime([100] * 10 + [97, 95]) is MarketRegime.RISK_OFF


def test_regime_fails_safe_on_bad_input():
    # missing/short/non-finite must NOT engage the kill-switch (it only adds restriction)
    assert assess_regime([]) is MarketRegime.NORMAL
    assert assess_regime([100.0]) is MarketRegime.NORMAL
    assert assess_regime([float("nan"), float("inf")]) is MarketRegime.NORMAL


# -- gate --------------------------------------------------------------------

def test_gate_blocks_new_exposure_in_fast_crash():
    g = gate_market_regime(MarketRegime.FAST_RISK_OFF, _intent(reduce_only=False))
    assert g.passed is False and "kill-switch" in g.detail


def test_gate_allows_reduce_only_in_fast_crash():
    assert gate_market_regime(MarketRegime.FAST_RISK_OFF, _intent(reduce_only=True)).passed is True


def test_gate_passes_in_normal_and_risk_off():
    assert gate_market_regime(MarketRegime.NORMAL, _intent()).passed is True
    assert gate_market_regime(MarketRegime.RISK_OFF, _intent()).passed is True  # flagged, tradable


# -- end-to-end through the firewall ----------------------------------------

def test_firewall_killswitch_rejects_fresh_order_in_crash():
    v = Firewall().evaluate(_intent(side=Side.BUY, notional=50.0), _ctx(MarketRegime.FAST_RISK_OFF))
    assert v.decision.value == "REJECT"
    assert v.first_failure.gate == "market_regime"


def test_firewall_killswitch_permits_genuine_de_risk_in_crash():
    long_qty = 5_000.0 / _quote().mid  # a ~$5k long to reduce
    v = Firewall().evaluate(
        _intent(side=Side.SELL, notional=50.0, reduce_only=True),
        _ctx(MarketRegime.FAST_RISK_OFF, position_qty=long_qty, exposure=5_000.0),
    )
    assert v.decision.value == "ALLOW"
