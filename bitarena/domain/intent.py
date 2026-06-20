"""TradeIntent — a proposed order, before the firewall has ruled on it.

An intent is what an agent *wants* to do. It is never executed directly; it must
first be evaluated by the firewall, which returns a signed :class:`Verdict`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from .market import InstrumentType, Side


class TradeIntent(BaseModel):
    """An immutable proposed order from a named agent.

    Exactly one of ``notional_usd`` or ``quantity`` may be omitted, but at least
    one must be present; the firewall normalizes ``quantity`` into an authoritative
    notional using a live quote (so a notional cap is always enforceable).
    """

    model_config = ConfigDict(frozen=True)

    agent_id: str
    symbol: str
    side: Side
    instrument: InstrumentType = InstrumentType.SPOT
    notional_usd: float | None = None
    quantity: float | None = None
    leverage: float = 1.0
    reduce_only: bool = False
    rationale: str | None = None
    ts: int | None = None  # epoch ms; stamped by the caller when available

    @model_validator(mode="after")
    def _check_sizing(self) -> "TradeIntent":
        if self.notional_usd is None and self.quantity is None:
            raise ValueError("intent must specify notional_usd or quantity")
        if self.notional_usd is not None and self.notional_usd <= 0:
            raise ValueError("notional_usd must be positive")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.leverage < 1.0:
            raise ValueError("leverage must be >= 1.0")
        return self

    @property
    def normalized_symbol(self) -> str:
        """Upper-cased symbol for consistent matching against the universe."""
        return self.symbol.strip().upper()
