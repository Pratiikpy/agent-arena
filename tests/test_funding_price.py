"""Tests for funding-settlement price interpolation across candle gaps (audit A7)."""

from __future__ import annotations

from bitarena.arena.engine import _funding_price


def test_interpolates_at_midpoint():
    # prev=(1000, 100), current=(2000, 200); a funding due at 1500 settles at 150, not 200
    assert _funding_price(1500, 1000, 100.0, 200.0, 2000) == 150.0


def test_no_prev_candle_uses_current_price():
    assert _funding_price(1500, None, None, 200.0, 2000) == 200.0


def test_funding_before_prev_uses_prev_price():
    assert _funding_price(500, 1000, 100.0, 200.0, 2000) == 100.0


def test_clamps_beyond_current_candle():
    assert _funding_price(9999, 1000, 100.0, 200.0, 2000) == 200.0


def test_gap_settles_each_interval_at_its_own_price():
    # a gap spanning three funding intervals must NOT settle them all at the latest price
    prices = [_funding_price(t, 0, 100.0, 130.0, 3000) for t in (1000, 2000, 3000)]
    assert prices[0] < prices[1] < prices[2] == 130.0
    assert len(set(prices)) == 3  # three distinct prices, not one repeated latest price
