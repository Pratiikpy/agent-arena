"""Edge-case tests for the anti-overfitting statistics (PSR / DSR / PBO)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bitarena.scoring.overfit import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_moments,
)


def test_sharpe_moments_degenerate_and_normal():
    assert sharpe_moments([]) == {"sr": 0.0, "n": 0, "skew": 0.0, "kurt": 3.0}
    assert sharpe_moments([0.01])["n"] == 1  # single observation -> safe defaults
    m = sharpe_moments([0.01, -0.005, 0.02, 0.0, 0.015])
    assert m["n"] == 5 and isinstance(m["sr"], float)


def test_psr_bounds_and_insufficient():
    assert math.isnan(probabilistic_sharpe_ratio(0.1, 1))  # n < 2 -> nan
    assert 0.0 <= probabilistic_sharpe_ratio(0.2, 100) <= 1.0


def test_expected_max_sharpe_edges():
    assert expected_max_sharpe(0.0, 10) == 0.0   # zero variance -> 0
    assert expected_max_sharpe(0.04, 1) == 0.0   # < 2 trials -> 0
    assert expected_max_sharpe(0.04, 50) > 0.0   # grows with the number of trials searched


def test_dsr_is_discounted_versus_plain_psr():
    # DSR measures the Sharpe against the expected MAX over the trial set (> 0),
    # so it must be <= PSR measured against a zero benchmark.
    psr0 = probabilistic_sharpe_ratio(0.3, 200)
    dsr = deflated_sharpe_ratio(0.3, 200, n_trials=20, sr_variance=0.02)
    assert dsr <= psr0 + 1e-9


def test_pbo_raises_on_non_2d_and_flags_insufficient():
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(np.array([1.0, 2.0, 3.0]))  # 1-D input
    res = probability_of_backtest_overfitting(np.zeros((8, 1)))  # only one strategy
    assert res["insufficient"] is True


def test_pbo_on_clean_matrix_is_in_range():
    rng = np.random.default_rng(0)
    mat = rng.normal(0.0, 0.01, size=(64, 4))
    res = probability_of_backtest_overfitting(mat, n_splits=8)
    assert res["insufficient"] is False
    assert 0.0 <= res["pbo"] <= 1.0
    assert res["n_combinations"] == 70  # C(8, 4)
