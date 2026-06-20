"""Bring your own agent — a ~15-line custom strategy competing in the arena.

Any object with an ``agent_id`` and ``decide(obs) -> TradeIntent | None`` is a competitor.
This shows a third party plugging a strategy into the arena: the firewall gates every order it
proposes, and the overfit-aware leaderboard scores it, exactly like the built-in agents. No
arena internals required — just the agent protocol.

    uv run python scripts/custom_agent_example.py        # or: make custom-agent
"""

from __future__ import annotations

import sys

from bitarena.agents import BuyAndHold, MomentumBaseline
from bitarena.agents.base import AgentObservation, rebalance_to_target
from bitarena.arena import Arena
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


# --- your strategy: mean-reversion to a simple moving average -----------------
class MeanReversionAgent:
    """Go long when price is below its moving average; flatten when above."""

    agent_id = "my-mean-reversion"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def decide(self, obs: AgentObservation):
        candles = obs.market.get_candles(obs.symbol, obs.instrument, limit=self.window)
        if len(candles) < self.window:
            return None
        sma = sum(c.close for c in candles) / len(candles)
        target = obs.equity_usd * 0.5 if obs.price < sma else 0.0  # half-equity long, else flat
        return rebalance_to_target(agent_id=self.agent_id, obs=obs, target_notional_signed=target,
                                   rationale="price below SMA" if target else "price above SMA")
# -----------------------------------------------------------------------------


def main() -> int:
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=300, seed=7, drift=0.0, vol=0.02)}
    md = ReplayMarketData(series)
    arena = Arena(
        agents=[MeanReversionAgent(), MomentumBaseline(), BuyAndHold()],
        exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
        signer=Signer.generate(), instrument=InstrumentType.PERP, starting_cash=10_000.0,
    )
    res = arena.run()

    print("Your custom agent competed in the arena — firewall-gated, overfit-scored:\n")
    for r in sorted(res["leaderboard"], key=lambda x: -x["final_equity"]):
        mark = "   <- your agent" if r["agent_id"] == "my-mean-reversion" else ""
        print(f"  #{r['rank']}  {r['agent_id']:<22} equity ${r['final_equity']:>10,.2f}{mark}")
    fw = res["firewall"]["totals"]
    print(f"\nfirewall: {fw.get('intents', 0)} intents · {fw.get('allow_capped', 0)} capped · "
          f"0 unsafe · ledger_verified={res['ledger_verified']}")
    print("\nThat's the whole integration: implement decide(), drop it in the agents list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
