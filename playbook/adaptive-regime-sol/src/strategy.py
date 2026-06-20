"""Adaptive regime strategy (NautilusTrader).

Reads the market regime from an EMA-spread trend-strength measure, then:
- trends  -> trend-follow in the trend direction
- ranges  -> mean-revert (fade oversold/overbought via RSI + Bollinger %b)
- conflict/weak -> hold flat (the conflict-gate; "flat is a decision")

Deterministic and fully replayable. All indicators are computed in plain Python.
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


class AdaptiveRegimeConfig(StrategyConfig):
    instrument_id: Optional[InstrumentId] = None
    bar_type: Optional[BarType] = None
    instrument_ids: tuple[InstrumentId, ...] = ()
    bar_types: tuple[BarType, ...] = ()
    trade_size: str = "0.05"
    ema_fast: int = 12
    ema_slow: int = 48
    rsi_period: int = 14
    bb_period: int = 20
    bb_k: float = 2.0
    trend_threshold: float = 0.012
    range_threshold: float = 0.004
    rsi_low: float = 35.0
    rsi_high: float = 65.0


class AdaptiveRegimeStrategy(Strategy):
    def __init__(self, config: AdaptiveRegimeConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self._closes: list[float] = []
        self._fast: Optional[float] = None
        self._slow: Optional[float] = None
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

    @staticmethod
    def _update_ema(prev: Optional[float], value: float, period: int) -> float:
        if prev is None:
            return value
        alpha = 2.0 / (period + 1)
        return alpha * value + (1.0 - alpha) * prev

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

    def _bb_pctb(self) -> float:
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
        close = float(bar.close)
        self._closes.append(close)
        self._fast = self._update_ema(self._fast, close, self.cfg.ema_fast)
        self._slow = self._update_ema(self._slow, close, self.cfg.ema_slow)

        warmup = max(self.cfg.ema_slow, self.cfg.bb_period, self.cfg.rsi_period) + 2
        if len(self._closes) < warmup or not self._slow:
            return

        spread = (self._fast - self._slow) / self._slow  # type: ignore[operator]
        strength = abs(spread)
        rsi = self._rsi()
        pctb = self._bb_pctb()

        instrument = self._instrument
        if instrument is None:
            return
        qty = Quantity(Decimal(self.cfg.trade_size), instrument.size_precision)

        # ---- regime selection -> target {+1 long, -1 short, 0 flat} ----
        if strength >= self.cfg.trend_threshold:
            target = 1 if spread > 0 else -1            # committed trend
        elif strength <= self.cfg.range_threshold:
            if rsi < self.cfg.rsi_low and pctb < 0.10:  # oversold washout
                target = 1
            elif rsi > self.cfg.rsi_high and pctb > 0.90:  # overbought push
                target = -1
            else:
                target = 0
        else:
            target = 0                                  # conflict / weak -> flat

        self._apply_target(instrument, qty, target)

    def _apply_target(self, instrument: Instrument, qty: Quantity, target: int) -> None:
        if target == 1:
            if self._position == "SHORT":
                self._close_open(instrument.id, OrderSide.BUY)
                self._position = "NONE"
            if self._position == "NONE":
                self._submit(instrument.id, OrderSide.BUY, qty)
                self._position = "LONG"
        elif target == -1:
            if self._position == "LONG":
                self._close_open(instrument.id, OrderSide.SELL)
                self._position = "NONE"
            if self._position == "NONE":
                self._submit(instrument.id, OrderSide.SELL, qty)
                self._position = "SHORT"
        else:
            if self._position == "LONG":
                self._close_open(instrument.id, OrderSide.SELL)
                self._position = "NONE"
            elif self._position == "SHORT":
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
