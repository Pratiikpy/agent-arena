"""Tests for performance metrics and anti-overfitting statistics."""

from __future__ import annotations

import numpy as np

from bitarena.scoring import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    max_drawdown,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe,
    sharpe_moments,
    summarize,
    total_return,
    win_rate,
)


def test_total_return_and_drawdown():
    eq = [100.0, 110.0, 90.0, 120.0]
    assert abs(total_return(eq) - 0.20) < 1e-9
    # worst trough is 90 from peak 110 -> -18.18%
    assert abs(max_drawdown(eq) - (90.0 / 110.0 - 1.0)) < 1e-9


def test_sharpe_zero_for_constant_returns():
    assert sharpe([0.01, 0.01, 0.01]) == 0.0  # no variance
    assert win_rate([0.01, -0.02, 0.03, 0.0]) == 0.5


def test_sharpe_positive_for_upward_noisy():
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, 500)
    assert sharpe(r) > 0


def test_psr_monotonic_and_bounded():
    assert probabilistic_sharpe_ratio(0.0, 100) == 0.5  # SR==benchmark -> 0.5
    strong = probabilistic_sharpe_ratio(0.3, 500)
    weak = probabilistic_sharpe_ratio(0.05, 500)
    assert 0.0 <= weak < strong <= 1.0


def test_psr_matches_bailey_lopez_de_prado_reference():
    # PSR(SR*) = Phi( (SR - SR*) * sqrt(n-1) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) ).
    # Hand-computed references (not the implementation), so this proves the formula, not just bounds:
    #   SR=0.5, n=10, skew=0, kurt=3 -> var=1.125, z=1.41421 -> Phi=0.921350
    assert abs(probabilistic_sharpe_ratio(0.5, 10, sr_benchmark=0.0, skew=0.0, kurt=3.0) - 0.921350) < 1e-5
    #   SR=1.0, n=25, skew=-0.5, kurt=4 -> var=1.75, z=3.70329 -> Phi=0.999455
    assert abs(probabilistic_sharpe_ratio(1.0, 25, sr_benchmark=0.0, skew=-0.5, kurt=4.0) - 0.999455) < 1e-5


def test_expected_max_sharpe_increases_with_trials():
    a = expected_max_sharpe(0.01, 10)
    b = expected_max_sharpe(0.01, 1000)
    assert 0 < a < b


def test_dsr_deflates_relative_to_psr():
    moments = dict(sr_hat=0.20, n=500, skew=0.0, kurt=3.0)
    psr = probabilistic_sharpe_ratio(0.20, 500)
    dsr = deflated_sharpe_ratio(n_trials=200, sr_variance=0.02, **moments)
    assert dsr < psr  # multiple-testing deflation lowers confidence


def test_sharpe_moments_shape():
    rng = np.random.default_rng(1)
    m = sharpe_moments(rng.normal(0, 0.01, 100))
    assert set(m) == {"sr", "n", "skew", "kurt"} and m["n"] == 100


def test_pbo_low_for_genuinely_skilled_strategy():
    rng = np.random.default_rng(3)
    noise = rng.normal(0.0, 0.01, (240, 6))
    noise[:, 0] += 0.005  # strategy 0 has a real, persistent edge
    res = probability_of_backtest_overfitting(noise, n_splits=8)
    assert not res["insufficient"]
    assert res["pbo"] < 0.2


def test_pbo_higher_for_noise_than_for_skill():
    # A single pure-noise draw is a noisy PBO estimate (one column always has the
    # best in-sample mean by chance). The robust, theory-backed property is that
    # noise is *more* overfit-prone than a real edge — averaged over draws.
    noise_pbos = []
    for seed in range(6):
        rng = np.random.default_rng(100 + seed)
        noise = rng.normal(0.0, 0.01, (240, 12))
        noise_pbos.append(probability_of_backtest_overfitting(noise, n_splits=8)["pbo"])
    mean_noise_pbo = float(np.mean(noise_pbos))

    rng = np.random.default_rng(3)
    skilled = rng.normal(0.0, 0.01, (240, 12))
    skilled[:, 0] += 0.005
    skilled_pbo = probability_of_backtest_overfitting(skilled, n_splits=8)["pbo"]

    assert mean_noise_pbo > 0.3
    assert mean_noise_pbo > skilled_pbo


def test_pbo_insufficient_data_flag():
    res = probability_of_backtest_overfitting(np.zeros((4, 3)), n_splits=10)
    assert res["insufficient"] is True


def test_summarize_is_json_safe():
    s = summarize([100, 101, 102, 101.5])
    assert all((v is None) or isinstance(v, (int, float)) for v in s.values())
