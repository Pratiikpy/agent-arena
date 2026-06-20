"""Per-agent portfolio accounting.

A signed cash + position model that is correct for both longs and shorts:
``equity = cash + position_qty * price``. Buying spends cash and adds base units;
selling adds cash and removes (or shorts) base units. Fees reduce cash. Perpetual
funding settles as a cash flow (longs pay shorts when the rate is positive), so a
position held across funding intervals harvests — or pays — carry. No leverage or
margin modelling — every agent is accounted identically, keeping the leaderboard fair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..connectors.base import OrderResult
from ..domain.market import Side


@dataclass
class Portfolio:
    """One agent's cash, position, and equity history."""

    agent_id: str
    starting_cash: float
    position_qty: float = 0.0
    fees_paid: float = 0.0
    funding_received: float = 0.0  # cumulative funding cash flow (+received / -paid)
    trades: int = 0
    cash_usd: float = field(init=False)
    equity_curve: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash_usd = self.starting_cash
        if not self.equity_curve:
            self.equity_curve = [self.starting_cash]

    def exposure_usd(self, price: float) -> float:
        return abs(self.position_qty) * price

    def equity(self, price: float) -> float:
        return self.cash_usd + self.position_qty * price

    def apply_fill(self, order: OrderResult) -> None:
        """Update cash/position from an accepted fill."""
        signed = order.filled_qty if order.side is Side.BUY else -order.filled_qty
        self.cash_usd -= signed * order.avg_price
        self.cash_usd -= order.fee_usd
        self.position_qty += signed
        self.fees_paid += order.fee_usd
        self.trades += 1

    def apply_funding(self, rate: float, price: float) -> float:
        """Settle one perpetual funding interval and return the cash flow.

        Convention: longs pay shorts when ``rate`` > 0, so the cash flow is
        ``-position_qty * price * rate`` (a long with a positive rate pays; a short
        with a positive rate receives). A flat book is unaffected.
        """
        cashflow = -self.position_qty * price * rate
        self.cash_usd += cashflow
        self.funding_received += cashflow
        return cashflow

    def mark(self, price: float) -> float:
        """Record one equity point at ``price`` and return it."""
        eq = self.equity(price)
        self.equity_curve.append(eq)
        return eq
