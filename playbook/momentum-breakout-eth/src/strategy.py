"""Momentum breakout strategy (NautilusTrader) — Donchian channel.

Enter long when price closes above the upper edge of its recent channel; enter short
when it closes below the lower edge. Exit on a tighter opposite channel that trails
the move. Deterministic and fully replayable.
"""

from decimal import Decimal
from typing import Optional

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DonchianBreakoutConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "0.05"
    entry_period: int = 20
    exit_period: int = 10


class DonchianBreakoutStrategy(Strategy):
    def __init__(self, config: DonchianBreakoutConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._highs: list[float] = []
        self._lows: list[float] = []
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

    def on_bar(self, bar: Bar) -> None:
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        self._highs.append(high)
        self._lows.append(low)

        entry, exit_ = self.cfg.entry_period, self.cfg.exit_period
        if len(self._highs) < entry + 1:
            return

        prior_high = max(self._highs[-(entry + 1):-1])
        prior_low = min(self._lows[-(entry + 1):-1])
        exit_high = max(self._highs[-(exit_ + 1):-1])
        exit_low = min(self._lows[-(exit_ + 1):-1])

        instrument = self._instrument
        if instrument is None:
            return
        qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)

        if self._position == "NONE":
            if close > prior_high:
                self._submit(instrument.id, OrderSide.BUY, qty)
                self._position = "LONG"
            elif close < prior_low:
                self._submit(instrument.id, OrderSide.SELL, qty)
                self._position = "SHORT"
            return

        if self._position == "LONG" and close < exit_low:
            self._close_open(instrument.id, OrderSide.SELL)
            self._position = "NONE"
        elif self._position == "SHORT" and close > exit_high:
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
