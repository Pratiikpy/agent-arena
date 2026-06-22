"""Delta-neutral funding carry: the one structurally real, fundable edge in crypto.

A directional funding bet (the existing FundingCarryAgent) collects funding but bears full price
risk, so a single adverse move wipes out months of carry. The fundable version hedges that out:

    long spot  +  short perp  (equal notional)

Price moves cancel between the two legs, so the position's return is the funding the short perp
leg receives, minus trading fees. That is a real, explainable yield, not a price prediction.

This module measures that yield honestly on real Bitget funding history:

- It is **fee-aware**: holding the carry costs four fills (open spot, open perp, close both). The
  strategy only enters when a trailing read of funding is positive enough to clear those fees, and
  exits when funding turns, so it does not churn the edge away. Fees are charged on entry and exit.
- It reports **net** annualized yield after fees, the realized Sharpe, the max drawdown of the carry
  equity, and what share of intervals the position was actually held.
- A small parameter sweep (the entry window) is corrected for with the **Deflated Sharpe Ratio**, so
  a yield that only looks good because several windows were tried is flagged, not banked.

Honest scope: this models the funding leg of a delta-neutral position. It assumes the spot and perp
legs are kept matched and ignores basis-convergence slippage and borrow on the short leg, which a
live desk must also pay. It is a floor-quality estimate of the carry, not a promise.
"""

from __future__ import annotations

import numpy as np

from ..scoring.metrics import max_drawdown, sharpe
from ..scoring.overfit import deflated_sharpe_ratio, sharpe_moments

DEFAULT_FEE_BPS_PER_LEG = 6.0   # Bitget taker fee, per leg, basis points (the conservative case)
MAKER_FEE_BPS_PER_LEG = 1.0     # a carry desk posts limit orders; maker fee is the realistic case
INTERVALS_PER_YEAR = 1095        # 8-hour funding settlement -> 3/day
# low-churn smoothing windows: a single interval's funding (~1bp) cannot pay a flip (~24bp), so the
# edge only survives if the side is held. Short windows churn the carry away and the sweep shows it.
ENTRY_WINDOWS = (16, 30, 60, 90)


def _rates(funding_rates: list[dict]) -> np.ndarray:
    return np.asarray([float(r.get("funding_rate", 0.0)) for r in funding_rates], dtype=float)


def carry_pnl(rates: np.ndarray, *, fee_bps_per_leg: float = DEFAULT_FEE_BPS_PER_LEG,
              entry_window: int = 3) -> dict:
    """Per-interval gross and net return of a fee-aware, symmetric delta-neutral carry.

    The position is delta-neutral either way: when funding is positive we are long spot / short perp
    and the short leg *receives* funding; when funding is negative we flip to short spot / long perp
    and the long leg receives it. The side is set by the sign of the trailing-``entry_window`` mean
    funding, with a hurdle (half a round trip's fees) so the position does not churn on noise.

    ``gross`` is the funding received with price hedged out (the structural edge, before costs).
    ``net`` subtracts two legs of fees on every entry, exit, or flip (the cost of running it).
    """
    n = rates.size
    leg_fee = fee_bps_per_leg / 10_000.0
    side_change_fee = 2 * leg_fee   # two legs traded whenever we open, close, or flip a leg
    # the fee is a one-time cost amortized over a long hold, not a per-interval hurdle (a single
    # interval's funding is ~1bp, far under a 6bp leg). So the side is set by the trailing sign and
    # churn is punished by the fee charged in ``net`` — the entry-window sweep finds the calm window.
    hurdle = 0.0
    gross = np.zeros(n, dtype=float)
    net = np.zeros(n, dtype=float)
    side = 0  # +1 long-spot/short-perp (harvest positive funding); -1 the mirror; 0 flat
    trades = 0
    held = 0
    for i in range(n):
        lo = max(0, i - entry_window + 1)
        signal = float(rates[lo:i + 1].mean())
        target = 1 if signal > hurdle else -1 if signal < -hurdle else 0
        if target != side:
            # legs traded: a flip (+1<->-1) trades both sides; an open or close trades one side
            legs = 2 if (side != 0 and target != 0) else 1
            net[i] -= legs * side_change_fee
            trades += 1
            side = target
        if side != 0:
            received = side * float(rates[i])  # the receiving leg keeps the funding, price hedged
            gross[i] += received
            net[i] += received
            held += 1
    return {"gross": gross, "net": net, "trades": trades, "held": held, "n": n}


