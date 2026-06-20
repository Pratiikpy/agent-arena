"""Offline tests for Bitget request signing and response parsing (no network)."""

from __future__ import annotations

import base64
import hashlib
import hmac

from bitarena.connectors.bitget.client import BitgetPublicData, sign_request


def test_sign_request_matches_reference_and_uppercases_method():
    ts, path, body, secret = "1700000000000", "/api/v2/spot/account/assets", "", "topsecret"
    expected = base64.b64encode(
        hmac.new(secret.encode(), f"{ts}GET{path}{body}".encode(), hashlib.sha256).digest()
    ).decode()
    assert sign_request(ts, "get", path, body, secret) == expected
    assert len(expected) == 44  # sha256 -> 32 bytes -> base64


def test_sign_request_changes_with_body():
    a = sign_request("1", "POST", "/p", "", "s")
    b = sign_request("1", "POST", "/p", '{"x":1}', "s")
    assert a != b


def test_parse_spot_ticker():
    payload = {
        "code": "00000",
        "data": [
            {"symbol": "BTCUSDT", "lastPr": "65000.5", "bidPr": "65000.0", "askPr": "65001.0", "ts": "1700000000000"}
        ],
    }
    q = BitgetPublicData._parse_ticker(payload, "BTCUSDT")
    assert q is not None
    assert q.last == 65000.5 and q.bid == 65000.0 and q.ask == 65001.0
    assert q.ts == 1700000000000 and not q.is_crossed


def test_parse_ticker_missing_data_returns_none():
    assert BitgetPublicData._parse_ticker({"code": "00000", "data": []}, "BTCUSDT") is None
    assert BitgetPublicData._parse_ticker({}, "BTCUSDT") is None


def test_parse_candles_sorts_ascending():
    payload = {
        "code": "00000",
        "data": [
            ["1700000060000", "101", "102", "100", "101.5", "10", "1015"],
            ["1700000000000", "100", "101", "99", "100.5", "12", "1206"],
        ],
    }
    candles = BitgetPublicData._parse_candles(payload)
    assert [c.ts for c in candles] == [1700000000000, 1700000060000]
    assert candles[0].open == 100.0 and candles[1].close == 101.5


def test_parse_candles_skips_malformed_rows():
    payload = {"data": [["bad"], ["1", "1", "1", "1", "1", "1"]]}
    candles = BitgetPublicData._parse_candles(payload)
    assert len(candles) == 1
