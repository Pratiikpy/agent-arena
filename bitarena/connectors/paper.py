"""Deterministic paper exchange + replayable / synthetic market data.

The paper exchange simulates marketable fills with a spread cross, size-dependent
slippage, and a taker fee — all deterministic functions of the order, so a
tournament replays identically. `ReplayMarketData` serves a precomputed candle
series advanced by the arena clock; `synthetic_series` generates a reproducible
price path for fully-offline runs.
"""

from __future__ import annotations

import hashlib

import numpy as np

from ..domain.market import Candle, InstrumentType, Quote, Side
from .base import MarketData, OrderResult


class PaperExchange:
    """Simulated marketable-order fills against a `MarketData` source."""

    name = "paper"

    def __init__(
        self,
        market: MarketData,
        *,
        taker_fee_bps: float = 6.0,
        base_slippage_bps: float = 1.0,
        impact_bps_per_10k: float = 5.0,
    ) -> None:
        self._market = market
        self.taker_fee_bps = taker_fee_bps
        self.base_slippage_bps = base_slippage_bps
        self.impact_bps_per_10k = impact_bps_per_10k
        self._seq = 0

    def get_quote(self, symbol: str, instrument: InstrumentType = InstrumentType.SPOT) -> Quote | None:
        return self._market.get_quote(symbol, instrument)

    def get_candles(
        self,
        symbol: str,
        instrument: InstrumentType = InstrumentType.SPOT,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        return self._market.get_candles(symbol, instrument, timeframe, limit)

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        notional_usd: float,
        instrument: InstrumentType = InstrumentType.SPOT,
        reduce_only: bool = False,
    ) -> OrderResult:
        quote = self._market.get_quote(symbol, instrument)
        ts = quote.ts if quote is not None else 0
        if quote is None or quote.is_crossed or quote.mid <= 0:
            return OrderResult.rejected(symbol, side, instrument, ts, "no usable quote")
        if notional_usd <= 0:
            return OrderResult.rejected(symbol, side, instrument, ts, "non-positive notional")

        ref = quote.ask if side is Side.BUY else quote.bid
        if ref <= 0:
            ref = quote.mid
        slippage = (self.base_slippage_bps + self.impact_bps_per_10k * (notional_usd / 10_000.0)) / 10_000.0
        fill_price = ref * (1.0 + slippage) if side is Side.BUY else ref * (1.0 - slippage)
        if fill_price <= 0:
            return OrderResult.rejected(symbol, side, instrument, ts, "degenerate fill price")

        qty = notional_usd / fill_price
        fee = notional_usd * self.taker_fee_bps / 10_000.0
        self._seq += 1
        return OrderResult(
            accepted=True,
            symbol=symbol.upper(),
            side=side,
            instrument=instrument,
            filled_qty=qty,
            avg_price=fill_price,
            notional_usd=notional_usd,
            fee_usd=fee,
            order_id=f"paper-{self._seq}",
            ts=ts,
        )


class ReplayMarketData:
    """Serve a fixed candle series per symbol, advanced by an external clock."""

    def __init__(self, series: dict[str, list[Candle]], *, spread_bps: float = 2.0) -> None:
        self._series = {sym.upper(): list(candles) for sym, candles in series.items()}
        self._spread_bps = spread_bps
        self._cursor = 0
        self._length = min((len(c) for c in self._series.values()), default=0)

    @property
    def length(self) -> int:
        return self._length

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def symbols(self) -> list[str]:
        return list(self._series.keys())

    def set_cursor(self, index: int) -> None:
        if self._length:
            self._cursor = max(0, min(index, self._length - 1))

    def advance(self) -> bool:
        """Step one bar forward. Returns False at the end of the series."""
        if self._cursor < self._length - 1:
            self._cursor += 1
            return True
        return False

    def get_quote(self, symbol: str, instrument: InstrumentType = InstrumentType.SPOT) -> Quote | None:
        candle = self._current(symbol)
        if candle is None:
            return None
        half = self._spread_bps / 2.0 / 10_000.0
        return Quote(
            symbol=symbol.upper(),
            bid=candle.close * (1.0 - half),
            ask=candle.close * (1.0 + half),
            last=candle.close,
            ts=candle.ts,
        )

    def get_candles(
        self,
        symbol: str,
        instrument: InstrumentType = InstrumentType.SPOT,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        series = self._series.get(symbol.upper())
        if not series:
            return []
        end = self._cursor + 1
        start = max(0, end - limit)
        return series[start:end]

    def _current(self, symbol: str) -> Candle | None:
        series = self._series.get(symbol.upper())
        if not series:
            return None
        return series[min(self._cursor, len(series) - 1)]


def _stable_seed(symbol: str, seed: int) -> int:
    digest = hashlib.sha256(f"{symbol.upper()}:{seed}".encode()).hexdigest()
    return int(digest[:8], 16)


def synthetic_series(
    symbol: str,
    n: int = 500,
    *,
    start_price: float = 100.0,
    seed: int = 7,
    drift: float = 0.0,
    vol: float = 0.01,
    start_ts: int = 0,
    step_ms: int = 60_000,
) -> list[Candle]:
    """A reproducible geometric-random-walk candle series for offline runs."""
    rng = np.random.default_rng(_stable_seed(symbol, seed))
    returns = rng.normal(drift, vol, n)
    prices = start_price * np.exp(np.cumsum(returns))
    candles: list[Candle] = []
    for i in range(n):
        close = float(prices[i])
        open_ = float(prices[i - 1]) if i > 0 else start_price
        wick = abs(float(rng.normal(0.0, vol / 2.0)))
        high = max(open_, close) * (1.0 + wick)
        low = min(open_, close) * (1.0 - wick)
        volume = abs(float(rng.normal(1_000.0, 100.0)))
        candles.append(
            Candle(ts=start_ts + i * step_ms, open=open_, high=high, low=low, close=close, volume=volume)
        )
    return candles