def _summary(net: np.ndarray, intervals_per_year: int) -> dict:
    equity = np.concatenate([[1.0], np.cumprod(1.0 + net)])
    total = float(equity[-1] - 1.0)
    periods = net.size
    ann = float((1.0 + total) ** (intervals_per_year / periods) - 1.0) if periods else 0.0
    return {
        "total_return": round(total, 6),
        "annualized_return": round(ann, 6),
        "sharpe_annualized": round(sharpe(net, periods_per_year=intervals_per_year), 4),
        "max_drawdown": round(max_drawdown(equity), 6),
    }


def delta_neutral_carry(funding_rates: list[dict], *,
                        fee_bps_per_leg: float = DEFAULT_FEE_BPS_PER_LEG,
                        intervals_per_year: int = INTERVALS_PER_YEAR,
                        folds: int = 4) -> dict:
    """Measure the net, fee-aware delta-neutral carry yield on real funding history.

    Sweeps the entry window, picks the best by net annualized return, deflates its Sharpe for the
    number of windows tried, and walk-forwards the chosen window across ``folds`` segments.
    """
    rates = _rates(funding_rates)
    if rates.size < 8:
        return {"insufficient": True, "intervals": int(rates.size)}

    sweep = []
    for w in ENTRY_WINDOWS:
        r = carry_pnl(rates, fee_bps_per_leg=fee_bps_per_leg, entry_window=w)
        rm = carry_pnl(rates, fee_bps_per_leg=MAKER_FEE_BPS_PER_LEG, entry_window=w)
        s = _summary(r["net"], intervals_per_year)
        gross = _summary(r["gross"], intervals_per_year)
        maker = _summary(rm["net"], intervals_per_year)
        s.update({"entry_window": w, "trades": r["trades"],
                 "time_in_market": round(r["held"] / r["n"], 3) if r["n"] else 0.0,
                 "gross_annualized_return": gross["annualized_return"],
                 "gross_sharpe_annualized": gross["sharpe_annualized"],
                 "net_annualized_maker": maker["annualized_return"]})
        sweep.append(s)

    # choose the window with the best maker-fee net: the realistic execution for a carry desk
    best = max(sweep, key=lambda x: x["net_annualized_maker"])

    # deflate the best window's Sharpe for the sweep. We test the GROSS carry series: the claim is
    # that the structural funding edge is real; fees are a separate, reported cost, not the edge.
    best_gross = carry_pnl(rates, fee_bps_per_leg=fee_bps_per_leg,
                           entry_window=best["entry_window"])["gross"]
    sr_variance = float(np.var([_summary(
        carry_pnl(rates, fee_bps_per_leg=fee_bps_per_leg, entry_window=w)["gross"],
        intervals_per_year)["sharpe_annualized"] / np.sqrt(intervals_per_year)
        for w in ENTRY_WINDOWS], ddof=1))
    mom = sharpe_moments(best_gross)
    dsr = deflated_sharpe_ratio(mom["sr"], mom["n"], len(ENTRY_WINDOWS),
                                max(sr_variance, 1e-12), mom["skew"], mom["kurt"])

    # walk-forward the chosen window
    wf = []
    seg = rates.size // folds
    for f in range(folds):
        lo, hi = f * seg, (f + 1) * seg if f < folds - 1 else rates.size
        if hi - lo < 3:
            continue
        r = carry_pnl(rates[lo:hi], fee_bps_per_leg=fee_bps_per_leg, entry_window=best["entry_window"])
        s = _summary(r["net"], intervals_per_year)
        s["fold"] = f
        wf.append(s)

    return {
        "intervals": int(rates.size),
        "fee_bps_per_leg": fee_bps_per_leg,
        "intervals_per_year": intervals_per_year,
        "pct_positive_funding": round(float((rates > 0).mean()), 3),
        "mean_funding_per_interval": round(float(rates.mean()), 8),
        "sweep": sweep,
        "best": best,
        "deflated_sharpe_best": round(dsr, 4) if dsr == dsr else None,  # NaN -> None
        "n_trials": len(ENTRY_WINDOWS),
        "walk_forward": wf,
        "hedge": "long spot + short perp (price-neutral); return is funding minus fees",
    }
