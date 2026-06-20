"""Quantify the firewall's protective value — a misbehaving agent, contained vs not.

The red-team proves *no unsafe order passes*. This study answers the next question — what
is that worth? A `RogueAgent` proposes a grossly oversized order every tick (a sizing bug,
or an attack). We run it through the arena twice on the *same* adverse market:

  - **contained**   — the real arena mandate; the firewall caps every order to the mandate.
  - **unprotected** — an effectively-unlimited mandate; the firewall allows the raw orders.

The gap in max drawdown / final equity is exactly what the firewall saved. Writes
``evidence/firewall_value.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from bitarena.agents.base import rebalance_to_target
from bitarena.arena import Arena
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.mandate import default_arena_mandate
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer

STARTING_CASH = 10_000.0
OVERSIZE = 8.0  # the rogue targets 8x the account in a fixed oversized long


class RogueAgent:
    """A misbehaving agent: holds a grossly oversized fixed long (8x the account)."""

    agent_id = "rogue"

    def decide(self, obs):
        # a fixed oversized target (not equity-relative, so it doesn't average down into a
        # crash) — the firewall's per-order + exposure caps are the only thing bounding it.
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=OVERSIZE * STARTING_CASH,
            min_trade_usd=10.0,
            allow_short=False,
            rationale="rogue: oversized 8x long",
        )


def _run(mandate, series) -> dict:
    market = ReplayMarketData({k: list(v) for k, v in series.items()})
    arena = Arena(
        agents=[RogueAgent()],
        exchange=PaperExchange(market),
        market=market,
        symbol="BTCUSDT",
        signer=Signer.generate(),
        instrument=InstrumentType.PERP,
        starting_cash=10_000.0,
        mandate=mandate,
    )
    res = arena.run()
    row = res["leaderboard"][0]
    return {
        "final_equity": row["final_equity"],
        "total_return": row.get("total_return"),
        "max_drawdown": row.get("max_drawdown"),
        "firewall": res["firewall"]["totals"],
    }


def main() -> None:
    # an adverse market (sustained ~20% drop) that punishes an over-leveraged long
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=300, seed=13, drift=-0.0007, vol=0.015)}

    real = default_arena_mandate(10_000.0, allowed_symbols=("BTCUSDT",))
    huge_caps = real.hard_caps.model_copy(
        update={
            "max_order_notional_usd": 1e12,
            "max_total_exposure_usd": 1e12,
            "max_leverage": 1000.0,
        }
    )
    unprotected_mandate = real.model_copy(update={"hard_caps": huge_caps})

    contained = _run(real, series)
    unprotected = _run(unprotected_mandate, series)

    saved_equity = round(contained["final_equity"] - unprotected["final_equity"], 2)
    out = {
        "description": "Firewall protective value: a RogueAgent (requests 8x-equity orders "
        "every tick) on an adverse market, contained by the firewall vs unprotected.",
        "market": "synthetic adverse (drift -0.4%/bar, vol 2%, 300 bars), seed 13",
        "oversize_multiple": OVERSIZE,
        "contained": contained,
        "unprotected": unprotected,
        "firewall_saved_usd": saved_equity,
        "finding": (
            f"The firewall capped {contained['firewall']['allow_capped']} oversized orders, "
            f"bounding the misbehaving agent to ${contained['final_equity']:,.0f} final equity; "
            f"unprotected, the same agent fell to ${unprotected['final_equity']:,.0f}. The "
            f"firewall saved ${saved_equity:,.0f} on a $10,000 account."
        ),
    }
    path = Path("evidence/firewall_value.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(out["finding"])
    print(f"evidence -> {path}")


if __name__ == "__main__":
    main()
