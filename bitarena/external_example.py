"""A reference 'external agent' that integrates with the firewall via one function.

This models a third-party developer's own trading bot. Its *only* contract with Agent
Arena is ``post_firewall(payload) -> verdict_dict`` — typically an HTTP POST to
``/firewall`` (or an MCP ``vet_trade`` call). The bot proposes trades from its own naive
strategy and only acts on what the firewall returns ALLOW / ALLOW_CAPPED for. This is the
Track-2 "another developer integrated it" proof, and it's transport-agnostic so it can be
driven by httpx in a script or a TestClient in a test.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from .connectors.base import MarketData
from .domain.market import InstrumentType
from .perception.market_features import rsi

VerdictFn = Callable[[dict], dict]


def run_external_agent(
    post_firewall: VerdictFn,
    market: MarketData,
    *,
    symbol: str,
    instrument: InstrumentType,
    steps: int = 60,
    equity_usd: float = 10_000.0,
    notional_usd: float = 200.0,
    advance: bool = True,
) -> dict:
    """Run a naive RSI-bounce bot that vets every trade through the firewall."""
    log: list[dict] = []
    allowed = capped = rejected = 0
    position_qty = 0.0

    for _ in range(steps):
        quote = market.get_quote(symbol, instrument)
        if quote is None:
            if advance and hasattr(market, "advance") and not market.advance():
                break
            continue
        candles = market.get_candles(symbol, instrument, limit=30)
        closes = np.array([c.close for c in candles], dtype=float)
        r = rsi(closes, 14) if closes.size >= 15 else 50.0

        side = "buy" if r < 35 else ("sell" if r > 65 else None)
        if side is not None:
            verdict = post_firewall(
                {
                    "agent_id": "external-rsi-bot",
                    "symbol": symbol,
                    "side": side,
                    "instrument": instrument.value,
                    "notional_usd": notional_usd,
                    "equity_usd": equity_usd,
                    "current_exposure_usd": abs(position_qty) * quote.mid,
                }
            )
            decision = verdict.get("decision")
            if decision == "ALLOW":
                allowed += 1
            elif decision == "ALLOW_CAPPED":
                capped += 1
            else:
                rejected += 1
            if decision in ("ALLOW", "ALLOW_CAPPED"):
                eff = verdict.get("effective_notional_usd") or 0.0
                signed = 1.0 if side == "buy" else -1.0
                position_qty += signed * eff / quote.mid
            log.append({
                "ts": quote.ts,
                "rsi": round(r, 1),
                "side": side,
                "decision": decision,
                "effective_notional_usd": verdict.get("effective_notional_usd"),
                "cert_valid": verdict.get("certificate_valid"),
            })

        if advance and hasattr(market, "advance") and not market.advance():
            break

    return {
        "agent": "external-rsi-bot",
        "symbol": symbol,
        "decisions": len(log),
        "allowed": allowed,
        "allow_capped": capped,
        "rejected": rejected,
        "all_verdicts_signed": all(e.get("cert_valid") for e in log) if log else True,
        "log": log[:60],
    }
