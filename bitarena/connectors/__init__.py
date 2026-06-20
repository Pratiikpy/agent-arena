"""Exchange connectors: protocol, paper exchange, replay/synthetic data, Bitget."""

from .base import ExchangeConnector, MarketData, OrderResult
from .paper import PaperExchange, ReplayMarketData, synthetic_series

__all__ = [
    "ExchangeConnector",
    "MarketData",
    "OrderResult",
    "PaperExchange",
    "ReplayMarketData",
    "synthetic_series",
]
