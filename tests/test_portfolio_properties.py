"""Property/fuzz tests for portfolio accounting — the financial-correctness core.

If accounting leaks value, every leaderboard number is wrong. These prove conservation
over random fill sequences: a fill at mark price moves equity by exactly minus the fee
(long or short), position tracks signed fills, and a round-trip costs only fees.
"""

from __future__ import annotations

import math
import random

from bitarena.arena.portfolio import Portfolio
from bitarena.connectors.base import OrderResult
from bitarena.domain.market import InstrumentType, Side


def _fill(side: Side, qty: float, price: float, fee: float) -> OrderResult:
    return OrderResult(
        accepted=True, symbol="BTCUSDT", side=side, instrument=InstrumentType.PERP,
        filled_qty=qty, avg_price=price, notional_usd=qty * price, fee_usd=fee,
        order_id="x", ts=0,
    )


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * (1.0 + abs(b))


def test_fill_changes_equity_by_exactly_minus_fee():
    rng = random.Random(1)
    for _ in range(2_000):
        pf = Portfolio(agent_id="t", starting_cash=10_000.0)
        price = rng.uniform(100.0, 70_000.0)  # evaluate conservation at the fill price
        for _ in range(rng.randint(1, 8)):
            side = rng.choice([Side.BUY, Side.SELL])
            fee = rng.uniform(0.0, 5.0)
            eq_before = pf.equity(price)
            pf.apply_fill(_fill(side, rng.uniform(0.001, 1.0), price, fee))
            assert _close(pf.equity(price), eq_before - fee)


def test_equity_is_cash_plus_position_value():
    rng = random.Random(2)
    for _ in range(1_000):
        pf = Portfolio(agent_id="t", starting_cash=rng.uniform(1_000.0, 50_000.0))
        for _ in range(rng.randint(0, 6)):
            pf.apply_fill(_fill(rng.choice([Side.BUY, Side.SELL]), rng.uniform(0.001, 1.0),
                                rng.uniform(100.0, 70_000.0), rng.uniform(0.0, 3.0)))
        mark_price = rng.uniform(100.0, 70_000.0)
        assert _close(pf.equity(mark_price), pf.cash_usd + pf.position_qty * mark_price)


def test_position_tracks_signed_fills():
    rng = random.Random(3)
    for _ in range(1_000):
        pf = Portfolio(agent_id="t", starting_cash=10_000.0)
        expected = 0.0
        for _ in range(rng.randint(1, 10)):
            side = rng.choice([Side.BUY, Side.SELL])
            qty = rng.uniform(0.001, 1.0)
            expected += qty if side is Side.BUY else -qty
            pf.apply_fill(_fill(side, qty, rng.uniform(100.0, 70_000.0), rng.uniform(0.0, 2.0)))
        assert abs(pf.position_qty - expected) < 1e-9


def test_round_trip_costs_only_fees():
    rng = random.Random(4)
    for _ in range(1_000):
        start = rng.uniform(1_000.0, 50_000.0)
        pf = Portfolio(agent_id="t", starting_cash=start)
        price, qty = rng.uniform(100.0, 70_000.0), rng.uniform(0.001, 1.0)
        f1, f2 = rng.uniform(0.0, 5.0), rng.uniform(0.0, 5.0)
        pf.apply_fill(_fill(Side.BUY, qty, price, f1))
        pf.apply_fill(_fill(Side.SELL, qty, price, f2))
        assert abs(pf.position_qty) < 1e-12
        assert _close(pf.equity(price), start - f1 - f2)
        assert _close(pf.fees_paid, f1 + f2)


def test_mark_appends_and_returns_equity():
    pf = Portfolio(agent_id="t", starting_cash=10_000.0)
    assert pf.equity_curve == [10_000.0]
    pf.apply_fill(_fill(Side.BUY, 0.1, 50_000.0, 1.0))
    val = pf.mark(50_000.0)
    assert pf.equity_curve[-1] == val and len(pf.equity_curve) == 2
    assert _close(val, 10_000.0 - 1.0)  # bought at mark -> only the fee is lost


def test_funding_settles_by_position_sign():
    price = 50_000.0
    # long pays when rate > 0
    long_pf = Portfolio(agent_id="t", starting_cash=10_000.0)
    long_pf.apply_fill(_fill(Side.BUY, 0.1, price, 0.0))
    eq = long_pf.equity(price)
    cf = long_pf.apply_funding(0.0001, price)
    assert cf < 0 and _close(long_pf.equity(price), eq + cf) and _close(long_pf.funding_received, cf)
    # short receives when rate > 0
    short_pf = Portfolio(agent_id="t", starting_cash=10_000.0)
    short_pf.apply_fill(_fill(Side.SELL, 0.1, price, 0.0))
    assert short_pf.apply_funding(0.0001, price) > 0
    # a flat book is unaffected
    assert Portfolio(agent_id="t", starting_cash=10_000.0).apply_funding(0.005, price) == 0.0


def test_funding_conserves_equity_over_random_settlements():
    rng = random.Random(8)
    for _ in range(1_000):
        pf = Portfolio(agent_id="t", starting_cash=10_000.0)
        price = rng.uniform(100.0, 70_000.0)
        for _ in range(rng.randint(0, 4)):
            pf.apply_fill(_fill(rng.choice([Side.BUY, Side.SELL]), rng.uniform(0.001, 1.0), price, rng.uniform(0.0, 2.0)))
        rate = rng.uniform(-0.01, 0.01)
        eq_before = pf.equity(price)
        cf = pf.apply_funding(rate, price)
        assert _close(pf.equity(price), eq_before + cf)
        assert _close(cf, -pf.position_qty * price * rate)
        assert math.isfinite(pf.equity(price))
