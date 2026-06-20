"""Statistical test of the conflict-gated swarm's edge vs naive momentum in chop.

The project's secondary thesis is "size by agreement, stay flat under conflict." Rather
than assert it from a single scenario, this runs many independent choppy (random-walk)
markets and measures the swarm-minus-momentum return distribution with a bootstrap 95%
confidence interval — the agent-thesis analogue of the overfit testing, applied to the
agents themselves. Honest by construction: if the CI straddles zero, the edge is not real.
"""

from __future__ import annotations

import math

import numpy as np

from ..agents import ConflictGatedSwarm, MomentumBaseline
from ..arena import Arena
from ..connectors import PaperExchange, ReplayMarketData, synthetic_series
from ..domain.market import InstrumentType
from ..firewall import Firewall, Signer


def _swarm_minus_momentum(market: ReplayMarketData, firewall: Firewall) -> float:
    arena = Arena(
        agents=[ConflictGatedSwarm(), MomentumBaseline()],
        exchange=PaperExchange(market),
        market=market,
        symbol="BTCUSDT",
        firewall=firewall,
        signer=firewall._signer,
        instrument=InstrumentType.PERP,
        starting_cash=10_000.0,
    )
    rows = {r["agent_id"]: (r["total_return"] or 0.0) for r in arena.run()["leaderboard"]}
    return rows.get("swarm", 0.0) - rows.get("baseline-momentum", 0.0)


def swarm_edge_in_chop(*, n_scenarios: int = 80, seed: int = 1000, n: int = 240,
                       vol: float = 0.012, boot: int = 2000) -> dict:
    firewall = Firewall(Signer.generate())
    diffs = np.array(
        [
            _swarm_minus_momentum(
                ReplayMarketData({
                    "BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed + i, drift=0.0, vol=vol)
                }),
                firewall,
            )
            for i in range(n_scenarios)
        ],
        dtype=float,
    )

    mean = float(diffs.mean())
    std = float(diffs.std(ddof=1)) if diffs.size > 1 else 0.0
    t_stat = mean / (std / math.sqrt(diffs.size)) if std > 0 else 0.0
    rng = np.random.default_rng(0)
    boots = np.array([rng.choice(diffs, size=diffs.size, replace=True).mean() for _ in range(boot)])
    ci_low, ci_high = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    return {
        "scenarios": int(diffs.size),
        "market": f"random-walk chop (vol={vol}, n={n} bars)",
        "mean_return_diff": round(mean, 5),
        "median_return_diff": round(float(np.median(diffs)), 5),
        "swarm_beats_momentum_rate": round(float((diffs > 0).mean()), 3),
        "t_stat": round(t_stat, 3),
        "ci95": [round(ci_low, 5), round(ci_high, 5)],
        "significant": bool(ci_low > 0),
    }
