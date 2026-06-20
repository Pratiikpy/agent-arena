"""Walk-forward characterization of the funding-carry agent's edge.

The funding-carry agent ranks top-3 by Sharpe on single windows across BTC/ETH/SOL — but
is that time-stable or window-specific? This splits one symbol's real history into
disjoint folds and, on each, runs the funding-carry agent against buy-hold with the
funding subset that overlaps that fold, reporting the per-fold excess return, how often it
beats buy-hold, and the real carry collected. Honest: if it only wins in one fold, say so.
"""

from __future__ import annotations

import numpy as np

from ..agents import BuyAndHold, FundingCarryAgent
from ..arena import Arena
from ..connectors import PaperExchange, ReplayMarketData
from ..domain.market import InstrumentType
from ..firewall import Firewall, Signer


def funding_agent_walk_forward(candles, funding, *, folds: int = 5, symbol: str = "BTCUSDT") -> dict:
    candles = list(candles)
    funding = list(funding or [])
    n = len(candles)
    if n < folds * 10:
        folds = max(2, n // 10) if n >= 20 else 1
    fold_size = max(1, n // folds)
    fw = Firewall(Signer.generate())

    rows = []
    for f in range(folds):
        start = f * fold_size
        seg = candles[start:] if f == folds - 1 else candles[start:start + fold_size]
        if len(seg) < 10:
            continue
        lo, hi = seg[0].ts, seg[-1].ts
        fund_seg = [r for r in funding if lo <= r.get("ts", -1) <= hi]
        md = ReplayMarketData({symbol: seg})
        arena = Arena(
            agents=[FundingCarryAgent(fund_seg), BuyAndHold()],
            exchange=PaperExchange(md), market=md, symbol=symbol,
            firewall=fw, signer=fw._signer, instrument=InstrumentType.PERP,
            starting_cash=10_000.0, funding=fund_seg,
        )
        res = arena.run()
        lb = {r["agent_id"]: r for r in res["leaderboard"]}
        fc_ret = lb.get("funding-carry", {}).get("total_return") or 0.0
        bh_ret = lb.get("benchmark-buyhold", {}).get("total_return") or 0.0
        rows.append({
            "fold": f + 1,
            "bars": len(seg),
            "settlements": res["funding_settlements"],
            "funding_carry_return": round(fc_ret, 5),
            "buyhold_return": round(bh_ret, 5),
            "excess": round(fc_ret - bh_ret, 5),
            "carry_usd": round(res["funding_received"].get("funding-carry", 0.0), 4),
        })

    excess = np.array([r["excess"] for r in rows], dtype=float)
    return {
        "folds": len(rows),
        "per_fold": rows,
        "mean_excess_vs_buyhold": round(float(excess.mean()), 5) if excess.size else 0.0,
        "beats_buyhold_rate": round(float((excess > 0).mean()), 3) if excess.size else 0.0,
        "total_carry_usd": round(sum(r["carry_usd"] for r in rows), 4),
    }
