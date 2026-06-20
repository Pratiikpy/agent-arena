"""Trading-agent protocol, the observation passed each tick, and a rebalance helper.

An agent receives an :class:`AgentObservation` (its current position, equity, the
mark price, and a market-data handle) and returns a :class:`TradeIntent` it would
like to place, or ``None`` to hold. The intent is never executed directly — the
arena routes it through the firewall first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..connectors.base import MarketData
from ..domain.intent import TradeIntent
from ..domain.market import InstrumentType, Side


@dataclass(frozen=True)
class AgentObservation:
    """What an agent sees on a single tick."""

    symbol: str
    instrument: InstrumentType
    ts: int
    equity_usd: float
    position_qty: float  # signed base units currently held (+ long, - short)
    price: float  # current mark (mid)
    market: MarketData


@runtime_checkable
class TradingAgent(Protocol):
    """A named decision policy."""

    agent_id: str

    def decide(self, obs: AgentObservation) -> TradeIntent | None: ...


def rebalance_to_target(
    *,
    agent_id: str,
    obs: AgentObservation,
    target_notional_signed: float,
    min_trade_usd: float = 10.0,
    allow_short: bool = True,
    rationale: str | None = None,
) -> TradeIntent | None:
    """Produce the order that moves the position toward a signed target notional.

    Returns ``None`` if the move is smaller than ``min_trade_usd``. ``reduce_only``
    is set only when the order strictly shrinks the current position without
    flipping sign (so the firewall's exposure caps still apply to any opening or
    flipping trade — conservative by design).
    """
    if obs.price <= 0:
        return None
    if not allow_short and target_notional_signed < 0:
        target_notional_signed = 0.0

    current = obs.position_qty * obs.price
    delta = target_notional_signed - current
    if abs(delta) < min_trade_usd:
        return None

    side = Side.BUY if delta > 0 else Side.SELL
    same_sign = (current > 0 and target_notional_signed > 0) or (
        current < 0 and target_notional_signed < 0
    )
    reducing = abs(target_notional_signed) < 1e-9 or (
        same_sign and abs(target_notional_signed) < abs(current)
    )
    return TradeIntent(
        agent_id=agent_id,
        symbol=obs.symbol,
        side=side,
        instrument=obs.instrument,
        notional_usd=abs(delta),
        reduce_only=reducing,
        rationale=rationale,
        ts=obs.ts,
    )
