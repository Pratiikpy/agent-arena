"""Exchange connector protocol and the shared OrderResult type.

`MarketData` is the read surface (quotes + candles). `ExchangeConnector` adds order
placement. The paper exchange and the live Bitget connector both satisfy these, so
the arena engine is agnostic to which one it runs against.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from ..domain.market import Candle, InstrumentType, Quote, Side


class OrderResult(BaseModel):
    """Outcome of a (paper or live) order placement."""

    model_config = ConfigDict(frozen=True)

    accepted: bool
    symbol: str
    side: Side
    instrument: InstrumentType
    filled_qty: float
    avg_price: float
    notional_usd: float
    fee_usd: float
    order_id: str
    ts: int
    error: str | None = None

    @classmethod
    def rejected(
        cls, symbol: str, side: Side, instrument: InstrumentType, ts: int, error: str
    ) -> "OrderResult":
        return cls(
            accepted=False,
            symbol=symbol,
            side=side,
            instrument=instrument,
            filled_qty=0.0,
            avg_price=0.0,
            notional_usd=0.0,
            fee_usd=0.0,
            order_id="",
            ts=ts,
            error=error,
        )


@runtime_checkable
class MarketData(Protocol):
    """Read-only market data surface."""

    def get_quote(
        self, symbol: str, instrument: InstrumentType = InstrumentType.SPOT
    ) -> Quote | None: ...

    def get_candles(
        self,
        symbol: str,
        instrument: InstrumentType = InstrumentType.SPOT,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]: ...


@runtime_checkable
class ExchangeConnector(MarketData, Protocol):
    """Market data plus order placement."""

    name: str

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        notional_usd: float,
        instrument: InstrumentType = InstrumentType.SPOT,
        reduce_only: bool = False,
    ) -> OrderResult: ...
