"""Tests for the funding-carry walk-forward characterization (structure + determinism)."""

from __future__ import annotations

from bitarena.connectors import synthetic_series
from bitarena.research import funding_agent_walk_forward


def _candles_and_funding(n=300, seed=4):
    candles = synthetic_series("BTCUSDT", n=n, seed=seed, drift=0.0005, vol=0.01)
    # a funding entry every ~8 bars, alternating sign, with ts on the candle timeline
    funding = [
        {"ts": candles[i].ts, "funding_rate": 0.0003 if (i // 8) % 2 else -0.0003}
        for i in range(0, n, 8)
    ]
    return candles, funding


def test_funding_walk_forward_structure():
    candles, funding = _candles_and_funding()
    r = funding_agent_walk_forward(candles, funding, folds=5)
    assert r["folds"] >= 2 and len(r["per_fold"]) == r["folds"]
    assert 0.0 <= r["beats_buyhold_rate"] <= 1.0
    for row in r["per_fold"]:
        assert set(row) >= {"fold", "bars", "settlements", "funding_carry_return", "buyhold_return", "excess", "carry_usd"}
        assert row["settlements"] >= 0


def test_funding_walk_forward_deterministic():
    candles, funding = _candles_and_funding()
    a = funding_agent_walk_forward(candles, funding, folds=4)
    b = funding_agent_walk_forward(candles, funding, folds=4)
    assert a == b
