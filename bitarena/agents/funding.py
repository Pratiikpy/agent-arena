"""FundingCarryAgent — harvest perpetual funding, the one structurally-real crypto edge.

It takes the side that *receives* funding: short when funding is strongly positive
(longs pay shorts), long when strongly negative, flat when funding is too small to be
worth the price risk. The arena credits the funding cash flow each settlement
(``Portfolio.apply_funding``), so the carry is real PnL.

Honest scope: a single-instrument perp agent cannot be delta-neutral (no spot leg), so
this bears directional price risk while collecting carry — unlike the pure delta-neutral
carry validated in the funding-carry study. Whether the funding income outweighs the
price risk is left to the arena to report. With no funding data it stays flat.
"""

from __future__ import annotations

import bisect

from ..domain.market import InstrumentType
from .base import AgentObservation, rebalance_to_target


class FundingCarryAgent:
    """Positions to receive perpetual funding when it clears a threshold."""

    def __init__(
        self,
        funding=None,
        *,
        agent_id: str = "funding-carry",
        threshold: float = 0.0001,
        base_fraction: float = 0.5,
    ) -> None:
        self.agent_id = agent_id
        self.threshold = threshold
        self.base_fraction = base_fraction
        self._index = self._build_index(funding or [])
        self._ts = [t for t, _ in self._index]
        self.last_rate = 0.0

    @staticmethod
    def _build_index(funding) -> list[tuple[int, float]]:
        items: list[tuple[int, float]] = []
        if isinstance(funding, dict):
            for k, v in funding.items():
                try:
                    items.append((int(k), float(v)))
                except (TypeError, ValueError):
                    continue
        else:
            for row in funding:
                try:
                    items.append((int(row["ts"]), float(row["funding_rate"])))
                except (TypeError, ValueError, KeyError):
                    continue
        items.sort()
        return items

    def rate_at(self, ts: int) -> float:
        """Most recent funding rate effective at or before ``ts`` (0.0 if none known)."""
        if not self._index:
            return 0.0
        i = bisect.bisect_right(self._ts, ts) - 1
        return self._index[i][1] if i >= 0 else 0.0

    def decide(self, obs: AgentObservation):
        if obs.instrument is not InstrumentType.PERP:
            return None  # funding only applies to perpetuals
        rate = self.rate_at(obs.ts)
        self.last_rate = rate
        if rate >= self.threshold:
            target = -self.base_fraction * obs.equity_usd  # short receives positive funding
            side = "short"
        elif rate <= -self.threshold:
            target = self.base_fraction * obs.equity_usd  # long receives negative funding
            side = "long"
        else:
            target = 0.0
            side = "flat"
        return rebalance_to_target(
            agent_id=self.agent_id,
            obs=obs,
            target_notional_signed=target,
            min_trade_usd=max(10.0, 0.02 * obs.equity_usd),
            allow_short=True,
            rationale=f"funding={rate:+.5f} -> {side} to receive carry",
        )
