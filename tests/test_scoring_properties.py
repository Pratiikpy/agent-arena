"""Property/fuzz tests for the scoring + anti-overfitting math.

These statistics underpin the "honest, overfit-aware scoring" half of the thesis, so
their mathematical invariants must hold over the input space — probabilities stay in
[0,1], deflation never *raises* confidence, drawdown stays in [-1,0], and summaries are
always JSON-safe (no NaN/inf leaking into the API).
"""

from __future__ import annotations

import math
import random

import numpy as np

from bitarena.scoring import (
    deflated_sharpe_ratio,
    max_drawdown,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
    summarize,
    win_rate,
)


def test_psr_always_in_unit_interval():
    rng = random.Random(1)
    for _ in range(2_000):
        p = probabilistic_sharpe_ratio(
            rng.uniform(-2.0, 2.0), rng.randint(5, 2_000),
            skew=rng.uniform(-3.0, 3.0), kurt=rng.uniform(1.6, 12.0),
        )
        assert math.isfinite(p) and 0.0 <= p <= 1.0


def test_dsr_bounded_and_never_exceeds_psr():
    # Deflated Sharpe deflates the benchmark above 0 for >=1 trials, so it can never be
    # more confident than the plain PSR. This is the core anti-overfit guarantee.
    rng = random.Random(2)
    for _ in range(2_000):
        sr = rng.uniform(-1.0, 2.0)
        n = rng.randint(30, 2_000)
        skew = rng.uniform(-2.0, 2.0)
        kurt = rng.uniform(2.0, 10.0)
        psr = probabilistic_sharpe_ratio(sr, n, skew=skew, kurt=kurt)
        dsr = deflated_sharpe_ratio(
            sr_hat=sr, n=n, n_trials=rng.randint(1, 500),
            sr_variance=rng.uniform(1e-6, 0.1), skew=skew, kurt=kurt,
        )
        if math.isfinite(dsr):
            assert 0.0 <= dsr <= 1.0
            assert dsr <= psr + 1e-9


def test_max_drawdown_in_minus_one_to_zero():
    rng = random.Random(3)
    for _ in range(1_000):
        n = rng.randint(2, 200)
        eq = np.cumprod(1.0 + np.array([rng.uniform(-0.2, 0.2) for _ in range(n)])) * 100.0
        eq = np.clip(eq, 1e-6, None)
        dd = max_drawdown(eq)
        assert -1.0 - 1e-9 <= dd <= 1e-9


def test_win_rate_in_unit_interval():
    rng = random.Random(4)
    for _ in range(1_000):
        rets = [rng.uniform(-0.1, 0.1) for _ in range(rng.randint(1, 300))]
        assert 0.0 <= win_rate(rets) <= 1.0


def test_pbo_bounded_or_insufficient():
    rng = random.Random(5)
    for _ in range(60):
        rows = rng.randint(20, 240)
        cols = rng.randint(2, 12)
        mat = np.array([[rng.gauss(0.0, 0.01) for _ in range(cols)] for _ in range(rows)])
        res = probability_of_backtest_overfitting(mat, n_splits=rng.choice([4, 6, 8]))
        if not res.get("insufficient"):
            assert 0.0 <= res["pbo"] <= 1.0


def test_summarize_is_always_json_safe_incl_degenerate():
    rng = random.Random(6)
    curves = [[100.0], [100.0, 100.0, 100.0], [100.0, 101.0]]
    for _ in range(300):
        n = rng.randint(1, 120)
        curves.append([100.0 + sum(rng.uniform(-1.0, 1.0) for _ in range(k)) for k in range(1, n + 1)])
    for eq in curves:
        s = summarize(eq)
        for v in s.values():
            assert v is None or (isinstance(v, (int, float)) and math.isfinite(v))
