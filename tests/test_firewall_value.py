"""The firewall's containment value: it bounds a misbehaving agent's loss to the mandate.

Complements the red-team (which proves no unsafe order passes) by checking the *consequence*:
under the real mandate the firewall keeps a rogue agent solvent on an adverse market where
an unprotected version goes bankrupt.
"""

from __future__ import annotations

from bitarena.agents.base import rebalance_to_target
from bitarena.arena import Arena
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.mandate import default_arena_mandate
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer


class _Rogue:
    agent_id = "rogue"

    def decide(self, obs):
        # a fixed, grossly oversized long (8x the starting account)
        return rebalance_to_target(
            agent_id="rogue", obs=obs, target_notional_signed=80_000.0,
            min_trade_usd=10.0, allow_short=False, rationale="oversized",
        )


def _run(mandate):
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=300, seed=13, drift=-0.0007, vol=0.015)}
    md = ReplayMarketData(series)
    res = Arena(
        agents=[_Rogue()], exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
        signer=Signer.generate(), instrument=InstrumentType.PERP, starting_cash=10_000.0,
        mandate=mandate,
    ).run()
    return res["leaderboard"][0]["final_equity"], res["firewall"]["totals"]


def test_firewall_contains_a_misbehaving_agent():
    real = default_arena_mandate(10_000.0, allowed_symbols=("BTCUSDT",))
    huge = real.model_copy(update={"hard_caps": real.hard_caps.model_copy(update={
        "max_order_notional_usd": 1e12, "max_total_exposure_usd": 1e12, "max_leverage": 1000.0,
    })})

    contained_eq, contained_fw = _run(real)
    unprotected_eq, _ = _run(huge)

    assert contained_fw["allow_capped"] > 0       # the firewall actively capped oversized orders
    assert contained_eq > 0.0                      # ...keeping the account solvent
    assert contained_eq > unprotected_eq + 5_000.0  # far better than unprotected (which went bankrupt)
