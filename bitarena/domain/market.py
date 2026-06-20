"""Market value objects: instruments, quotes, candles, positions, balances.

All types are immutable (``frozen=True``) so they can be passed freely through the
firewall, agents, and ledger without any component mutating shared state.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class Side(str, Enum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for a buy, -1 for a sell (used for signed position math)."""
        return 1 if self is Side.BUY else -1


class InstrumentType(str, Enum):
    """Instrument classes the arena trades on Bitget."""

    SPOT = "spot"
    PERP = "perp"  # USDT-margined perpetual futures
    TOKENIZED_EQUITY = "tokenized_equity"  # Bitget tokenized US stocks (rAAPL, ...)


class Quote(BaseModel):
    """Top-of-book snapshot for one symbol."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    bid: float
    ask: float
    last: float
    ts: int  # epoch milliseconds

    @property
    def mid(self) -> float:
        """Mid price, falling back to ``last`` when the book is one-sided."""
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last

    @property
    def spread_bps(self) -> float:
        """Half-spread-aware relative spread in basis points (0 if unknown)."""
        if self.bid > 0 and self.ask > 0 and self.mid > 0:
            return (self.ask - self.bid) / self.mid * 10_000.0
        return 0.0

    @property
    def is_crossed(self) -> bool:
        """A crossed/locked book (bid >= ask) is unusable for execution."""
        return self.bid > 0 and self.ask > 0 and self.bid >= self.ask


class Candle(BaseModel):
    """OHLCV bar."""

    model_config = ConfigDict(frozen=True)

    ts: int  # epoch milliseconds (open time)
    open: float
    high: float
    low: float
    close: float
    volume: float


class Position(BaseModel):
    """A net position in one symbol. ``qty`` is signed: positive long, negative short."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: float
    avg_price: float
    instrument: InstrumentType = InstrumentType.SPOT

    def market_value(self, price: float) -> float:
        """Absolute market value (exposure) at ``price``."""
        return abs(self.qty) * price

    def unrealized_pnl(self, price: float) -> float:
        """Mark-to-market PnL given the current ``price``."""
        return (price - self.avg_price) * self.qty


class Balance(BaseModel):
    """Account balance snapshot in USD terms."""

    model_config = ConfigDict(frozen=True)

    equity_usd: float
    available_usd: float
