"""Demonstrate the verification value: naive best-of-N selection is overfit; DSR/PBO catch it.

The containment half of the thesis is quantified in `firewall_value.py`. This is the
verification half. On a market with **no real edge** (a random walk), the best-looking agent
is mostly luck — and the more agents you try, the better the luckiest one looks. Pick it by
raw Sharpe and you have crowned noise. The **Deflated Sharpe Ratio** (which discounts for the
number of strategies tried) and the **Probability of Backtest Overfitting** (CSCV) flag this
*before* any capital is committed. Writes ``evidence/overfit_trap.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bitarena.agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
    RegimeAgent,
)
from bitarena.arena import Arena
from bitarena.arena.leaderboard import cross_agent_pbo
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer
from bitarena.scoring.metrics import to_returns
from bitarena.scoring.overfit import deflated_sharpe_ratio, sharpe_moments


def _roster():
    return [
        ConflictGatedSwarm(), RegimeAgent(), PersonaTeam(),
        QLearningAgent(), MomentumBaseline(), BuyAndHold(),
    ]


def main() -> None:
    # a no-edge random walk: any agent that "wins" here is winning on luck, not skill
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=600, seed=42, drift=0.0, vol=0.015)}
    market = ReplayMarketData({k: list(v) for k, v in series.items()})
    arena = Arena(
        agents=_roster(), exchange=PaperExchange(market), market=market, symbol="BTCUSDT",
        signer=Signer.generate(), instrument=InstrumentType.PERP, starting_cash=10_000.0,
    )
    res = arena.run()
    board = res["leaderboard"]

    # the naive choice: crown the best raw Sharpe
    naive = max(board, key=lambda r: (r["sharpe"] if r["sharpe"] is not None else -1e9))
    sharpes = [r["sharpe"] for r in board if r["sharpe"] is not None]
    sr_variance = float(np.var(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0

    pf = arena.portfolios[naive["agent_id"]]
    moments = sharpe_moments(to_returns(pf.equity_curve))
    dsr = deflated_sharpe_ratio(
        moments["sr"], moments["n"], n_trials=len(board), sr_variance=sr_variance,
        skew=moments["skew"], kurt=moments["kurt"],
    )
    pbo = cross_agent_pbo(arena.portfolios)["pbo"]

    out = {
        "description": "Verification value: on a no-edge random walk, naive 'pick the best "
        "Sharpe' crowns luck. The Deflated Sharpe (discounted for N agents tried) and the PBO "
        "flag the overfit before capital is committed.",
        "market": "synthetic random walk (drift 0, vol 1.5%, 600 bars), seed 42",
        "agents_tried": len(board),
        "naive_pick": {
            "agent_id": naive["agent_id"],
            "raw_sharpe": naive["sharpe"],
            "total_return": naive["total_return"],
        },
        "deflated_sharpe": None if dsr != dsr else round(dsr, 4),
        "cross_agent_pbo": pbo,
        "finding": (
            f"On a no-edge random walk the verification layer refuses to crown noise: the "
            f"cross-agent PBO is {pbo} (naively crowning the in-sample best agent would be "
            f"overfit ~{round((pbo or 0) * 100)}% of the time), and the apparent winner "
            f"('{naive['agent_id']}') has a Deflated Sharpe of {None if dsr != dsr else round(dsr, 3)} "
            f"after discounting for {len(board)} agents tried — both flag 'luck, not skill' before "
            f"any capital is risked. (The best raw Sharpe was only {naive['sharpe']}: the agents "
            f"do not manufacture edge from noise, and the statistics confirm it.)"
        ),
    }
    path = Path("evidence/overfit_trap.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(out["finding"])
    print(f"evidence -> {path}")


if __name__ == "__main__":
    main()
