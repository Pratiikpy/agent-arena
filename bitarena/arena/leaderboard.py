"""Leaderboard construction and the cross-agent overfitting check.

Agents are ranked by per-period Sharpe (tie-broken by total return). Each row also
carries PSR (probability the Sharpe beats zero). A separate cross-agent PBO answers
a sharper question: if you picked the in-sample best agent, how likely is that choice
to be overfit rather than skilled?
"""

from __future__ import annotations

import math

import numpy as np

from ..scoring.metrics import summarize, to_returns
from ..scoring.overfit import (
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
    probability_of_backtest_overfitting,
    sharpe_moments,
)
from .portfolio import Portfolio

_NEG_INF = float("-inf")


def _sparkline(curve: list[float], points: int = 32) -> list[float]:
    """Evenly-downsampled equity curve for an inline UI sparkline — the agent's *real* path,
    not a synthesized shape. Returns the curve as-is when it is already short enough."""
    if not curve:
        return []
    if len(curve) <= points:
        return [round(float(x), 2) for x in curve]
    step = (len(curve) - 1) / (points - 1)
    return [round(float(curve[round(i * step)]), 2) for i in range(points)]


def build_leaderboard(portfolios: dict[str, Portfolio], periods_per_year: float | None = None) -> list[dict]:
    rows: list[dict] = []
    moments_by_id: dict[str, dict] = {}
    for agent_id, pf in portfolios.items():
        metrics = summarize(pf.equity_curve, periods_per_year)
        returns = to_returns(pf.equity_curve)
        moments = sharpe_moments(returns)
        moments_by_id[agent_id] = moments
        psr = probabilistic_sharpe_ratio(moments["sr"], moments["n"], skew=moments["skew"], kurt=moments["kurt"])
        rows.append(
            {
                "agent_id": agent_id,
                "final_equity": round(pf.equity_curve[-1], 2),
                "trades": pf.trades,
                "fees_usd": round(pf.fees_paid, 2),
                "psr": None if math.isnan(psr) else round(psr, 4),
                "equity_sparkline": _sparkline(pf.equity_curve),
                **metrics,
            }
        )

    # Deflate every agent's Sharpe against the expected-max-Sharpe of THIS trial set (the agents
    # themselves): an agent whose Sharpe is no better than the luckiest draw across N competitors
    # is flagged as selection luck, not skill. This is what makes the overfit math *load-bearing* —
    # it carries a per-row verdict and breaks Sharpe ties — rather than a printed-once diagnostic.
    srs = [moments_by_id[r["agent_id"]]["sr"] for r in rows]
    n_trials = len(rows)
    sr_variance = float(np.var(srs, ddof=1)) if n_trials > 1 else 0.0
    for r in rows:
        m = moments_by_id[r["agent_id"]]
        dsr = deflated_sharpe_ratio(m["sr"], m["n"], n_trials, sr_variance, skew=m["skew"], kurt=m["kurt"])
        r["dsr"] = None if math.isnan(dsr) else round(dsr, 4)
        # DSR >= 0.95: the Sharpe survives the multiple-testing bar (genuine skill). Below: not
        # distinguishable from the luckiest-of-N draw — the ranking treats it as luck, honestly.
        r["skill_significant"] = bool(r["dsr"] is not None and r["dsr"] >= 0.95)

    # Rank by Sharpe, but break ties by DSR (skill over luck) before raw return — so the
    # verification layer visibly shapes the order, not just an appended column.
    rows.sort(key=lambda r: (r["sharpe"] if r["sharpe"] is not None else _NEG_INF,
                             r["dsr"] if r.get("dsr") is not None else _NEG_INF,
                             r["total_return"] if r["total_return"] is not None else _NEG_INF),
              reverse=True)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


def cross_agent_pbo(portfolios: dict[str, Portfolio], n_splits: int = 10) -> dict:
    """PBO over the per-tick returns of all agents (overfitting of 'pick the winner')."""
    curves = [to_returns(pf.equity_curve) for pf in portfolios.values()]
    lengths = {len(c) for c in curves}
    if len(curves) < 2 or len(lengths) != 1 or curves[0].size < n_splits:
        return {"pbo": None, "insufficient": True, "n_combinations": 0}
    matrix = np.column_stack(curves)
    result = probability_of_backtest_overfitting(matrix, n_splits=n_splits)
    if result.get("insufficient"):
        return {"pbo": None, "insufficient": True, "n_combinations": 0}
    return {"pbo": round(result["pbo"], 4), "insufficient": False, "n_combinations": result["n_combinations"]}
