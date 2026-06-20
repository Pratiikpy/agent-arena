"""Bitget v2 REST client.

Public market data needs no credentials. Account reads and order placement use the
Bitget v2 signing scheme: ``ACCESS-SIGN = base64(HMAC_SHA256(secret,
timestamp + method + requestPath + body))``.

Response parsing is isolated into static methods (``_parse_ticker`` /
``_parse_candles``) so it can be unit-tested offline without network or keys. All
data reads fail soft (return ``None`` / ``[]``) so the firewall fail-closes upstream
on a missing quote rather than the client raising.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time

import httpx

from ...domain.market import Candle, InstrumentType, Quote, Side
from ..base import OrderResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.bitget.com"

# timeframe -> Bitget v2 spot granularity
_SPOT_GRANULARITY = {
    "1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "4h": "4h", "1d": "1day",
}
# timeframe -> Bitget v2 mix (futures) granularity
_MIX_GRANULARITY = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "4h": "4H", "1d": "1D",
}
_MIX_PRODUCT_TYPE = "USDT-FUTURES"


def sign_request(timestamp: str, method: str, request_path: str, body: str, secret: str) -> str:
    """Bitget v2 ACCESS-SIGN: base64(HMAC-SHA256(secret, ts+METHOD+path+body))."""
    prehash = f"{timestamp}{method.upper()}{request_path}{body}"
    digest = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


class BitgetPublicData:
    """Public (keyless) Bitget market data: quotes and candles for spot and perps."""

    name = "bitget-public"

    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 10.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BitgetPublicData":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- public reads ------------------------------------------------------

    def get_quote(self, symbol: str, instrument: InstrumentType = InstrumentType.SPOT) -> Quote | None:
        symbol = symbol.upper()
        try:
            if instrument is InstrumentType.PERP:
                resp = self._client.get(
                    "/api/v2/mix/market/ticker",
                    params={"symbol": symbol, "productType": _MIX_PRODUCT_TYPE},
                )
            else:
                resp = self._client.get("/api/v2/spot/market/tickers", params={"symbol": symbol})
            resp.raise_for_status()
            return self._parse_ticker(resp.json(), symbol)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("bitget quote fetch failed for %s: %s", symbol, exc)
            return None

    def get_candles(
        self,
        symbol: str,
        instrument: InstrumentType = InstrumentType.SPOT,
        timeframe: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        symbol = symbol.upper()
        try:
            if instrument is InstrumentType.PERP:
                granularity = _MIX_GRANULARITY.get(timeframe, "1m")
                resp = self._client.get(
                    "/api/v2/mix/market/candles",
                    params={
                        "symbol": symbol,
                        "granularity": granularity,
                        "productType": _MIX_PRODUCT_TYPE,
                        "limit": str(limit),
                    },
                )
            else:
                granularity = _SPOT_GRANULARITY.get(timeframe, "1min")
                resp = self._client.get(
                    "/api/v2/spot/market/candles",
                    params={"symbol": symbol, "granularity": granularity, "limit": str(limit)},
                )
            resp.raise_for_status()
            return self._parse_candles(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("bitget candles fetch failed for %s: %s", symbol, exc)
            return []

    # -- parsing (offline-testable) ---------------------------------------

    @staticmethod
    def _parse_ticker(payload: dict, symbol: str) -> Quote | None:
        rows = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows:
            return None
        row = next(
            (r for r in rows if isinstance(r, dict) and str(r.get("symbol", "")).upper() == symbol),
            rows[0] if isinstance(rows[0], dict) else None,
        )
        if not isinstance(row, dict):
            return None

        def _f(*keys: str) -> float:
            for key in keys:
                if key in row and row[key] not in (None, ""):
                    try:
                        v = float(row[key])
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(v):  # never let inf/nan through (also avoids int(inf))
                        return v
            return 0.0

        last = _f("lastPr", "last", "close")
        bid = _f("bidPr", "bestBid", "buyOne") or last
        ask = _f("askPr", "bestAsk", "sellOne") or last
        ts = int(_f("ts", "timestamp")) or 0
        if last <= 0 and bid <= 0 and ask <= 0:
            return None
        return Quote(symbol=symbol, bid=bid, ask=ask, last=last or (bid + ask) / 2.0, ts=ts)

    @staticmethod
    def _parse_candles(payload: dict) -> list[Candle]:
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[Candle] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            try:
                values = [float(row[i]) for i in range(6)]
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(v) for v in values):
                continue  # reject inf/nan rather than poison a Candle (or crash int(inf))
            out.append(
                Candle(
                    ts=int(values[0]),
                    open=values[1],
                    high=values[2],
                    low=values[3],
                    close=values[4],
                    volume=values[5],
                )
            )
        out.sort(key=lambda c: c.ts)  # Bitget may return newest-first
        return out

    # -- funding rate (perp) ----------------------------------------------

    def get_funding_history(self, symbol: str, limit: int = 300) -> list[dict]:
        """Historical perpetual funding rates (ascending by time). Keyless.

        Returns ``[{"ts": <epoch ms>, "funding_rate": <float>}, ...]``. Paginates
        the Bitget v2 history endpoint (pageSize 100) until ``limit`` is reached.
        """
        symbol = symbol.upper()
        out: list[dict] = []
        pages = max(1, math.ceil(limit / 100))
        try:
            for page_no in range(1, pages + 1):
                resp = self._client.get(
                    "/api/v2/mix/market/history-fund-rate",
                    params={
                        "symbol": symbol,
                        "productType": _MIX_PRODUCT_TYPE,
                        "pageSize": "100",
                        "pageNo": str(page_no),
                    },
                )
                resp.raise_for_status()
                rows = self._parse_funding(resp.json())
                if not rows:
                    break
                out.extend(rows)
                if len(out) >= limit:
                    break
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("bitget funding fetch failed for %s: %s", symbol, exc)
        out.sort(key=lambda r: r["ts"])
        return out[-limit:] if limit else out

    @staticmethod
    def _parse_funding(payload: dict) -> list[dict]:
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            rate = row.get("fundingRate")
            ts = row.get("fundingTime") or row.get("ts")
            if rate in (None, ""):
                continue
            try:
                fr = float(rate)
                ts_val = int(ts) if ts else 0
            except (TypeError, ValueError):
                continue
            if not math.isfinite(fr):
                continue  # skip inf/nan funding rates
            out.append({"ts": ts_val, "funding_rate": fr})
        return out


class BitgetConnector(BitgetPublicData):
    """Authenticated Bitget connector: public data + account reads + order placement."""

    name = "bitget"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(base_url=base_url, timeout=timeout)
        self._api_key = api_key
        self._secret = secret_key
        self._passphrase = passphrase

    def _headers(self, method: str, request_path: str, body: str) -> dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY": self._api_key,
            "ACCESS-SIGN": sign_request(timestamp, method, request_path, body, self._secret),
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
            "locale": "en-US",
        }

    def get_account_assets(self) -> dict | None:
        """Read spot account assets (authenticated). Returns the raw data payload."""
        path = "/api/v2/spot/account/assets"
        try:
            resp = self._client.get(path, headers=self._headers("GET", path, ""))
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("bitget account read failed: %s", exc)
            return None

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        notional_usd: float,
        instrument: InstrumentType = InstrumentType.SPOT,
        reduce_only: bool = False,
    ) -> OrderResult:
        """Place a spot market order. Buy size is quote (USDT); sell size is base qty.

        Live order placement requires Trade permission on the key. Any non-zero
        Bitget error code is surfaced as a rejected OrderResult (never raises), so
        the arena records the rejection rather than crashing.
        """
        symbol = symbol.upper()
        quote = self.get_quote(symbol, instrument)
        ts = quote.ts if quote is not None else int(time.time() * 1000)
        if quote is None or quote.mid <= 0:
            return OrderResult.rejected(symbol, side, instrument, ts, "no quote for sizing")
        if instrument is not InstrumentType.SPOT:
            return OrderResult.rejected(symbol, side, instrument, ts, "live perp orders not enabled")

        price = quote.ask if side is Side.BUY else quote.bid
        if price <= 0:
            price = quote.mid
        size = notional_usd if side is Side.BUY else notional_usd / price
        body_obj = {
            "symbol": symbol,
            "side": side.value,
            "orderType": "market",
            "force": "gtc",
            "size": f"{size:.8f}",
        }
        body = json.dumps(body_obj)
        path = "/api/v2/spot/trade/place-order"
        try:
            resp = self._client.post(path, headers=self._headers("POST", path, body), content=body)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return OrderResult.rejected(symbol, side, instrument, ts, f"order request failed: {exc}")

        if str(data.get("code")) != "00000":
            return OrderResult.rejected(
                symbol, side, instrument, ts, f"bitget {data.get('code')}: {data.get('msg')}"
            )

        order_id = str((data.get("data") or {}).get("orderId", ""))
        qty = notional_usd / price
        return OrderResult(
            accepted=True,
            symbol=symbol,
            side=side,
            instrument=instrument,
            filled_qty=qty,
            avg_price=price,
            notional_usd=notional_usd,
            fee_usd=0.0,  # actual fee resolved on fill query; unknown at ack time
            order_id=order_id,
            ts=ts,
        )
