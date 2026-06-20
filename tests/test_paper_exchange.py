"""Tests for the paper exchange, replay data, and synthetic series determinism."""

from __future__ import annotations

from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.market import Side


def test_synthetic_series_is_deterministic():
    a = synthetic_series("BTCUSDT", n=100, seed=7)
    b = synthetic_series("BTCUSDT", n=100, seed=7)
    assert [c.close for c in a] == [c.close for c in b]
    c = synthetic_series("BTCUSDT", n=100, seed=8)
    assert [x.close for x in a] != [x.close for x in c]
    assert len(a) == 100 and all(x.high >= x.low for x in a)


def test_replay_advance_and_window():
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=50, seed=1)}
    md = ReplayMarketData(series)
    assert md.length == 50 and md.cursor == 0
    q0 = md.get_quote("btcusdt")
    assert q0 is not None and q0.ask > q0.bid
    assert len(md.get_candles("BTCUSDT", limit=10)) == 1  # only bar 0 visible
    md.advance()
    assert md.cursor == 1 and len(md.get_candles("BTCUSDT", limit=10)) == 2
    md.set_cursor(49)
    assert md.advance() is False  # at the end


def test_paper_buy_fills_above_mid_with_fee():
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=10, start_price=100.0, seed=1)}
    md = ReplayMarketData(series, spread_bps=4.0)
    px = PaperExchange(md, taker_fee_bps=6.0)
    q = md.get_quote("BTCUSDT")
    r = px.place_order(symbol="BTCUSDT", side=Side.BUY, notional_usd=1_000.0)
    assert r.accepted
    assert r.avg_price > q.mid  # crossed the spread + slippage
    assert abs(r.filled_qty - 1_000.0 / r.avg_price) < 1e-9
    assert abs(r.fee_usd - 1_000.0 * 6.0 / 10_000.0) < 1e-9


def test_paper_sell_fills_below_mid():
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=10, seed=1)}
    md = ReplayMarketData(series, spread_bps=4.0)
    px = PaperExchange(md)
    q = md.get_quote("BTCUSDT")
    r = px.place_order(symbol="BTCUSDT", side=Side.SELL, notional_usd=500.0)
    assert r.accepted and r.avg_price < q.mid


def test_paper_rejects_unknown_symbol():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=5, seed=1)})
    px = PaperExchange(md)
    r = px.place_order(symbol="DOGEUSDT", side=Side.BUY, notional_usd=100.0)
    assert not r.accepted and r.error


def test_paper_rejects_non_positive_notional():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=5, seed=1)})
    px = PaperExchange(md)
    assert not px.place_order(symbol="BTCUSDT", side=Side.BUY, notional_usd=0.0).accepted
    r = px.place_order(symbol="BTCUSDT", side=Side.BUY, notional_usd=-50.0)
    assert not r.accepted and "notional" in (r.error or "")


def test_paper_exchange_market_passthroughs():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=8, seed=1)})
    px = PaperExchange(md)
    assert px.get_quote("BTCUSDT") is not None
    assert len(px.get_candles("BTCUSDT", limit=5)) == 1  # cursor at bar 0


def test_replay_symbols_and_empty_for_unknown():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=5, seed=1)})
    assert md.symbols == ["BTCUSDT"]
    assert md.get_candles("UNKNOWN") == []
