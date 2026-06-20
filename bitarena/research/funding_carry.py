"""Funding-carry edge study — the one structurally-real crypto edge.

A delta-neutral position (long spot + short perp at equal notional) is price-neutral
and collects the perpetual funding the short leg receives when funding is positive.
Per funding interval the strategy return is approximately the funding rate. This is a
market-microstructure fact, not a pattern fit to the past.

We validate honestly: passive carry, an adaptive threshold sweep (hold only when
funding clears a threshold), a Deflated Sharpe that accounts for the small parameter
search, and walk-forward segments to check stability across time.
"""

from __future__ import annotations

import numpy as np

from ..scoring.metrics import max_drawdown, sharpe, win_rate
from ..scoring.overfit import deflated_sharpe_ratio, probabilistic_sharpe_ratio, sharpe_moments

INTERVALS_PER_YEAR = 1095.0  # funding settles every 8h -> ~3/day


def carry_returns(funding_rates, *, adaptive: bool = False, threshold: float = 0.0) -> np.ndarray:
    """Per-interval return of a delta-neutral short-perp/long-spot carry.

    The short perp receives funding when the rate is positive, so the per-interval
    return is the funding rate. ``adaptive`` holds only when funding exceeds
    ``threshold`` (else flat -> 0 return for that interval).
    """
    fr = np.asarray(funding_rates, dtype=float)
    if adaptive:
        return np.where(fr > threshold, fr, 0.0)
    return fr.copy()


def equity_curve(returns, start: float = 1.0) -> np.ndarray:
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return np.array([start], dtype=float)
    return np.concatenate([[start], start * np.cumprod(1.0 + r)])


def _metrics(returns) -> dict:
    r = np.asarray(returns, dtype=float)
    eq = equity_curve(r)
    n = int(r.size)
    growth = float(eq[-1] / eq[0]) if eq.size > 1 and eq[0] > 0 else 1.0
    ann_return = float(growth ** (INTERVALS_PER_YEAR / n) - 1.0) if n > 0 and growth > 0 else 0.0
    m = sharpe_moments(r)
    psr = probabilistic_sharpe_ratio(m["sr"], m["n"], skew=m["skew"], kurt=m["kurt"])
    return {
        "intervals": n,
        "total_return": round(growth - 1.0, 6),
        "annualized_return": round(ann_return, 6),
        "sharpe_annualized": round(sharpe(r, periods_per_year=INTERVALS_PER_YEAR), 4),
        "max_drawdown": round(max_drawdown(eq), 6),
        "pct_positive": round(win_rate(r), 4),
        "psr": None if psr != psr else round(psr, 4),
        "sr_per_period": round(m["sr"], 6),
    }


def walk_forward(funding_rates, *, folds: int = 4, adaptive: bool = False, threshold: float = 0.0) -> list[dict]:
    fr = np.asarray(funding_rates, dtype=float)
    if fr.size < folds * 5:
        return []
    out = []
    for i, seg in enumerate(np.array_split(fr, folds)):
        metrics = _metrics(carry_returns(seg, adaptive=adaptive, threshold=threshold))
        metrics["fold"] = i + 1
        out.append(metrics)
    return out


def study(funding_rates, *, thresholds=(0.0, 0.00005, 0.0001, 0.0002), folds: int = 4) -> dict:
    """Full honest carry study: passive, adaptive sweep, Deflated Sharpe, walk-forward."""
    fr = np.asarray(funding_rates, dtype=float)
    passive = _metrics(carry_returns(fr))

    sweep = []
    srs = []
    for t in thresholds:
        r = carry_returns(fr, adaptive=True, threshold=t)
        srs.append(sharpe_moments(r)["sr"])
        entry = _metrics(r)
        entry["threshold"] = t
        sweep.append(entry)
    best = max(sweep, key=lambda s: (s["sharpe_annualized"] if s["sharpe_annualized"] is not None else -9.0))

    bm = sharpe_moments(carry_returns(fr, adaptive=True, threshold=best["threshold"]))
    sr_var = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0  # sample variance (ddof=1), matches DSR convention
    dsr = deflated_sharpe_ratio(bm["sr"], bm["n"], len(thresholds), sr_var, skew=bm["skew"], kurt=bm["kurt"])

    return {
        "intervals": int(fr.size),
        "pct_positive_funding": round(float((fr > 0).mean()), 4) if fr.size else None,
        "mean_funding_per_interval": round(float(fr.mean()), 8) if fr.size else None,
        "passive_carry": passive,
        "adaptive_sweep": sweep,
        "adaptive_best": best,
        "deflated_sharpe_best": None if dsr != dsr else round(dsr, 4),
        "n_trials": len(thresholds),
        "walk_forward_passive": walk_forward(fr, folds=folds),
    }
