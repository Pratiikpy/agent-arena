"""Anti-overfitting statistics: PSR, Deflated Sharpe Ratio, and PBO (CSCV).

Reimplemented from the source papers (formulas are factual content; see NOTICE):
  - Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio".
  - Bailey, Borwein, Lopez de Prado, Zhu (2017), "The Probability of Backtest
    Overfitting" (Combinatorially Symmetric Cross-Validation).

These let the leaderboard separate genuine skill from selection luck: a high
Sharpe found after searching many strategies is discounted (DSR), and a strategy
that wins in-sample but not out-of-sample is flagged (PBO).
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
from scipy.stats import kurtosis as _kurtosis
from scipy.stats import norm
from scipy.stats import rankdata
from scipy.stats import skew as _skew

EULER_MASCHERONI = 0.5772156649015329


def sharpe_moments(returns: np.ndarray | list[float]) -> dict:
    """Per-period Sharpe plus the higher moments PSR needs (skew, Pearson kurtosis)."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return {"sr": 0.0, "n": int(r.size), "skew": 0.0, "kurt": 3.0}
    sd = r.std(ddof=1)
    sr = float(r.mean() / sd) if sd > 0 else 0.0
    return {
        "sr": sr,
        "n": int(r.size),
        "skew": float(_skew(r)),
        "kurt": float(_kurtosis(r, fisher=False)),  # normal == 3.0
    }


def probabilistic_sharpe_ratio(
    sr_hat: float, n: int, sr_benchmark: float = 0.0, skew: float = 0.0, kurt: float = 3.0
) -> float:
    """PSR: probability the true (per-period) Sharpe exceeds ``sr_benchmark``."""
    if n < 2:
        return float("nan")
    # var of the Sharpe estimator (Bailey & Lopez de Prado). A non-positive term means the
    # estimator variance is undefined — return NaN rather than clamping to ~0, which would
    # snap z to +inf and manufacture a false PSR=1.0 for exactly the degenerate fat-tailed
    # high-Sharpe agents PSR is meant to flag.
    var_term = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat ** 2
    if var_term <= 0:
        return float("nan")
    z = (sr_hat - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(var_term)
    return float(norm.cdf(z))


def expected_max_sharpe(sr_variance: float, n_trials: int) -> float:
    """Expected maximum (per-period) Sharpe under the null across ``n_trials``.

    SR0 = sqrt(Var) * [ (1-gamma)*Z(1 - 1/N) + gamma*Z(1 - 1/(N*e)) ].
    """
    if n_trials < 2 or sr_variance <= 0:
        return 0.0
    s = math.sqrt(sr_variance)
    a = norm.ppf(1.0 - 1.0 / n_trials)
    b = norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(s * ((1.0 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b))


def deflated_sharpe_ratio(
    sr_hat: float,
    n: int,
    n_trials: int,
    sr_variance: float,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """DSR: PSR measured against the expected-max-Sharpe of the trial set."""
    sr0 = expected_max_sharpe(sr_variance, n_trials)
    return probabilistic_sharpe_ratio(sr_hat, n, sr_benchmark=sr0, skew=skew, kurt=kurt)


def probability_of_backtest_overfitting(
    returns_matrix: np.ndarray | list[list[float]],
    n_splits: int = 16,
    metric: str = "sharpe",
) -> dict:
    """PBO via CSCV over a (T observations x N strategies) return matrix.

    For each way of splitting the rows into equal in-sample / out-of-sample halves,
    pick the in-sample best strategy and record its out-of-sample relative rank as
    a logit. PBO is the fraction of splits where the in-sample winner lands below
    the out-of-sample median (logit < 0).
    """
    matrix = np.asarray(returns_matrix, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (T observations x N strategies)")
    t, n = matrix.shape
    if n < 2 or n_splits % 2 != 0 or t < n_splits:
        return {"pbo": float("nan"), "n_combinations": 0, "insufficient": True}

    chunks = np.array_split(np.arange(t), n_splits)

    def perf(block: np.ndarray) -> np.ndarray:
        if metric == "sharpe":
            mean = block.mean(axis=0)
            sd = block.std(axis=0, ddof=1)
            sd = np.where(sd == 0, np.nan, sd)
            return np.nan_to_num(mean / sd, nan=0.0)
        return block.mean(axis=0)

    logits: list[float] = []
    for is_sel in combinations(range(n_splits), n_splits // 2):
        is_set = set(is_sel)
        is_rows = np.concatenate([chunks[i] for i in is_sel])
        oos_rows = np.concatenate([chunks[i] for i in range(n_splits) if i not in is_set])
        is_perf = perf(matrix[is_rows, :])
        oos_perf = perf(matrix[oos_rows, :])
        best = int(np.argmax(is_perf))
        # tie-averaged ranks: a flat/no-information matrix yields rank ~ (n+1)/2 for every
        # strategy, so omega ~ 0.5 and PBO ~ 0.5 (correct), not a confident PBO=1.0.
        rank = rankdata(oos_perf, method="average")  # 1..n, ascending
        omega = rank[best] / (n + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1.0 - omega)))

    arr = np.array(logits)
    return {
        "pbo": float((arr < 0).mean()),
        "n_combinations": len(arr),
        "median_logit": float(np.median(arr)),
        "insufficient": False,
    }
