"""Evaluate one trade intent through the firewall and print the signed certificate.

This is the 10-second proof: a verdict (ALLOW / ALLOW_CAPPED / REJECT) plus an
Ed25519-signed certificate that anyone can verify offline.

Example:
    uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 50
    uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 999999  # capped
"""

from __future__ import annotations

import argparse
import json

from bitarena.config import load_settings
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain import InstrumentType, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall, verify_certificate


def get_quote(source: str, symbol: str, instrument: InstrumentType):
    if source == "bitget":
        client = BitgetPublicData()
        try:
            quote = client.get_quote(symbol, instrument)
        finally:
            client.close()
        if quote is not None:
            return quote
        print("[warn] no Bitget quote — falling back to synthetic")
    market = ReplayMarketData({symbol: synthetic_series(symbol, n=60, seed=1)})
    market.set_cursor(59)
    return market.get_quote(symbol, instrument)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one intent through the firewall.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--notional", type=float, default=50.0)
    parser.add_argument("--instrument", choices=["perp", "spot"], default="spot")
    parser.add_argument("--source", choices=["bitget", "synthetic"], default="bitget")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--exposure", type=float, default=0.0)
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    quote = get_quote(args.source, args.symbol, instrument)
    if quote is None:
        print("could not obtain a quote")
        return

    firewall = Firewall.with_key(load_settings().signing_key_path)
    mandate = default_arena_mandate(args.equity, allowed_symbols=(args.symbol.upper(),))
    intent = TradeIntent(
        agent_id="external-agent",
        symbol=args.symbol,
        side=Side(args.side),
        instrument=instrument,
        notional_usd=args.notional,
    )
    ctx = EvalContext(
        mandate=mandate,
        equity_usd=args.equity,
        quote=quote,
        current_exposure_usd=args.exposure,
        now_ms=quote.ts,
        max_quote_age_ms=10 ** 15,
    )
    verdict = firewall.evaluate(intent, ctx)
    print(
        json.dumps(
            {
                "intent": {"symbol": args.symbol, "side": args.side, "notional_usd": args.notional},
                "quote": {"mid": round(quote.mid, 4), "ts": quote.ts},
                "decision": verdict.decision.value,
                "reason": verdict.reason,
                "effective_notional_usd": verdict.effective_notional_usd,
                "gates": [{"gate": g.gate, "passed": g.passed, "detail": g.detail} for g in verdict.gates],
                "certificate": verdict.certificate.model_dump() if verdict.certificate else None,
                "certificate_valid": verify_certificate(verdict.certificate) if verdict.certificate else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
