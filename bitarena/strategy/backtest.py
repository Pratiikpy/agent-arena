"""Backtest gate for a generated strategy: it must run clean over a price path and actually trade
before it is allowed to compete. Returns trades, total return, and Sharpe; ``admit`` is the bar.
"""

from __future__ import annotations

import numpy as np


def backtest(decide, prices: list[float], *, warmup: int = 20, fee_bps: float = 2.0) -> dict:
    """Replay ``decide`` bar-by-bar over ``prices`` and report how it would have traded.

    The strategy returns a target exposure in [-1, 1] each bar; turnover pays a fee. Any runtime
    error during replay fails the backtest (``ok=False``) rather than admitting a broken strategy.
    """
    prices = [float(p) for p in prices]
    if len(prices) <= warmup + 2:
        return {"ok": False, "error": "not enough price history", "trades": 0}

    equity, pos, trades = 1.0, 0.0, 0
    curve = [equity]
    for t in range(warmup, len(prices) - 1):
        obs = {"price": prices[t], "prices": prices[: t + 1], "position": pos, "equity": equity * 10_000.0}
        try:
            sig = float(decide(obs))
        except Exception as exc:  # a strategy that throws mid-run is not admissible
            return {"ok": False, "error": f"runtime error during backtest: {exc}", "trades": trades}
        if sig != sig:  # NaN guard
            return {"ok": False, "error": "strategy returned NaN", "trades": trades}
        sig = max(-1.0, min(1.0, sig))
        if abs(sig - pos) > 1e-9:
            trades += 1
            equity *= 1.0 - (fee_bps / 10_000.0) * abs(sig - pos)  # turnover cost
        pos = sig
        equity *= 1.0 + pos * (prices[t + 1] / prices[t] - 1.0)
        curve.append(equity)

    arr = np.asarray(curve, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    sd = float(np.std(rets, ddof=1)) if rets.size > 1 else 0.0
    sharpe = float(np.mean(rets) / sd * np.sqrt(rets.size)) if sd > 0 else 0.0
    return {
        "ok": True,
        "trades": trades,
        "total_return": round(float(arr[-1] - 1.0), 4),
        "sharpe": round(sharpe, 3),
        "bars": int(arr.size),
    }


def admit(result: dict, *, min_trades: int = 2) -> bool:
    """Admission bar: it ran clean and it actually traded (a flat strategy is not a strategy)."""
    return bool(result.get("ok")) and int(result.get("trades", 0)) >= min_trades
