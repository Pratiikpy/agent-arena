"""Tests for the core market value objects (signed math, mid/spread, position PnL)."""

from __future__ import annotations

from bitarena.domain.market import Position, Quote, Side


def test_side_sign():
    assert Side.BUY.sign == 1
    assert Side.SELL.sign == -1


def test_quote_mid_normal_and_one_sided_fallback():
    q = Quote(symbol="BTCUSDT", bid=100.0, ask=102.0, last=101.5, ts=0)
    assert q.mid == 101.0
    one_sided = Quote(symbol="BTCUSDT", bid=0.0, ask=0.0, last=99.0, ts=0)
    assert one_sided.mid == 99.0  # book one-sided -> fall back to last


def test_quote_spread_bps():
    q = Quote(symbol="BTCUSDT", bid=99.95, ask=100.05, last=100.0, ts=0)
    assert abs(q.spread_bps - 10.0) < 1e-6  # (0.10 / 100) * 10_000 = 10 bps
    assert Quote(symbol="BTCUSDT", bid=0.0, ask=0.0, last=100.0, ts=0).spread_bps == 0.0


def test_quote_is_crossed():
    assert Quote(symbol="BTCUSDT", bid=101.0, ask=100.0, last=100.0, ts=0).is_crossed is True
    assert Quote(symbol="BTCUSDT", bid=100.0, ask=100.1, last=100.0, ts=0).is_crossed is False


def test_position_market_value_and_pnl_long_and_short():
    long = Position(symbol="BTCUSDT", qty=0.5, avg_price=100.0)
    assert long.market_value(120.0) == 60.0          # |0.5| * 120
    assert long.unrealized_pnl(120.0) == 10.0         # (120 - 100) * 0.5

    short = Position(symbol="BTCUSDT", qty=-0.5, avg_price=100.0)
    assert short.market_value(120.0) == 60.0          # exposure is absolute
    assert short.unrealized_pnl(120.0) == -10.0       # (120 - 100) * -0.5 -> a short loses as price rises
