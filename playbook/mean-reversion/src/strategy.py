"""Mean-reversion strategy (NautilusTrader) — RSI + Bollinger %b.

Fades stretched moves: long an oversold washout near the lower band, short an
overbought push near the upper band, and exit as price reverts toward the mean.
Deterministic and fully replayable.
"""

from decimal import Decimal
import math
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class MeanReversionConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "1.0"
    rsi_period: int = 14
    bb_period: int = 20
    bb_k: float = 2.0
    rsi_low: float = 30.0
    rsi_high: float = 70.0
    stop_low: float = -0.05
    stop_high: float = 1.05


class MeanReversionStrategy(Strategy):
    def __init__(self, config: MeanReversionConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._closes: list[float] = []
        self._position: str = "NONE"  # NONE / LONG / SHORT
        self._instrument: Optional[Instrument] = None

    def on_start(self) -> None:
        bar_type = self.cfg.bar_type or (self.cfg.bar_types[0] if self.cfg.bar_types else None)
        instrument_id = self.cfg.instrument_id or (
            self.cfg.instrument_ids[0] if self.cfg.instrument_ids else None
        )
        if bar_type is None or instrument_id is None:
            raise RuntimeError("bar_type and instrument_id must be set")
        self._instrument = self.cache.instrument(instrument_id)
        self.subscribe_bars(bar_type)

    def _rsi(self) -> float:
        n = self.cfg.rsi_period
        if len(self._closes) < n + 1:
            return 50.0
        seg = self._closes[-(n + 1):]
        gains = 0.0
        losses = 0.0
        for i in range(1, len(seg)):
            d = seg[i] - seg[i - 1]
            if d >= 0:
                gains += d
            else:
                losses -= d
        if losses == 0:
            return 100.0 if gains > 0 else 50.0
        rs = (gains / n) / (losses / n)
        return 100.0 - 100.0 / (1.0 + rs)

    def _pctb(self) -> float:
        n = self.cfg.bb_period
        if len(self._closes) < n:
            return 0.5
        seg = self._closes[-n:]
        mean = sum(seg) / n
        var = sum((x - mean) ** 2 for x in seg) / (n - 1) if n > 1 else 0.0
        sd = math.sqrt(var)
        if sd == 0:
            return 0.5
        upper = mean + self.cfg.bb_k * sd
        lower = mean - self.cfg.bb_k * sd
        if upper == lower:
            return 0.5
        return (self._closes[-1] - lower) / (upper - lower)

    def on_bar(self, bar: Bar) -> None:
        self._closes.append(float(bar.close))
        warmup = max(self.cfg.bb_period, self.cfg.rsi_period) + 2
        if len(self._closes) < warmup:
            return

        rsi = self._rsi()
        pctb = self._pctb()
        instrument = self._instrument
        if instrument is None:
            return
        qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)

        if self._position == "NONE":
            if rsi < self.cfg.rsi_low and pctb < 0.10:
                self._submit(instrument.id, OrderSide.BUY, qty)
                self._position = "LONG"
            elif rsi > self.cfg.rsi_high and pctb > 0.90:
                self._submit(instrument.id, OrderSide.SELL, qty)
                self._position = "SHORT"
            return

        # exit a long on reversion to the mean (take profit) OR on a break below the
        # band (stop loss — the reversion thesis is invalidated, cut the trend risk)
        if self._position == "LONG" and (pctb > 0.5 or rsi > 50.0 or pctb < self.cfg.stop_low):
            self._close_open(instrument.id, OrderSide.SELL)
            self._position = "NONE"
        elif self._position == "SHORT" and (pctb < 0.5 or rsi < 50.0 or pctb > self.cfg.stop_high):
            self._close_open(instrument.id, OrderSide.BUY)
            self._position = "NONE"

    def _submit(self, instrument_id: InstrumentId, side: OrderSide, quantity: Quantity) -> None:
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=quantity,
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def _close_open(self, instrument_id: InstrumentId, side: OrderSide) -> None:
        for position in self.cache.positions_open(instrument_id=instrument_id):
            self._submit(instrument_id, side, position.quantity)

    def on_stop(self) -> None:
        if self._instrument is not None:
            self.cancel_all_orders(self._instrument.id)
            self.close_all_positions(self._instrument.id)
