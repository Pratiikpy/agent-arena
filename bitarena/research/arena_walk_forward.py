"""Walk-forward robustness for arena agents.

Splits a price series into disjoint contiguous folds and runs the full arena on each,
reporting every agent's per-fold return plus stability across folds (mean, std,
fraction of positive folds, and a mean/std consistency ratio). The agents are
parameter-free, so this is a temporal-stability test — does an edge hold across
different windows, or is it a one-window fluke? — complementary to PBO.
"""

from __future__ import annotations

import numpy as np

from ..agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
    RegimeAgent,
)
from ..arena import Arena
from ..connectors import PaperExchange, ReplayMarketData
from ..domain.market import InstrumentType
from ..firewall import Firewall, Signer


def default_roster():
    return [
        ConflictGatedSwarm(),
        RegimeAgent(),
        PersonaTeam(),
        QLearningAgent(),
        MomentumBaseline(),
        BuyAndHold(),
    ]


def walk_forward_arena(
    candles,
    *,
    symbol: str,
    instrument: InstrumentType = InstrumentType.PERP,
    folds: int = 5,
    roster_factory=default_roster,
    signer: Signer | None = None,
    starting_cash: float = 10_000.0,
) -> dict:
    """Run the arena on each contiguous fold; aggregate per-agent stability."""
    candles = list(candles)
    n = len(candles)
    if n < folds * 30:
        folds = max(2, n // 30) if n >= 60 else 1
    fold_size = max(1, n // folds)
    firewall = Firewall(signer or Signer.generate())

    per_agent: dict[str, list[float]] = {}
    per_fold: list[dict] = []
    for f in range(folds):
        start = f * fold_size
        seg = candles[start:] if f == folds - 1 else candles[start:start + fold_size]
        if len(seg) < 20:
            continue
        md = ReplayMarketData({symbol: seg})
        arena = Arena(
            agents=roster_factory(),
            exchange=PaperExchange(md),
            market=md,
            symbol=symbol,
            firewall=firewall,
            signer=firewall._signer,
            instrument=instrument,
            starting_cash=starting_cash,
        )
        result = arena.run()
        fold_row = {"fold": f + 1, "bars": len(seg), "results": {}}
        for row in result["leaderboard"]:
            aid = row["agent_id"]
            ret = row["total_return"] or 0.0
            per_agent.setdefault(aid, []).append(ret)
            fold_row["results"][aid] = round(ret, 5)
        per_fold.append(fold_row)

    summary: dict[str, dict] = {}
    for aid, rets in per_agent.items():
        arr = np.array(rets, dtype=float)
        std = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
        summary[aid] = {
            "folds": int(arr.size),
            "mean_return": round(float(arr.mean()), 5),
            "std_return": round(std, 5),
            "pct_positive_folds": round(float((arr > 0).mean()), 3),
            "worst_fold": round(float(arr.min()), 5),
            "best_fold": round(float(arr.max()), 5),
            "consistency": round(float(arr.mean() / (std + 1e-9)), 3) if arr.size > 1 else None,
        }
    return {"folds": len(per_fold), "per_fold": per_fold, "summary": summary}
