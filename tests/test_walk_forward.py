"""Tests for the arena walk-forward robustness harness."""

from __future__ import annotations

from bitarena.connectors import synthetic_series
from bitarena.domain.market import InstrumentType
from bitarena.research import walk_forward_arena


def test_walk_forward_runs_and_aggregates():
    candles = synthetic_series("BTCUSDT", n=600, seed=11, drift=0.001, vol=0.012)
    report = walk_forward_arena(candles, symbol="BTCUSDT", instrument=InstrumentType.PERP, folds=4)
    assert report["folds"] >= 2
    assert "swarm" in report["summary"] and "regime" in report["summary"]
    for s in report["summary"].values():
        assert s["folds"] >= 2
        assert -1.0 <= s["pct_positive_folds"] <= 1.0
        assert s["worst_fold"] <= s["best_fold"]


def test_walk_forward_deterministic():
    candles = synthetic_series("BTCUSDT", n=480, seed=5, drift=0.001, vol=0.01)
    a = walk_forward_arena(candles, symbol="BTCUSDT", folds=3)
    b = walk_forward_arena(candles, symbol="BTCUSDT", folds=3)
    assert a["summary"] == b["summary"]
