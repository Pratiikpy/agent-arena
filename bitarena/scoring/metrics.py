"""Performance metrics computed from an equity curve or a return series.

Pure NumPy. All functions are defined for short/degenerate inputs (return 0.0 or
an empty array rather than raising), so they are safe to call on an agent that
barely traded.
"""

from __future__ import annotations

import numpy as np


def to_returns(equity: np.ndarray | list[float]) -> np.ndarray:
    """Simple period returns from an equity curve."""
    e = np.asarray(equity, dtype=float)
    if e.size < 2:
        return np.array([], dtype=float)
    prev = e[:-1]
    safe = np.where(prev == 0.0, np.nan, prev)
    return np.nan_to_num(e[1:] / safe - 1.0, nan=0.0)


def total_return(equity: np.ndarray | list[float]) -> float:
    e = np.asarray(equity, dtype=float)
    if e.size < 2 or e[0] == 0:
        return 0.0
    return float(e[-1] / e[0] - 1.0)


def sharpe(returns: np.ndarray | list[float], periods_per_year: float | None = None, rf: float = 0.0) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - rf
    sd = excess.std(ddof=1)
    if sd == 0:
        return 0.0
    s = excess.mean() / sd
    if periods_per_year:
        s *= np.sqrt(periods_per_year)
    return float(s)


def sortino(returns: np.ndarray | list[float], periods_per_year: float | None = None, rf: float = 0.0) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - rf
    downside = excess[excess < 0]
    dd = np.sqrt(np.mean(downside ** 2)) if downside.size else 0.0
    if dd == 0:
        return 0.0
    s = excess.mean() / dd
    if periods_per_year:
        s *= np.sqrt(periods_per_year)
    return float(s)


def max_drawdown(equity: np.ndarray | list[float]) -> float:
    """Worst peak-to-trough decline as a negative fraction (e.g. -0.25)."""
    e = np.asarray(equity, dtype=float)
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(e)
    peak = np.where(peak == 0.0, np.nan, peak)
    dd = (e - peak) / peak
    return float(np.nan_to_num(dd, nan=0.0).min())


def volatility(returns: np.ndarray | list[float], periods_per_year: float | None = None) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    v = r.std(ddof=1)
    if periods_per_year:
        v *= np.sqrt(periods_per_year)
    return float(v)


def win_rate(returns: np.ndarray | list[float]) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    return float((r > 0).mean())


def profit_factor(returns: np.ndarray | list[float]) -> float:
    r = np.asarray(returns, dtype=float)
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def calmar(equity: np.ndarray | list[float]) -> float:
    mdd = abs(max_drawdown(equity))
    if mdd == 0:
        return 0.0
    return total_return(equity) / mdd


def _json_safe(value: float) -> float | None:
    if value is None or np.isnan(value) or np.isinf(value):
        return None
    return round(float(value), 6)


def summarize(equity: np.ndarray | list[float], periods_per_year: float | None = None) -> dict:
    """A JSON-safe metrics summary for the leaderboard (no NaN/inf leaks)."""
    returns = to_returns(equity)
    return {
        "total_return": _json_safe(total_return(equity)),
        "sharpe": _json_safe(sharpe(returns, periods_per_year)),
        "sortino": _json_safe(sortino(returns, periods_per_year)),
        "max_drawdown": _json_safe(max_drawdown(equity)),
        "volatility": _json_safe(volatility(returns, periods_per_year)),
        "win_rate": _json_safe(win_rate(returns)),
        "profit_factor": _json_safe(profit_factor(returns)),
        "calmar": _json_safe(calmar(equity)),
        "periods": int(np.asarray(returns).size),
    }
